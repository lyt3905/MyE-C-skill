import sys, time, json
from PIL import Image
import numpy as np
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen

T = "个人 2"; CHAN = "2348249"; SHOTS = screen.SHOTS
MAIN = (542, 1612)

def title():
    w = screen.find_window(T); return w["title"] if w else ""

def wait_title(need, timeout, poll=0.8):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if need in title(): return round(time.time()-t0,1)
        time.sleep(poll)
    return -1

def badge_cols(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    r,g,b = a[...,0],a[...,1],a[...,2]
    m = (r>195)&(g>160)&(b<110)
    m[:1400,:] = False; m[1800:,:] = False
    m[:, :400] = False; m[:, 1900:] = False
    ys,xs = np.nonzero(m)
    if len(xs) < 60: return []
    xs_sorted = np.sort(xs)
    groups=[]; cur=[xs_sorted[0]]
    for v in xs_sorted[1:]:
        if v - cur[-1] <= 40: cur.append(v)
        else: groups.append(cur); cur=[v]
    groups.append(cur)
    out=[]
    for g in groups:
        if len(g) >= 40:
            gx=np.array(g)
            out.append(int(gx.mean()))
    return out

def run(pid, chan=CHAN):
    out={"pid":pid}
    screen.preguard(T)
    screen.hotkey("ctrl+t"); time.sleep(0.7)
    screen.navurl(f"https://csp.aliexpress.com/ait/cn_pop/item_product/product_publish?productId={pid}&channelId={chan}", yes=True, target=T)
    out["page"]=wait_title("商品发布",25)
    time.sleep(2.5)
    screen.click(2600, 1100, yes=True, target=T)
    screen.hotkey("ctrl+home"); time.sleep(1.0)
    s=screen.grab(f"dr_{pid}")["shot"]
    im=Image.open(s).convert("RGB")
    cols=badge_cols(im)
    out["badge_cols"]=cols
    if not cols:
        out["status"]="NO_COMPOSITE"
    else:
        x=cols[0]
        if x < 700:
            out["status"]="ALREADY_MAIN"
        else:
            screen.drag(x, 1612, MAIN[0], MAIN[1], yes=True, target=T)
            time.sleep(2.5)
            out["status"]="DRAGGED"
    s2=screen.grab(f"dn_{pid}")["shot"]
    Image.open(s2).convert("RGB").crop((420,1150,1900,1800)).resize((1110,488), Image.LANCZOS).save(str(SHOTS/f"crop_dn_{pid}.png"))
    out["crop"]=str(SHOTS/f"crop_dn_{pid}.png")
    print(json.dumps(out, ensure_ascii=False))

if __name__=="__main__":
    run(sys.argv[1])
