import sys, time, json
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen

def probe(text, target="个人 2"):
    screen.preguard(target)
    screen.set_clipboard("")
    screen.hotkey("ctrl+f"); time.sleep(0.3)
    screen.hotkey("ctrl+a"); screen.hotkey("delete"); time.sleep(0.5)
    a = screen.grab("probe_a")["shot"]
    screen.set_clipboard(text)
    screen.hotkey("ctrl+v"); time.sleep(1.1)
    b = screen.grab("probe_b")["shot"]
    from PIL import Image
    import numpy as np
    A = np.asarray(Image.open(a).convert("L"), float)
    B = np.asarray(Image.open(b).convert("L"), float)
    d = np.abs(A - B)
    d[0:130, 2700:] = 0          # 排除右上 find 条
    H, W = d.shape
    frac = (d > 25).mean() * 100
    ys, xs = np.where(d > 25)
    box = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None
    screen.hotkey("esc")
    print(json.dumps({"probe": text, "changed_pct": round(frac, 2), "box": box}, ensure_ascii=False))
    return frac, box

if __name__ == "__main__":
    probe(sys.argv[1])
