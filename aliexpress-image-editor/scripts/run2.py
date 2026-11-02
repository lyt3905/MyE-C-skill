import sys, time, json
from PIL import Image
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen

TARGET = "个人 2"
CHAN = "2348249"
EXT_ICON = (2732, 48)
BACKFILL = (3700, 226)
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

def run(pid, wait_s=45, chan=CHAN):
    out = {"pid": pid, "wait": wait_s}
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
    time.sleep(wait_s)
    screen.grab(f"editor_{pid}")   # 编辑器状态留证
    click_try = 0
    for i in range(5):
        screen.click(*BACKFILL, yes=True, target=TARGET)
        click_try = i
        time.sleep(5)
        if "图片编辑器" not in title():
            break
        time.sleep(3)
    out["backfill"] = click_try
    time.sleep(1.5)
    screen.click(700, 1050, yes=True, target=TARGET)
    screen.hotkey("ctrl+home"); time.sleep(0.9)
    shot = screen.grab(f"row_{pid}")["shot"]
    im = Image.open(shot).convert("RGB")
    im.crop((420, 1150, 1900, 1800)).save(str(SHOTS / f"crop_row_{pid}.png"))
    out["row_crop"] = str(SHOTS / f"crop_row_{pid}.png")
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    a = sys.argv
    run(a[1], int(a[2]) if len(a) > 2 else 45, a[3] if len(a) > 3 else CHAN)
