# 注意：本文件是 ae-img-audit/_shopread.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""只读：判断当前审核的商品集合属于哪个店铺（按详情区里的店铺链接账号）。"""
import json, glob, collections, re, sys
sys.stdout.reconfigure(encoding='utf-8')

fs = glob.glob('work/marvel_scan/backup/*.json')
c = collections.Counter()
samples = []
for f in fs:
    d = json.load(open(f, encoding='utf-8'))
    dj = d.get('descriptionJson') or ''
    if isinstance(dj, (dict, list)):
        dj = json.dumps(dj, ensure_ascii=False)
    c['n'] += 1
    if '1105641114' in dj:
        c['shana1_1105641114'] += 1
    if '1105382170' in dj:
        c['store62_1105382170'] += 1
    if not ('1105641114' in dj or '1105382170' in dj):
        c['no_acct'] += 1
    if len(samples) < 5:
        for m in re.findall(r'https?://[^"\\ ]*store[^"\\ ]*', dj):
            samples.append((d['id'], m[:110])); break
print(dict(c))
for s in samples:
    print(s)
