#!/usr/bin/env python3
"""生成安装包所需的图标资源（三平台通用）。

从 core/ui_theme.py 的盾牌图标放大重绘，产出：
    packaging/assets/frameguard.png      1024×1024，macOS iconset 与 Linux 图标源
    packaging/assets/frameguard.ico      Windows 多尺寸（16/32/48/64/128/256）
    packaging/assets/frameguard_512.png  AppImage 用 512×512

用法：
    python packaging/build_assets.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

# 与 core/ui_theme.py 的 favicon 保持同一套形状，按 128 基准等比放大
BASE = 128
CYAN = (34, 211, 238, 255)
DARK = (8, 14, 28, 255)
GREEN = (45, 212, 167, 255)


def _scaled(points, k: float):
    return [(x * k, y * k) for x, y in points]


def render(size: int) -> Image.Image:
    k = size / BASE
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        [6 * k, 6 * k, size - 6 * k, size - 6 * k],
        radius=26 * k,
        fill=DARK,
        outline=CYAN,
        width=max(1, round(4 * k)),
    )
    # 盾牌外形
    draw.polygon(
        _scaled([(64, 24), (100, 38), (100, 70), (64, 106), (28, 70), (28, 38)], k),
        fill=(34, 211, 238, 38),
        outline=CYAN,
    )
    # 对勾
    draw.line(
        _scaled([(46, 66), (60, 80), (86, 50)], k),
        fill=GREEN,
        width=max(2, round(9 * k)),
        joint="curve",
    )
    return img


def main() -> int:
    os.makedirs(ASSETS, exist_ok=True)

    master = render(1024)
    png_path = os.path.join(ASSETS, "frameguard.png")
    master.save(png_path)
    print(f"✅ {png_path}")

    master.resize((512, 512), Image.LANCZOS).save(os.path.join(ASSETS, "frameguard_512.png"))
    print(f"✅ {os.path.join(ASSETS, 'frameguard_512.png')}")

    ico_path = os.path.join(ASSETS, "frameguard.ico")
    master.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"✅ {ico_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
