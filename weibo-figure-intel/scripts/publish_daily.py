#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把手办情报简报发布到 GitHub Pages（固定入口 + 每日存档）。

发布什么
    当日 HTML/MD + 该页引用到的缩略图（media/thumb/）。
    固定入口 index.html 永远指向最新一天，archive.html 列历史。
不发布什么
    **原图（media/view/）不入库**。页面里的缩略图点开直接跳原微博看大图，
    所以仓库每天只增加约 1~2 MB，而不是原方案的 30~40 MB。

用法
    python publish_daily.py                    # 发布 output 里最新一天并推送
    python publish_daily.py --date 2026-09-30  # 指定日期
    python publish_daily.py --dry-run          # 只生成，不 commit / push
    python publish_daily.py --repo-dir D:/x    # 指定发布仓本地目录
    python publish_daily.py --rebuild-all      # 顺带重刷仓里已有的全部日页（补时间线）
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(SKILL_DIR, "output")
DATA_DIR = os.path.join(SKILL_DIR, "data")
BUILD_DIGEST = os.path.join(SKILL_DIR, "scripts", "build_digest.py")

DEFAULT_REPO_DIR = os.path.join(os.path.expanduser("~"), "Documents", "GitHub", "figure-intel")
DEFAULT_REPO_URL = "https://github.com/lyt3905/figure-intel.git"
SITE_BASE = "https://lyt3905.github.io/figure-intel/"

# 发布仓只放成品页与缩略图。SKILL.md 的「本地验证」一节会让你把日页复制成
# _preview.html 用 Edge 无头截图——这类临时文件绝不能跟着 `git add -A` 进公开仓
# （2026-10-05 踩过一次：_preview.html 被顺手提交），所以每次发布都重写一份 .gitignore。
PUBLISH_IGNORE = """# 本文件由 publish_daily.py 自动写入，请不要手工编辑
# 截图 / 预览用的临时文件，不是成品
_preview*.html
_*.png
_*.tmp
"""

_INTEL_NAME = re.compile(r"^intel-(\d{4}-\d{2}-\d{2})\.json$")
_DAY_PAGE = re.compile(r"^\d{4}-\d{2}-\d{2}\.html$")
_THUMB_REF = re.compile(r"media/thumb/([^\"'\s>)]+)")

_WEEK_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def weekday_cn(date):
    try:
        import datetime as _dt
        return _WEEK_CN[_dt.datetime.strptime(date, "%Y-%m-%d").weekday()]
    except ValueError:
        return ""


def repo_days(repo_dir):
    """发布仓里已经存在的日页日期，升序。"""
    if not os.path.isdir(repo_dir):
        return []
    return sorted(n[:-5] for n in os.listdir(repo_dir) if _DAY_PAGE.match(n))


def latest_date():
    if not os.path.isdir(DATA_DIR):
        return None
    days = []
    for n in os.listdir(DATA_DIR):
        m = _INTEL_NAME.match(n)
        if m:
            days.append(m.group(1))
    return max(days) if days else None


def ensure_repo(repo_dir, url):
    if os.path.isdir(os.path.join(repo_dir, ".git")):
        return False
    parent = os.path.dirname(repo_dir)
    if parent:
        os.makedirs(parent, exist_ok=True)
    print(f"  发布仓不存在，克隆 {url}")
    subprocess.run(["git", "clone", url, repo_dir], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    return True


def build_page(date, out_html, media_rel="media", repo_dir=None):
    """渲染某一天的发布版 HTML。

    日期时间线的链接按**发布站**的命名（`<date>.html`）生成，并且日期清单直接从
    发布仓里扫（`--day-source`）—— 这样翻页只会落在真正已发布的日期上，
    不会翻到一个本地有、线上没有的页。当前这天尚未落盘时由 build_digest 自行并入。
    """
    src = os.path.join(DATA_DIR, f"intel-{date}.json")
    if not os.path.exists(src):
        raise SystemExit(f"❌ 找不到情报源文件：{src}")
    cmd = [sys.executable, BUILD_DIGEST, "--input", src, "--format", "html",
           "--html-out", out_html, "--publish", "--media-rel", media_rel,
           "--day-link", "{date}.html",
           "--day-index", "archive.html", "--day-index-label", "全部日期 →"]
    if repo_dir:
        cmd += ["--day-source", repo_dir]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)


def copy_thumbs(html, repo_dir):
    """把页面引用到的缩略图同步进发布仓。原图（view/）一律不复制。"""
    names = sorted(set(_THUMB_REF.findall(html)))
    dst_dir = os.path.join(repo_dir, "media", "thumb")
    os.makedirs(dst_dir, exist_ok=True)
    added, missing = 0, []
    for n in names:
        dst = os.path.join(dst_dir, n)
        if os.path.exists(dst):
            continue
        src = os.path.join(OUTPUT_DIR, "media", "thumb", n)
        if not os.path.exists(src):
            missing.append(n)
            continue
        shutil.copy2(src, dst)
        added += 1
    return len(names), added, missing


