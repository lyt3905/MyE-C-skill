#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""外链探针：把微博正文里的短链/商品链展开，尽量从落地页里抽出价格与预计发售/到货时间。

用法：
    python link_probe.py --input data/filtered-XXXX.json [--crawl] [--port 9222]

流程：
  1. 从每条微博（含转发原文）里提取链接（t.cn / 商品站 / 官网）；
  2. 逐条解析跳转（t.cn 需要展开）；
  3. 按落地域名决定取页方式：
       - 淘宝/天猫/闲鱼 等需登录站：走 CDP（本机 Edge，独立 profile，需人工登录过一次）；
       - 其它站点：直接 HTTP 抓取；
  4. 从页面文本里匹配价格（¥/￥/元/円/RMB/USD）与日期（发售/出货/预购/到货 + 年月日）；
  5. 结果写 data/link-probe-YYYYMMDD.json，并在 stdout 打一张紧凑表。

设计约束：任何一条链接失败都不影响主流程；全部异常都被吞掉并记录在结果的 note 里。
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request, gzip, io

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.abspath(os.path.join(HERE, "..", "data"))

LINK_RE = re.compile(
    r"(?:https?://)?(?:"
    r"t\.cn/[A-Za-z0-9]+|"
    r"m\.weibo\.cn/sinaurl\?[^\s\u4e00-\u9fff]+|"
    r"(?:item\.taobao\.com|detail\.tmall\.com|h5\.m\.taobao\.com|m\.tb\.cn|2\.taobao\.com|"
    r"chaoshi\.detail\.tmall\.com|s\.click\.taobao\.com|market\.m\.taobao\.com)/[^\s\u4e00-\u9fff（）()【】，。]*|"
    r"(?:m\.goofish\.com|www\.goofish\.com|2\.taobao\.com)/[^\s\u4e00-\u9fff（）()【】，。]*|"
    r"[a-z0-9.-]+\.(?:com|cn|net|jp|toys|shop)/[^\s\u4e00-\u9fff（）()【】，。]*"
    r")", re.I)

SHOP_HOSTS = ("taobao.com", "tmall.com", "goofish.com", "tb.cn", "tmall.hk", "1688.com")

