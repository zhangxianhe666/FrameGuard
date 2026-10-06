"""全局配置与数据模型。

配置优先级（自低到高）：
    代码内置默认值  <  项目根目录的 .env 文件  <  系统环境变量  <  界面中填写的值

因此 API Key 等敏感信息无需写进代码，放在 .env（已被 .gitignore 忽略）或环境变量中即可。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# 运行形态与目录布局
#
# 有两种运行方式，两者的「资源在哪里」和「数据写到哪里」并不相同：
#
#   1) 源码运行（python app.py / serve.py）
#      资源、输出、缓存、.env 都在项目目录内 —— 与历史行为完全一致。
#
#   2) 安装包运行（PyInstaller 冻结）
#      资源（prompts/rules 等）随安装包分发，位于本次运行的临时解压目录
#      （sys._MEIPASS），只读语义、随时可能被系统清理；
#      因此报告输出、抽帧缓存、崩溃日志必须落到**用户数据目录**，
#      否则用户重启程序后报告就"消失"了。
# --------------------------------------------------------------------------
APP_NAME = "FrameGuard"
APP_VERSION = "1.0.0"
APP_LABEL = "帧防 FrameGuard"

FROZEN = bool(getattr(sys, "frozen", False))


def _user_data_dir() -> str:
    """各平台约定的用户数据目录（安装后读写报告与缓存的地方）。"""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP_NAME)


if FROZEN:
    # sys._MEIPASS 是 PyInstaller 本次运行的资源目录；拿不到时退回到可执行文件所在目录
    RESOURCE_DIR = os.path.abspath(
        getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
    )
    EXE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BASE_DIR = RESOURCE_DIR
    DATA_DIR = _user_data_dir()
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RESOURCE_DIR = BASE_DIR
    EXE_DIR = BASE_DIR
    DATA_DIR = BASE_DIR


def _load_dotenv(path: str) -> None:
    """读取简单的 KEY=VALUE 形式的 .env 文件（不覆盖已存在的环境变量）。

    自行实现以避免引入 python-dotenv 依赖。支持 # 注释、引号包裹、export 前缀。
    """
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


_load_dotenv(os.path.join(BASE_DIR, ".env"))

if FROZEN:
    # 打包运行时的 .env 查找顺序（先命中的优先，因为不会覆盖已存在的变量）：
    #   1. 用户数据目录 —— 升级、移动安装目录都不会丢配置
    #   2. 可执行文件同级目录 —— 便于"绿色版"把 .env 放在程序旁边
    for _candidate in (
        os.path.join(DATA_DIR, ".env"),
        os.path.join(EXE_DIR, ".env"),
        os.path.join(RESOURCE_DIR, ".env"),
    ):
        _load_dotenv(_candidate)


def _env_path(name: str, default: str) -> str:
    """允许用环境变量把输出/缓存目录重定向到项目外（便于容器化部署）。"""
    value = (os.environ.get(name) or "").strip()
    if not value:
        return default
    return os.path.abspath(os.path.expanduser(value))


PROMPT_DIR = os.path.join(RESOURCE_DIR, "prompts")
RULES_DIR = os.path.join(RESOURCE_DIR, "rules")
OUTPUT_DIR = _env_path("FRAMEGUARD_OUTPUT_DIR", os.path.join(DATA_DIR, "outputs"))
CACHE_DIR = _env_path("FRAMEGUARD_CACHE_DIR", os.path.join(DATA_DIR, "cache"))

for _d in (OUTPUT_DIR, CACHE_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError:
        pass

# --------------------------------------------------------------------------
# 多模态模型默认参数（可在界面中修改）
# --------------------------------------------------------------------------
DEFAULT_BASE_URL = os.environ.get("FRAMEGUARD_BASE_URL", "https://chat.intern-ai.org.cn/api/v1/")
# 不再硬编码密钥：从环境变量 / .env 读取，也可直接在界面里填写
DEFAULT_API_KEY = os.environ.get("FRAMEGUARD_API_KEY", "")
DEFAULT_MODEL = os.environ.get("FRAMEGUARD_MODEL", "InternVL3.5-241B-A28B")

DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TIMEOUT = 120
DEFAULT_WORKERS = 4

# 送入模型前对图像做等比缩放，长边不超过该像素值，以控制 token 消耗
DEFAULT_MAX_IMAGE_SIDE = 1280
DEFAULT_JPEG_QUALITY = 85

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".m4v", ".ts"}


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------
@dataclass
class ModelConfig:
    """多模态模型连接配置。

    proxy 说明：
      - 留空（默认）= 直连，并**显式忽略** HTTP_PROXY / HTTPS_PROXY 等环境变量。
        可避免进程继承到临时/已失效的代理，从而出现 APIConnectionError: Connection error。
      - 填写 = 走指定代理，例如 http://127.0.0.1:7890
    """

    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout: int = DEFAULT_TIMEOUT
    proxy: str = ""

    def masked_key(self) -> str:
        if len(self.api_key) <= 10:
            return "***"
        return f"{self.api_key[:6]}...{self.api_key[-4:]}"


@dataclass
class Frame:
    """一帧待分析图像。"""

    path: str
    timestamp: datetime
    source: str = ""          # 摄像机名 / 目录名 / 文件名
    index: int = 0            # 采集序号（1 起）
    note: str = ""

    def time_str(self, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
        return self.timestamp.strftime(fmt)


@dataclass
class FrameResult:
    """单帧分析结果。"""

    frame: Frame
    ok: bool = False
    parsed: Dict[str, Any] = field(default_factory=dict)   # 模型返回的结构化结果
    raw: str = ""                                          # 模型原始输出
    error: str = ""
    latency: float = 0.0
    usage: Dict[str, Any] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)    # 命中的违规字段名

    @property
    def is_violation(self) -> bool:
        return bool(self.violations)

    def summary(self) -> str:
        """判定依据总述 / 原始输出摘要。"""
        if self.parsed:
            for key in ("判定依据总述", "依据总述", "summary"):
                value = self.parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return (self.raw or self.error or "").strip()


@dataclass
class AnalysisReport:
    """一次分析任务的汇总结果。"""

    started_at: datetime
    finished_at: Optional[datetime] = None
    frames: List[Frame] = field(default_factory=list)
    results: List[FrameResult] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)
    violation_map: Dict[str, List[str]] = field(default_factory=dict)
    source_label: str = ""
    model_label: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.frames)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    @property
    def violation_frames(self) -> List[FrameResult]:
        return [r for r in self.results if r.ok and r.is_violation]

    @property
    def violation_count(self) -> int:
        return len(self.violation_frames)

    @property
    def violation_rate(self) -> float:
        base = self.succeeded
        return (self.violation_count / base * 100) if base else 0.0

    def duration_str(self) -> str:
        end = self.finished_at or datetime.now()
        seconds = (end - self.started_at).total_seconds()
        return f"{seconds:.1f} 秒"

    def field_stats(self) -> Dict[str, Dict[str, Any]]:
        """按字段统计违规次数。"""
        stats: Dict[str, Dict[str, Any]] = {}
        for name in self.fields:
            hits = [r for r in self.results if r.ok and name in r.violations]
            valid = [r for r in self.results if r.ok]
            counts: Dict[str, int] = {}
            for r in valid:
                value = str(r.parsed.get(name, "")).strip() or "未判定"
                counts[value] = counts.get(value, 0) + 1
            stats[name] = {
                "violations": len(hits),
                "checked": len(valid),
                "rate": (len(hits) / len(valid) * 100) if valid else 0.0,
                "value_counts": counts,
                "violation_values": self.violation_map.get(name, []),
            }
        return stats
