"""视觉安全 · 监控合规分析工具（Gradio 界面）。

用法：
    python app.py
"""

from __future__ import annotations

import html
import os
import signal
import socket
import subprocess
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.analyzer import VLMAnalyzer, list_models                     # noqa: E402
from core.config import (                                              # noqa: E402
    CACHE_DIR,
    DEFAULT_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_IMAGE_SIDE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    DEFAULT_WORKERS,
    FROZEN,
    OUTPUT_DIR,
    RULES_DIR,
    AnalysisReport,
    ModelConfig,
)
from core.demo import generate_demo_frames                             # noqa: E402
from core.pipeline import (                                            # noqa: E402
    DETAIL_HEADERS,
    JobRunner,
    JobSettings,
    detail_dataframe,
    preview_overview_html,
)
from core.prompt import (                                              # noqa: E402
    VARIABLES,
    list_template_variables,
    load_default_template,
)
from core.report import PERIOD_CHOICES, build_html_report, group_by_period  # noqa: E402
from core.rules import parse_rules                                     # noqa: E402
from core.sources import detect_source_kind, is_image_file, is_video_file, probe_source  # noqa: E402
from core import ui_theme                                              # noqa: E402

RULES_FILE = os.path.join(RULES_DIR, "default_rules.md")
PERIOD_LABELS = [label for label, _ in PERIOD_CHOICES]
PERIOD_VALUE_BY_LABEL = {label: value for label, value in PERIOD_CHOICES}
PERIOD_LABEL_BY_VALUE = {value: label for label, value in PERIOD_CHOICES}

CURRENT: Dict[str, Optional[JobRunner]] = {"runner": None}


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------
def _load_default_rules() -> str:
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as fh:
            return fh.read()
    return ""


