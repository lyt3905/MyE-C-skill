#!/usr/bin/env python
"""Single-product main-image refresh driver (corrected SOP, 2026-10-31).

Why this script exists
----------------------
On 2026-10-30 a 29-product batch was "completed" and then thrown away: after
`回填到商品页` + `确认上传` the new composite only lives in the PAGE MEMORY
(last slot of 更多图片). The following `ctrl+r` discarded it, so every product
kept its previous main image while the log said "done".

This driver NEVER reloads and NEVER clicks 提交. It stops with the tab open so
the seller can press 提交 themselves.

Safety carried by this script (learned 2026-10-31, machine shared with a human)
-----------------------------------------------------------------------------
* Every click / drag / scroll brings Edge back to the foreground first
  (`focus_edge()`), because the seller keeps switching to the DSH GUI and
  SendInput goes to whatever window is foreground.
* `new_tab()` focuses Edge, presses Ctrl+T and **verifies the window title says
  新建标签页**; if it does not, the stage ABORTS instead of navigating - a
  navigation inside a dirty product tab raises Chrome's beforeunload dialog.
* `navurl` is always called with `--no-auto-leave`: screen.py would otherwise
  click 「离开」 for us and silently discard the previous product's edits.
  If the dialog still shows up, press `esc` (cancel) - do not click 离开.
* Subprocess output is decoded as UTF-8 (`encoding="utf-8"`); the default GBK
  decoding mangles 「新建标签页」 into `新建标�页` and breaks every title check.

Stages (run from this scripts folder, physical pixels, 3840x2160@200%)

  python one_product.py open    <productId> [--tag t3]
  python one_product.py backfill            [--tag t3]     # editor + 46s + 回填 + 确认上传 + row shot
  python one_product.py drag    x1 y1 x2 y2 [--tag t3]     # last thumb -> LEFT HALF of slot 1
  python one_product.py customs             [--tag t3]     # scroll, shot, orange score
  python one_product.py customs-ok          [--tag t3]     # 去设置 -> 确认 -> shot

Typical loop for one product (coordinates drift with the scroll position, so
always measure them from the 1:1 crops the previous stage saved):
  python one_product.py open 1005013435506485 --tag q1
  # read shots\\pq1_0page.png (address bar must show productId=...)
  python one_product.py backfill --tag q1
  # read shots\\pq1_4row.png -> note the LAST thumbnail centre by eye
  python one_product.py drag 1585 1676 417 1672 --tag q1
  # read shots\\pq1_5main.png  (main slot must show the new composite)
  python one_product.py customs --tag q1        # orange score > 0 proves the change is live
  python one_product.py customs-ok --tag q1     # grey 已设置 x, orange gone -> STOP

Do NOT run `backfill` twice on the same page (a second 回填 appends a duplicate).
"""
import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCREEN = os.path.join(HERE, "screen.py")
CUA = r"C:\Users\shana\Documents\deepseek-harness\default-workspace\ae-tools\cua.ps1"
SHOTS = os.path.join(os.path.dirname(HERE), "shots")

# --- physical coordinates measured on 3840x2160 @200% (2026-10-31) -----------
EXT_ICON = (2910, 40)           # address-bar right side "AliExpress 图片编辑器"
BACKFILL = (3720, 245)          # 回填到商品页
CONFIRM_UPLOAD = (1956, 1774)   # blue 确认上传 (only when the row has no new image yet)
CUSTOMS_SET = (408, 1182)       # 去设置, valid after wheel 1500 900 6
DRAWER_OK = (3737, 1999)        # drawer bottom-right 确认
SCROLL_AT = (1500, 900)         # wheel target inside the content column
SCROLL_NOTCHES = 6
MAIN_SLOT_X = 417               # LEFT HALF of the 主图 slot (same row as 更多图片)
SUBMIT_BUTTON = (2890, 1999)    # NEVER CLICK

CHANNEL = "2465459"             # PureSun Toys Store
ROW_SCAN = "200,1500,3200,380"  # wider band for thumbnail-box detection
ROW_REGION = "200,1520,3200,300"    # 商品图片 row (主图 + 更多图片)
ROW_READ = "280,1330,1320,470"      # 主图行, readable size
CUSTOMS_READ = "240,1000,1300,300"  # 海关监管属性 block


