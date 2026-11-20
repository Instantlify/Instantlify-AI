from PIL import Image, ImageDraw, ImageFilter
import math
from pathlib import Path

OUT = Path(__file__).parent
SOURCE = Path(r'C:\Users\Jawad\.codex\generated_images\01a1e91a-601b-72f2-a0d5-9b5a0f412475\exec-8c2c0ee9-115a-440a-ad64-b9b4d7e1fd3c.png')
art = Image.open(SOURCE).convert('RGB').crop((55, 440, 425, 810)).resize((444, 444), Image.Resampling.LANCZOS)
bg = Image.new('RGB', art.size, (10, 18, 22))
frames = []
def smooth(x):
    x = max(0, min(1, x))
    return x*x*(3-2*x)

for n in range(100):
    t = n / 25
    mask = Image.new('L', art.size)
    d = ImageDraw.Draw(mask)
    reveal = smooth(t / 1.05)
    d.rectangle((0, 0, int(444*reveal), 444), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2))
    frame = Image.composite(art, bg, mask)
    pulse = max(0, math.sin((t-1.4)*math.pi/.7)) if 1.4 < t < 2.1 else 0
    if pulse:
        glow = Image.new('RGB', art.size, (185,245,120))
        gm = Image.new('L', art.size)
        gd = ImageDraw.Draw(gm)
        gd.ellipse((336, 163, 396, 223), fill=int(90*pulse))
        gm = gm.filter(ImageFilter.GaussianBlur(12))
        frame = Image.composite(glow, frame, gm)
        star = Image.new('RGBA', art.size)
        sd = ImageDraw.Draw(star)
        cx, cy = 366, 193
        r = 12*pulse
        sd.polygon([(cx,cy-r),(cx+r*.28,cy-r*.28),(cx+r,cy),(cx+r*.28,cy+r*.28),(cx,cy+r),(cx-r*.28,cy+r*.28),(cx-r,cy),(cx-r*.28,cy-r*.28)],fill=(220,255,185,int(255*pulse)))
        frame = Image.alpha_composite(frame.convert('RGBA'), star).convert('RGB')
    if t > 3.5:
        frame = Image.blend(frame,bg,smooth((t-3.5)/.45))
    frames.append(frame)

palette = art.quantize(colors=128)
frames = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
frames[0].save(OUT/'instantlify-icon-animated.gif', save_all=True, append_images=frames[1:], duration=40, loop=0, optimize=True, disposal=2)
art.save(OUT/'instantlify-icon-preview.png')
print(OUT/'instantlify-icon-animated.gif')
