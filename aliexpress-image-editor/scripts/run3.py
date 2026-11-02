import sys, time, json
from PIL import Image
import numpy as np
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen
from findtext import findtext

T = "个人 2"
CHAN = "2348249"
EXT_ICON = (2732, 48)
BACKFILL = (3700, 226)
DRAWER_OK = (3765, 2000)
WARN = "请重新补全并提交海关监管属性"
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

def warn_score():
    screen.preguard(T)
    screen.set_clipboard("")
    screen.hotkey("ctrl+f"); time.sleep(0.2)
    screen.hotkey("ctrl+a"); screen.hotkey("delete"); time.sleep(0.35)
    a = screen.grab("wa")["shot"]
    screen.set_clipboard(WARN)
    screen.hotkey("ctrl+v"); time.sleep(1.0)
    b = screen.grab("wb")["shot"]
    A = np.asarray(Image.open(a).convert("L"), float)
    B = np.asarray(Image.open(b).convert("L"), float)
    d = np.abs(A - B)
    d[0:260, 1700:2900] = 0
    frac = (d > 25).mean() * 100
    return round(frac, 2)

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
    time.sleep(10)                      # 等上传弹窗内的合成图传完
    screen.hotkey("esc"); time.sleep(0.6)
    screen.click(2600, 800, yes=True, target=T)
    screen.hotkey("ctrl+home"); time.sleep(0.9)
    shot = screen.grab(f"row_{pid}")["shot"]
    im = Image.open(shot).convert("RGB")
    im.crop((420, 1150, 1900, 1800)).save(str(SHOTS / f"crop_row_{pid}.png"))
    out["row_crop"] = str(SHOTS / f"crop_row_{pid}.png")
    w1 = warn_score()
    out["warn_before"] = w1
    if w1 > 1.0:
        box = findtext(WARN, target=T, keep=True)
        out["box"] = box
        if box:
            x = max(20, box[0] - 150); y = int((box[1] + box[3]) / 2)
            screen.click(x, y, yes=True, target=T)
            time.sleep(1.8)
            screen.click(*DRAWER_OK, yes=True, target=T)
            time.sleep(1.6)
        screen.hotkey("esc"); time.sleep(0.5)
        out["warn_after"] = warn_score()
        screen.grab(f"after_{pid}")
        Image.open(str(SHOTS / f"after_{pid}.png")).convert("RGB").crop((300, 200, 2400, 1400)).resize((1050, 600), Image.LANCZOS).save(str(SHOTS / f"crop_after_{pid}.png"))
        screen.hotkey("esc")
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    a = sys.argv
    run(a[1], int(a[2]) if len(a) > 2 else 40, a[3] if len(a) > 3 else CHAN)
