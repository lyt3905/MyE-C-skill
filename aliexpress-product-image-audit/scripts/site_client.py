# -*- coding: utf-8 -*-
"""站点客户端与图像小工具（aliexpress-product-image-audit skill 通用件）

从 ae-img-audit/pipeline.py 抽出（2026-11-07），pipeline.py 现在反过来 import 本文件，
所以这里只有一份实现，改这里等于改 pipeline。

凭据**不写在本文件**，按下面顺序找（先找到先用）：
  1. 环境变量 AE_SITE_BASE / AE_SITE_USER / AE_SITE_PWD
  2. 环境变量 AE_SITE_CFG 指向的 json 文件
  3. 当前工作目录的 cfg.local.json（推荐：ae-img-audit/cfg.local.json）
  4. 从当前目录往上最多 3 层找 cfg.local.json
  5. ~/.dsh/secrets/ae-site.json

json 格式：{"base": "https://...", "user": "...", "pwd": "..."}

用法：
    from site_client import Site, pad_square, fit_long, crop_banner_to_square
    Site.instance = Site.instance or Site()
    s = Site.instance
    p = s.product(4571)
"""

import os, sys, json, re, ssl, uuid, urllib.request, http.cookiejar
import numpy as np
import cv2

CFG_FILENAME = "cfg.local.json"


def _cfg_candidates():
    seen = []
    p = os.environ.get("AE_SITE_CFG")
    if p:
        seen.append(p)
    cur = os.path.abspath(os.getcwd())
    for _ in range(4):
        seen.append(os.path.join(cur, CFG_FILENAME))
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    seen.append(os.path.join(os.path.expanduser("~"), ".dsh", "secrets", "ae-site.json"))
    out = []
    for x in seen:
        if x not in out:
            out.append(x)
    return out


def load_cfg():
    """返回 {"base","user","pwd"}；缺 user/pwd 就报错，绝不回退到硬编码密码。"""
    raise RuntimeError('Automatic credential discovery disabled; provide explicit read-only credentials')


class _LazyConfig(dict):
    """Legacy dictionary interface, loaded only on actual credential access."""
    def __getitem__(self, key):
        if not self:
            self.update(load_cfg())
        return super().__getitem__(key)

CFG = _LazyConfig()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"

