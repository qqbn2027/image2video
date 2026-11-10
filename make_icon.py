# -*- coding: utf-8 -*-
"""生成应用图标 app.ico（打包时使用）。"""
from PIL import Image, ImageDraw

def make_icon(out="app.ico", size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 圆角渐变背景
    for y in range(size):
        t = y / size
        r = int(38 + (18 - 38) * t)
        g = int(120 + (52 - 120) * t)
        b = int(200 + (110 - 200) * t)
        d.line([(0, y), (size, y)], fill=(r, g, b, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=52, fill=255)
    img.putalpha(mask)
    # 播放三角
    cx, cy = size // 2, size // 2
    tri = [(cx - 52, cy - 74), (cx - 52, cy + 74), (cx + 80, cy)]
    d.polygon(tri, fill=(255, 255, 255, 240))
    # 胶片横线装饰
    for i in range(3):
        y = 40 + i * 18
        d.rounded_rectangle([34, y, 34 + 46, y + 7], radius=4, fill=(255, 255, 255, 90))
    img.save(out, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    return out


if __name__ == "__main__":
    print(make_icon())
