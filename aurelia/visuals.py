"""Visuals: generate PNG scene backgrounds with cinematic look using Pillow, and convert to short video clips via ffmpeg zoom/pan."""
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import numpy as np
from pathlib import Path
import subprocess
import os

BASE_FONT = None
try:
    BASE_FONT = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
except Exception:
    BASE_FONT = ImageFont.load_default()

def starfield_image(w=1920, h=1080, seed=None):
    rng = np.random.RandomState(0 if seed is None else seed)
    stars = rng.rand(h,w)
    img = (stars * 255).astype('uint8')
    im = Image.fromarray(img, mode='L')
    im = im.convert('RGB')
    im = im.filter(ImageFilter.GaussianBlur(radius=1.2))
    return im

def render_scene_png(scene, out_png: Path, aspect='16:9'):
    # Choose resolution by aspect: youtube 1920x1080, tiktok 1080x1920 fallbacks
    w,h = 1920,1080
    text = scene.get('text','')
    # base starfield
    bg = starfield_image(w,h)
    draw = ImageDraw.Draw(bg)
    # gold HUD accent: top-left and bottom-right ribbons
    accent = (212,175,55)
    draw.rectangle([(30,30),(w-30,120)], fill=(10,10,10,200))
    draw.rectangle([(30,h-120),(w-30,h-30)], fill=(10,10,10,200))
    # title text
    title = scene.get('title','Aurelia')
    try:
        draw.text((60,40), title, font=BASE_FONT, fill=accent)
    except Exception:
        draw.text((60,40), title, fill=accent)
    # main text block
    txt = scene.get('text','')
    # wrap text
    lines = wrap_text(txt, BASE_FONT, w-200)
    y = 220
    for line in lines[:12]:
        draw.text((120,y), line, font=BASE_FONT, fill=(230,230,230))
        y += 54
    bg.save(out_png)

def wrap_text(text, font, max_width):
    words = text.split()
    lines = []
    cur = ''
    for w in words:
        t = cur + (' ' if cur else '') + w
        size = font.getsize(t)[0] if hasattr(font, 'getsize') else len(t)*10
        if size <= max_width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def render_png_to_clip(png_path: Path, out_mp4: Path, duration=6.0, profile='both'):
    # Use ffmpeg to create zoom/pan (slow zoom-in) and encode to mp4
    # Command: ffmpeg -loop 1 -i img -vf "scale=1920:1080,zoompan=..." -t duration -r 30 out
    w,h = 1920,1080
    filter_chain = f"scale={w}:{h},zoompan=z='zoom+0.0008':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration*30)}:s={w}x{h}"
    cmd = [
        'ffmpeg','-y','-loop','1','-i',str(png_path),'-vf',filter_chain,'-c:v','libx264','-t',str(duration),'-pix_fmt','yuv420p','-r','30',str(out_mp4)
    ]
    subprocess.run(cmd, check=True)