def run(cmd):
    print("$", " ".join(cmd))
    return subprocess.run(cmd)


def shot(path, rect=None, scale=1.0):
    # the seller keeps stealing the foreground; a crop of another window is useless
    focus_edge()
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", CUA,
           "-Cmd", "shot", "-Out", path, "-Scale", str(scale), "-Mode", "screen"]
    if rect:
        cmd += ["-Rect", rect]
    run(cmd)


def focus_edge():
    """Bring the Edge window back to the foreground.

    The seller keeps the DSH GUI focused while we work, so a click issued
    without this can land on the wrong window.
    """
    p = subprocess.run([sys.executable, SCREEN, "focus", "Microsoft"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    ok = '"foreground": true' in p.stdout
    if not ok:
        print("!! focus_edge failed: %s" % p.stdout.strip()[:120])
    return ok


def click(x, y):
    focus_edge()
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", CUA,
         "-Cmd", "click", "-X", str(x), "-Y", str(y)])


def drag(x1, y1, x2, y2, steps=30):
    focus_edge()
    run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", CUA,
         "-Cmd", "drag", "-X", str(x1), "-Y", str(y1), "-X2", str(x2), "-Y2", str(y2),
         "-Steps", str(steps)])


def sk(*args):
    r = run([sys.executable, SCREEN, *[str(a) for a in args]])
    return r