class _SiteTransport:
    def account_fingerprint(self):
        from account_identity import fingerprint
        return fingerprint(self.cfg['base'],self.call('/api/auth/me'))
    def current_shop(self):
        response = self.call('/api/auth/me')
        data = response.get('data') if isinstance(response, dict) else None
        shop = data.get('selectedShopId') if isinstance(data, dict) else None
        if shop is None: raise ValueError('SHOP_CONTEXT_UNVERIFIED')
        return shop
    # 单例槽位：`Site.instance = Site.instance or Site()` 靠它，先置 None 才不会 AttributeError
    instance = None

    def __init__(self, cfg=None, *, verify_tls=None):
        if cfg is not None:
            if verify_tls is not True or not isinstance(cfg, dict) or any(not isinstance(cfg.get(k), str) or not cfg[k] for k in ('base', 'user', 'pwd')):
                raise ValueError('explicit credentials require TLS verification')
            from urllib.parse import urlsplit
            endpoint = urlsplit(cfg['base'])
            if endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
                raise ValueError('explicit credentials require a valid HTTPS base')
            self.cfg = dict(cfg)
        else:
            raise RuntimeError('Explicit credentials required; automatic discovery disabled')
        ctx = ssl.create_default_context()
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx), urllib.request.HTTPCookieProcessor(self.cj))
        self.login()

    def login(self):
        self.call("/api/auth/login", {"username": self.cfg["user"], "password": self.cfg["pwd"]})

    def call(self, path, data=None, method=None):
        h = {"Accept": "application/json"}
        body = json.dumps(data).encode() if data is not None else None
        if body:
            h["Content-Type"] = "application/json"
        r = urllib.request.Request(self.cfg["base"] + path, data=body, headers=h,
                                   method=method or ("POST" if body else "GET"))
        with self.op.open(r, timeout=120) as f:
            return json.loads(f.read().decode())

    def product(self, pid):
        return self.call("/api/admin/products/%s" % pid)["data"]

    def worker(self):
        return self.call("/api/admin/toy-image-workers/status")["data"]["summary"]

    def status(self, pid, value):
        return self.call("/api/admin/products/%s/status" % pid, {"status": value})

    def save(self, pid, images=None, desc=None, extra=None, *, expected_state_hash=None, description_image_deletions=None, description_image_replacements=None):
        """等价于控制台「保存」按钮：PUT /api/admin/products/{id}?autoSave=true
        与不带 autoSave 的 PUT 有本质区别（实测 2026-11-07）：
          - 带 autoSave：不改状态、不重新分配图片 id、不插 AI 封面。
          - 不带：触发 INGEST_POST_PROCESS —— 全图改名重传、自动生成 AI 封面插 main[0]、
            状态被推进到 EDITING(待生图) 或 READY_TO_PUBLISH(待发布)。
        images: {'main': [...], 'detail': [...]} 局部覆盖；desc: 新的 descriptionJson。

        ⚠️ weight 必须原样回传（2026-11-07 实测）：这个 PUT 是「缺字段就填默认值」的全量覆盖，
        body 里不带 weight 时服务端会把 weight 重置成默认 0.3，并连带按新重量重算 sku.shippingFee
        （0.2→0.3 时 7.43→8.8）。所以下面把商品当前的 weight 一起带上；要改重量就显式传
        extra={'weight': x}，别指望它保持不变。

        ⚠️ identityJson 同样会被重置（2026-11-09 九件实测，推翻 2026-11-07 在 4826 上的旧结论）：
        body 里不带 identityJson 时服务端把它写成 {"logoCode":""}，**modelCode 键直接丢**。
        所以下面把商品当前的 identityJson 一起带上（要改编号就显式传 extra={'identityJson': ...}，
        必须是 json.dumps 后的字符串）。brand 缺失时不会被重置。
        """
        p = self.product(pid)
        if expected_state_hash is not None:
            from product_state import canonical_state_hash
            actual_state_hash = canonical_state_hash(p)
            if actual_state_hash != expected_state_hash:
                raise RuntimeError("Site.save precondition failed: expected state %s, got %s" %
                                   (expected_state_hash, actual_state_hash))
        body = {k: p.get(k) for k in ('titleEn', 'titleTranslationZh', 'descriptionJson',
                                      'skus', 'price', 'weight', 'identityJson', 'presale') if k in p}
        imgs = dict(p.get('images') or {})
        if images:
            imgs.update(images)
        body['images'] = imgs
        if desc is not None:
            body['descriptionJson'] = desc
        if extra:
            body.update(extra)
        approved_description=p.get('descriptionJson')
        if description_image_deletions or description_image_replacements:
            if expected_state_hash is None:raise ValueError('DESCRIPTION_IMAGE_STATE_BINDING_REQUIRED')
            from description_images import edit_body_images
            approved_description=edit_body_images(approved_description,description_image_deletions or [],description_image_replacements or {})
        if (('descriptionJson' in body) != ('descriptionJson' in p)
                or type(body.get('descriptionJson')) is not type(approved_description)
                or body.get('descriptionJson') != approved_description):
            raise ValueError('DESCRIPTION_MUTATION_FORBIDDEN')
        if isinstance(body.get('identityJson'),dict):
            body['identityJson']=json.dumps(body['identityJson'],ensure_ascii=False)
        return self.call('/api/admin/products/%s?autoSave=true' % pid, body, method='PUT')

    def blacklist(self, pid, image_url):
        """删除该图并加入黑名单（站点采集时自动过滤同 URL）。"""
        return self.call('/api/admin/products/%s/images/blacklist' % pid, {'imageUrl': image_url})

    def replace_links(self, pid):
        """POST /replace-image-links：把商品内图片链接批量替换（返回 replaced/failed/skipped）。"""
        return self.call('/api/admin/products/%s/replace-image-links' % pid, {})

    def upload(self, local):
        from pathlib import Path
        from PIL import Image
        import io
        data=Path(local).read_bytes()
        with Image.open(io.BytesIO(data)) as image:
            mime=Image.MIME.get(image.format)
            image.verify()
        if mime not in {'image/png','image/jpeg','image/webp'}:raise ValueError('unsupported upload MIME')
        bnd = "----pp" + uuid.uuid4().hex
        body = b"".join([
            ("--%s\r\n" % bnd).encode(),
            ('Content-Disposition: form-data; name="file"; filename="%s"\r\n' % os.path.basename(local)).encode(),
            ('Content-Type: '+mime+'\r\n\r\n').encode(),
            data,
            ("\r\n--%s--\r\n" % bnd).encode(),
        ])
        r = urllib.request.Request(self.cfg["base"] + "/api/admin/uploads/images", data=body,
                                   headers={"Content-Type": "multipart/form-data; boundary=" + bnd}, method="POST")
        with self.op.open(r, timeout=180) as f:
            return json.loads(f.read().decode())["data"]["url"]

    def download(self, url, dst):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.aliexpress.com/"})
        with urllib.request.urlopen(req, timeout=90) as f:
            blob = f.read()
        with open(dst, "wb") as fh:
            fh.write(blob)
        return dst


