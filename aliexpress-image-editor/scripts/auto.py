import sys, time, json
from PIL import Image
import numpy as np
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen

TARGET = "个人 2"
CHAN = "2348249"
EXT_ICON = (2732, 48)
BACKFILL = (3700, 226)
WARN = "请重新补全并提交海关监管属性"
SHOTS = screen.SHOTS

def title():
    w = screen.find_window(TARGET)
    return w["title"] if w else ""

def wait_title(need, timeout, poll=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if need in title():
            return True, round(time.time() - t0, 1)
        time.sleep(poll)
    return False, round(time.time() - t0, 1)

def probe_warn():
    """用 Ctrl+F 输入警告文案，靠页面是否发生滚动判断该文案是否存在（无需 OCR）。"""
    screen.preguard(TARGET)
    screen.set_clipboard("")
    screen.hotkey("ctrl+f"); time.sleep(0.25)
    screen.hotkey("ctrl+a"); screen.hotkey("delete"); time.sleep(0.4)
    a = screen.grab("pa")["shot"]
    screen.set_clipboard(WARN)
    screen.hotkey("ctrl+v"); time.sleep(1.0)
    b = screen.grab("pb")["shot"]
    A = np.asarray(Image.open(a).convert("L"), float)
    B = np.asarray(Image.open(b).convert("L"), float)
    d = np.abs(A - B)
    d[0:260, 1700:2900] = 0     # 排除 find 浮条
    frac = (d > 25).mean() * 100
    screen.hotkey("esc")
    return round(frac, 2)

def run(pid, chan=CHAN):
    out = {"pid": pid}
    screen.preguard(TARGET)
    screen.hotkey("ctrl+t"); time.sleep(0.7)
    url = f"https://csp.aliexpress.com/ait/cn_pop/item_product/product_publish?productId={pid}&channelId={chan}"
    screen.navurl(url, yes=True, target=TARGET)
    ok, dt = wait_title("商品发布", 25); out["page"] = [ok, dt]
    time.sleep(1.0)
    screen.click(*EXT_ICON, yes=True, target=TARGET)
    ok, dt = wait_title("图片编辑器", 15); out["editor"] = [ok, dt]
    if not ok:
        out["status"] = "EDITOR_NOT_OPEN"; print(json.dumps(out, ensure_ascii=False)); return
    time.sleep(24)
    for i in range(6):
        screen.click(*BACKFILL, yes=True, target=TARGET)
        time.sleep(4.5)
        if "图片编辑器" not in title():
            out["backfill"] = ["ok", i]; break
        time.sleep(3.5)
    else:
        out["status"] = "BACKFILL_FAIL"; print(json.dumps(out, ensure_ascii=False)); return
    time.sleep(1.2)
    # 回到顶部，拍图库行
    screen.click(700, 1050, yes=True, target=TARGET)
    screen.hotkey("ctrl+home"); time.sleep(0.8)
    shot = screen.grab(f"row_{pid}")["shot"]
    im = Image.open(shot).convert("RGB")
    im.crop((420, 1150, 1900, 1800)).save(str(SHOTS / f"crop_row_{pid}.png"))
    out["row_crop"] = str(SHOTS / f"crop_row_{pid}.png")
    out["warn_score"] = probe_warn()
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else CHAN)
