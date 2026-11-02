import sys, time, json
from PIL import Image
sys.path.insert(0, r"C:\Users\shana\Documents\GitHub\MyE-C-skill\aliexpress-image-editor\scripts")
import screen
T="个人 2"; SHOTS=screen.SHOTS
def title():
    w=screen.find_window(T); return w["title"] if w else ""
screen.preguard(T)
screen.click(150, 780, yes=True, target=T); time.sleep(1.2)
print("tab:", title())
screen.click(2732, 48, yes=True, target=T)
t0=time.time()
while time.time()-t0 < 15 and "图片编辑器" not in title():
    time.sleep(0.6)
print("editor:", title(), round(time.time()-t0,1))
time.sleep(12)
screen.grab("p3-editor2")
screen.click(3700, 226, yes=True, target=T)
for i in range(6):
    time.sleep(0.7)
    s=screen.grab(f"p3-toast{i}")["shot"]
    im=Image.open(s).convert("RGB")
    im.crop((900, 60, 3000, 460)).save(str(SHOTS/f"crop-toast{i}.png"))
print("after:", title())