# ---------------- 描述区同步 ----------------
def _u_path(u):
    return re.sub(r"\?.*$", "", u or "").rsplit("/", 1)[-1]


def remap_description(d, mapping):
    """Removed legacy operation: the fixed field must remain opaque."""
    raise ValueError('DESCRIPTION_OPERATION_FORBIDDEN')


def prune_description(d, new_detail):
    """Removed legacy operation: the fixed field must remain opaque."""
    raise ValueError('DESCRIPTION_OPERATION_FORBIDDEN')



class ReadOnlySiteClient:
    """Explicitly configured read client; no product mutation methods."""
    instance = None
    @classmethod
    def from_transport(cls,transport):
        client=object.__new__(cls)
        client.__transport=transport
        client.coordination_key=transport.account_fingerprint()
        return client
    def readonly_client(self):return self
    def account_fingerprint(self):return self.__transport.account_fingerprint()
    def __init__(self, cfg=None, *, verify_tls=True):
        self.__transport = _SiteTransport(cfg=cfg, verify_tls=verify_tls)
        import hashlib
        account_cfg=getattr(self.__transport,'cfg',{})
        if not isinstance(account_cfg,dict):account_cfg={}
        self.coordination_key=hashlib.sha256(json.dumps({k:account_cfg.get(k) for k in ('base','user')},sort_keys=True).encode()).hexdigest()
    def product(self, pid):
        return self.__transport.product(pid)
    def worker(self):
        return self.__transport.worker()
    def download(self,url,destination):
        return self.__transport.download(url,destination)
    def current_shop(self):
        response = self.call('/api/auth/me')
        data = response.get('data') if isinstance(response, dict) else None
        shop_id = data.get('selectedShopId') if isinstance(data, dict) else None
        if shop_id is None:
            raise ValueError('SHOP_CONTEXT_UNVERIFIED: auth/me has no selectedShopId')
        return shop_id
    def call(self, path, data=None, method=None):
        if data is not None or (method or 'GET').upper() != 'GET':
            raise PermissionError('Read-only client rejects mutations; use Executor IPC')
        return self.__transport.call(path, method='GET')

Site = ReadOnlySiteClient

