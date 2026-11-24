"""生成程序图标 assets/app.ico（打包 EXE 用）与 assets/app.png（界面/文档用）。

用法：python tools/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

BLUE = (37, 99, 235)
BLUE_DARK = (29, 78, 216)
WHITE = (255, 255, 255)


def draw(size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r = int(size * 0.22)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BLUE)
    # 底部稍深的色带，交代"层叠"意象
    d.rounded_rectangle([0, int(size * 0.70), size - 1, size - 1],
                        radius=r, fill=BLUE_DARK)
    d.rectangle([0, int(size * 0.70), size - 1, int(size * 0.86)], fill=BLUE_DARK)

    # 三层递增的"打印层"
    w = size * 0.46
    bar_h = size * 0.070
    gap = size * 0.046
    y0 = size * 0.385
    for i, k in enumerate((0.62, 0.82, 1.0)):
        bw = w * k
        x0 = (size - w) / 2 + (w - bw) / 2
        d.rounded_rectangle([x0, y0 + i * (bar_h + gap),
                             x0 + bw, y0 + i * (bar_h + gap) + bar_h],
                            radius=bar_h / 2, fill=WHITE)

    # 顶部喷嘴（三角形 + 小方块）
    nz_w = size * 0.20
    top = size * 0.14
    d.rectangle([(size - nz_w) / 2, top, (size + nz_w) / 2, top + size * 0.10],
                fill=WHITE)
    d.polygon([((size - nz_w * 0.78) / 2, top + size * 0.10),
               ((size + nz_w * 0.78) / 2, top + size * 0.10),
               (size / 2, top + size * 0.22)], fill=WHITE)
    return img


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    big = draw(512)
    big.save(ASSETS / "app.png")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    big.save(ASSETS / "app.ico", sizes=sizes)
    print("已生成：", ASSETS / "app.ico", (ASSETS / "app.ico").stat().st_size, "bytes")
    print("已生成：", ASSETS / "app.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
