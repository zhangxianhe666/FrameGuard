"""监控分析报告生成：按时间段汇总，输出 HTML / Markdown / CSV / JSON。"""

from __future__ import annotations

import csv
import html
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .analyzer import encode_thumbnail
from .config import AnalysisReport, FrameResult, OUTPUT_DIR

# --------------------------------------------------------------------------
# 时间段切分
# --------------------------------------------------------------------------
PERIOD_CHOICES: List[Tuple[str, str]] = [
    ("不分组（整体汇总）", "all"),
    ("每 5 分钟", "5min"),
    ("每 15 分钟", "15min"),
    ("每 30 分钟", "30min"),
    ("每小时", "hour"),
    ("每 4 小时", "4hour"),
    ("每天", "day"),
]
PERIOD_LABELS = dict(PERIOD_CHOICES)


def _floor_dt(dt: datetime, minutes: int) -> datetime:
    total = dt.hour * 60 + dt.minute
    floored = (total // minutes) * minutes if minutes else 0
    return dt.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


def period_key(dt: datetime, mode: str) -> Tuple[datetime, str]:
    """返回某帧所属时间段的 (起点, 展示标签)。"""
    if mode in ("all", "", None):
        return dt.replace(hour=0, minute=0, second=0, microsecond=0), "全部时段"
    if mode == "day":
        start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start.strftime("%Y-%m-%d")
    if mode == "hour":
        start = dt.replace(minute=0, second=0, microsecond=0)
        return start, start.strftime("%m-%d %H:00")
    if mode == "4hour":
        start = dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
        return start, f"{start.strftime('%m-%d')} {start.hour:02d}:00–{(start.hour + 4) % 24:02d}:00"
    minutes = int(mode.replace("min", "")) if mode.endswith("min") else 60
    start = _floor_dt(dt, minutes)
    end = start + __import__("datetime").timedelta(minutes=minutes)
    return start, f"{start.strftime('%m-%d %H:%M')}–{end.strftime('%H:%M')}"


def group_by_period(results: List[FrameResult], mode: str) -> List[Dict[str, Any]]:
    """把结果按时间段分组，返回按时间排序的分组列表。"""
    buckets: Dict[datetime, Dict[str, Any]] = {}
    for r in results:
        start, label = period_key(r.frame.timestamp, mode)
        bucket = buckets.setdefault(
            start,
            {"start": start, "label": label, "results": [], "violations": []},
        )
        bucket["results"].append(r)
        if r.ok and r.is_violation:
            bucket["violations"].append(r)

    groups = sorted(buckets.values(), key=lambda b: b["start"])
    for group in groups:
        checked = [r for r in group["results"] if r.ok]
        group["checked"] = len(checked)
        group["failed"] = len(group["results"]) - len(checked)
        group["violation_count"] = len(group["violations"])
        group["violation_rate"] = (len(group["violations"]) / len(checked) * 100) if checked else 0.0
        counter: Dict[str, int] = {}
        for r in group["violations"]:
            for name in r.violations:
                counter[name] = counter.get(name, 0) + 1
        group["violation_counter"] = dict(sorted(counter.items(), key=lambda kv: -kv[1]))
        group["top_violation"] = (
            max(counter.items(), key=lambda kv: kv[1])[0] if counter else "—"
        )
    return groups


# --------------------------------------------------------------------------
# 明细表
# --------------------------------------------------------------------------
def results_to_rows(report: AnalysisReport, mode: str) -> List[Dict[str, Any]]:
    """把每帧结果展开成表行，供 CSV / 表格展示。"""
    rows: List[Dict[str, Any]] = []
    fields = report.fields
    for r in report.results:
        _start, label = period_key(r.frame.timestamp, mode)
        row: Dict[str, Any] = {
            "时间段": label,
            "时间": r.frame.time_str(),
            "序号": r.frame.index,
            "来源": r.frame.source,
            "图像": os.path.basename(r.frame.path),
            "图像路径": r.frame.path,
            "是否违规": "是" if (r.ok and r.is_violation) else ("否" if r.ok else "分析失败"),
            "违规项": "；".join(r.violations),
            "判定依据总述": r.summary(),
            "分析状态": "成功" if r.ok else f"失败：{r.error}",
            "耗时(秒)": f"{r.latency:.2f}",
        }
        for name in fields:
            row[name] = r.parsed.get(name, "") if r.ok else ""
        rows.append(row)
    return rows


CSV_BASE_COLUMNS = [
    "时间段", "时间", "序号", "来源", "图像", "图像路径",
    "是否违规", "违规项", "判定依据总述", "分析状态", "耗时(秒)",
]


# --------------------------------------------------------------------------
# HTML 报告
# --------------------------------------------------------------------------
def _fmt_rate(rate: float) -> str:
    return f"{rate:.1f}%"


def build_html_report(
    report: AnalysisReport,
    mode: str = "hour",
    include_thumbnails: bool = True,
    max_detail_rows: int = 300,
) -> str:
    """生成自包含的 HTML 报告字符串。"""
    groups = group_by_period(report.results, mode)
    stats = report.field_stats()
    total = report.total
    succeeded = report.succeeded
    failed = report.failed
    violations = report.violation_count

    risk_level, risk_class = _risk_level(report.violation_rate, failed, succeeded)

    # ---------------- 头部 ----------------
    head = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>监控合规分析报告 · {html.escape(report.started_at.strftime('%Y-%m-%d %H:%M'))}</title>
<style>
  :root {{
    --bg:#f5f7fa; --card:#ffffff; --ink:#1c2434; --sub:#5b6b83; --line:#e3e8f0;
    --brand:#2b5cff; --danger:#e2453c; --warn:#e08b18; --ok:#18a06a; --chip:#eef2fb;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:0 0 60px; background:var(--bg); color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
         font-size:14px; line-height:1.6; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:28px 20px; }}
  h1 {{ font-size:24px; margin:0 0 6px; letter-spacing:.3px; }}
  h2 {{ font-size:17px; margin:34px 0 12px; padding-left:11px; border-left:4px solid var(--brand); }}
  .meta {{ color:var(--sub); font-size:13px; margin-bottom:22px; }}
  .meta span {{ margin-right:18px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:15px 17px; }}
  .card .k {{ color:var(--sub); font-size:12px; }}
  .card .v {{ font-size:26px; font-weight:700; margin-top:5px; letter-spacing:.5px; }}
  .card .u {{ font-size:12px; color:var(--sub); margin-left:3px; font-weight:400; }}
  .risk {{ display:inline-block; padding:3px 12px; border-radius:999px; font-weight:700; font-size:13px; }}
  .risk.r0 {{ background:#e6f7ee; color:#0f7a4d; }}
  .risk.r1 {{ background:#fff5e0; color:#a86400; }}
  .risk.r2 {{ background:#fdecea; color:#c0362d; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card); border-radius:12px; overflow:hidden;
           border:1px solid var(--line); font-size:13px; }}
  th, td {{ padding:9px 11px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ background:#f0f4fb; color:#3c4a60; font-weight:600; white-space:nowrap; }}
  tr:last-child td {{ border-bottom:none; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .pill {{ display:inline-block; padding:1px 9px; border-radius:999px; font-size:12px; font-weight:600; }}
  .pill.bad {{ background:#fdecea; color:#c0362d; }}
  .pill.good {{ background:#e6f7ee; color:#0f7a4d; }}
  .pill.na {{ background:#eceff5; color:#6b7a90; }}
  .bar {{ background:#eef2f8; border-radius:6px; height:8px; overflow:hidden; min-width:60px; }}
  .bar > i {{ display:block; height:100%; background:var(--danger); }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  @media (max-width:820px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
  .detail {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; margin-bottom:12px;
             display:flex; gap:14px; }}
  .detail img {{ width:190px; height:auto; border-radius:8px; border:1px solid var(--line); flex:none; object-fit:cover; }}
  .detail .body {{ flex:1; min-width:0; }}
  .detail .t {{ font-weight:700; margin-bottom:4px; }}
  .detail .d {{ color:var(--sub); font-size:13px; }}
  .detail .tags {{ margin:6px 0 8px; }}
  ul.vlist {{ margin:6px 0 0; padding-left:20px; }}
  ul.vlist li {{ margin-bottom:3px; }}
  .note {{ background:#fffbf0; border:1px solid #f3e2bd; color:#7a5b13; border-radius:10px; padding:11px 14px; font-size:13px; margin-bottom:10px; }}
  .foot {{ margin-top:34px; color:var(--sub); font-size:12px; text-align:center; }}
  .empty {{ color:var(--sub); padding:18px; text-align:center; }}
</style>
</head>
<body>
<div class="wrap">
<h1>工作场所合规监控分析报告</h1>
<div class="meta">
  <span>分析时间：{html.escape(report.started_at.strftime('%Y-%m-%d %H:%M:%S'))}</span>
  <span>数据来源：{html.escape(report.source_label or '—')}</span>
  <span>识别模型：{html.escape(report.model_label or '—')}</span>
  <span>分组方式：{html.escape(PERIOD_LABELS.get(mode, mode))}</span>
</div>
"""
    if report.notes:
        for note in report.notes:
            head += f'<div class="note">{html.escape(note)}</div>\n'

    # ---------------- 概览卡片 ----------------
    head += f"""
<div class="cards">
  <div class="card"><div class="k">分析图像总数</div><div class="v">{total}<span class="u">帧</span></div></div>
  <div class="card"><div class="k">成功分析</div><div class="v" style="color:var(--ok)">{succeeded}<span class="u">帧</span></div></div>
  <div class="card"><div class="k">违规图像</div><div class="v" style="color:var(--danger)">{violations}<span class="u">帧</span></div></div>
  <div class="card"><div class="k">违规率</div><div class="v">{_fmt_rate(report.violation_rate)}</div></div>
  <div class="card"><div class="k">分析失败</div><div class="v" style="color:var(--warn)">{failed}<span class="u">帧</span></div></div>
  <div class="card"><div class="k">综合风险等级</div><div class="v"><span class="risk {risk_class}">{risk_level}</span></div></div>
</div>
"""

    # ---------------- 分时段汇总 ----------------
    head += """
<h2>分时段汇总</h2>
<table>
<thead><tr>
<th>时间段</th><th>图像数</th><th>已分析</th><th>违规数</th><th>违规率</th><th>违规占比</th><th>主要违规项</th>
</tr></thead>
<tbody>
"""
    if not groups:
        head += '<tr><td colspan="7" class="empty">暂无数据</td></tr>'
    for group in groups:
        rate = group["violation_rate"]
        width = min(100.0, rate)
        top = group["top_violation"]
        if group["violation_counter"]:
            top += f"（{group['violation_counter'][group['top_violation']]} 次）"
        head += (
            f"<tr><td><b>{html.escape(group['label'])}</b></td>"
            f"<td class='num'>{len(group['results'])}</td>"
            f"<td class='num'>{group['checked']}</td>"
            f"<td class='num' style='color:var(--danger);font-weight:700'>{group['violation_count']}</td>"
            f"<td class='num'>{_fmt_rate(rate)}</td>"
            f"<td><div class='bar'><i style='width:{width:.1f}%'></i></div></td>"
            f"<td>{html.escape(top)}</td></tr>\n"
        )
    head += "</tbody></table>\n"

    # ---------------- 各维度统计 ----------------
    head += '<h2>各识别维度统计</h2>\n<table><thead><tr><th>识别维度</th><th>违规次数</th><th>违规率</th><th>违规占比</th><th>取值分布</th></tr></thead><tbody>\n'
    if not stats:
        head += '<tr><td colspan="5" class="empty">未解析到识别维度</td></tr>'
    for name, stat in stats.items():
        width = min(100.0, stat["rate"])
        dist = "、".join(f"{html.escape(str(k))}×{v}" for k, v in sorted(stat["value_counts"].items(), key=lambda kv: -kv[1]))
        head += (
            f"<tr><td><b>{html.escape(name)}</b></td>"
            f"<td class='num' style='color:var(--danger);font-weight:700'>{stat['violations']}</td>"
            f"<td class='num'>{_fmt_rate(stat['rate'])}</td>"
            f"<td><div class='bar'><i style='width:{width:.1f}%'></i></div></td>"
            f"<td>{dist or '—'}</td></tr>\n"
        )
    head += "</tbody></table>\n"

    # ---------------- 违规明细 ----------------
    head += '<h2>违规明细</h2>\n'
    vframes = [r for r in report.results if r.ok and r.is_violation]
    if not vframes:
        head += '<div class="card empty">本次分析未发现违规现象。</div>\n'
    else:
        for r in vframes[:max_detail_rows]:
            thumb = encode_thumbnail(r.frame.path) if include_thumbnails else ""
            tags = "".join(f'<span class="pill bad">{html.escape(v)}</span> ' for v in r.violations)
            values = ""
            if report.fields:
                values = "<div class='d'>" + "；".join(
                    f"{html.escape(n)}：{html.escape(str(r.parsed.get(n, '—')))}" for n in report.fields
                ) + "</div>"
            img_tag = f'<img src="{thumb}" alt="帧">' if thumb else ""
            head += (
                f'<div class="detail">{img_tag}<div class="body">'
                f'<div class="t">{html.escape(r.frame.time_str())} · '
                f'{html.escape(r.frame.source or "")} · 第 {r.frame.index} 帧</div>'
                f'<div class="tags">{tags}</div>'
                f'<div class="d">{html.escape(r.summary() or "—")}</div>'
                f'{values}'
                f'</div></div>\n'
            )
        if len(vframes) > max_detail_rows:
            head += f'<div class="note">仅展示前 {max_detail_rows} 条违规明细，完整明细请查看随附的 CSV 文件。</div>\n'

    # ---------------- 分析失败 ----------------
    if failed:
        head += '<h2>分析失败记录</h2><table><thead><tr><th>时间</th><th>图像</th><th>失败原因</th></tr></thead><tbody>\n'
        for r in report.results:
            if not r.ok:
                head += (
                    f"<tr><td>{html.escape(r.frame.time_str())}</td>"
                    f"<td>{html.escape(os.path.basename(r.frame.path))}</td>"
                    f"<td>{html.escape(r.error)}</td></tr>\n"
                )
        head += "</tbody></table>\n"

    head += f"""
<div class="foot">
  本次分析共 {total} 帧，耗时 {html.escape(report.duration_str())}；报告生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
  判定结果由多模态模型自动生成，仅作为合规巡查的辅助参考，最终结论请以现场核实为准。
</div>
</div>
</body>
</html>
"""
    return head


def _risk_level(rate: float, failed: int, succeeded: int) -> Tuple[str, str]:
    total = failed + succeeded
    fail_ratio = (failed / total * 100) if total else 0.0
    if rate >= 30 or fail_ratio >= 30:
        return "高风险", "r2"
    if rate >= 10 or fail_ratio >= 10:
        return "中风险", "r1"
    if rate > 0 or failed:
        return "低风险", "r1"
    return "未见异常", "r0"


# --------------------------------------------------------------------------
# Markdown 报告
# --------------------------------------------------------------------------
def build_markdown_report(report: AnalysisReport, mode: str = "hour", max_detail_rows: int = 200) -> str:
    groups = group_by_period(report.results, mode)
    stats = report.field_stats()
    lines: List[str] = []
    lines.append("# 工作场所合规监控分析报告")
    lines.append("")
    lines.append(f"- **分析时间**：{report.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **数据来源**：{report.source_label or '—'}")
    lines.append(f"- **识别模型**：{report.model_label or '—'}")
    lines.append(f"- **分组方式**：{PERIOD_LABELS.get(mode, mode)}")
    lines.append(f"- **分析图像总数**：{report.total} 帧（成功 {report.succeeded}，失败 {report.failed}）")
    lines.append(f"- **违规图像**：{report.violation_count} 帧，违规率 {_fmt_rate(report.violation_rate)}")
    level, _ = _risk_level(report.violation_rate, report.failed, report.succeeded)
    lines.append(f"- **综合风险等级**：{level}")
    lines.append("")
    if report.notes:
        lines.append("> " + "；".join(report.notes))
        lines.append("")

    lines.append("## 分时段汇总")
    lines.append("")
    lines.append("| 时间段 | 图像数 | 已分析 | 违规数 | 违规率 | 主要违规项 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for group in groups:
        top = group["top_violation"]
        if group["violation_counter"]:
            top += f"（{group['violation_counter'][group['top_violation']]} 次）"
        lines.append(
            f"| {group['label']} | {len(group['results'])} | {group['checked']} | "
            f"{group['violation_count']} | {_fmt_rate(group['violation_rate'])} | {top} |"
        )
    lines.append("")

    lines.append("## 各识别维度统计")
    lines.append("")
    lines.append("| 识别维度 | 违规次数 | 违规率 | 取值分布 |")
    lines.append("| --- | ---: | ---: | --- |")
    for name, stat in stats.items():
        dist = "、".join(f"{k}×{v}" for k, v in sorted(stat["value_counts"].items(), key=lambda kv: -kv[1]))
        lines.append(f"| {name} | {stat['violations']} | {_fmt_rate(stat['rate'])} | {dist or '—'} |")
    lines.append("")

    lines.append("## 违规明细")
    lines.append("")
    vframes = [r for r in report.results if r.ok and r.is_violation]
    if not vframes:
        lines.append("本次分析未发现违规现象。")
    else:
        for r in vframes[:max_detail_rows]:
            lines.append(f"### {r.frame.time_str()} · {r.frame.source} · 第 {r.frame.index} 帧")
            lines.append("")
            lines.append(f"- **违规项**：{'、'.join(r.violations)}")
            lines.append(f"- **图像**：`{r.frame.path}`")
            lines.append(f"- **判定依据**：{r.summary() or '—'}")
            values = "；".join(f"{n}：{r.parsed.get(n, '—')}" for n in report.fields)
            if values:
                lines.append(f"- **各项判定**：{values}")
            lines.append("")
        if len(vframes) > max_detail_rows:
            lines.append(f"> 仅展示前 {max_detail_rows} 条违规明细，完整明细见 CSV。")
            lines.append("")

    if report.failed:
        lines.append("## 分析失败记录")
        lines.append("")
        lines.append("| 时间 | 图像 | 失败原因 |")
        lines.append("| --- | --- | --- |")
        for r in report.results:
            if not r.ok:
                lines.append(f"| {r.frame.time_str()} | {os.path.basename(r.frame.path)} | {r.error} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"本次分析共 {report.total} 帧，耗时 {report.duration_str()}。"
        "判定结果由多模态模型自动生成，仅作为合规巡查的辅助参考，最终结论请以现场核实为准。"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------
def _task_dir(report: AnalysisReport, tag: str = "") -> str:
    name = report.started_at.strftime("%Y%m%d_%H%M%S")
    if tag:
        name += f"_{tag}"
    path = os.path.join(OUTPUT_DIR, name)
    os.makedirs(path, exist_ok=True)
    return path


def write_reports(
    report: AnalysisReport,
    mode: str = "hour",
    include_thumbnails: bool = True,
    tag: str = "",
) -> Dict[str, str]:
    """输出全部报告文件，返回 {类型: 路径}。"""
    out = _task_dir(report, tag)
    paths: Dict[str, str] = {}

    stamp = report.started_at.strftime("%Y%m%d_%H%M%S")

    html_path = os.path.join(out, f"监控分析报告_{stamp}.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_html_report(report, mode=mode, include_thumbnails=include_thumbnails))
    paths["html"] = html_path

    md_path = os.path.join(out, f"监控分析报告_{stamp}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(build_markdown_report(report, mode=mode))
    paths["markdown"] = md_path

    csv_path = os.path.join(out, f"分析明细_{stamp}.csv")
    rows = results_to_rows(report, mode)
    columns = CSV_BASE_COLUMNS + [n for n in report.fields if n not in CSV_BASE_COLUMNS]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in columns})
    paths["csv"] = csv_path

    json_path = os.path.join(out, f"结构化结果_{stamp}.json")
    payload = {
        "分析时间": report.started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "数据来源": report.source_label,
        "识别模型": report.model_label,
        "分组方式": PERIOD_LABELS.get(mode, mode),
        "识别维度": report.fields,
        "违规值配置": report.violation_map,
        "统计": {
            "图像总数": report.total,
            "成功": report.succeeded,
            "失败": report.failed,
            "违规帧数": report.violation_count,
            "违规率": round(report.violation_rate, 2),
            "耗时": report.duration_str(),
        },
        "分时段汇总": [
            {
                "时间段": g["label"],
                "图像数": len(g["results"]),
                "已分析": g["checked"],
                "违规数": g["violation_count"],
                "违规率": round(g["violation_rate"], 2),
                "违规项统计": g["violation_counter"],
            }
            for g in group_by_period(report.results, mode)
        ],
        "各维度统计": report.field_stats(),
        "明细": [
            {
                "时间": r.frame.time_str(),
                "序号": r.frame.index,
                "来源": r.frame.source,
                "图像路径": r.frame.path,
                "分析成功": r.ok,
                "违规": r.is_violation,
                "违规项": r.violations,
                "判定结果": {k: v for k, v in r.parsed.items() if not k.startswith("__")},
                "判定依据总述": r.summary(),
                "耗时秒": round(r.latency, 2),
                "错误": r.error,
            }
            for r in report.results
        ],
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    paths["json"] = json_path
    paths["dir"] = out
    return paths
