import sys, time, json
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen

def findtext(text, target="个人 2", keep=False):
    screen.preguard(target)
    screen.set_clipboard(text)
    time.sleep(0.15)
    screen.hotkey("ctrl+f")
    time.sleep(0.35)
    screen.hotkey("ctrl+a")
    screen.hotkey("ctrl+v")
    time.sleep(0.9)
    info = screen.grab("find_" + str(abs(hash(text)) % 100000))
    from PIL import Image
    im = Image.open(info["shot"]).convert("RGB")
    px = im.load()
    W, H = im.size
    pts = []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            r, g, b = px[x, y]
            if r > 235 and 130 < g < 205 and b < 90:   # find highlight orange/yellow
                pts.append((x, y))
    box = None
    if pts:
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        box = [min(xs), min(ys), max(xs), max(ys)]
    if not keep:
        screen.hotkey("esc")
    print(json.dumps({"text": text, "count": len(pts), "box": box, "shot": info["shot"]}, ensure_ascii=False))
    return box

if __name__ == "__main__":
    findtext(sys.argv[1], keep=("--keep" in sys.argv))
