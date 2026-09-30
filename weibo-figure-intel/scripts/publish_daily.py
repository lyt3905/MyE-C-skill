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
"""

import argparse
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

_INTEL_NAME = re.compile(r"^intel-(\d{4}-\d{2}-\d{2})\.json$")
_DAY_PAGE = re.compile(r"^\d{4}-\d{2}-\d{2}\.html$")
_THUMB_REF = re.compile(r"media/thumb/([^\"'\s>)]+)")


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


def build_page(date, out_html, media_rel="media"):
    src = os.path.join(DATA_DIR, f"intel-{date}.json")
    if not os.path.exists(src):
        raise SystemExit(f"❌ 找不到情报源文件：{src}")
    cmd = [sys.executable, BUILD_DIGEST, "--input", src, "--format", "html",
           "--html-out", out_html, "--publish", "--media-rel", media_rel]
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


def inject_nav(html, date):
    """在 <body> 之后插一条发布导航（纯内联样式，不干扰简报自身 CSS）。"""
    bar = (
        '<div style="display:flex;align-items:center;gap:12px;padding:9px 18px;'
        'background:#1f2430;color:#fff;font:13px/1.5 system-ui,-apple-system,'
        "'Segoe UI',sans-serif\">"
        '<span style="font-weight:600">手办情报 · 每日更新</span>'
        f'<span style="opacity:.72">{date}</span>'
        '<a href="archive.html" style="margin-left:auto;color:#9ecbff;'
        'text-decoration:none">历史归档 →</a>'
        '</div>'
    )
    m = re.search(r"<body[^>]*>", html)
    if not m:
        return bar + html
    i = m.end()
    return html[:i] + bar + html[i:]


def build_archive(repo_dir):
    days = sorted((n[:-5] for n in os.listdir(repo_dir) if _DAY_PAGE.match(n)),
                  reverse=True)
    if days:
        items = "\n".join(
            f'<li><a href="{d}.html"><b>{d}</b></a></li>' for d in days)
    else:
        items = "<li>暂无存档</li>"
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
  a{{display:block;padding:12px 16px;background:#fff;border:1px solid #e5e7eb;
    border-radius:10px;color:#1c2029;text-decoration:none}}
  a:hover{{border-color:#9ecbff;background:#f2f8ff}}
  .back{{display:inline-block;margin-bottom:18px;color:#2563eb;text-decoration:none;font-size:13px}}
</style></head>
<body><div class="w">
<a class="back" href="index.html">← 返回最新一期</a>
<h1>手办情报 · 历史归档</h1>
<p class="sub">共 {len(days)} 期 · 每日自动更新</p>
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


def main():
    ap = argparse.ArgumentParser(description="发布手办情报简报到 GitHub Pages")
    ap.add_argument("--date", help="要发布的日期 YYYY-MM-DD，默认取最新")
    ap.add_argument("--repo-dir", default=DEFAULT_REPO_DIR, help="发布仓本地目录")
    ap.add_argument("--repo-url", default=DEFAULT_REPO_URL)
    ap.add_argument("--site-base", default=SITE_BASE)
    ap.add_argument("--dry-run", action="store_true", help="只生成文件，不 commit / push")
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

    print("\n[2/6] 生成发布版 HTML（缩略图外链 / 点图跳原博）")
    day_html = os.path.join(args.repo_dir, f"{date}.html")
    build_page(date, day_html)
    html = open(day_html, "r", encoding="utf-8").read()
    print(f"  {date}.html  {len(html.encode()) / 1024:.1f} KB")

    print("\n[3/6] 同步缩略图（原图不入库）")
    total, added, missing = copy_thumbs(html, args.repo_dir)
    print(f"  页面引用 {total} 张，新增 {added} 张，缺失 {len(missing)} 张")
    if missing:
        print(f"  ⚠️ 本地缺图（页面会显示空白，可重跑 attach_media.py --download 补齐）："
              f"{', '.join(missing[:5])}{' ...' if len(missing) > 5 else ''}")

    print("\n[4/6] 写入固定入口与历史归档")
    html = inject_nav(html, date)
    with open(day_html, "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(args.repo_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(args.repo_dir, "archive.html"), "w", encoding="utf-8") as f:
        f.write(build_archive(args.repo_dir))
    md_src = os.path.join(OUTPUT_DIR, f"手办情报-{date}.md")
    if os.path.exists(md_src):
        shutil.copy2(md_src, os.path.join(args.repo_dir, f"{date}.md"))
        print(f"  index.html + archive.html + {date}.md")
    else:
        print("  index.html + archive.html")

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
