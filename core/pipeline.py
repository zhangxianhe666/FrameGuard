"""任务编排：采集 → 模型分析 → 生成报告。"""

from __future__ import annotations

import html
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

from .analyzer import VLMAnalyzer
from .config import (
    DEFAULT_MAX_IMAGE_SIDE,
    DEFAULT_WORKERS,
    AnalysisReport,
    Frame,
    FrameResult,
    ModelConfig,
)
from .prompt import build_variable_values, load_default_template, render_template
from .report import group_by_period, results_to_rows, write_reports
from .rules import RuleSet, parse_rules
from .sources import (
    collect_from_image_dir,
    collect_from_video_file,
    detect_source_kind,
    iter_stream_frames,
)


@dataclass
class JobSettings:
    """一次分析任务的全部参数。"""

    source: str = ""
    source_type: str = "自动识别"        # 自动识别 / 视频流 / 图片目录 / 视频文件
    interval_sec: float = 60.0
    duration_min: float = 10.0
    max_frames: int = 0
    recursive: bool = True
    start_offset_min: float = 0.0

    rules_text: str = ""
    template: str = ""
    extra_context: str = ""

    model: ModelConfig = field(default_factory=ModelConfig)
    workers: int = DEFAULT_WORKERS
    max_image_side: int = DEFAULT_MAX_IMAGE_SIDE
    retries: int = 2

    period: str = "hour"
    include_thumbnails: bool = True


