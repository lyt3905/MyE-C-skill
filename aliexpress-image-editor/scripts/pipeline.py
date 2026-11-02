import sys, time, json
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen

TARGET = "个人 2"
CHAN = "2348249"
EXT_ICON = (2732, 48)
BACKFILL = (3700, 226)
WARN = "请重新补全并提交海关监管属性"

def title():
    w = screen.find_window(TARGET)
    return w["title"] if w else ""

def wait_title(need, timeout, poll=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        t = title()
        if need in t:
            return True, round(time.time() - t0, 1)
        time.sleep(poll)
    return False, round(time.time() - t0, 1)

def url_now():
    screen.hotkey("ctrl+l"); time.sleep(0.2)
    screen.hotkey("ctrl+c"); time.sleep(0.25)
    u = screen.get_clipboard() if hasattr(screen, "get_clipboard") else None
    screen.hotkey("esc")
    return u

def run(pid, chan=CHAN):
    out = {"pid": pid}
    screen.preguard(TARGET)
    screen.hotkey("ctrl+t"); time.sleep(0.7)
    url = f"https://csp.aliexpress.com/ait/cn_pop/item_product/product_publish?productId={pid}&channelId={chan}"
    screen.navurl(url, yes=True, target=TARGET)
    ok, dt = wait_title("商品发布", 25)
    out["page_loaded"] = [ok, dt]
    time.sleep(1.2)
    # 点扩展图标
    screen.click(*EXT_ICON, yes=True, target=TARGET)
    ok, dt = wait_title("图片编辑器", 15)
    out["editor_open"] = [ok, dt]
    if not ok:
        out["status"] = "EDITOR_NOT_OPEN"
        print(json.dumps(out, ensure_ascii=False)); return
    time.sleep(26)   # 抠图 + 智能排版
    # 轮询点回填，直到标签页自动切回商品发布
    for i in range(6):
        screen.click(*BACKFILL, yes=True, target=TARGET)
        time.sleep(5)
        if "图片编辑器" not in title():
            out["backfill"] = ["ok", i]
            break
        time.sleep(4)
    else:
        out["backfill"] = ["fail"]
        out["status"] = "BACKFILL_FAIL"
        print(json.dumps(out, ensure_ascii=False)); return
    time.sleep(1.5)
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else CHAN)