PRICE_RES = [
    (r"(?:¥|￥|RMB|人民币)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", "CNY"),
    (r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:元|块|人民币)", "CNY"),
    (r"(?:HK\$|港币)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", "HKD"),
    (r"(?:US\$|USD|\$)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", "USD"),
    (r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:円|日元|JPY)", "JPY"),
]
DATE_RE = re.compile(
    r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*(?:[月./-]\s*(\d{1,2})\s*[日号]?)?|"
    r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
KEY_WORDS = ("发售", "發售", "出货", "出貨", "到货", "到貨", "上市", "预购", "預購", "预售", "預售",
             "预订", "預訂", "开订", "開訂", "预定", "発売", "予約", "release", "preorder", "arrival")


def http_get(url, timeout=25, limit=800000, cookie=None):
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
               "Accept": "text/html,application/xhtml+xml,*/*", "Accept-Encoding": "gzip, deflate"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(limit)
        if r.headers.get("Content-Encoding") == "gzip":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        return r.geturl(), raw.decode("utf-8", "ignore")


def resolve(url, timeout=15):
    """展开短链：只跟随重定向，不下载正文。"""
    if not url.lower().startswith("http"):
        url = "http://" + url
    opener = urllib.request.build_opener(NoRedirect)
    cur, hops = url, 0
    while hops < 6:
        try:
            req = urllib.request.Request(cur, headers={"User-Agent": UA}, method="GET")
            r = opener.open(req, timeout=timeout)
            return r.geturl() if hasattr(r, "geturl") else cur
        except NoRedirected as e:
            loc = e.headers.get("Location")
            if not loc:
                return e.url
            cur = urllib.parse.urljoin(e.url, loc)
            hops += 1
        except Exception:
            return cur
    return cur


class NoRedirected(Exception):
    def __init__(self, url, headers):
        self.url, self.headers = url, headers


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise NoRedirected(req.full_url, headers)


def html_to_text(html):
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n{2,}", "\n", html)).strip()


# 商品页里更可靠的「主价格」写法，优先于裸 ¥ 数字
PRICE_LABELED = [
    (r"(?:预定|預定|预订|預訂|预售|預售|开订|開訂)价格\s*[:：]?\s*(?:¥|￥|RMB)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", "预定"),
    (r"(?:售价|售價|价格|價格|定价|定價)\s*[:：]?\s*(?:¥|￥|RMB)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", "标价"),
    (r"(?:定金|訂金|deposit)\s*[:：]?\s*(?:¥|￥|RMB)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", "定金"),
]


def pick_price(text, title=""):
    """返回 (price 字符串, 类型)。淘宝「预定」页正文里同时有定金和总价，
    这里优先取『预定价格/售价』这类明确标注；只有现货页才回退到页面上的最大金额，
    避免把定金/评分数字当成售价。"""
    for pat, kind in PRICE_LABELED:
        m = re.search(pat, text)
        if m:
            return f"¥{m.group(1)}", kind
    preorder_like = any(k in (title + text[:3000]) for k in ("预定", "預定", "预售", "預售", "订金", "訂金"))
    if preorder_like:
        return None, "预定页无总价"
    cands = []
    for pat, cur in PRICE_RES:
        for m in re.finditer(pat, text):
            raw = m.group(1).replace(",", "")
            try:
                v = float(raw)
            except ValueError:
                continue
            if v >= 10:
                cands.append((v, cur))
    if not cands:
        return None, None
    v, cur = max(cands)
    return f"{cur} {v:g}", "页面价"


DATE_FULL = re.compile(
    r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*月?(?:\s*[./-]?\s*(\d{1,2})\s*[日号])?\s*(?:份)?"
    r"(?:\s*(左右|前后|上旬|中旬|下旬|底|初))?")

# 这些上下文说明日期与「何时能拿到手」无关，直接丢弃
DATE_NOISE = ("已购", "购买", "浏览", "评价", "成交", "下单", "签收", "发货时间", "剩余", "库存")


def pick_dates(text):
    """返回 [{date, kw}]：只保留带发售/到货/预售语义的日期，并带上触发关键词。"""
    out, seen = [], set()
    for m in DATE_FULL.finditer(text):
        s = max(0, m.start() - 30)
        e = min(len(text), m.end() + 16)
        ctx = text[s:e]
        if any(n in ctx for n in DATE_NOISE):
            continue
        kw = next((k for k in KEY_WORDS if k in ctx), None)
        if not kw:
            continue
        y, mo, d, approx = m.group(1), m.group(2), m.group(3), m.group(4)
        seg = f"{y}年{int(mo)}月" + (f"{int(d)}日" if d else "") + (approx or "")
        if seg in seen:
            continue
        seen.add(seg)
        out.append({"date": seg, "kw": kw})
        if len(out) >= 4:
            break
    return out


BRANDS = None


def load_brands():
    """从 lexicon.json 的 brand 词典里读出品牌名，用于从商品标题里猜厂商。"""
    global BRANDS
    if BRANDS is not None:
        return BRANDS
    BRANDS = []
    try:
        lx = json.load(open(os.path.join(HERE, "lexicon.json"), encoding="utf-8"))
        terms = (lx.get("terms") or {}).get("brand") or {}
        for brand, aliases in terms.items():
            al = aliases if isinstance(aliases, list) else []
            BRANDS.append((brand, [brand] + [a for a in al if isinstance(a, str)][:8]))
    except Exception:
        BRANDS = []
    return BRANDS


def guess_brand(title):
    t = (title or "").lower()
    if not t:
        return None
    for brand, keys in load_brands():
        for k in keys:
            if k and k.lower() in t:
                return brand
    return None


def shop_channel(url):
    u = (url or "").lower()
    if "taobao.com" in u or "m.tb.cn" in u:
        return "淘宝"
    if "tmall.com" in u:
        return "天猫"
    if "goofish.com" in u:
        return "闲鱼"
    if "1688.com" in u:
        return "1688"
    if "weidian.com" in u:
        return "微店"
    return urllib.parse.urlparse(url or "").netloc


def to_intel_item(rec):
    """把一条探针结果转成 intel 条目（商品页来源），供合并进精抽草稿。"""
    title = (rec.get("title") or "").strip()
    for suffix in ("-淘宝网", "-tmall.com天猫", "-天猫Tmall.com", "_淘宝网"):
        title = title.replace(suffix, "")
    title = title.strip()
    kind = rec.get("price_kind") or ""
    dates = rec.get("dates") or []
    eta = dates[0]["date"] if dates else None
    # 只有「拿到价格」或「拿到到货/发售时间」的页面才值得变成情报条
    if not (rec.get("price") or eta):
        return None
    if not title:
        # 模板站 / JS 渲染站的标题常为空，用域名兜底，别把有价格的页面丢掉
        host = shop_channel(rec.get("final_url") or "")
        title = f"{host} 商品页" if host else ""
    # 官网首页之类的落地页没有商品信息
    low_title = title.lower()
    if not title or "official website" in low_title or low_title in ("home", "首页", "官方网站"):
        return None
    preorder_like = ("预定" in title or "預定" in title or "预售" in title or "預售" in title
                     or kind in ("预定", "定金", "预定页无总价"))
    itype = "开订" if preorder_like else ("发售" if "现货" in title else "其他")

    bits = [f"商品页：{title}"]
    if rec.get("price"):
        tag = {"定金": "（定金）", "预定": "（预定总价）"}.get(kind, "")
        bits.append(f"标价 {rec['price']}{tag}")
    if eta:
        suffix = "" if eta.endswith(("左右", "前后", "上旬", "中旬", "下旬")) else "左右"
        bits.append(f"{eta}{suffix}到货（店铺预估）")
    if rec.get("final_url"):
        bits.append(rec["final_url"].split("?")[0].replace("https://", "").replace("http://", ""))
    item = {
        "post_id": rec["post_id"],
        "intel_type": itype,
        "channel": shop_channel(rec.get("final_url") or ""),
        "summary": "｜".join(bits)[:220],
        "relevance": "中",
        "relevance_reason": "微博附带商品页链接，自动补充价格/到货时间",
        "tags": ["商品页", "link-probe"],
    }
    brand = guess_brand(title)
    if brand:
        item["brand"] = brand
    if rec.get("price") and kind != "定金":
        item["price"] = rec["price"]
    if eta:
        item["release_date"] = eta
    return item


def pick_title(html, url):
    """<title> 常常是空的（JS 渲染 / 模板站），依次退到 og:title、h1、商品名 meta。"""
    for pat in (r"(?is)<title[^>]*>(.*?)</title>",
                r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']{3,160})',
                r'(?is)<meta[^>]+content=["\']([^"\']{3,160})["\'][^>]+property=["\']og:title',
                r"(?is)<h1[^>]*>(.*?)</h1>"):
        m = re.search(pat, html)
        if m:
            t = re.sub(r"(?is)<[^>]+>", "", m.group(1))
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) >= 3:
                return t[:120]
    m = re.search(r'(?is)itemprop=["\']name["\'][^>]*>([^<]{3,120})', html)
    if m:
        return m.group(1).strip()[:120]
    return None