# ---------------- 图像小工具 ----------------
def banner_rows(bgr, thr=0.5, min_h_frac=0.03):
    """底部/顶部整幅彩色横幅：返回 (位, 起始行, 行数) 或 None（★必须传彩色图）
    用 5 行平滑后的饱和度行占比，从边缘往里找连续段（旧版遇到底边几个非饱和行就提前 break，4649 的红横幅因此漏判）"""
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    satm = (hsv[:, :, 1] > 80)
    sat = satm.mean(axis=1)
    mn = max(40, int(min_h_frac * h))

    def width_ok(y0, y1):
        """横幅必须是整幅宽的色带：多数列在带内多数行上是高饱和"""
        col = satm[y0:y1].mean(axis=0)
        return float((col >= 0.5).mean()) >= 0.6

    def walk_from(y_from, y_to, step):
        """从边缘往里走，容忍 <=12 行空洞（横幅上有白字/logo 会把整行拉低）"""
        y, start, holes = y_from, y_from, 0
        while (y - y_to) * step < 0:
            if sat[y] >= thr:
                start = y; holes = 0
            else:
                holes += 1
                if holes > 12:
                    break
            y += step
        return start

    s0 = walk_from(h - 1, int(0.40 * h), -1)
    rows = h - s0
    if rows >= mn and width_ok(s0, h):
        return ("bottom", s0, rows)
    s1 = walk_from(0, int(0.60 * h), 1)
    if s1 >= mn and width_ok(0, s1):
        return ("top", 0, s1)
    return None


def crop_banner_to_square(src, dst, out=800):
    """裁掉整幅横幅并把内容在 800×800 白底居中（横幅内容区不足 800 时等比放大）"""
    bgr = cv2.imdecode(np.fromfile(src, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = bgr.shape[:2]
    band = banner_rows(bgr)
    if not band:
        return None
    pos, y0, rows = band
    if pos == "bottom":
        keep = bgr[:y0]
    else:
        keep = bgr[y0 + rows:]
    g = cv2.cvtColor(keep, cv2.COLOR_BGR2GRAY)
    nz = (g < 250)
    ys, xs = np.where(nz)
    if len(ys) == 0:
        return None
    x0, x1, yy0, yy1 = xs.min(), xs.max(), ys.min(), ys.max()
    sub = keep[yy0:yy1 + 1, x0:x1 + 1]
    sh, sw = sub.shape[:2]
    scale = min(1.0 * (out - 24) / sw, 1.0 * (out - 24) / sh, 3.0)
    nw, nh = int(sw * scale), int(sh * scale)
    if scale != 1.0:
        sub = cv2.resize(sub, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.full((out, out, 3), 255, np.uint8)
    canvas[(out - nh) // 2:(out - nh) // 2 + nh, (out - nw) // 2:(out - nw) // 2 + nw] = sub
    cv2.imwrite(dst, canvas, [cv2.IMWRITE_JPEG_QUALITY, 94])
    return {"cut": rows, "pos": pos, "scale": round(scale, 3)}


def pad_square(src, dst, out=800):
    """等比放大 + 白底补边到 out×out（小图/盒照用）"""
    bgr = cv2.imdecode(np.fromfile(src, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = bgr.shape[:2]
    scale = min(1.0 * out / w, 1.0 * out / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    r = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.full((out, out, 3), 255, np.uint8)
    canvas[(out - nh) // 2:(out - nh) // 2 + nh, (out - nw) // 2:(out - nw) // 2 + nw] = r
    cv2.imwrite(dst, canvas, [cv2.IMWRITE_JPEG_QUALITY, 94])
    return {"scale": round(scale, 3)}


def fit_long(src, dst, out=1200):
    """详情图用：只缩不放，保持原比例（不强制 800×800）"""
    bgr = cv2.imdecode(np.fromfile(src, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = bgr.shape[:2]
    s = min(1.0, 1.0 * out / max(h, w))
    if s < 1.0:
        bgr = cv2.resize(bgr, (int(round(w * s)), int(round(h * s))), interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(dst, bgr, [cv2.IMWRITE_JPEG_QUALITY, 94])
    return {"scale": round(s, 3)}


# ---------------- OCR / 指纹小工具 ----------------
_OCR = None
def ocr_boxes(path, max_side=1100):
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    scale = 1.0
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    res, _ = _OCR(img)
    out = []
    for box, text, conf in (res or []):
        xs = [p[0] / scale for p in box]; ys = [p[1] / scale for p in box]
        out.append({"text": text, "conf": float(conf),
                    "box": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]})
    return out


def phash(gray):
    img = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    d = cv2.dct(img)[:8, :8]
    med = np.median(d[1:, 1:])
    bits = (d > med).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(bool(b))
    return "%016x" % v


def ham(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")
