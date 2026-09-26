"""生成合成的演示图像，用于在无真实监控视频时验证整条分析链路是否连通。

每次调用都会新建一个带时间戳的子目录，**不会触碰目录中已有的任何文件**，
因此不会与用户自己放进来的测试图片混在一起。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

from PIL import Image, ImageDraw

from .config import CACHE_DIR


def _person(
    draw: ImageDraw.ImageDraw,
    x: int,
    base_y: int,
    scale: float,
    helmet: bool = True,
    vest: bool = True,
    phone: bool = False,
) -> None:
    """在画面上绘制一个简化的站立人形。"""
    s = scale
    skin = (222, 184, 148)
    cloth = (66, 86, 130)
    # 腿
    draw.rectangle([x - 9 * s, base_y - 46 * s, x - 2 * s, base_y], fill=(48, 52, 64))
    draw.rectangle([x + 2 * s, base_y - 46 * s, x + 9 * s, base_y], fill=(48, 52, 64))
    # 躯干
    draw.rectangle([x - 15 * s, base_y - 90 * s, x + 15 * s, base_y - 44 * s], fill=cloth)
    # 反光背心：高饱和黄底 + 亮条，便于模型识别
    if vest:
        draw.rectangle([x - 17 * s, base_y - 88 * s, x + 17 * s, base_y - 46 * s], fill=(240, 208, 48))
        draw.rectangle([x - 17 * s, base_y - 74 * s, x + 17 * s, base_y - 70 * s], fill=(228, 232, 236))
        draw.rectangle([x - 17 * s, base_y - 60 * s, x + 17 * s, base_y - 56 * s], fill=(228, 232, 236))
        draw.rectangle([x - 4 * s, base_y - 88 * s, x + 4 * s, base_y - 46 * s], fill=cloth)
    # 手臂
    draw.rectangle([x - 22 * s, base_y - 88 * s, x - 15 * s, base_y - 52 * s], fill=cloth)
    if phone:
        draw.rectangle([x - 20 * s, base_y - 62 * s, x - 15 * s, base_y - 46 * s], fill=cloth)
        draw.rectangle([x - 13 * s, base_y - 68 * s, x + 3 * s, base_y - 50 * s], fill=(28, 30, 36))
    else:
        draw.rectangle([x + 15 * s, base_y - 88 * s, x + 22 * s, base_y - 52 * s], fill=cloth)
    # 头
    draw.ellipse([x - 11 * s, base_y - 112 * s, x + 11 * s, base_y - 90 * s], fill=skin)
    # 安全帽
    if helmet:
        draw.pieslice([x - 14 * s, base_y - 123 * s, x + 14 * s, base_y - 94 * s],
                      start=180, end=360, fill=(242, 178, 42))
        draw.rectangle([x - 16 * s, base_y - 100 * s, x + 16 * s, base_y - 96 * s], fill=(242, 178, 42))
    else:
        # 露出的头发，强化「未戴安全帽」的视觉特征
        draw.pieslice([x - 11 * s, base_y - 116 * s, x + 11 * s, base_y - 96 * s],
                      start=180, end=360, fill=(48, 38, 34))


def _scene(scenario: Dict[str, Any], w: int = 960, h: int = 540) -> Image.Image:
    img = Image.new("RGB", (w, h), (206, 210, 214))
    draw = ImageDraw.Draw(img)
    # 地面与墙裙
    draw.rectangle([0, int(h * 0.62), w, h], fill=(158, 160, 162))
    draw.rectangle([0, int(h * 0.60), w, int(h * 0.63)], fill=(120, 122, 126))
    # 背景设备 / 工作台
    draw.rectangle([int(w * 0.60), int(h * 0.40), int(w * 0.92), int(h * 0.62)], fill=(96, 108, 126))
    draw.rectangle([int(w * 0.06), int(h * 0.34), int(w * 0.24), int(h * 0.62)], fill=(88, 96, 110))
    # 两名作业人员
    _person(draw, int(w * 0.38), int(h * 0.80), 1.5, **scenario["p1"])
    _person(draw, int(w * 0.52), int(h * 0.78), 1.35, **scenario["p2"])
    # 工具：乱放 vs 收入工具箱
    if scenario.get("stray_tool"):
        draw.line([int(w * 0.74), int(h * 0.83), int(w * 0.81), int(h * 0.78)], fill=(52, 54, 60), width=5)
        draw.line([int(w * 0.76), int(h * 0.85), int(w * 0.83), int(h * 0.80)], fill=(176, 178, 182), width=4)
    else:
        draw.rectangle([int(w * 0.64), int(h * 0.72), int(w * 0.75), int(h * 0.86)],
                       fill=(58, 74, 96), outline=(32, 44, 60), width=3)
        draw.rectangle([int(w * 0.645), int(h * 0.862), int(w * 0.745), int(h * 0.878)],
                       fill=(44, 56, 74))
    draw.text((16, h - 24), "DEMO FRAME (synthetic) - not real camera footage", fill=(84, 88, 94))
    return img


# 场景库：约三分之一为完全合规，避免演示结果永远是 100% 违规
SCENARIOS: List[Dict[str, Any]] = [
    dict(p1=dict(helmet=True, vest=True, phone=False), p2=dict(helmet=True, vest=True), stray_tool=False),
    dict(p1=dict(helmet=False, vest=True, phone=False), p2=dict(helmet=True, vest=True), stray_tool=False),
    dict(p1=dict(helmet=True, vest=True, phone=True), p2=dict(helmet=True, vest=True), stray_tool=False),
    dict(p1=dict(helmet=True, vest=True, phone=False), p2=dict(helmet=True, vest=True), stray_tool=True),
    dict(p1=dict(helmet=True, vest=False, phone=False), p2=dict(helmet=True, vest=True), stray_tool=False),
    dict(p1=dict(helmet=True, vest=True, phone=False), p2=dict(helmet=True, vest=True), stray_tool=False),
    dict(p1=dict(helmet=True, vest=True, phone=False), p2=dict(helmet=True, vest=True), stray_tool=False),
    dict(p1=dict(helmet=False, vest=False, phone=True), p2=dict(helmet=True, vest=True), stray_tool=True),
]


def generate_demo_frames(count: int = 6, out_dir: str = "", clean: bool = True) -> str:
    """生成演示图像，返回新目录路径。

    每次调用都会创建一个独立子目录（默认 `cache/demo_frames/demo_<时间戳>`），
    不会删除或覆盖任何已有文件。
    """
    count = max(1, min(int(count), len(SCENARIOS) * 3))
    if not out_dir:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(CACHE_DIR, "demo_frames", f"demo_{stamp}")
    os.makedirs(out_dir, exist_ok=True)

    base = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=count - 1)
    existing = {
        f for f in os.listdir(out_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp"))
    } if clean else set()

    for i in range(count):
        scenario = SCENARIOS[i % len(SCENARIOS)]
        img = _scene(scenario)
        stamp = (base + timedelta(minutes=i)).strftime("%Y%m%d_%H%M%S")
        name = f"cam01_{stamp}.jpg"
        # 同名文件已被用户占用时自动避让，绝不覆盖
        if name in existing:
            name = f"cam01_{stamp}_demo{i + 1}.jpg"
        img.save(os.path.join(out_dir, name), quality=90)
    return out_dir