def probe_plain(url, timeout=25):
    final, html = http_get(url, timeout=timeout)
    text = html_to_text(html)
    return {"via": "http", "final_url": final,
            "title": pick_title(html, final),
            "text": text[:60000]}


def probe_cdp(url, port=9222, profile=r"C:\Users\shana\EdgeWeibo", wait_ms=3500):
    sys.path.insert(0, HERE)
    import cdp_util
    tab = cdp_util.open_tab(url, port=port, profile=profile)
    try:
        final = tab.goto(url, wait_ms=wait_ms)
        return {"via": "cdp", "final_url": final, "title": tab.title()[:120],
                "text": tab.text()[:60000], "login_wall": "login.taobao.com" in (final or "")}
    finally:
        tab.close()


def needs_login(url):
    return any(h in url for h in SHOP_HOSTS)


# 微博站内的视频/图片/抽奖落地页没有商品信息，直接跳过
INNER_HOSTS = ("passport.weibo.com", "photo.weibo.com", "login.sina.com.cn", "passport.weibo.cn")


def skip_landing(url):
    u = (url or "").lower()
    if any(h in u for h in INNER_HOSTS):
        return True
    return "weibo.com/tv/" in u or "lottery" in u or "login.php" in u


def collect(posts):
    """从微博帖子里收集 (post_id, [urls])。"""
    out = []
    for p in posts:
        blob = " ".join(filter(None, [p.get("text"), (p.get("retweeted") or {}).get("text"),
                                      (p.get("retweeted") or {}).get("url")]))
        urls = []
        for m in LINK_RE.finditer(blob):
            u = m.group(0)
            if not u.lower().startswith("http"):
                u = "http://" + u
            if u not in urls:
                urls.append(u)
        if urls:
            out.append((p.get("post_id"), urls))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="filtered-*.json")
    ap.add_argument("--out", default=None)
    ap.add_argument("--crawl", action="store_true", help="真的打开页面（默认只展开短链）")
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--profile", default=r"C:\Users\shana\EdgeWeibo")
    ap.add_argument("--max-per-post", type=int, default=2)
    ap.add_argument("--emit-items", nargs="?", const="auto", default=None,
                    help="把有价格/到货时间的商品页转成 intel 草稿条目（默认 data/_spec-links-YYYYMMDD.json）")
    ap.add_argument("--merge-into", default=None, help="把这些条目合并进既有 spec 文件（按 post_id+标题去重）")
    a = ap.parse_args()

    data = json.load(open(a.input, encoding="utf-8"))
    posts = data.get("posts") or []
    tasks = collect(posts)
    cache_path = os.path.join(DATA, "link_cache.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}

    results = []
    for pid, urls in tasks:
        for u in urls[: a.max_per_post]:
            rec = {"post_id": pid, "short_url": u}
            try:
                final = cache.get(u, {}).get("final_url") or resolve(u)
                rec["final_url"] = final
                rec["needs_login"] = needs_login(final)
                if skip_landing(final):
                    rec["note"] = "微博站内页（视频/图片/抽奖），无商品信息，跳过"
                    results.append(rec)
                    continue
                if a.crawl:
                    if rec["needs_login"]:
                        page = probe_cdp(u, port=a.port, profile=a.profile)
                    else:
                        page = probe_plain(u)
                    rec.update({k: page.get(k) for k in ("via", "title", "login_wall")})
                    text = page.get("text") or ""
                    rec["price"], rec["price_kind"] = pick_price(text, rec.get("title") or "")
                    rec["dates"] = pick_dates(text)
                    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                    rec["matched"] = [ln[:120] for ln in lines
                                      if any(k in ln for k in KEY_WORDS)
                                      and not any(n in ln for n in DATE_NOISE)][:5]
                    eta = [ln[:160] for ln in lines
                           if any(k in ln for k in ("到货", "到貨", "出货", "出貨", "发售", "發售"))
                           and not any(n in ln for n in DATE_NOISE)]
                    rec["eta_lines"] = eta[:2]
                    if not rec.get("price"):
                        rec["note"] = "落地页未见价格" + ("（登录墙）" if rec.get("login_wall") else "")
                    if not rec.get("dates"):
                        rec["note"] = (rec.get("note") or "") + " / 未见发售到货时间"
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"
            results.append(rec)
            if rec.get("final_url"):
                cache[u] = {"final_url": rec["final_url"], "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    out = a.out or os.path.join(DATA, f"link-probe-{time.strftime('%Y%m%d-%H%M%S')}.json")
    json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "input": a.input,
               "crawl": bool(a.crawl), "results": results}, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"链接 {len(results)} 条 / 含链接贴 {len(tasks)} 条 → {out}")
    dom = {}
    for r in results:
        host = urllib.parse.urlparse(r.get("final_url") or "").netloc.lower()
        dom[host] = dom.get(host, 0) + 1
    print("落地域名分布:", json.dumps(dom, ensure_ascii=False))
    if a.crawl:
        for r in results:
            if r.get("price") or r.get("dates"):
                ds = " / ".join(f"{d['date']}({d['kw']})" for d in (r.get("dates") or []))
                print(f"  [OK] {r['short_url']} -> {r.get('final_url')}\n"
                      f"       标题: {r.get('title')}\n"
                      f"       价格: {r.get('price')} ({r.get('price_kind')})"
                      f"{'  时间: ' + ds if ds else ''}")
                for ln in (r.get("eta_lines") or [])[:1]:
                    print(f"       原文: {ln}")
            elif r.get("error") or r.get("login_wall"):
                print(f"  [..] {r['short_url']} -> {r.get('final_url')} | {r.get('error') or '登录墙'}")
            else:
                print(f"  [--] {r['short_url']} -> {r.get('final_url')} | 无价格/时间")

    # ---------- 把商品页转成 intel 草稿条目 ----------
    if a.emit_items:
        items = [it for it in (to_intel_item(r) for r in results) if it]
        path = a.emit_items
        if path == "auto":
            path = os.path.join(DATA, f"_spec-links-{time.strftime('%Y%m%d')}.json")
        json.dump(items, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"商品页情报条目 {len(items)} 条 → {path}")
        for it in items:
            print(f"  · [{it['intel_type']}] {it.get('brand') or '-'} | {it['summary'][:110]}")
        if a.merge_into and os.path.exists(a.merge_into):
            spec = json.load(open(a.merge_into, encoding="utf-8"))
            # 容忍 {date, items:[...]} 包裹形式，统一为数组（assemble_intel 只接受数组）
            if isinstance(spec, dict):
                if not isinstance(spec.get("items"), list):
                    sys.exit("✗ --merge-into 的 spec 必须是 JSON 数组，或含 items 数组的对象")
                spec = spec["items"]
            by_pid = {}
            for s in spec:
                by_pid.setdefault(str(s.get("post_id")), []).append(s)
            enriched, added = [], []
            for it in items:
                pid = str(it["post_id"])
                hit = by_pid.get(pid)
                if not hit:
                    spec.append(it)
                    by_pid[pid] = [it]
                    added.append(it)
                    continue
                # 同一 post_id 已有条目：只补齐空着的价格/时间，不新增重复情报
                tgt = hit[0]
                changed = []
                if it.get("price") and not tgt.get("price"):
                    tgt["price"] = it["price"]
                    changed.append(f"price={it['price']}")
                if it.get("release_date") and not tgt.get("release_date"):
                    tgt["release_date"] = it["release_date"]
                    changed.append(f"release_date={it['release_date']}")
                if it.get("preorder_date") and not tgt.get("preorder_date"):
                    tgt["preorder_date"] = it["preorder_date"]
                    changed.append(f"preorder_date={it['preorder_date']}")
                if changed:
                    tag = "、".join(changed)
                    tgt["summary"] = (tgt.get("summary") or "").rstrip("。") + f"（商品页补：{tag}）"
                    enriched.append((pid, tag))
            json.dump(spec, open(a.merge_into, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"合并进 {a.merge_into}：补齐 {len(enriched)} 条 / 新增 {len(added)} 条，共 {len(spec)} 条")
            for pid, tag in enriched:
                print(f"  ~ {pid} ← {tag}")
            for it in added:
                print(f"  + {it['post_id']} | {it['summary'][:90]}")


if __name__ == "__main__":
    main()
