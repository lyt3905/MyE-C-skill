import sys, time, json
from PIL import Image
import numpy as np
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen

T = "个人 2"
CHAN = "2348249"
EXT_ICON = (2732, 48)
BACKFILL = (3700, 226)
DRAWER_OK = (3770, 2000)
SHOTS = screen.SHOTS

def title():
    w = screen.find_window(T)
    return w["title"] if w else ""

def wait_title(need, timeout, poll=0.8):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if need in title():
            return round(time.time() - t0, 1)
        time.sleep(poll)
    return -1

def find_goset(im):
    """在左栏找“去设置”按钮（白底蓝边小按钮），返回屏幕坐标中心。"""
    a = np.asarray(im.convert("RGB")).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mask = (b > 170) & (b - r > 60) & (g < 170) & (r < 130)
    mask[:, :430] = False
    mask[:, 700:] = False
    mask[:300, :] = False
    ys, xs = np.nonzero(mask)
    if len(xs) < 40:
        return None
    # 聚成行
    order = np.argsort(ys)
    ys, xs = ys[order], xs[order]
    groups = []
    cur = [0]
    for i in range(1, len(ys)):
        if ys[i] - ys[i - 1] <= 6:
            cur.append(i)
        else:
            groups.append(cur); cur = [i]
    groups.append(cur)
    best = None
    for grp in groups:
        gy = ys[grp]; gx = xs[grp]
        h = gy.max() - gy.min(); w = gx.max() - gx.min()
        if 20 <= h <= 60 and 60 <= w <= 170:
            best = (int(gx.mean()), int(gy.mean()))
    return best

def run(pid, wait_s=40, chan=CHAN):
    out = {"pid": pid}
    screen.preguard(T)
    screen.hotkey("ctrl+t"); time.sleep(0.7)
    url = f"https://csp.aliexpress.com/ait/cn_pop/item_product/product_publish?productId={pid}&channelId={chan}"
    screen.navurl(url, yes=True, target=T)
    out["page"] = wait_title("商品发布", 25)
    time.sleep(1.0)
    screen.click(*EXT_ICON, yes=True, target=T)
    out["editor"] = wait_title("图片编辑器", 15)
    if out["editor"] < 0:
        out["status"] = "EDITOR_NOT_OPEN"; print(json.dumps(out, ensure_ascii=False)); return
    time.sleep(wait_s)
    screen.grab(f"ed_{pid}")
    for i in range(3):
        screen.click(*BACKFILL, yes=True, target=T)
        time.sleep(6)
        if "图片编辑器" not in title():
            break
    time.sleep(10)
    screen.hotkey("esc"); time.sleep(0.6)
    screen.click(2600, 800, yes=True, target=T)
    screen.hotkey("ctrl+home"); time.sleep(0.9)
    shot = screen.grab(f"row_{pid}")["shot"]
    im = Image.open(shot).convert("RGB")
    im.crop((420, 1150, 1900, 1800)).save(str(SHOTS / f"crop_row_{pid}.png"))
    out["row_crop"] = str(SHOTS / f"crop_row_{pid}.png")
    # 滚到海关监管属性
    screen.wheel(1500, 1200, 6, yes=True, target=T)
    time.sleep(1.2)
    s2 = screen.grab(f"cust_{pid}")["shot"]
    im2 = Image.open(s2).convert("RGB")
    im2.crop((300, 200, 2400, 2100)).resize((1050, 950), Image.LANCZOS).save(str(SHOTS / f"crop_cust_{pid}.png"))
    pos = find_goset(im2)
    out["goset"] = pos
    out["cust_crop"] = str(SHOTS / f"crop_cust_{pid}.png")
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    a = sys.argv
    run(a[1], int(a[2]) if len(a) > 2 else 40, a[3] if len(a) > 3 else CHAN)