def sk_text(*args):
    p = subprocess.run([sys.executable, SCREEN, *[str(a) for a in args]],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    print(p.stdout.strip())
    if p.stderr.strip():
        print(p.stderr.strip())
    return p.stdout


def fg_title():
    import json
    p = subprocess.run([sys.executable, SCREEN, "windows"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    try:
        return json.loads(p.stdout)[0].get("title", "")
    except Exception:
        return ""


def out(tag, name):
    os.makedirs(SHOTS, exist_ok=True)
    return os.path.join(SHOTS, "p%s_%s.png" % (tag, name))


def orange_score(png):
    """Count 'warning orange' pixels — the 海关 orange banner is the change proof.

    Calibrated on 2026-10-31 crops of CUSTOMS_READ: warning visible ≈ 138,
    after 确认 (grey 已设置 only) ≈ 5. So: >50 = warning present, <20 = cleared.

    Product photos can be white/light, so pixel segmentation of the thumbnail row
    is unreliable (tried 2026-10-31: white studio shots look exactly like the page
    background, gaps merge) — measure thumbnail positions by eye on a 1:1 crop.
    """
    from PIL import Image
    im = Image.open(png).convert("RGB")
    px = im.load()
    w, h = im.size
    n = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if r > 170 and 70 < g < 160 and b < 100:
                n += 1
    return n


def row_boxes(png, ox, oy, scale=1.0):
    """Locate the thumbnail boxes of the 商品图片 row in a 1:1 crop.

    Column heuristic: a thumbnail column contains a lot of "ink" (any channel
    < 232) because the photo inside is not page-white; the gutters between
    thumbnails are pure white.  Returns a list of dicts with PHYSICAL centres,
    left-to-right.  White-on-white composites still pass because the brand strip
    and the model label add ink.
    """
    from PIL import Image
    im = Image.open(png).convert("RGB")
    px = im.load()
    w, h = im.size
    y0, y1 = int(h * 0.08), int(h * 0.92)
    band = y1 - y0
    ink = []
    for x in range(w):
        n = 0
        for y in range(y0, y1, 2):
            r, g, b = px[x, y]
            if min(r, g, b) < 232:
                n += 1
        ink.append(n)
    thr = max(6, int(band * 0.12))
    groups = []
    start = None
    for x, n in enumerate(ink):
        if n >= thr:
            if start is None:
                start = x
        else:
            if start is not None:
                groups.append((start, x - 1))
                start = None
    if start is not None:
        groups.append((start, w - 1))

    boxes = []
    for a, b in groups:
        wp = (b - a + 1) / scale
        if wp < 70 or wp > 340:
            continue
        ys = []
        for y in range(y0, y1):
            for x in range(a, b + 1, 3):
                r, g, bb = px[x, y]
                if min(r, g, bb) < 232:
                    ys.append(y)
                    break
        if not ys:
            continue
        cy = (min(ys) + max(ys)) / 2
        boxes.append({"x": ox + ((a + b) / 2), "y": oy + cy, "w": wp,
                      "left": ox + a, "right": ox + b})
    return boxes


def stage_auto(tag, pid):
    """open -> backfill -> locate the new thumbnail -> drag -> customs, in one go."""
    if not stage_open(pid, CHANNEL, tag):
        return False
    stage_backfill(tag)
    p = out(tag, "4scan")
    shot(p, rect=ROW_SCAN, scale=1.0)
    boxes = row_boxes(p, 200, 1500, 1.0)
    print("row boxes (phys x centre, width):",
          [(round(b["x"]), round(b["w"])) for b in boxes])
    if len(boxes) < 2:
        print("!! ABORT drag: could not locate thumbnails; inspect", p)
        return False
    last = boxes[-1]
    print("new composite assumed at phys (%.0f, %.0f)" % (last["x"], last["y"]))
    drag(int(last["x"]), int(last["y"]), MAIN_SLOT_X, int(last["y"]))
    time.sleep(4)
    shot(out(tag, "5main"), rect=ROW_READ, scale=1.0)
    focus_edge()
    sk("wheel", SCROLL_AT[0], SCROLL_AT[1], SCROLL_NOTCHES, "--yes")
    time.sleep(2)
    pc = out(tag, "5customs")
    shot(pc, rect=CUSTOMS_READ, scale=1.0)
    print("orange score before =", orange_score(pc), "(>50 => change is live)")
    click(*CUSTOMS_SET)
    time.sleep(4)
    shot(out(tag, "6drawer"), scale=0.5)
    click(*DRAWER_OK)
    time.sleep(4)
    pd = out(tag, "7customs_done")
    shot(pd, rect=CUSTOMS_READ, scale=1.0)
    print("orange score after =", orange_score(pd), "(<20 => cleared)")
    print("!! verify 5main.png + 7customs_done.png. DO NOT reload, DO NOT submit.")
    return True


def new_tab():
    """Focus Edge, then Ctrl+T and confirm we really got a blank tab.

    Without the focus step the keystroke lands on whatever window is
    foreground (e.g. the DSH GUI) and the following navigation would run in
    the *current* product tab -> beforeunload 'leave site?' dialog -> and
    screen.py navurl would click 'Leave' for you, discarding unsaved edits.
    """
    sk("focus", "Microsoft")
    time.sleep(0.6)
    for attempt in range(3):
        before = fg_title()
        sk_text("hotkey", "ctrl+t")
        time.sleep(1.8)
        after = fg_title()
        if "新建标签页" in after or "New tab" in after:
            print("new tab ok (attempt %d): %s" % (attempt + 1, after))
            return True
        print("!! no blank tab after ctrl+t (attempt %d): before=%s after=%s"
              % (attempt + 1, before, after))
        time.sleep(1.0)
    return False


def stage_open(pid, channel, tag):
    url = ("https://csp.aliexpress.com/ait/cn_pop/item_product/product_publish"
           "?productId=%s&channelId=%s" % (pid, channel))
    if not new_tab():
        print("!! ABORT: no blank tab; refusing to navigate (would risk discarding another product's edits)")
        return False
    # --no-auto-leave: never let navurl answer 'Leave' on a beforeunload dialog
    sk_text("navurl", url, "--yes", "--target", "Microsoft", "--no-auto-leave")
    time.sleep(14)
    shot(out(tag, "0page"), rect="640,34,1150,62", scale=2.0)
    print("!! address-bar crop must show productId=%s" % pid)
    return True


def stage_backfill(tag, wait_editor=46, wait_dialog=20, wait_confirm=8):
    click(*EXT_ICON)
    time.sleep(8)
    shot(out(tag, "1editor"), scale=0.5)
    print("!! foreground title should now be 'AliExpress 图片编辑器'")
    time.sleep(max(0, wait_editor - 8))
    shot(out(tag, "2cutout"), scale=0.5)          # expect 抠图 6/6 成功
    click(*BACKFILL)
    time.sleep(wait_dialog)
    shot(out(tag, "3dialog"), scale=0.5)          # 已添加图片 + file name + 校验通过
    click(*CONFIRM_UPLOAD)
    time.sleep(wait_confirm)
    shot(out(tag, "4row"), rect=ROW_REGION, scale=1.0)
    print("!! new composite must be the LAST thumbnail; drag it onto the LEFT HALF of slot 1")


def stage_drag(tag, x1, y1, x2, y2):
    drag(x1, y1, x2, y2)
    time.sleep(4)
    shot(out(tag, "5main"), rect=ROW_READ, scale=1.0)


def stage_customs(tag):
    focus_edge()
    sk("wheel", SCROLL_AT[0], SCROLL_AT[1], SCROLL_NOTCHES, "--yes")
    time.sleep(2)
    p = out(tag, "5customs")
    shot(p, rect=CUSTOMS_READ, scale=1.0)
    print("orange score =", orange_score(p), "(>0 => the page really changed)")
    print("!! expect orange warning + 去设置, then run: customs-ok")


def stage_customs_ok(tag):
    click(*CUSTOMS_SET)
    time.sleep(4)
    shot(out(tag, "6drawer"), scale=0.5)
    click(*DRAWER_OK)
    time.sleep(4)
    p = out(tag, "7customs_done")
    shot(p, rect=CUSTOMS_READ, scale=1.0)
    print("orange score after =", orange_score(p), "(0 => warning cleared)")
    print("!! expect grey 已设置 x. DO NOT reload, DO NOT submit — leave the tab open.")


def stage_finish(tag, x1, y1):
    """drag the last thumbnail onto the LEFT HALF of slot 1, then set customs.

    x1,y1 = centre of the new composite in the 更多图片 row (measured from the
    crop saved by `backfill`).  The left half of slot 1 is a fixed x on the same
    row, so y2 = y1 keeps the drag perfectly horizontal.
    """
    drag(x1, y1, MAIN_SLOT_X, y1)
    time.sleep(4)
    shot(out(tag, "5main"), rect=ROW_READ, scale=1.0)
    focus_edge()
    sk("wheel", SCROLL_AT[0], SCROLL_AT[1], SCROLL_NOTCHES, "--yes")
    time.sleep(2)
    p = out(tag, "5customs")
    shot(p, rect=CUSTOMS_READ, scale=1.0)
    pre = orange_score(p)
    print("orange score before =", pre, "(>50 => change is live, good)")
    click(*CUSTOMS_SET)
    time.sleep(4)
    shot(out(tag, "6drawer"), scale=0.5)
    click(*DRAWER_OK)
    time.sleep(4)
    p2 = out(tag, "7customs_done")
    shot(p2, rect=CUSTOMS_READ, scale=1.0)
    print("orange score after =", orange_score(p2), "(<20 => warning cleared)")
    print("!! expect grey 已设置 x. DO NOT reload, DO NOT submit — leave the tab open.")


def main():
    ap = argparse.ArgumentParser(description="one product: open/backfill/drag/customs (never submit)")
    ap.add_argument("stage", choices=["open", "backfill", "drag", "customs", "customs-ok", "finish", "auto"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--channel", default="2465459")
    ap.add_argument("--tag", default="x")
    a = ap.parse_args()

    if a.stage == "open":
        stage_open(a.args[0], a.channel, a.tag)
    elif a.stage == "backfill":
        stage_backfill(a.tag)
    elif a.stage == "drag":
        x1, y1, x2, y2 = [int(v) for v in a.args[:4]]
        stage_drag(a.tag, x1, y1, x2, y2)
    elif a.stage == "customs":
        stage_customs(a.tag)
    elif a.stage == "customs-ok":
        stage_customs_ok(a.tag)
    elif a.stage == "auto":
        stage_auto(a.tag, a.args[0])
    elif a.stage == "finish":
        x1, y1 = [int(v) for v in a.args[:2]]
        stage_finish(a.tag, x1, y1)
    print("done:", a.stage)


if __name__ == "__main__":
    main()