def inject_nav(html, date, repo_dir=None):
    """在 <body> 之后插一条发布导航（纯内联样式，不干扰简报自身 CSS）。"""
    days = repo_days(repo_dir) if repo_dir else []
    if date not in days:
        days = sorted(days + [date])
    pos = ""
    if days:
        pos = (f'<span style="opacity:.55">第 {days.index(date) + 1} / '
               f'{len(days)} 期</span>')
    bar = (
        '<div style="display:flex;align-items:center;gap:12px;padding:9px 18px;'
        'background:#1f2430;color:#fff;font:13px/1.5 system-ui,-apple-system,'
        "'Segoe UI',sans-serif\">"
        '<span style="font-weight:600">手办情报 · 每日更新</span>'
        f'<span style="opacity:.72">{date} {weekday_cn(date)}</span>'
        + pos +
        '<a href="archive.html" style="margin-left:auto;color:#9ecbff;'
        'text-decoration:none">历史归档 →</a>'
        '</div>'
    )
    m = re.search(r"<body[^>]*>", html)
    if not m:
        return bar + html
    i = m.end()
    return html[:i] + bar + html[i:]


def _day_stat(date):
    """某期简报的情报条数（读本地 intel JSON；读不到就返回 None）。"""
    p = os.path.join(DATA_DIR, f"intel-{date}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return len(d.get("items") or [])
    except Exception:
        return None


def build_archive(repo_dir):
    days_desc = sorted(repo_days(repo_dir), reverse=True)
    total = len(days_desc)
    if days_desc:
        rows = []
        for k, d in enumerate(days_desc):
            n = _day_stat(d)
            meta = f'{weekday_cn(d)} · 第 {total - k} 期'
            if n is not None:
                meta += f' · {n} 条情报'
            badge = ('<span class="lv">最新</span>' if k == 0 else '')
            rows.append(f'<li><a href="{d}.html"><b>{d}</b>{badge}'
                        f'<span class="meta">{meta}</span>'
                        f'<span class="go">阅读 →</span></a></li>')
        items = "\n".join(rows)
    else:
        items = '<li class="empty">暂无存档</li>'
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>手办情报 · 历史归档</title>
<style>
  body{{margin:0;padding:32px 20px;background:#f6f7f9;color:#1c2029;
    font:15px/1.7 system-ui,-apple-system,'Segoe UI','Microsoft YaHei',sans-serif}}
  .w{{max-width:640px;margin:0 auto}}
  h1{{font-size:20px;font-weight:600;margin:0 0 4px}}
  p.sub{{color:#6b7280;font-size:13px;margin:0 0 22px}}
  ul{{list-style:none;padding:0;margin:0}}
  li{{margin:0 0 8px}}
  a{{display:flex;align-items:baseline;gap:10px;padding:12px 16px;background:#fff;
    border:1px solid #e5e7eb;border-radius:10px;color:#1c2029;text-decoration:none}}
  a:hover{{border-color:#9ecbff;background:#f2f8ff}}
  b{{font-weight:600}}
  .meta{{color:#6b7280;font-size:12.5px}}
  .go{{margin-left:auto;color:#2563eb;font-size:12.5px;white-space:nowrap}}
  .lv{{font-size:11.5px;font-weight:600;color:#1a7a45;background:#e6f3ea;
    border-radius:5px;padding:1px 7px}}
  li.empty{{color:#9ca3af;font-size:13px}}
  .back{{display:inline-block;margin-bottom:18px;color:#2563eb;text-decoration:none;font-size:13px}}
</style></head>
<body><div class="w">
<a class="back" href="index.html">← 返回最新一期</a>
<h1>手办情报 · 历史归档</h1>
<p class="sub">共 {total} 期 · 每日自动更新</p>
<ul>
{items}
</ul></div></body></html>
"""


def git(repo_dir, *args, check=True):
    return subprocess.run(["git", *args], cwd=repo_dir, check=check,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def repo_size_mb(repo_dir):
    total = 0
    for root, _dirs, files in os.walk(repo_dir):
        if ".git" in root.split(os.sep):
            continue
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 1048576


def render_day(date, repo_dir):
    """渲染一天 → 同步缩略图 → 注入发布导航条。

    返回 (html, 页面引用张数, 新增张数, 缺失文件名表)。
    每一步都从零重写该日页，所以可以反复跑（重刷不会叠加导航条）。
    """
    out = os.path.join(repo_dir, f"{date}.html")
    build_page(date, out, repo_dir=repo_dir)
    with open(out, "r", encoding="utf-8") as f:
        html = f.read()
    total, added, missing = copy_thumbs(html, repo_dir)
    html = inject_nav(html, date, repo_dir)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return html, total, added, missing


def main():
    ap = argparse.ArgumentParser(description="发布手办情报简报到 GitHub Pages")
    ap.add_argument("--date", help="要发布的日期 YYYY-MM-DD，默认取最新")
    ap.add_argument("--repo-dir", default=DEFAULT_REPO_DIR, help="发布仓本地目录")
    ap.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    ap.add_argument("--site-base", default=SITE_BASE)
    ap.add_argument("--dry-run", action="store_true", help="只生成文件，不 commit / push")
    ap.add_argument("--rebuild-all", action="store_true",
                    help="顺带重刷发布仓里已有的全部日页（用于给历史期补上"
                         "顶部日期时间线 / 统一版式），一次提交")
    args = ap.parse_args()

    date = args.date or latest_date()
    if not date:
        raise SystemExit("❌ data/ 下没有找到 intel-YYYY-MM-DD.json")
    print(f"发布日期：{date}")

    print("\n[1/6] 准备发布仓")
    cloned = ensure_repo(args.repo_dir, args.repo_url)
    if cloned:
        git(args.repo_dir, "config", "user.name", "figure-intel-bot", check=False)
        git(args.repo_dir, "config", "user.email", "lyt3905@users.noreply.github.com",
            check=False)
    print(f"  {args.repo_dir}")

    print("\n[2/6] 生成发布版 HTML（缩略图外链 / 点图跳原博 / 顶部日期时间线）")
    html, total, added, missing = render_day(date, args.repo_dir)
    print(f"  {date}.html  {len(html.encode()) / 1024:.1f} KB")
    print(f"  页面引用缩略图 {total} 张，新增 {added} 张，缺失 {len(missing)} 张")
    if missing:
        print(f"  ⚠️ 本地缺图（页面会显示空白，可重跑 attach_media.py --download 补齐）："
              f"{', '.join(missing[:5])}{' ...' if len(missing) > 5 else ''}")

    if args.rebuild_all:
        others = [d for d in repo_days(args.repo_dir) if d != date]
        if others:
            print(f"\n[3/6] 重刷仓里已有的另外 {len(others)} 期"
                  f"（给历史页补日期时间线）")
            for d in others:
                try:
                    _, t, a, m = render_day(d, args.repo_dir)
                except SystemExit as e:
                    print(f"  ⚠️ 跳过 {d}：{e}")
                    continue
                print(f"  {d} ✓ 引用 {t} / 新增 {a}"
                      + (f" / ⚠️ 缺 {len(m)}" if m else ""))
        else:
            print("\n[3/6] 发布仓暂无其他历史期，跳过重刷")
    else:
        print("\n[3/6] 跳过历史期重刷（加 --rebuild-all 可一并刷新）")

    print("\n[4/6] 写入固定入口与历史归档")
    days = repo_days(args.repo_dir)
    latest = max(days) if days else date
    if latest != date:
        # --date 指定了旧日期时，入口页仍要指向最新一期，不能倒退
        with open(os.path.join(args.repo_dir, f"{latest}.html"), "r",
                  encoding="utf-8") as f:
            html = f.read()
        print(f"  入口页取最新一期 {latest}（本次发布的是 {date}）")
    with open(os.path.join(args.repo_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(args.repo_dir, "archive.html"), "w", encoding="utf-8") as f:
        f.write(build_archive(args.repo_dir))
    with open(os.path.join(args.repo_dir, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(PUBLISH_IGNORE)
    md_src = os.path.join(OUTPUT_DIR, f"手办情报-{date}.md")
    if os.path.exists(md_src):
        shutil.copy2(md_src, os.path.join(args.repo_dir, f"{date}.md"))
        print(f"  index.html + archive.html + .gitignore + {date}.md")
    else:
        print("  index.html + archive.html + .gitignore")

    size = repo_size_mb(args.repo_dir)
    print(f"  发布仓当前体积：{size:.1f} MB")

    print("\n[5/6] 提交")
    if args.dry_run:
        print("  --dry-run：跳过提交与推送")
        st = git(args.repo_dir, "status", "--short", check=False)
        print("  待提交文件：")
        for line in st.stdout.strip().splitlines()[:15]:
            print("   ", line)
    else:
        git(args.repo_dir, "add", "-A", check=False)
        r = git(args.repo_dir, "commit", "-m",
                f"digest: {date} 手办情报每日简报", check=False)
        if "nothing to commit" in (r.stdout + r.stderr):
            print("  无变化，跳过提交")
        else:
            print("  ✅ 已提交")

        print("\n[6/6] 推送")
        p = git(args.repo_dir, "push", "origin", "main", check=False)
        if p.returncode != 0:
            print("  ❌ 推送失败：")
            print("  ", (p.stderr or p.stdout).strip()[:400])
            return 1
        print("  ✅ 已推送 origin/main")

    print("\n" + "=" * 56)
    print("固定入口（收藏这一个就够）：")
    print(f"  {args.site_base}")
    print("今日存档：")
    print(f"  {args.site_base}{date}.html")
    print("历史归档：")
    print(f"  {args.site_base}archive.html")
    print("=" * 56)
    print("提示：GitHub Pages 首次构建约需 1 分钟；之后每次推送约 30~60 秒生效。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