def _rules_report(rules_text: str) -> str:
    ruleset = parse_rules(rules_text)
    if not ruleset.fields:
        lines = ["### ⚠️ 规则解析结果", "", "未解析出任何判定字段。"]
        lines += [f"- {w}" for w in ruleset.warnings]
        lines += [
            "",
            "**推荐书写格式：**",
            "```markdown",
            "### 1. 是否所有人员都佩戴安全帽",
            "- 合法取值：是 / 否",
            "- 违规取值：否",
            "- 判定标准：……（画面中无人时判定为「是」）",
            "```",
        ]
        return "\n".join(lines)

    lines = [f"### ✅ 已解析出 {len(ruleset.fields)} 个判定维度", ""]
    lines.append("| # | 字段名 | 合法取值 | 违规取值 | 来源 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for f in ruleset.fields:
        allowed = " / ".join(f.allowed_values) or "未限定"
        violation = " / ".join(f.violation_values) or "—"
        origin = "自动推断" if f.inferred else ("规则指定" if f.violation_values else "未配置")
        lines.append(f"| {f.index} | {f.name} | {allowed} | {violation} | {origin} |")
    for w in ruleset.warnings:
        lines.append("")
        lines.append(f"> ⚠️ {w}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 按钮回调
# --------------------------------------------------------------------------
def on_load_rules() -> str:
    text = _load_default_rules()
    return text or "未找到默认规则文件（rules/default_rules.md）。"


def on_check_rules(rules_text: str) -> str:
    return _rules_report(rules_text)


def on_test_source(source: str) -> str:
    source = (source or "").strip()
    if not source:
        return "请先填写视频流地址、视频文件路径或图片目录路径。"
    kind = detect_source_kind(source)
    if kind == "dir":
        from core.sources import collect_from_image_dir

        try:
            frames, notes = collect_from_image_dir(source, recursive=True, max_frames=0)
            msg = [f"✅ 图片目录可用，共 {len(frames)} 张图片。"]
            for f in frames[:3]:
                msg.append(f"- 示例：{os.path.basename(f.path)} → {f.time_str()}")
            if len(frames) > 3:
                msg.append(f"- …（共 {len(frames)} 张）")
            msg += [f"- {n}" for n in notes]
            return "\n".join(msg)
        except Exception as exc:                            # noqa: BLE001
            return f"❌ {type(exc).__name__}: {exc}"
    if kind == "video":
        ok, info = probe_source(source)
        return ("✅ " if ok else "❌ ") + info
    if kind == "stream":
        ok, info = probe_source(source)
        return ("✅ " if ok else "❌ ") + info
    if kind == "image":
        ok = is_image_file(source)
        return ("✅ 单张图片可用：" if ok else "❌ 无法识别该文件：") + source
    if os.path.exists(os.path.expanduser(source)):
        return f"✅ 路径存在，但类型未识别：{source}"
    return (
        "❌ 无法识别的数据源。\n"
        "- 视频流示例：`rtsp://admin:密码@192.168.1.64:554/Streaming/Channels/101`\n"
        "- 视频文件示例：Windows `D:\\\\videos\\\\2026-09-22.mp4` ／ macOS Linux `/home/user/videos/2026-09-22.mp4`\n"
        "- 图片目录示例：Windows `D:\\\\监控截图` ／ macOS Linux `/home/user/监控截图`"
    )


def on_test_model(base_url: str, api_key: str, model: str, proxy: str) -> str:
    conf = ModelConfig(
        base_url=(base_url or "").strip() or DEFAULT_BASE_URL,
        api_key=(api_key or "").strip() or DEFAULT_API_KEY,
        model=(model or "").strip() or DEFAULT_MODEL,
        timeout=DEFAULT_TIMEOUT,
        proxy=(proxy or "").strip(),
    )
    ok, message = VLMAnalyzer(conf).test_connection()
    return ("✅ " if ok else "❌ ") + message


def on_list_models(base_url: str, api_key: str, proxy: str) -> Tuple[str, Any]:
    conf = ModelConfig(
        base_url=(base_url or "").strip() or DEFAULT_BASE_URL,
        api_key=(api_key or "").strip() or DEFAULT_API_KEY,
        timeout=DEFAULT_TIMEOUT,
        proxy=(proxy or "").strip(),
    )
    ok, models, error = list_models(conf)
    if not ok:
        return f"❌ 无法获取模型列表：{error}", gr.update()
    return f"✅ 接口共返回 {len(models)} 个模型：\n" + "\n".join(f"- {m}" for m in models[:60]), gr.update(choices=models)


def on_selfcheck(base_url: str, api_key: str, model: str, proxy: str) -> str:
    """一键网络环境自检：列出会被继承的代理变量，并用真实请求验证连通性。"""
    lines = ["#### 🔍 网络环境自检", ""]

    proxy_vars = {
        k: v for k, v in os.environ.items()
        if k.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
    }
    if proxy_vars:
        lines.append("**检测到本机代理环境变量**（本工具默认**忽略**这些变量，走直连）：")
        lines.append("")
        for k, v in sorted(proxy_vars.items()):
            lines.append(f"- `{k}` = `{v}`")
        lines.append("")
        lines.append(
            "> 若这台机器访问外网**必须**经过代理，请在下方「网络代理」中显式填写地址"
            "（如 `http://127.0.0.1:7890`）；否则保持留空即可。"
        )
    else:
        lines.append("本机未设置代理环境变量，使用直连模式。")
    lines.append("")

    conf = ModelConfig(
        base_url=(base_url or "").strip() or DEFAULT_BASE_URL,
        api_key=(api_key or "").strip() or DEFAULT_API_KEY,
        model=(model or "").strip() or DEFAULT_MODEL,
        timeout=DEFAULT_TIMEOUT,
        proxy=(proxy or "").strip(),
    )
    lines.append(f"**连接方式**：{'代理 ' + conf.proxy if conf.proxy else '直连（忽略环境变量代理）'}")
    lines.append(f"**目标地址**：`{conf.base_url}`")
    lines.append("")
    ok, message = VLMAnalyzer(conf).test_connection()
    lines.append(("✅ " if ok else "❌ ") + f"**连通性测试：** {message}")
    if not ok:
        lines.append("")
        lines.append("可在终端进一步定位：")
        lines.append("```bash")
        lines.append(f"curl -I {conf.base_url}")
        lines.append("# 若 curl 能通、但这里失败 → 多为代理或证书问题")
        lines.append("```")
    return "\n".join(lines)


def on_gen_demo(count: float) -> Tuple[str, str]:
    try:
        path = generate_demo_frames(int(count))
    except Exception as exc:                                # noqa: BLE001
        return "", f"❌ 演示图片生成失败：{type(exc).__name__}: {exc}"
    return path, f"✅ 已生成 {int(count)} 张演示图片：`{path}`\n（合成图形，仅用于验证整条链路是否连通；真实分析请使用实际监控画面。）"


def on_stop() -> str:
    runner = CURRENT.get("runner")
    if runner is None:
        return "当前没有正在运行的任务。"
    runner.request_stop()
    return "已发送停止指令，正在收尾……"


def on_template_vars(template: str) -> str:
    names = list_template_variables(template)
    if not names:
        return "模板中未发现 `{{变量}}` 占位符。"
    registry = {v.name: v for v in VARIABLES}
    lines = ["#### 模板变量", "", "| 变量 | 来源 | 说明 |", "| --- | --- | --- |"]
    for name in names:
        var = registry.get(name)
        if var:
            origin = "程序自动填充" if var.auto else "界面 / 用户提供"
            lines.append(f"| `{{{{{name}}}}}` | {origin} | {var.description} |")
        else:
            lines.append(f"| `{{{{{name}}}}}` | 未注册 | 未在变量表中定义，将原样保留 |")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 结果打包
# --------------------------------------------------------------------------
def _pack(report: Optional[AnalysisReport], log_lines: List[str], runner: JobRunner) -> Tuple:
    settings = runner.settings
    paths = runner.output_paths or {}

    status = "待开始"
    overview = ui_theme.EMPTY_STATE_HTML
    period_rows: List[List[Any]] = []
    detail_rows: List[List[Any]] = []
    gallery: List[Tuple[str, str]] = []

    if report is not None and not report.results:
        overview = ui_theme.RUNNING_STATE_HTML
    elif report is not None:
        overview = preview_overview_html(report)

    if report is not None:
        if report.total:
            status = (
                f"**进度**：已分析 {report.succeeded}/{report.total} 帧 · "
                f"违规 **{report.violation_count}** 帧（{report.violation_rate:.1f}%） · "
                f"失败 {report.failed} 帧"
            )
        else:
            status = "正在采集图像……"
        for group in group_by_period(report.results, settings.period):
            period_rows.append([
                group["label"],
                len(group["results"]),
                group["checked"],
                group["violation_count"],
                f"{group['violation_rate']:.1f}%",
                group["top_violation"],
            ])
        detail_rows = detail_dataframe(report, settings.period)
        for r in report.results:
            if r.ok and r.is_violation:
                caption = f"{r.frame.time_str('%H:%M:%S')} · {'、'.join(r.violations)}"
                gallery.append((r.frame.path, caption))

    files = [paths[key] for key in ("html", "markdown", "csv", "json") if key in paths]

    preview = ""
    if report is not None and paths.get("html"):
        report_html = build_html_report(
            report, mode=settings.period, include_thumbnails=False, max_detail_rows=40
        )
        preview = (
            '<iframe srcdoc="' + html.escape(report_html, quote=True) + '" '
            'style="width:100%;height:780px;border:1px solid #2b3549;border-radius:10px;background:#fff"></iframe>'
        )
        status += f"\n\n**报告已生成**：`{paths.get('dir', '')}`"

    log_text = "\n".join(log_lines[-500:])
    return status, overview, period_rows, detail_rows, gallery, log_text, files, preview


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def on_start(
    source_type: str,
    source: str,
    interval_sec: float,
    duration_min: float,
    max_frames: float,
    recursive: bool,
    start_offset_min: float,
    rules_text: str,
    template_text: str,
    extra_context: str,
    period_label: str,
    include_thumbs: bool,
    base_url: str,
    api_key: str,
    model: str,
    proxy: str,
    temperature: float,
    max_tokens: float,
    workers: float,
    max_image_side: float,
    retries: float,
):
    empty = (ui_theme.EMPTY_STATE_HTML, "", [], [], [], "", [], "")
    if not ((api_key or "").strip() or DEFAULT_API_KEY.strip()):
        yield (
            "⚠️ 尚未配置 API Key。请在「⑥ 模型配置 → API Key」中填写，"
            "或复制 `.env.example` 为 `.env` 并设置 `FRAMEGUARD_API_KEY`。",
        ) + empty
        return
    if not (source or "").strip():
        yield ("⚠️ 请先填写视频流地址或图片目录路径。",) + empty
        return
    if not (rules_text or "").strip():
        yield ("⚠️ 请先填写识别规则，或点击「加载默认规则」。",) + empty
        return

    settings = JobSettings(
        source=source.strip(),
        source_type=source_type,
        interval_sec=float(interval_sec or 60),
        duration_min=float(duration_min or 10),
        max_frames=int(max_frames or 0),
        recursive=bool(recursive),
        start_offset_min=float(start_offset_min or 0),
        rules_text=rules_text,
        template=(template_text or "").strip() or load_default_template(),
        extra_context=extra_context or "",
        model=ModelConfig(
            base_url=(base_url or "").strip() or DEFAULT_BASE_URL,
            api_key=(api_key or "").strip() or DEFAULT_API_KEY,
            model=(model or "").strip() or DEFAULT_MODEL,
            temperature=float(temperature if temperature is not None else DEFAULT_TEMPERATURE),
            max_tokens=int(max_tokens or DEFAULT_MAX_TOKENS),
            timeout=DEFAULT_TIMEOUT,
            proxy=(proxy or "").strip(),
        ),
        workers=max(1, int(workers or DEFAULT_WORKERS)),
        max_image_side=int(max_image_side or DEFAULT_MAX_IMAGE_SIDE),
        retries=max(0, int(retries or 0)),
        period=PERIOD_VALUE_BY_LABEL.get(period_label, "hour"),
        include_thumbnails=bool(include_thumbs),
    )

    runner = JobRunner(settings)
    CURRENT["runner"] = runner
    log_lines: List[str] = []
    log_lines.append(f"[任务] 数据源类型：{source_type}｜数据源：{source}")
    yield ("🚀 任务已启动……", ui_theme.RUNNING_STATE_HTML, [], [], [], "\n".join(log_lines), [], "")

    try:
        for log, report in runner.run():
            log_lines.append(log)
            yield _pack(report, log_lines, runner)
    except Exception as exc:                                # noqa: BLE001
        detail = traceback.format_exc(limit=3)
        log_lines.append(f"[错误] {type(exc).__name__}: {exc}")
        log_lines.append(detail)
        yield (f"❌ 任务失败：{type(exc).__name__}: {exc}", *empty[1:], "\n".join(log_lines[-500:]), [], "")
    finally:
        CURRENT["runner"] = None

    if runner.report is not None:
        note = "\n\n✅ **任务结束**。"
        if runner.output_paths.get("html"):
            note += "可在「报告文件」中下载完整报告，或在下方直接预览。"
        log_lines.append(f"[任务] 结束，耗时 {runner.report.duration_str()}")
    else:
        note = ""
    packed = _pack(runner.report, log_lines, runner)
    yield (packed[0] + note,) + packed[1:]


# --------------------------------------------------------------------------
# 界面
# --------------------------------------------------------------------------
def build_ui() -> gr.Blocks:
    theme = ui_theme.build_theme()
    demo = gr.Blocks(title="帧防 FrameGuard · 视觉安全智能分析", fill_width=True, theme=theme)

    with demo:
        gr.HTML(ui_theme.HERO_HTML, elem_id="hero")

        with gr.Row():
            # ------------------------------------------------ 左侧配置
            with gr.Column(scale=4, min_width=380, elem_id="config-col"):
                with gr.Accordion("① 数据来源", open=True):
                    source_type = gr.Radio(
                        choices=["自动识别", "视频流", "图片目录", "视频文件"],
                        value="自动识别",
                        label="数据源类型",
                        info="「自动识别」会根据填写内容自动判断是流地址、视频文件还是图片目录。",
                    )
                    source = gr.Textbox(
                        label="数据源",
                        placeholder="rtsp://admin:密码@192.168.1.64:554/Streaming/Channels/101   或   D:\\监控截图（Windows）/ /home/user/监控截图（macOS、Linux）",
                        lines=2,
                    )
                    with gr.Row():
                        test_source_btn = gr.Button("测试数据源连通性", size="sm")
                        demo_btn = gr.Button("生成演示图片", size="sm")
                    demo_count = gr.Slider(2, 18, value=6, step=1, label="演示图片数量")
                    source_msg = gr.Markdown("")

                with gr.Accordion("② 采样参数", open=True):
                    with gr.Row():
                        interval_sec = gr.Number(value=60, label="采样间隔（秒）", precision=0,
                                                 info="默认 60 秒 = 每分钟一帧")
                        duration_min = gr.Number(value=10, label="视频流采集时长（分钟）", precision=0,
                                                 info="仅视频流实时抽帧时生效")
                    with gr.Row():
                        max_frames = gr.Number(value=0, label="最大帧数（0 = 不限制）", precision=0)
                        start_offset_min = gr.Number(value=0, label="视频起始偏移（分钟）", precision=0,
                                                     info="仅视频文件生效")
                    recursive = gr.Checkbox(value=True, label="图片目录递归扫描子目录")

                with gr.Accordion("③ 识别规则（决定判定维度与输出字段）", open=True):
                    rules_text = gr.Textbox(
                        label="识别规则",
                        value=_load_default_rules(),
                        lines=16,
                        max_lines=40,
                        placeholder="### 1. 是否所有人员都佩戴安全帽\n- 合法取值：是 / 否\n- 违规取值：否\n- 判定标准：……",
                    )
                    with gr.Row():
                        load_rules_btn = gr.Button("加载默认规则", size="sm")
                        check_rules_btn = gr.Button("校验规则", size="sm")
                    rules_msg = gr.Markdown("")

                with gr.Accordion("④ 补充说明（作为变量注入提示词）", open=False):
                    extra_context = gr.Textbox(
                        label="补充上下文 {{EXTRA_CONTEXT}}",
                        lines=3,
                        placeholder="例如：该画面为夜间红外模式；该区域为配电房，无关人员不得进入。",
                    )

                with gr.Accordion("⑤ 提示词模板（可自定义，支持 {{变量}} 注入）", open=False):
                    template_text = gr.Textbox(
                        label="提示词模板",
                        value=load_default_template(),
                        lines=14,
                        max_lines=40,
                    )
                    with gr.Row():
                        check_vars_btn = gr.Button("查看模板变量", size="sm")
                    vars_msg = gr.Markdown("")

                with gr.Accordion("⑥ 模型配置", open=False):
                    base_url = gr.Textbox(value=DEFAULT_BASE_URL, label="BaseURL")
                    api_key = gr.Textbox(value=DEFAULT_API_KEY, label="API Key", type="password")
                    model = gr.Dropdown(
                        choices=[DEFAULT_MODEL],
                        value=DEFAULT_MODEL,
                        label="模型名称",
                        allow_custom_value=True,
                    )
                    proxy = gr.Textbox(
                        value="",
                        label="网络代理",
                        placeholder="留空 = 直连（忽略系统代理环境变量）；如需代理填 http://127.0.0.1:7890",
                        info="留空时为直连，并显式忽略 HTTP_PROXY/HTTPS_PROXY 等环境变量，可避免继承到失效代理导致 Connection error。",
                    )
                    with gr.Row():
                        test_model_btn = gr.Button("测试模型连接", size="sm")
                        list_models_btn = gr.Button("查询可用模型", size="sm")
                        selfcheck_btn = gr.Button("网络环境自检", size="sm")
                    with gr.Row():
                        temperature = gr.Slider(0.0, 1.0, value=DEFAULT_TEMPERATURE, step=0.05, label="temperature")
                        workers = gr.Slider(1, 16, value=DEFAULT_WORKERS, step=1, label="并发数")
                    with gr.Row():
                        max_tokens = gr.Number(value=DEFAULT_MAX_TOKENS, label="max_tokens", precision=0)
                        retries = gr.Number(value=2, label="失败重试次数", precision=0)
                    max_image_side = gr.Slider(
                        640, 2048, value=DEFAULT_MAX_IMAGE_SIDE, step=64,
                        label="图像长边上限（px）",
                        info="越小越省 token、越快；越小也可能丢失细节",
                    )
                    model_msg = gr.Markdown("")

                with gr.Accordion("⑦ 报告设置", open=False):
                    period_label = gr.Dropdown(
                        choices=PERIOD_LABELS, value=PERIOD_LABEL_BY_VALUE["hour"], label="时间段分组方式"
                    )
                    include_thumbs = gr.Checkbox(value=True, label="报告中内嵌违规帧缩略图")

                with gr.Row():
                    start_btn = gr.Button("▶️ 开始分析", variant="primary", size="lg", scale=3, elem_id="btn-start")
                    stop_btn = gr.Button("⏹️ 停止", size="lg", scale=1, elem_id="btn-stop")

            # ------------------------------------------------ 右侧结果
            with gr.Column(scale=6, min_width=460, elem_id="result-col"):
                status = gr.Markdown("待开始", elem_id="status-bar")
                with gr.Tabs():
                    with gr.Tab("概览"):
                        overview = gr.HTML(ui_theme.EMPTY_STATE_HTML, elem_id="overview-box")
                        period_table = gr.Dataframe(
                            headers=["时间段", "图像数", "已分析", "违规数", "违规率", "主要违规项"],
                            datatype=["str", "number", "number", "number", "str", "str"],
                            value=[],
                            interactive=False,
                            wrap=True,
                            max_height=320,
                        )
                    with gr.Tab("违规明细"):
                        gallery = gr.Gallery(
                            value=[], columns=3, height=520, object_fit="cover",
                            allow_preview=True, label="违规帧", elem_id="gallery-box",
                        )
                    with gr.Tab("逐帧明细"):
                        detail_table = gr.Dataframe(
                            headers=DETAIL_HEADERS,
                            value=[],
                            interactive=False,
                            wrap=True,
                            max_height=560,
                        )
                    with gr.Tab("报告文件"):
                        files_box = gr.File(label="下载报告（HTML / Markdown / CSV / JSON）",
                                            file_count="multiple", elem_id="files-box")
                        preview = gr.HTML("", elem_id="report-preview")
                    with gr.Tab("运行日志"):
                        log_box = gr.Textbox(value="", lines=26, max_lines=40, show_label=False,
                                             autoscroll=True, interactive=False, buttons=["copy"],
                                             elem_id="log-box")

        outputs = [status, overview, period_table, detail_table, gallery, log_box, files_box, preview]

        # ------------------------------------------------------ 事件绑定
        load_rules_btn.click(on_load_rules, outputs=[rules_text]).then(
            on_check_rules, inputs=[rules_text], outputs=[rules_msg]
        )
        check_rules_btn.click(on_check_rules, inputs=[rules_text], outputs=[rules_msg])
        rules_text.change(on_check_rules, inputs=[rules_text], outputs=[rules_msg])
        check_vars_btn.click(on_template_vars, inputs=[template_text], outputs=[vars_msg])
        test_source_btn.click(on_test_source, inputs=[source], outputs=[source_msg])
        demo_btn.click(on_gen_demo, inputs=[demo_count], outputs=[source, source_msg])
        test_model_btn.click(
            on_test_model, inputs=[base_url, api_key, model, proxy], outputs=[model_msg]
        )
        list_models_btn.click(
            on_list_models, inputs=[base_url, api_key, proxy], outputs=[model_msg, model]
        )
        selfcheck_btn.click(
            on_selfcheck, inputs=[base_url, api_key, model, proxy], outputs=[model_msg]
        )

        start_btn.click(
            on_start,
            inputs=[
                source_type, source, interval_sec, duration_min, max_frames, recursive, start_offset_min,
                rules_text, template_text, extra_context, period_label, include_thumbs,
                base_url, api_key, model, proxy, temperature, max_tokens, workers, max_image_side, retries,
            ],
            outputs=outputs,
        )
        stop_btn.click(on_stop, outputs=[status])

    return demo


def _ensure_utf8_console() -> None:
    """把 stdout / stderr 切成 UTF-8，避免 Windows 上打印中文直接崩溃。

    安装包由 GUI 方式启动（PyInstaller 的 console=False），且 PyInstaller 的
    bootloader 会忽略 PYTHONIOENCODING / PYTHONUTF8，Windows 下 sys.stdout 仍然
    是本地代码页（cp1252）。此时哪怕一句 print("提示：……") 也会抛
    UnicodeEncodeError，表现为「双击没反应 / 一闪而过」。
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:               # GUI 启动没有控制台，print 本就是空操作
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _pick_port(host: str, wanted: int) -> int:
    """端口被占用时向后顺延，避免双击启动直接失败（安装包场景尤其重要）。"""
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    for candidate in range(wanted, wanted + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((probe_host, candidate))
                return candidate
            except OSError:
                continue
    return wanted


PID_FILE = os.path.join(CACHE_DIR, "app.pid")


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, timeout=10).stdout
            return str(pid) in out
        except Exception:                                   # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def frozen_control_command() -> bool:
    """打包运行下支持 `FrameGuard stop` / `FrameGuard status` 关闭或查看后台服务。

    返回 True 表示本次进程只做了一次控制操作、无需启动界面。
    """
    if not FROZEN or len(sys.argv) < 2:
        return False
    command = sys.argv[1].strip().lower()
    if command not in ("stop", "status"):
        return False

    pid = None
    try:
        with open(PID_FILE, "r", encoding="utf-8") as fh:
            pid = int((fh.read() or "").strip())
    except (OSError, ValueError):
        pid = None
    alive = bool(pid and _process_alive(pid))

    if command == "status":
        print(f"帧防 FrameGuard：{'运行中 PID=' + str(pid) if alive else '未运行'}")
        return True

    if alive and pid:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=15)
            else:
                os.kill(pid, signal.SIGTERM)
            print(f"已停止帧防 FrameGuard（PID={pid}）")
        except OSError:
            print(f"⚠️  无法结束 PID={pid}，请手动处理")
    else:
        print("没有正在运行的帧防 FrameGuard。")
    try:
        os.remove(PID_FILE)
    except OSError:
        pass
    return True


def _install_crash_logger() -> None:
    """打包运行没有控制台，把未捕获异常落盘，Windows 上额外弹窗，避免"闪退无提示"。"""

    def _hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        log_path = os.path.join(CACHE_DIR, "crash.log")
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"\n[{datetime.now().isoformat()}] FrameGuard 异常\n{detail}\n")
        except OSError:
            log_path = "(未能写入崩溃日志)"
        if os.name == "nt" and os.environ.get("FRAMEGUARD_HEADLESS", "").strip() != "1":
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    None, detail[-1500:], f"帧防 FrameGuard 异常\n日志：{log_path}", 0x10
                )
            except Exception:                               # noqa: BLE001
                pass
        stderr = getattr(sys, "__stderr__", None)
        if stderr is not None:
            try:
                stderr.write(detail)
            except (UnicodeEncodeError, ValueError, OSError):
                pass

    sys.excepthook = _hook


def main() -> None:
    _ensure_utf8_console()

    if FROZEN:
        _install_crash_logger()
        if frozen_control_command():
            return

    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(PID_FILE, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass

    ui = build_ui()
    ui.queue()

    host = os.environ.get("FRAMEGUARD_HOST") or os.environ.get("VISUAL_SAFETY_HOST", "127.0.0.1")
    port = int(os.environ.get("FRAMEGUARD_PORT") or os.environ.get("VISUAL_SAFETY_PORT", "7891"))
    port = _pick_port(host, port)

    if not DEFAULT_API_KEY.strip():
        print("=" * 68)
        print("提示：未检测到 API Key。")
        print("   方式一：在界面「⑥ 模型配置 → API Key」中直接填写；")
        print("   方式二：复制 .env.example 为 .env 并填入 FRAMEGUARD_API_KEY。")
        print(f"   数据目录（.env / 报告 / 缓存）：{os.path.dirname(CACHE_DIR)}")
        print("=" * 68)

    print(f"帧防 FrameGuard 启动中 → http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}")
    print(f"报告输出目录：{OUTPUT_DIR}")

    # 安装包运行时自动拉起系统默认浏览器；源码运行保持原行为。
    # 显式设置 FRAMEGUARD_OPEN_BROWSER=0/1 可强制覆盖（自动化测试用 0）。
    _open_env = os.environ.get("FRAMEGUARD_OPEN_BROWSER", "").strip()
    if _open_env == "1":
        open_browser = True
    elif _open_env == "0":
        open_browser = False
    else:
        open_browser = FROZEN

    ui.launch(
        server_name=host,
        server_port=port,
        allowed_paths=[OUTPUT_DIR, CACHE_DIR],
        inbrowser=open_browser,
        show_error=True,
        # Gradio 6：外观相关参数统一在 launch 阶段传入
        css=ui_theme.CSS,
        head=ui_theme.HEAD_HTML,
        favicon_path=ui_theme.ensure_favicon(),
        footer_links=[],
    )


if __name__ == "__main__":
    main()
