"""图像采集：把「视频流 / 视频文件 / 图片目录」统一转换成带时间戳的帧序列。

- 视频流（RTSP / RTMP / HTTP-FLV / 摄像头）：按固定间隔实时抽帧（默认每 60 秒一帧）。
- 视频文件（mp4 等）：按时间轴跳转抽帧，可覆盖整段历史录像。
- 图片目录：扫描目录下的图片，时间戳优先取自文件名，其次取文件修改时间。
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Callable, Iterator, List, Optional, Tuple

from .config import CACHE_DIR, IMAGE_EXTS, VIDEO_EXTS, Frame

# --------------------------------------------------------------------------
# 文件名时间戳解析
# --------------------------------------------------------------------------
_TS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[ _\-T]?(\d{2})[-_.:]?(\d{2})[-_.:]?(\d{2})"), "%Y%m%d%H%M%S"),
    (re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[ _\-T](\d{2})[-_.:](\d{2})"), "%Y%m%d%H%M"),
    (re.compile(r"(20\d{2})[-_.](\d{2})[-_.](\d{2})"), "%Y%m%d"),
]
_UNIX_RE = re.compile(r"(?<!\d)(1[0-9]{12}|1[0-9]{9})(?!\d)")


def parse_timestamp_from_name(name: str) -> Optional[datetime]:
    """从文件名中尝试解析时间戳，失败返回 None。"""
    stem = os.path.splitext(os.path.basename(name))[0]

    for pattern, fmt in _TS_PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        digits = "".join(match.groups())
        try:
            if fmt == "%Y%m%d":
                return datetime.strptime(digits, fmt)
            return datetime.strptime(digits, fmt)
        except ValueError:
            continue

    unix = _UNIX_RE.search(stem)
    if unix:
        value = int(unix.group(1))
        if value > 10 ** 12:                 # 毫秒
            value //= 1000
        try:
            return datetime.fromtimestamp(value)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _fallback_timestamp(path: str) -> datetime:
    try:
        return datetime.fromtimestamp(os.path.getmtime(path))
    except OSError:
        return datetime.now()


def _session_dir(tag: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(CACHE_DIR, f"frames_{tag}_{stamp}")
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------
# 1) 图片目录
# --------------------------------------------------------------------------
def is_image_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def is_video_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def collect_from_image_dir(
    directory: str,
    recursive: bool = True,
    max_frames: int = 0,
    sample_evenly: bool = True,
) -> Tuple[List[Frame], List[str]]:
    """扫描图片目录，返回 (帧列表, 提示信息)。"""
    notes: List[str] = []
    directory = os.path.expanduser(directory.strip())
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"目录不存在：{directory}")

    files: List[str] = []
    if recursive:
        for root, _dirs, names in os.walk(directory):
            if os.path.basename(root).startswith("."):
                continue
            for name in names:
                if name.startswith("."):
                    continue
                full = os.path.join(root, name)
                if is_image_file(full):
                    files.append(full)
    else:
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            if not name.startswith(".") and os.path.isfile(full) and is_image_file(full):
                files.append(full)

    if not files:
        raise FileNotFoundError(f"目录中未找到图片文件：{directory}")

    files.sort()
    named = sum(1 for f in files if parse_timestamp_from_name(f) is not None)
    if named == 0:
        notes.append("文件名中未识别到时间戳，已改用文件修改时间作为帧时间。")

    if max_frames and len(files) > max_frames:
        if sample_evenly:
            step = len(files) / float(max_frames)
            picked = [files[min(len(files) - 1, int(i * step))] for i in range(max_frames)]
            picked = sorted(set(picked))
        else:
            picked = files[:max_frames]
        notes.append(f"图片共 {len(files)} 张，按上限抽取 {len(picked)} 张参与分析。")
        files = picked

    frames: List[Frame] = []
    for i, path in enumerate(files, 1):
        ts = parse_timestamp_from_name(path) or _fallback_timestamp(path)
        frames.append(
            Frame(
                path=path,
                timestamp=ts,
                source=os.path.basename(directory.rstrip(os.sep)) or directory,
                index=i,
            )
        )
    frames.sort(key=lambda f: f.timestamp)
    for i, frame in enumerate(frames, 1):
        frame.index = i
    return frames, notes


# --------------------------------------------------------------------------
# 2) 视频文件
# --------------------------------------------------------------------------
def collect_from_video_file(
    path: str,
    interval_sec: float = 60.0,
    max_frames: int = 0,
    start_offset: float = 0.0,
    end_offset: Optional[float] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Frame], List[str]]:
    """从视频文件中按时间间隔抽帧。"""
    import cv2

    notes: List[str] = []
    path = os.path.expanduser(path.strip())
    if not os.path.isfile(path):
        raise FileNotFoundError(f"视频文件不存在：{path}")

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频文件：{path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps <= 0:
        fps = 25.0
        notes.append("无法读取视频帧率，按 25 fps 估算。")
    duration = total / fps if total else 0.0
    if duration <= 0:
        notes.append("无法读取视频时长，将顺序解码直到视频结束。")

    base_time = parse_timestamp_from_name(path)
    if base_time is None:
        base_time = _fallback_timestamp(path) - timedelta(seconds=duration)
        notes.append("文件名中未识别到录制时间，已按「文件修改时间 − 视频时长」估算起始时间。")

    out_dir = _session_dir("video")
    end_offset = duration if end_offset is None else min(end_offset, duration)

    frames: List[Frame] = []
    offset = max(0.0, start_offset)
    source_name = os.path.basename(path)
    sequential = duration <= 0

    if sequential:                                  # 未知时长：顺序解码抽帧
        read_frames = 0
        next_target = 0.0
        while True:
            ok, img = cap.read()
            if not ok:
                break
            now = read_frames / fps
            if now >= next_target:
                saved = os.path.join(out_dir, f"frame_{len(frames) + 1:05d}.jpg")
                if cv2.imwrite(saved, img):
                    frames.append(
                        Frame(path=saved, timestamp=base_time + timedelta(seconds=now),
                              source=source_name, index=len(frames) + 1)
                    )
                next_target += interval_sec
                if max_frames and len(frames) >= max_frames:
                    break
            read_frames += 1
    else:
        targets = []
        t = offset
        while t <= end_offset:
            targets.append(t)
            t += interval_sec
        if max_frames and len(targets) > max_frames:
            step = len(targets) / float(max_frames)
            targets = [targets[min(len(targets) - 1, int(i * step))] for i in range(max_frames)]
            notes.append(f"按间隔共 {len(targets) + 0} 个时间点，已按上限抽取 {len(targets)} 帧。")

        for t in targets:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, img = cap.read()
            if not ok:
                continue
            saved = os.path.join(out_dir, f"frame_{len(frames) + 1:05d}.jpg")
            if cv2.imwrite(saved, img):
                frames.append(
                    Frame(path=saved, timestamp=base_time + timedelta(seconds=t),
                          source=source_name, index=len(frames) + 1)
                )
            if on_log:
                on_log(f"已抽取 {len(frames)} 帧（视频位置 {t:.0f}s / 共 {duration:.0f}s）")

    cap.release()
    if not frames:
        raise RuntimeError("未能从视频中抽取到任何帧，请检查文件是否可正常播放。")
    notes.append(f"视频时长约 {duration:.0f} 秒，抽帧间隔 {interval_sec:.0f} 秒，共抽取 {len(frames)} 帧。")
    return frames, notes


# --------------------------------------------------------------------------
# 3) 视频流（实时抽帧）
# --------------------------------------------------------------------------
def iter_stream_frames(
    url: str,
    interval_sec: float = 60.0,
    duration_min: float = 10.0,
    max_frames: int = 0,
    warmup_sec: float = 5.0,
    on_log: Optional[Callable[[str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Iterator[Frame]:
    """连接视频流并按间隔实时抽帧，逐帧 yield。

    真·实时录制：每 interval_sec 保存一帧，持续 duration_min 分钟。
    """
    import cv2
    import time as _time

    url = url.strip()
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        raise RuntimeError(
            f"无法打开视频流：{url}\n"
            "请确认地址可访问（RTSP 示例：rtsp://user:pass@ip:554/stream1；"
            "HTTP-FLV/M3U8 示例：http://ip:port/live/stream.m3u8）。"
        )

    out_dir = _session_dir("stream")
    deadline = _time.monotonic() + max(0.0, duration_min) * 60.0
    last_saved = 0.0
    count = 0
    started = _time.monotonic()
    failures = 0

    if on_log:
        on_log(f"视频流连接成功，开始抽帧（间隔 {interval_sec:.0f} 秒，持续 {duration_min:.0f} 分钟）")

    try:
        while _time.monotonic() < deadline:
            if should_stop and should_stop():
                if on_log:
                    on_log("收到停止指令，结束视频流采集。")
                break
            ok, img = cap.read()
            if not ok:
                failures += 1
                if failures >= 30:
                    if on_log:
                        on_log("连续读取失败，视频流可能已中断，结束采集。")
                    break
                _time.sleep(0.2)
                continue
            failures = 0
            now = _time.monotonic()
            if now - started < warmup_sec:
                continue
            if now - last_saved >= interval_sec or last_saved == 0.0:
                last_saved = now
                count += 1
                saved = os.path.join(out_dir, f"frame_{count:05d}.jpg")
                if cv2.imwrite(saved, img):
                    frame = Frame(
                        path=saved,
                        timestamp=datetime.now(),
                        source=url.split("/")[-1] or "视频流",
                        index=count,
                    )
                    if on_log:
                        on_log(f"已采集第 {count} 帧（{frame.time_str('%H:%M:%S')}）")
                    yield frame
                if max_frames and count >= max_frames:
                    if on_log:
                        on_log(f"已达到帧数上限 {max_frames}，结束采集。")
                    break
            _time.sleep(0.05)
    finally:
        cap.release()
    if on_log:
        on_log(f"视频流采集结束，共采集 {count} 帧。")


def probe_source(path_or_url: str, timeout: float = 15.0) -> Tuple[bool, str]:
    """探测视频源是否可连接，并返回分辨率/帧率等基本信息。"""
    import cv2

    cap = cv2.VideoCapture(path_or_url.strip())
    if not cap.isOpened():
        return False, "无法打开该视频源，请检查地址、账号密码与网络连通性。"
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        ok, _frame = cap.read()
        info = f"连接成功：分辨率 {width}×{height}，帧率 {fps:.2f} fps"
        if total > 0 and fps > 0:
            info += f"，时长约 {total / fps:.0f} 秒"
        if not ok:
            info += "（已连接但暂时读取不到画面，可能是流刚建立）"
        return True, info
    finally:
        cap.release()


def detect_source_kind(value: str) -> str:
    """判断输入是目录、视频文件还是流地址。"""
    value = (value or "").strip()
    if not value:
        return "empty"
    low = value.lower()
    if low.startswith(("rtsp://", "rtmp://", "rtmps://", "http://", "https://", "udp://", "tcp://", "rtp://")):
        return "stream"
    expanded = os.path.expanduser(value)
    if os.path.isdir(expanded):
        return "dir"
    if os.path.isfile(expanded):
        if is_video_file(expanded):
            return "video"
        if is_image_file(expanded):
            return "image"
    return "unknown"