class JobRunner:
    """执行分析任务，支持流式进度与中途停止。"""

    def __init__(self, settings: JobSettings) -> None:
        self.settings = settings
        self.stop_event = threading.Event()
        self.report: Optional[AnalysisReport] = None
        self.logs: List[str] = []
        self.output_paths: Dict[str, str] = {}
        self._analyzer: Optional[VLMAnalyzer] = None
        self._collect_notes: List[str] = []

    # ------------------------------------------------------------------
    def request_stop(self) -> None:
        self.stop_event.set()

    def _log(self, message: str) -> str:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self.logs.append(line)
        return line

    # ------------------------------------------------------------------
    def _collect(self) -> Generator[Tuple[str, List[Frame]], None, List[Frame]]:
        """采集帧序列；视频流场景会边采集边 yield 日志。"""
        settings = self.settings
        kind = settings.source_type
        if kind in ("自动识别", "auto", ""):
            kind = detect_source_kind(settings.source)
            mapping = {"stream": "视频流", "dir": "图片目录", "video": "视频文件", "image": "图片目录", "unknown": "未知"}
            kind = mapping.get(kind, "未知")

        notes: List[str] = []
        frames: List[Frame] = []

        if kind == "视频流":
            yield self._log(f"开始连接视频流：{settings.source}"), []
            collected: List[Frame] = []
            for frame in iter_stream_frames(
                settings.source,
                interval_sec=settings.interval_sec,
                duration_min=settings.duration_min,
                max_frames=int(settings.max_frames) if settings.max_frames else 0,
                on_log=None,
                should_stop=self.stop_event.is_set,
            ):
                collected.append(frame)
                yield self._log(
                    f"已采集第 {len(collected)} 帧 · {frame.time_str('%H:%M:%S')}"
                ), collected
            frames = collected
            notes.append(
                f"视频流按每 {settings.interval_sec:.0f} 秒采集一帧，共采集 {len(frames)} 帧。"
            )
            if not frames:
                raise RuntimeError("视频流采集结束但未获取到任何帧，请检查流地址或延长采集时长。")

        elif kind == "图片目录":
            path = settings.source
            if os.path.isfile(path):
                path = os.path.dirname(path)
            yield self._log(f"扫描图片目录：{path}"), []
            frames, notes = collect_from_image_dir(
                path,
                recursive=settings.recursive,
                max_frames=int(settings.max_frames) if settings.max_frames else 0,
            )
            yield self._log(f"共找到 {len(frames)} 张图片待分析"), frames

        elif kind == "视频文件":
            yield self._log(f"读取视频文件：{settings.source}"), []
            frames, notes = collect_from_video_file(
                settings.source,
                interval_sec=settings.interval_sec,
                max_frames=int(settings.max_frames) if settings.max_frames else 0,
                start_offset=settings.start_offset_min * 60.0,
            )
            yield self._log(f"视频抽帧完成，共 {len(frames)} 帧"), frames

        else:
            raise ValueError(
                f"无法识别的数据源：{settings.source}\n"
                "请输入视频流地址（rtsp:// / http://）、视频文件路径或图片目录路径。"
            )

        self._collect_notes = notes
        return frames

    # ------------------------------------------------------------------
    def run(self) -> Generator[Tuple[str, AnalysisReport], None, None]:
        """执行任务，逐帧 yield (日志, 当前报告快照)。"""
        settings = self.settings
        started = datetime.now()
        report = AnalysisReport(
            started_at=started,
            source_label=_short(settings.source),
            model_label=settings.model.model,
        )
        self.report = report

        # 1) 解析规则
        ruleset: RuleSet = parse_rules(settings.rules_text)
        report.fields = ruleset.field_names
        report.violation_map = ruleset.violation_map
        report.notes.extend(ruleset.warnings)
        if ruleset.fields:
            yield self._log(
                f"规则解析完成，共 {len(ruleset.fields)} 个判定维度："
                + "、".join(ruleset.field_names)
            ), report
        else:
            yield self._log("警告：未能从规则中解析出判定字段，将只输出模型的原始判定。"), report

        # 2) 模板校验
        template = settings.template or load_default_template()
        probe = render_template(
            template,
            build_variable_values(
                rules_text=ruleset.as_text(),
                frame_time="2026-01-01 00:00:00",
                camera_name="校验",
                extra_context=settings.extra_context,
            ),
        )
        if probe.missing:
            report.notes.append(
                "提示词模板中存在未提供取值的变量：" + "、".join(probe.missing) + "（已原样保留）。"
            )

        # 3) 采集
        frames: List[Frame] = []
        collector = self._collect()
        while True:
            try:
                log, snapshot = next(collector)
            except StopIteration:
                break
            if log:
                yield log, report
            if snapshot:
                frames = snapshot
        report.notes.extend(self._collect_notes)
        report.frames = frames

        if not frames:
            raise RuntimeError("未采集到任何待分析图像。")

        if self.stop_event.is_set():
            yield self._log("任务已被用户停止。"), report
            report.finished_at = datetime.now()
            return

        # 4) 模型分析
        self._analyzer = VLMAnalyzer(
            settings.model, workers=settings.workers, max_image_side=settings.max_image_side
        )
        yield self._log(
            f"开始分析：共 {len(frames)} 帧，并发 {settings.workers}，模型 {settings.model.model}"
        ), report

        throttle = max(1, len(frames) // 25)

        # 批量并发分析，边跑边推送进度
        results: List[FrameResult] = []
        pending: List[Frame] = list(frames)
        analyzer = self._analyzer

        from concurrent.futures import ThreadPoolExecutor, as_completed

        done_count = 0
        collected: List[Optional[FrameResult]] = [None] * len(pending)
        order: Dict[str, int] = {frame.path: idx for idx, frame in enumerate(pending)}

        with ThreadPoolExecutor(max_workers=settings.workers) as pool:
            futures = {
                pool.submit(
                    analyzer.analyze_frame, frame, ruleset, template,
                    settings.extra_context, None, settings.retries,
                ): frame
                for frame in pending
            }
            for future in as_completed(futures):
                frame = futures[future]
                try:
                    result = future.result()
                except Exception as exc:                       # noqa: BLE001
                    result = FrameResult(frame=frame, error=f"{type(exc).__name__}: {exc}")
                collected[order[frame.path]] = result
                done_count += 1
                if self.stop_event.is_set():
                    for f in futures:
                        f.cancel()
                    break
                if done_count % throttle == 0 or done_count == len(pending):
                    report.results = [r for r in collected if r is not None]
                    flag = "⚠ 违规" if (result.ok and result.is_violation) else ("✓ 正常" if result.ok else "✗ 失败")
                    yield self._log(
                        f"[{done_count}/{len(pending)}] {result.frame.time_str('%H:%M:%S')} {flag}"
                    ), report

        report.results = [r for r in collected if r is not None]
        report.finished_at = datetime.now()

        yield self._log(
            f"分析完成：成功 {report.succeeded} 帧，失败 {report.failed} 帧，"
            f"发现违规 {report.violation_count} 帧（违规率 {report.violation_rate:.1f}%）"
        ), report

        # 5) 输出报告
        if report.results:
            try:
                paths = write_reports(
                    report,
                    mode=settings.period,
                    include_thumbnails=settings.include_thumbnails,
                )
                self.output_paths = paths
                yield self._log(f"报告已生成：{paths['dir']}"), report
            except Exception as exc:                            # noqa: BLE001
                self.output_paths = {}
                yield self._log(f"报告生成失败：{type(exc).__name__}: {exc}"), report
        else:
            self.output_paths = {}


def _short(value: str, limit: int = 60) -> str:
    value = (value or "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


# --------------------------------------------------------------------------
# 预览数据
# --------------------------------------------------------------------------
def _kpi_card(label: str, value: str, accent: str, sub: str = "") -> str:
    return f"""
    <div style="flex:1;min-width:118px;position:relative;overflow:hidden;
                background:linear-gradient(150deg,rgba(15,25,48,.92),rgba(10,17,32,.78));
                border:1px solid rgba(150,180,230,.16);border-radius:14px;padding:12px 14px;
                box-shadow:0 12px 30px -20px rgba(0,0,0,.95)">
      <div style="position:absolute;left:0;top:0;bottom:0;width:3px;background:{accent};
                  box-shadow:0 0 14px {accent}"></div>
      <div style="color:#8298b8;font-size:11.5px;letter-spacing:.05em">{label}</div>
      <div style="font-size:24px;font-weight:800;color:{accent};line-height:1.25;
                  font-variant-numeric:tabular-nums">{value}</div>
      {f'<div style="color:#63799c;font-size:11px">{sub}</div>' if sub else ''}
    </div>
    """


def _risk_badge(rate: float, failed: int, succeeded: int) -> str:
    total = failed + succeeded
    fail_ratio = (failed / total * 100) if total else 0.0
    if rate >= 30 or fail_ratio >= 30:
        text, color = "高风险", "#ff4d6d"
    elif rate >= 10 or fail_ratio >= 10:
        text, color = "中风险", "#ffb020"
    elif rate > 0 or failed:
        text, color = "低风险", "#ffb020"
    else:
        text, color = "未见异常", "#2dd4a7"
    return (
        f'<span style="display:inline-block;padding:4px 13px;border-radius:999px;font-weight:800;'
        f'font-size:13px;color:{color};background:{color}22;border:1px solid {color}66;'
        f'box-shadow:0 0 18px -4px {color}99">{text}</span>'
    )


def preview_overview_html(report: AnalysisReport) -> str:
    """生成结果概览 HTML（KPI + 风险等级 + 各维度违规分布）。"""
    if report is None:
        return ""

    # ---- 各维度违规分布 ----
    stats = report.field_stats()
    dim_rows = []
    for name, stat in stats.items():
        rate = stat["rate"]
        color = "#ff4d6d" if rate >= 30 else ("#ffb020" if rate > 0 else "#2dd4a7")
        dim_rows.append(
            f"<div style='margin-bottom:9px'>"
            f"<div style='display:flex;justify-content:space-between;gap:12px;margin-bottom:4px'>"
            f"<span style='color:#cfe0f7;font-size:12.5px'>{html.escape(name)}</span>"
            f"<span style='color:{color};font-size:12.5px;font-weight:700;white-space:nowrap'>"
            f"{stat['violations']} / {stat['checked']} 帧 · {rate:.0f}%</span>"
            f"</div>"
            f"<div style='height:8px;border-radius:5px;background:rgba(255,255,255,.07);overflow:hidden'>"
            f"<div style='height:100%;width:{min(100.0, rate):.1f}%;border-radius:5px;"
            f"background:linear-gradient(90deg,{color},{color}99);box-shadow:0 0 12px {color}'>"
            f"</div></div></div>"
        )
    dim_block = "".join(dim_rows) or (
        "<div style='color:#63799c;font-size:12.5px'>未解析到判定维度</div>"
    )

    cards = (
        _kpi_card("图像总数", str(report.total), "#22d3ee", "帧")
        + _kpi_card("成功分析", str(report.succeeded), "#2dd4a7", f"失败 {report.failed}")
        + _kpi_card("违规帧数", str(report.violation_count), "#ff4d6d", "命中违规规则")
        + _kpi_card("违规率", f"{report.violation_rate:.1f}%", "#ffb020", "占已分析帧")
        + _kpi_card("已用时长", f"{report.duration_str().split()[0]}", "#a855f7", "秒")
    )

    return f"""
    <div style="font-family:'Inter',-apple-system,'PingFang SC',sans-serif;font-size:13px">
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">{cards}</div>
      <div style="display:flex;align-items:center;gap:10px;margin:0 0 16px">
        <span style="color:#8298b8;font-size:12.5px">综合风险等级</span>{_risk_badge(report.violation_rate, report.failed, report.succeeded)}
      </div>
      <div style="background:rgba(8,14,28,.55);border:1px solid rgba(150,180,230,.14);
                  border-radius:14px;padding:14px 16px">
        <div style="color:#a9c0e0;font-size:12.5px;font-weight:600;margin-bottom:11px">
          各识别维度违规分布
        </div>
        {dim_block}
      </div>
    </div>
    """


def detail_dataframe(report: AnalysisReport, period: str = "hour") -> List[List[Any]]:
    """供界面表格展示的明细行。"""
    if report is None:
        return []
    rows = results_to_rows(report, period)
    out: List[List[Any]] = []
    for row in rows:
        out.append([
            row["时间段"], row["时间"], row["序号"], row["是否违规"], row["违规项"],
            row["判定依据总述"][:160], row["分析状态"],
        ])
    return out


DETAIL_HEADERS = ["时间段", "时间", "序号", "是否违规", "违规项", "判定依据总述", "分析状态"]
