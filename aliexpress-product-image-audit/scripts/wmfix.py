# 注意：本文件是 ae-img-audit/wmfix.py 的通用副本，运行依赖同目录的 site_client.py。
# 项目专属的重型工具（pipeline.py 的 scan/apply/verify/OCR 判据库）不在 skill 里。
# -*- coding: utf-8 -*-
"""水印/店名文字裁切器（确定性）：按 OCR 命中的水印行所在边做裁切，裁完再 OCR 复验，最多 2 轮。
用法: python wmfix.py calc    只统计
      python wmfix.py write   把裁好的文件写进 plan（REPLACE_WEB）
"""
import sys, os, re, json
sys.path.insert(0, '.'); sys.stdout.reconfigure(encoding='utf-8')
from site_client import ocr_boxes
import cv2, numpy as np

WM_CJK = re.compile(r'店|商铺|专营|旗舰|批发|代购|淘宝|阿里巴巴')
WM_EN = re.compile(r'(?i)\b(store|shop|aliexpress|in\s*stock|official\s*store|sold\s*by)\b')
SLOGAN_MIN = 15   # 顶部纯大写英文口号（≥15 字符）视为加字

def classify(t):
    tl = t.strip()
    if WM_CJK.search(tl): return 'cjk'
    if WM_EN.search(tl): return 'en'
    up = re.sub(r'[^A-Z]', '', tl)
    if len(up) >= SLOGAN_MIN and len(up) >= 0.8 * len(tl.replace(' ', '')): return 'slogan'
    return None

def wm_lines(f, minconf=0.55):
    b = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = b.shape[:2]
    out = []
    for bx in ocr_boxes(f):
        if bx['conf'] < minconf: continue
        k = classify(bx['text'])
        if k: out.append((k, bx['text'], bx['box']))
    return w, h, out

def one_pass(f, kind, dst):
    w, h, hits = wm_lines(f)
    if not hits: return None, []
    top, bot = 0, h
    for k, t, box in hits:
        if k == 'slogan':
            if box[1] <= 0.12 * h: top = max(top, box[3])
            continue
        if box[3] >= 0.85 * h and box[1] >= 0.58 * h: bot = min(bot, box[1])
        elif box[1] <= 0.12 * h: top = max(top, box[3])
        # 中部水印：交给人（不做裁切）
    if top == 0 and bot == h: return None, hits
    y0 = max(0, top - 8); y1 = min(h, bot + 8)
    if y1 - y0 < 0.55 * h: return None, hits
    img = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_COLOR)[y0:y1]
    cv2.imwrite(dst, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return {'src': (w, h), 'crop': (y0, y1)}, hits

def fix(f, kind, dst):
    """裁 + 复验，最多 2 轮。返回 (ok, 说明)"""
    cur = f; rects = []
    for rnd in range(2):
        r, hits = one_pass(cur, kind, dst)
        if r is None:
            if rnd == 0: return (True, '无需裁') if not hits else (False, '命中但无法裁: %s' % '|'.join(h[1] for h in hits[:3]))
            return True, '裁 1 轮后干净'
        rects.append(r['crop']); cur = dst
    w, h, left = wm_lines(dst)
    left = [x for x in left if x[0] != 'slogan']
    if left: return False, '仍剩: %s' % '|'.join(x[1] for x in left[:3])
    return True, '裁 %d 轮干净' % len(rects)

def main(mode):
    tot = okn = badn = 0; bads = []; plans = {}; cache = {}
    for pid in range(4847, 4873):
        d = 'work/pp_%d' % pid
        pl = json.load(open(os.path.join(d, 'plan.json'), encoding='utf-8'))
        os.makedirs(os.path.join(d, 'act'), exist_ok=True)
        n = 0
        for it in pl['images']:
            f = it.get('file')
            if not f or not os.path.exists(f): continue
            name = '%s_%d' % (it['kind'], it['idx'])
            if it['kind'] == 'detail' and it.get('action') in ('CN_POSTER', 'DELETE'): continue
            dst = os.path.join(d, 'act', name + '_wm.jpg')
            ok, why = fix(f, it['kind'], dst)
            tot += 1
            if ok and why != '无需裁':
                n += 1; it['action'] = 'REPLACE_WEB'; it['web_file'] = dst; it['reason'] = '本地裁水印（%s）' % why
            elif not ok:
                badn += 1; bads.append('%d %s: %s' % (pid, name, why))
        if n: plans[pid] = n
        cache[pid] = pl
    print('检查 %d 张，需改写 %d 张，失败/需人工 %d 张' % (tot, sum(plans.values()), badn))
    print('按商品:', json.dumps(plans, ensure_ascii=False))
    for b in bads: print('  !', b)
    if mode == 'write':
        for pid, pl in cache.items():
            json.dump(pl, open('work/pp_%d/plan.json' % pid, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('plan.json 已写回 %d 个商品' % len(cache))

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'calc')