"""整段横幅 / 纯色底贴边字 的擦除工具（skill 自带，不依赖 pipeline.py）。

用途：对付「整条店名横幅（纯色或渐变底）」「贴在纯色底上的促销红字」这类水印。
与 erase24b/erase24c（inpainting）不同：这两种场景 inpaint 会糊、会留残影，
正确做法是「整段填白 + 按行插值」，本模块就是这两步。

2026-11-07 在 4826（Mr. Li's Studio Store 粉色横幅 + 紫圆红字 In stock）实测的配方，
抽成函数；改参数前先看该件报告里的 ROI 取值。

约定：所有图像都是 BGR（cv2 读进来的原样），所有 ROI 都是 (x0, y0, x1, y1) 且右开下开。
"""

import cv2
import numpy as np


def band_mask(img, ref_bgr, tol=60, y1=None):
    """标出与参照色 ref_bgr 相近的像素（容忍每通道 max 差 <= tol）。y1 限制只看顶部若干行。"""
    h = img.shape[0] if y1 is None else min(y1, img.shape[0])
    d = np.abs(img[:h].astype(int) - np.array(ref_bgr, dtype=int)).max(axis=2)
    return (d <= tol).astype(np.uint8)


def wipe_band(img, mask, pad=3, fill=(255, 255, 255), grow=5, iters=2):
    """把 mask 区域内所有行、从左到右的整段涂成 fill。

    mask 先膨胀 grow×grow、iters 次，再取命中像素的包围盒，把包围盒内每一行整段填满
    （横幅文字通常比底色深，整段填白比只填字符更干净）。原地修改并返回 img。
    """
    m = cv2.dilate(mask.astype(np.uint8), np.ones((grow, grow), np.uint8), iters)
    ys, xs = np.where(m > 0)
    if len(ys) == 0:
        return img
    y0, y1 = max(0, ys.min() - pad), min(img.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(img.shape[1], xs.max() + pad + 1)
    img[y0:y1, x0:x1] = fill
    return img


def color_mask(img, roi, kind="red", dilate=7):
    """在 roi=(x0,y0,x1,y1) 内按颜色挑字。

    kind:
      "red"   —— 红字压浅底（R 高、R- 通道差明显）
      "any"   —— 只要不是近白/近黑的都算（谨慎，容易带进商品本体）
    """
    x0, y0, x1, y1 = roi
    sub = img[y0:y1, x0:x1]
    B, G, R = sub[:, :, 0].astype(int), sub[:, :, 1].astype(int), sub[:, :, 2].astype(int)
    if kind == "red":
        m = (R > 120) & (R - G > 55) & (R - B > 20) & (G < 140)
    else:
        gray = sub.mean(axis=2)
        m = (gray < 220) & (gray > 20)
    m = cv2.dilate(m.astype(np.uint8), np.ones((dilate, dilate), np.uint8), 2).astype(bool)
    full = np.zeros(img.shape[:2], bool)
    full[y0:y1, x0:x1] = m
    return full


def fill_rowwise(img, mask, pad=6, max_span=None):
    """按行插值：mask 覆盖的像素用同一行左右两侧未覆盖像素线性插值补上。

    适合「字压在渐变底 / 实拍底」的场景（填白会留下白色补丁）。原地修改并返回 img。
    pad 控制上下留白行数；max_span 是单行可插值的最大跨度（超了说明 mask 太宽，跳过该行更安全）。
    """
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return img
    y0, y1 = max(0, ys.min() - pad), min(img.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(img.shape[1], xs.max() + pad + 1)
    for y in range(y0, y1):
        rm = mask[y, x0:x1]
        if not rm.any():
            continue
        idx = np.where(~rm)[0]
        if len(idx) < 2:
            continue
        if max_span is not None and (idx.max() - idx.min()) > max_span:
            continue
        span = np.arange(x1 - x0)
        for k in range(3):
            v = img[y, x0:x1, k].astype(float)
            img[y, x0:x1, k] = np.interp(span, idx, v[idx]).astype(np.uint8)
    return img


def crop_border(img, box, size=800, preserve_aspect=False):
    """按 (x0, y0, x1, y1) 裁掉装饰边框，再缩放回 size×size。"""
    x0, y0, x1, y1 = box
    c = img[y0:y1, x0:x1]
    if preserve_aspect:
        height,width=c.shape[:2];scale=size/max(height,width)
        resized=cv2.resize(c,(max(1,round(width*scale)),max(1,round(height*scale))),interpolation=cv2.INTER_LANCZOS4)
        result=np.full((size,size,3),255,dtype=img.dtype)
        top=(size-resized.shape[0])//2;left=(size-resized.shape[1])//2
        result[top:top+resized.shape[0],left:left+resized.shape[1]]=resized
        return result
    return cv2.resize(c, (size, size), interpolation=cv2.INTER_LANCZOS4)


def check_residue(img, roi, kind="red", min_px=8):
    """擦完自检：ROI 内同类颜色还剩多少像素。返回 (剩余像素数, 是否干净)。"""
    m = color_mask(img, roi, kind=kind, dilate=1)
    n = int(m.sum())
    return n, n < min_px


if __name__ == "__main__":
    # 4826 的复现命令（参数照该件报告）：证明这套配方可以从原始图复现线上结果
    import sys

    src = sys.argv[1] if len(sys.argv) > 1 else "work/pp_4826/src/main_0.png"
    img = cv2.imread(src)
    img = crop_border(img, (17, 25, 778, 785))
    h, w = img.shape[:2]
    pink = img[0:16].reshape(-1, 3).mean(axis=0)          # 横幅底色取样
    wipe_band(img, band_mask(img, pink, tol=60, y1=16))
    text = color_mask(img, (0, 600, 150, h), kind="red")
    fill_rowwise(img, text)
    out = sys.argv[2] if len(sys.argv) > 2 else "work/_clean_band_out.png"
    cv2.imwrite(out, img)
    print("wrote", out, img.shape)
