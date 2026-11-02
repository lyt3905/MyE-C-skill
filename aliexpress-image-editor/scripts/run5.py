import sys, time, json
from PIL import Image
import numpy as np
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen

T = "个人 2"
CHAN = "2348249"
EXT_ICON = (2732, 48)
BACKFILL = (3700, 226)
UPLOAD_OK = (2011, 1769)
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

def brightness(im, box):
    a = np.asarray(im.convert("L"), float)
    x0, y0, x1, y1 = box
    return round(a[y0:y1, x0:x1].mean(), 1)

def modal_open():
    s = screen.grab("mchk")["shot"]
    im = Image.open(s)
    return brightness(im, (500, 300, 1200, 600)) < 190

def find_warn_icon_y(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mask = (r > 190) & (g > 55) & (g < 155) & (b < 95)
    mask[:, :560] = False
    mask[:, 730:] = False
    mask[:250, :] = False
    ys, xs = np.nonzero(mask)
    if len(xs) < 25:
        return None
    return int(np.median(ys))

def run(pid, wait_s=40, chan=CHAN, do_cust=True):
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
    got = False
    for i in range(3):
        screen.click(*BACKFILL, yes=True, target=T)
        t0 = time.time()
        while time.time() - t0 < 30:
            if "图片编辑器" not in title() and modal_open():
                got = True; break
            time.sleep(1.5)
        if got: break
    out["modal"] = got
    if got:
        time.sleep(13)                      # 等合成图上传完成
        screen.click(*UPLOAD_OK, yes=True, target=T)
        time.sleep(2)
        if modal_open():
            screen.hotkey("esc"); time.sleep(1)
    screen.click(2600, 1100, yes=True, target=T)
    screen.hotkey("ctrl+home"); time.sleep(0.9)
    shot = screen.grab(f"row_{pid}")["shot"]
    im = Image.open(shot).convert("RGB")
    im.crop((420, 1150, 1900, 1800)).save(str(SHOTS / f"crop_row_{pid}.png"))
    out["row_crop"] = str(SHOTS / f"crop_row_{pid}.png")
    if do_cust:
        screen.wheel(1500, 1200, 6, yes=True, target=T)
        time.sleep(1.2)
        s2 = screen.grab(f"cust_{pid}")["shot"]
        im2 = Image.open(s2).convert("RGB")
        im2.crop((300, 200, 2400, 2100)).resize((1050, 950), Image.LANCZOS).save(str(SHOTS / f"crop_cust_{pid}.png"))
        y = find_warn_icon_y(im2)
        out["icon_y"] = y
        out["cust_crop"] = str(SHOTS / f"crop_cust_{pid}.png")
        if y:
            screen.click(505, y, yes=True, target=T)
            time.sleep(1.8)
            screen.click(*DRAWER_OK, yes=True, target=T)
            time.sleep(1.8)
            s3 = screen.grab(f"fin_{pid}")["shot"]
            Image.open(s3).convert("RGB").crop((300, 200, 2400, 2100)).resize((1050, 950), Image.LANCZOS).save(str(SHOTS / f"crop_fin_{pid}.png"))
            out["fin_crop"] = str(SHOTS / f"crop_fin_{pid}.png")
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    a = sys.argv
    run(a[1], int(a[2]) if len(a) > 2 else 40, a[3] if len(a) > 3 else CHAN)
