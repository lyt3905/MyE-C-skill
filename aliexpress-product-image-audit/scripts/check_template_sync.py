#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""规则文档与核心脚本双份一致性校验（仓库版 <-> skill 副本）。

维护口径：规则文档与模板的正本都在项目目录 `ae-img-audit/`，skill 里存可移植副本，
拿 skill 到别的机器时能自足。两份必须字节一致，否则子任务会拿到旧口径
（历史上「前缀一律 Hot Sale」就是这么漂的；2026-11-07 又发现 `站点接口备忘.md`
仓库版落后 skill 版 17 行）。

比对清单（14 对）：
    子任务模板-单件商品.md  <-> templates/子任务模板.md
    SOP-商品图片整改.md     <-> references/SOP-商品图片整改.md
    SOP-商品标题重写.md     <-> references/SOP-商品标题重写.md
    站点接口备忘.md         <-> references/站点接口备忘.md
    判例与陷阱.md           <-> references/判例与陷阱.md
    audit_one.py            <-> scripts/audit_one.py
    site_client.py           <-> scripts/site_client.py
    product_state.py         <-> scripts/product_state.py
    token_opt_plan.py        <-> scripts/token_opt_plan.py
    description_refs.py      <-> scripts/description_refs.py
    apply_token_plan.py      <-> scripts/apply_token_plan.py
    render_token_report.py   <-> scripts/render_token_report.py
    tests/test_token_opt.py  <-> tests/test_token_opt.py
    check_template_sync.py   <-> scripts/check_template_sync.py

用法：
    python check_template_sync.py             # 只校验，有不一致返回 1
    python check_template_sync.py --push      # 仓库 -> skill 副本（全部同步对）
    python check_template_sync.py --pull      # skill 副本 -> 仓库（全部同步对）
    python check_template_sync.py --push --only 站点接口备忘
                                              # 只同步一对（名字可用前缀，见 PAIRS）
"""
import hashlib
import os
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8')

SKILL_DIR = os.path.join(os.path.expanduser('~'), '.dsh', 'skills', 'aliexpress-product-image-audit')

# (显示名, 仓库相对路径, skill 相对路径)
PAIRS = [
    ('子任务模板', '子任务模板-单件商品.md', 'templates/子任务模板.md'),
    ('SOP-商品图片整改', 'SOP-商品图片整改.md', 'references/SOP-商品图片整改.md'),
    ('SOP-商品标题重写', 'SOP-商品标题重写.md', 'references/SOP-商品标题重写.md'),
    ('站点接口备忘', '站点接口备忘.md', 'references/站点接口备忘.md'),
    ('判例与陷阱', '判例与陷阱.md', 'references/判例与陷阱.md'),
    ('audit_one', 'audit_one.py', 'scripts/audit_one.py'),
    ('site_client', 'site_client.py', 'scripts/site_client.py'),
    ('product_state', 'product_state.py', 'scripts/product_state.py'),
    ('token_opt_plan', 'token_opt_plan.py', 'scripts/token_opt_plan.py'),
    ('description_refs', 'description_refs.py', 'scripts/description_refs.py'),
    ('apply_token_plan', 'apply_token_plan.py', 'scripts/apply_token_plan.py'),
    ('render_token_report', 'render_token_report.py', 'scripts/render_token_report.py'),
    ('token_opt_tests', 'tests/test_token_opt.py', 'tests/test_token_opt.py'),
    ('check_template_sync', 'check_template_sync.py', 'scripts/check_template_sync.py'),
]

# 用来认「项目目录」的标志文件：碰到任意一个就当这里是 ae-img-audit
MARKERS = ('子任务模板-单件商品.md', 'SOP-商品图片整改.md', 'pipeline.py')


def find_repo():
    """定位项目目录（含正本 md 的那一层）。顺序：AE_ROOT -> 本文件上溯 -> cwd。"""
    cands = []
    if os.environ.get('AE_ROOT'):
        cands.append(os.environ['AE_ROOT'])
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        cands.append(d)
        d = os.path.dirname(d)
    cands.append(os.getcwd())
    for c in cands:
        if not c or not os.path.isdir(c):
            continue
        hits = sum(1 for m in MARKERS if os.path.exists(os.path.join(c, m)))
        if hits >= 2:
            return c
    return os.getcwd()


def md5(path):
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def info(path):
    h = md5(path)
    if h is None:
        return '(缺失)'
    size = os.path.getsize(path)
    try:
        with open(path, encoding='utf-8') as f:
            lines = sum(1 for _ in f)
        return 'md5=%s  %6d B  %4d 行' % (h[:12], size, lines)
    except UnicodeDecodeError:
        # 非 UTF-8（例如被别的工具按 GBK 写过）不算崩，md5 照样能判等
        return 'md5=%s  %6d B  <非 UTF-8，行数略>' % (h[:12], size)


def main():
    args = sys.argv[1:]
    push = '--push' in args
    pull = '--pull' in args
    if push and pull:
        print('--push 与 --pull 不能同时用')
        return 2
    only = None
    if '--only' in args:
        i = args.index('--only')
        if i + 1 >= len(args):
            print('--only 后面要跟名字，可选：' + ' / '.join(p[0] for p in PAIRS))
            return 2
        only = args[i + 1]

    repo = find_repo()
    print('项目目录：%s' % repo)
    print('skill 目录：%s' % SKILL_DIR)
    print()

    sel = [p for p in PAIRS if only is None or p[0].startswith(only)]
    if not sel:
        print('没匹配到任何一对，可选：' + ' / '.join(p[0] for p in PAIRS))
        return 2

    if push or pull:
        for name, rel, srel in sel:
            src = os.path.join(repo, rel) if push else os.path.join(SKILL_DIR, srel)
            dst = os.path.join(SKILL_DIR, srel) if push else os.path.join(repo, rel)
            if not os.path.exists(src):
                print('[跳过] %s：源不存在 %s' % (name, src))
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            print('[已同步 %s] %s' % ('仓库->skill' if push else 'skill->仓库', name))
        print()

    bad = []
    for name, rel, srel in sel:
        a = os.path.join(repo, rel)
        b = os.path.join(SKILL_DIR, srel)
        ha, hb = md5(a), md5(b)
        ok = ha is not None and ha == hb
        print('%s %s' % ('OK  ' if ok else 'FAIL', name))
        print('       仓库 : %s  %s' % (info(a), rel))
        print('       skill: %s  %s' % (info(b), srel))
        if not ok:
            bad.append(name)

    print()
    if bad:
        print('FAIL：%d/%d 对不一致 -> %s' % (len(bad), len(sel), '、'.join(bad)))
        print('确认哪份是新口径后，用 --push（仓库为准）或 --pull（skill 为准）同步，再提交。')
        return 1
    print('OK：%d/%d 对字节一致' % (len(sel), len(sel)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
