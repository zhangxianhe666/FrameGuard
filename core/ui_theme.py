"""界面视觉层：自定义主题、CSS、头部资源与站点图标。

设计方向：深色「监控指挥中心」—— 深空底色 + 极光渐变 + 玻璃拟态面板 + 霓虹强调色。
所有配色同时写入 light / dark 两套变量，保证浏览器无论深浅色模式都呈现同一套观感。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import gradio as gr

from .config import CACHE_DIR

# --------------------------------------------------------------------------
# 配色
# --------------------------------------------------------------------------
C_BG = "#05070f"          # 最深底色
C_PANEL = "#0b1120"       # 面板
C_PANEL_2 = "#0e1730"     # 次级面板
C_BORDER = "#1c2947"      # 边框
C_INK = "#e8eefc"         # 主文字
C_SUB = "#7f93b5"         # 次级文字
C_CYAN = "#22d3ee"
C_BLUE = "#3b82f6"
C_VIOLET = "#a855f7"
C_OK = "#2dd4a7"
C_WARN = "#ffb020"
C_DANGER = "#ff4d6d"


# --------------------------------------------------------------------------
# 主题
# --------------------------------------------------------------------------
def _both(key: str, value: str) -> Dict[str, str]:
    """同时写入常规与 dark 变量，避免受浏览器深浅色模式影响。"""
    return {key: value, f"{key}_dark": value}


def build_theme() -> gr.themes.Base:
    theme = gr.themes.Base(
        primary_hue="cyan",
        secondary_hue="violet",
        neutral_hue="slate",
        radius_size=gr.themes.sizes.radius_md,
        font=[
            gr.themes.GoogleFont("Inter"),
            "system-ui",
            "-apple-system",
            "PingFang SC",
            "Hiragino Sans GB",
            "Microsoft YaHei",
            "sans-serif",
        ],
        font_mono=[
            gr.themes.GoogleFont("JetBrains Mono"),
            "ui-monospace",
            "SFMono-Regular",
            "Menlo",
            "monospace",
        ],
    )

    settings: Dict[str, Any] = {}
    settings.update(_both("body_background_fill", C_BG))
    settings.update(_both("body_text_color", C_INK))
    settings.update(_both("body_text_color_subdued", C_SUB))
    settings.update(_both("background_fill_primary", C_PANEL))
    settings.update(_both("background_fill_secondary", C_PANEL_2))
    settings.update(_both("border_color_primary", C_BORDER))
    settings.update(_both("border_color_accent", C_CYAN))
    settings.update(_both("color_accent", C_CYAN))
    settings.update(_both("color_accent_soft", "rgba(34,211,238,0.12)"))

    # 面板 / 卡片
    settings.update(_both("block_background_fill", C_PANEL))
    settings.update(_both("block_border_color", C_BORDER))
    settings.update(_both("block_border_width", "1px"))
    settings.update(_both("block_label_background_fill", "transparent"))
    settings.update(_both("block_label_text_color", C_SUB))
    settings.update(_both("block_label_border_width", "0px"))
    settings.update(_both("block_title_text_color", C_INK))
    settings.update(_both("block_title_text_weight", "600"))
    settings.update(_both("block_shadow", "none"))
    settings.update(_both("panel_background_fill", C_PANEL))
    settings.update(_both("panel_border_width", "0px"))
    settings["block_radius"] = "16px"

    # 输入控件
    settings.update(_both("input_background_fill", "#080e1c"))
    settings.update(_both("input_border_color", "#20304f"))
    settings.update(_both("input_border_color_focus", C_CYAN))
    settings.update(_both("input_placeholder_color", "#57698a"))
    settings.update(_both("input_shadow", "none"))
    settings.update(_both("input_shadow_focus", "0 0 0 3px rgba(34,211,238,0.16)"))
    settings["input_radius"] = "10px"

    # 按钮
    settings.update(_both("button_primary_background_fill", C_CYAN))
    settings.update(_both("button_primary_background_fill_hover", "#4fe0f5"))
    settings.update(_both("button_primary_text_color", "#04121c"))
    settings.update(_both("button_primary_border_color", "transparent"))
    settings.update(_both("button_secondary_background_fill", "#111c33"))
    settings.update(_both("button_secondary_background_fill_hover", "#17253f"))
    settings.update(_both("button_secondary_text_color", C_INK))
    settings.update(_both("button_secondary_border_color", C_BORDER))
    settings["button_large_radius"] = "12px"

    # 表格
    settings.update(_both("table_border_color", C_BORDER))
    settings.update(_both("table_even_background_fill", C_PANEL))
    settings.update(_both("table_odd_background_fill", "#0f1930"))
    settings.update(_both("table_row_focus", "rgba(34,211,238,0.10)"))

    # 勾选 / 滑块 / 加载
    settings.update(_both("checkbox_background_color", "#0a1120"))
    settings.update(_both("checkbox_background_color_selected", C_CYAN))
    settings.update(_both("checkbox_border_color", "#28395c"))
    settings.update(_both("checkbox_border_color_focus", C_CYAN))
    settings.update(_both("checkbox_label_background_fill", "#0b1425"))
    settings.update(_both("checkbox_label_border_color", C_BORDER))
    settings.update(_both("checkbox_label_text_color", C_INK))
    settings.update(_both("slider_color", C_CYAN))
    settings.update(_both("loader_color", C_CYAN))

    # 链接 / 代码
    settings.update(_both("link_text_color", C_CYAN))
    settings.update(_both("link_text_color_hover", "#67e8f9"))
    settings.update(_both("link_text_color_visited", C_CYAN))
    settings.update(_both("code_background_fill", "#0a1424"))
    settings.update(_both("stat_background_fill", C_PANEL_2))
    settings.update(_both("shadow_drop", "0 10px 30px -12px rgba(0,0,0,0.75)"))
    settings.update(_both("shadow_drop_lg", "0 18px 50px -18px rgba(0,0,0,0.85)"))

    try:
        return theme.set(**settings)
    except Exception:                       # 个别键在不同版本缺失时降级
        return theme


# --------------------------------------------------------------------------
# 头部资源
# --------------------------------------------------------------------------
HEAD_HTML = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script>
(function () {
  // 强制深色：无论系统偏好如何，都呈现统一的控制台观感
  function force() {
    var r = document.documentElement, b = document.body;
    if (r && !r.classList.contains('dark')) r.classList.add('dark');
    if (b && !b.classList.contains('dark')) b.classList.add('dark');
  }
  force();
  document.addEventListener('DOMContentLoaded', force);
  try {
    new MutationObserver(force).observe(document.documentElement, {
      attributes: true, attributeFilter: ['class']
    });
  } catch (e) {}
})();
</script>
"""


# --------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------
CSS = """
/* ===== 字体 & 底色 ===== */
.gradio-container, body {
  font-family: 'Inter', system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif !important;
  background: transparent !important;
  color: #e8eefc !important;
}
body {
  background-color: #05070f !important;
  background-image:
    radial-gradient(1100px 620px at 12% -8%, rgba(34,211,238,.16), transparent 62%),
    radial-gradient(950px 560px at 88% 4%, rgba(168,85,247,.15), transparent 60%),
    radial-gradient(900px 700px at 50% 108%, rgba(59,130,246,.13), transparent 62%) !important;
  background-attachment: fixed !important;
}
/* 细网格叠加，强化「控制台」质感 */
body::before {
  content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image:
    linear-gradient(rgba(120,160,220,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(120,160,220,.045) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(1200px 800px at 50% 0%, #000 20%, transparent 78%);
  -webkit-mask-image: radial-gradient(1200px 800px at 50% 0%, #000 20%, transparent 78%);
}
.gradio-container { position: relative; z-index: 1; max-width: 1560px !important; }

/* ===== 滚动条 ===== */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: rgba(10,17,32,.6); }
::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, rgba(34,211,238,.55), rgba(59,130,246,.55));
  border-radius: 8px; border: 2px solid transparent; background-clip: padding-box;
}
::-webkit-scrollbar-thumb:hover { background: linear-gradient(180deg, #22d3ee, #3b82f6); background-clip: padding-box; }

/* ===== 顶部 Hero ===== */
#hero { margin-bottom: 14px; }
.error-wrap, .error { display: none !important; }

.hero {
  position: relative; overflow: hidden;
  border-radius: 22px; padding: 26px 30px 24px;
  background:
    linear-gradient(135deg, rgba(12,20,38,.92) 0%, rgba(10,16,32,.86) 46%, rgba(20,14,40,.88) 100%);
  border: 1px solid rgba(34,211,238,.20);
  box-shadow: 0 22px 60px -30px rgba(0,0,0,.95), inset 0 1px 0 rgba(255,255,255,.05);
  animation: heroIn .7s cubic-bezier(.22,1,.36,1) both;
}
@keyframes heroIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: none; } }
.hero::before {
  content: ''; position: absolute; inset: -60% -20%;
  background: conic-gradient(from 0deg, transparent 0 62%, rgba(34,211,238,.16) 74%, transparent 84%);
  animation: spin 14s linear infinite; pointer-events: none;
}
@keyframes spin { to { transform: rotate(360deg); } }
/* 扫描线 */
.hero::after {
  content: ''; position: absolute; left: 0; right: 0; height: 2px; top: 0;
  background: linear-gradient(90deg, transparent, rgba(34,211,238,.9), transparent);
  filter: blur(.5px); animation: scan 5.5s ease-in-out infinite;
}
@keyframes scan { 0%,100% { top: 0; opacity: .25; } 50% { top: 100%; opacity: .95; } }

.hero-inner { position: relative; z-index: 2; }
.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 12.5px; letter-spacing: .06em; font-weight: 700;
  color: #8fe9f7; background: rgba(34,211,238,.10);
  border: 1px solid rgba(34,211,238,.30); border-radius: 999px; padding: 5px 14px;
}
.hero-title {
  margin: 13px 0 6px; font-size: 34px; line-height: 1.16; font-weight: 800; letter-spacing: -.4px;
  background: linear-gradient(100deg, #22d3ee 0%, #60a5fa 26%, #a855f7 52%, #22d3ee 78%);
  background-size: 300% 100%;
  -webkit-background-clip: text; background-clip: text; color: transparent;
  animation: hueMove 9s linear infinite;
}
@keyframes hueMove { to { background-position: 300% 0; } }
.hero-sub { color: #8ba1c4; font-size: 14px; margin: 0 0 15px; max-width: 900px; }
.hero-chips { display: flex; flex-wrap: wrap; gap: 9px; }
.chip {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 12.5px; color: #d3e2f8; background: rgba(255,255,255,.055);
  border: 1px solid rgba(160,190,235,.22); border-radius: 999px; padding: 5px 12px;
  transition: border-color .25s, transform .25s, background .25s;
}
.chip:hover { border-color: rgba(34,211,238,.6); background: rgba(34,211,238,.1); transform: translateY(-1px); }
.chip i { font-style: normal; font-size: 13px; }
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: #2dd4a7; box-shadow: 0 0 10px #2dd4a7; animation: pulse 2.1s infinite; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(45,212,167,.55);} 70% { box-shadow: 0 0 0 9px rgba(45,212,167,0);} 100% { box-shadow: 0 0 0 0 rgba(45,212,167,0);} }

/* ===== 状态条 ===== */
#status-bar {
  border-radius: 14px; padding: 12px 16px !important;
  background: linear-gradient(135deg, rgba(12,20,38,.80), rgba(14,23,48,.62)) !important;
  border: 1px solid rgba(34,211,238,.16) !important;
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
}
#status-bar p { margin: 0 !important; font-size: 13.5px !important; }
#status-bar strong { color: #22d3ee; }

/* ===== 折叠面板（玻璃拟态，Gradio 6 实际类名 .gr-accordion）===== */
.gr-accordion {
  background: linear-gradient(160deg, rgba(12,20,38,.72), rgba(10,16,30,.58)) !important;
  border: 1px solid rgba(150,180,230,.13) !important;
  border-radius: 16px !important; margin-bottom: 10px !important;
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  transition: border-color .3s, box-shadow .3s; overflow: hidden;
  position: relative;
}
.gr-accordion:hover { border-color: rgba(34,211,238,.30) !important; }
.gr-accordion .label-wrap {
  padding: 12px 16px !important; font-weight: 600 !important; font-size: 13.5px !important;
  color: #cfe0f7 !important; border-radius: 16px !important; transition: background .25s !important;
}
.gr-accordion .label-wrap:hover { background: rgba(34,211,238,.055) !important; }
/* 展开时左侧霓虹指示条 */
.gr-accordion:has(.label-wrap.open)::before {
  content: ''; position: absolute; left: 0; top: 14px; bottom: 14px; width: 3px;
  border-radius: 3px; background: linear-gradient(180deg, #22d3ee, #a855f7);
  box-shadow: 0 0 16px rgba(34,211,238,.85);
}
.gr-accordion:has(.label-wrap.open) { border-color: rgba(34,211,238,.32) !important; }

/* ===== 按钮 ===== */
button.primary, #btn-start {
  border: none !important; color: #04121c !important; font-weight: 700 !important;
  letter-spacing: .3px;
  background: linear-gradient(120deg, #22d3ee 0%, #38bdf8 42%, #818cf8 100%) !important;
  box-shadow: 0 10px 26px -12px rgba(34,211,238,.85), inset 0 1px 0 rgba(255,255,255,.35) !important;
  position: relative; overflow: hidden; transition: transform .2s, box-shadow .2s !important;
}
button.primary:hover, #btn-start:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 34px -12px rgba(34,211,238,1), inset 0 1px 0 rgba(255,255,255,.4) !important;
}
button.primary::after, #btn-start::after {
  content: ''; position: absolute; inset: 0; transform: translateX(-130%);
  background: linear-gradient(110deg, transparent 32%, rgba(255,255,255,.45) 50%, transparent 68%);
}
button.primary:hover::after, #btn-start:hover::after { animation: sheen 1.05s ease; }
@keyframes sheen { to { transform: translateX(130%); } }

#btn-stop {
  background: linear-gradient(120deg, rgba(255,77,109,.16), rgba(255,77,109,.07)) !important;
  border: 1px solid rgba(255,77,109,.45) !important; color: #ff8ea1 !important; font-weight: 700 !important;
  transition: all .2s !important;
}
#btn-stop:hover { background: rgba(255,77,109,.24) !important; box-shadow: 0 8px 22px -12px rgba(255,77,109,.9); }

button.secondary {
  background: rgba(255,255,255,.045) !important;
  border: 1px solid rgba(150,180,230,.18) !important;
  color: #cfe0f7 !important; transition: all .2s !important;
}
button.secondary:hover {
  border-color: rgba(34,211,238,.55) !important;
  background: rgba(34,211,238,.09) !important;
  box-shadow: 0 8px 20px -14px rgba(34,211,238,.9);
}

/* ===== 标签页（Gradio 6：button[role=tab]）===== */
.tabs .tab-container[role="tablist"] {
  border-bottom: 1px solid rgba(150,180,230,.14) !important;
  gap: 4px !important; background: transparent !important; padding: 0 2px !important;
}
.tabs .tab-container[role="tablist"] > button[role="tab"] {
  background: transparent !important; border: none !important;
  color: #7f93b5 !important; font-weight: 600 !important; font-size: 13.5px !important;
  padding: 9px 16px !important; border-radius: 10px 10px 0 0 !important;
  transition: color .2s, background .2s !important; position: relative;
}
.tabs .tab-container[role="tablist"] > button[role="tab"]:hover {
  color: #cfe0f7 !important; background: rgba(255,255,255,.035) !important;
}
.tabs .tab-container[role="tablist"] > button[role="tab"].selected {
  color: #e8eefc !important; background: rgba(34,211,238,.07) !important;
}
.tabs .tab-container[role="tablist"] > button[role="tab"].selected::after {
  content: ''; position: absolute; left: 12px; right: 12px; bottom: -1px; height: 2px;
  background: linear-gradient(90deg, #22d3ee, #a855f7); border-radius: 2px;
  box-shadow: 0 0 12px rgba(34,211,238,.9);
}
/* 隐藏移动端冗余的 tab 容器 */
.tab-container.visually-hidden { display: none !important; }

/* ===== 数据表 ===== */
.table-wrap, .table-container {
  border: 1px solid rgba(150,180,230,.14) !important; border-radius: 14px !important;
  overflow: hidden !important; background: rgba(8,14,28,.6) !important;
}
.table-wrap table { font-size: 12.5px !important; background: transparent !important; }
.table-wrap .header-row, .table-wrap thead tr {
  background: linear-gradient(180deg, rgba(23,37,63,.95), rgba(16,26,46,.92)) !important;
}
.table-wrap .header-cell, .table-wrap thead th {
  color: #a9c0e0 !important; font-weight: 700 !important; font-size: 12px !important;
  letter-spacing: .04em; border-bottom: 1px solid rgba(34,211,238,.22) !important;
  white-space: nowrap !important; background: transparent !important;
}
.table-wrap .cell-wrap, .table-wrap tbody td { color: #d5e2f5 !important; }
.table-wrap tbody tr:hover td, .table-wrap .cell-wrap:hover {
  background: rgba(34,211,238,.055) !important;
}
.table-wrap td, .table-wrap th, .table-wrap .cell-wrap { font-variant-numeric: tabular-nums; }

/* ===== 图库（违规图像墙）===== */
#gallery-box {
  background: rgba(8,14,28,.55) !important;
  border: 1px solid rgba(150,180,230,.14) !important;
  border-radius: 14px !important; padding: 10px !important;
}
#gallery-box .thumbnail-item, #gallery-box .grid-wrap > *, #gallery-box .gallery-item {
  border-radius: 11px !important; overflow: hidden !important;
  border: 1px solid rgba(150,180,230,.14) !important;
  transition: transform .28s cubic-bezier(.22,1,.36,1), box-shadow .28s, border-color .28s !important;
}
#gallery-box .thumbnail-item:hover, #gallery-box .gallery-item:hover {
  transform: translateY(-4px) scale(1.02);
  border-color: rgba(255,77,109,.7) !important;
  box-shadow: 0 16px 34px -16px rgba(255,77,109,.85) !important;
}
#gallery-box .upload-container, #gallery-box .empty {
  background: rgba(8,14,28,.5) !important; border-radius: 12px !important;
}

/* ===== 日志 ===== */
#log-box textarea {
  font-family: 'JetBrains Mono', ui-monospace, Menlo, monospace !important;
  font-size: 12.2px !important; line-height: 1.62 !important;
  background: #060b16 !important; color: #9fd8e8 !important;
  border: 1px solid rgba(34,211,238,.18) !important;
}
#log-box textarea::selection { background: rgba(34,211,238,.3); }

/* ===== 文件下载 ===== */
#files-box {
  background: rgba(10,18,34,.55) !important;
  border: 1px solid rgba(150,180,230,.15) !important; border-radius: 12px !important;
  padding: 8px !important;
}
#files-box button:hover { border-color: rgba(34,211,238,.5) !important; }

/* ===== 报告预览 iframe ===== */
#report-preview iframe {
  border-radius: 14px !important; border: 1px solid rgba(150,180,230,.2) !important;
  box-shadow: 0 20px 50px -24px rgba(0,0,0,.9);
}

/* ===== 输入控件焦点光晕 ===== */
input:focus, textarea:focus, select:focus {
  box-shadow: 0 0 0 3px rgba(34,211,238,.16) !important;
  border-color: rgba(34,211,238,.75) !important;
}
label > span, .block-title, .block-title > span {
  color: #93a8c8 !important; font-size: 12.5px !important; font-weight: 500 !important;
}
.info-text { color: #63799c !important; font-size: 11.8px !important; }

/* ===== 结果区 / 配置区间距 ===== */
#result-col { gap: 12px; }
#config-col { gap: 0; }

/* ===== 加载态进度条 ===== */
.progress-bar, .progress-level-inner { background: linear-gradient(90deg, #22d3ee, #a855f7) !important; }

/* ===== 数据表空状态 ===== */
.table-wrap .no-rows, .no-rows { color: #63799c !important; background: transparent !important; }

/* 移动端收敛 */
@media (max-width: 860px) {
  .hero { padding: 20px 18px; } .hero-title { font-size: 24px; }
  .gradio-container { padding: 12px !important; }
}
"""


# --------------------------------------------------------------------------
# Hero
# --------------------------------------------------------------------------
HERO_HTML = """
<div class="hero">
  <div class="hero-inner">
    <div class="hero-badge"><span class="live-dot"></span>帧防 · FrameGuard</div>
    <h1 class="hero-title">视觉安全智能分析</h1>
    <p class="hero-sub">
      你的任何安全分析任务都可交给他，洞悉最细微的安全隐患
    </p>
    <div class="hero-chips">
      <span class="chip"><i>🎥</i>视频流实时抽帧</span>
      <span class="chip"><i>🗂️</i>图片目录批量分析</span>
      <span class="chip"><i>📐</i>自定义判定规则</span>
      <span class="chip"><i>🕒</i>分时段违规汇总</span>
      <span class="chip"><i>📊</i>HTML / CSV / JSON 报告</span>
    </div>
  </div>
</div>
"""


# --------------------------------------------------------------------------
# 运行中态
# --------------------------------------------------------------------------
RUNNING_STATE_HTML = """
<div style="font-family:'Inter',-apple-system,'PingFang SC',sans-serif">
  <div style="position:relative;overflow:hidden;border-radius:18px;padding:38px 30px;text-align:center;
              background:linear-gradient(150deg,rgba(12,20,38,.78),rgba(10,16,30,.6));
              border:1px solid rgba(34,211,238,.24)">
    <div style="position:absolute;left:0;right:0;height:2px;top:0;
                background:linear-gradient(90deg,transparent,#22d3ee,transparent);
                animation:vsScan 2.2s ease-in-out infinite"></div>
    <div style="display:inline-flex;align-items:center;gap:10px;
                padding:7px 16px;border-radius:999px;
                background:rgba(34,211,238,.10);border:1px solid rgba(34,211,238,.35)">
      <span class="live-dot"></span>
      <span style="color:#8fe9f7;font-size:12.5px;font-weight:700;letter-spacing:.12em">
        ANALYSING · 正在分析
      </span>
    </div>
    <div style="color:#8298b8;font-size:13px;margin-top:14px">
      正在采集图像并逐帧提交多模态模型判定，结果会实时刷新
    </div>
    <div style="margin:22px auto 0;max-width:420px;height:6px;border-radius:5px;
                background:rgba(255,255,255,.07);overflow:hidden">
      <div style="height:100%;width:38%;border-radius:5px;
                  background:linear-gradient(90deg,#22d3ee,#a855f7);
                  animation:vsSlide 1.5s ease-in-out infinite"></div>
    </div>
  </div>
</div>
<style>
@keyframes vsScan { 0%,100%{top:0;opacity:.35} 50%{top:100%;opacity:1} }
@keyframes vsSlide { 0%{margin-left:-40%} 100%{margin-left:100%} }
</style>
"""


# --------------------------------------------------------------------------
# 初始引导态（结果区未开始分析时展示）
# --------------------------------------------------------------------------
EMPTY_STATE_HTML = """
<div style="font-family:'Inter',-apple-system,'PingFang SC',sans-serif">
  <div style="position:relative;overflow:hidden;border-radius:18px;padding:34px 30px;
              background:linear-gradient(150deg,rgba(12,20,38,.72),rgba(10,16,30,.55));
              border:1px dashed rgba(34,211,238,.28);text-align:center">
    <div style="font-size:40px;line-height:1;margin-bottom:12px;
                filter:drop-shadow(0 0 18px rgba(34,211,238,.55))">🛰️</div>
    <div style="font-size:17px;font-weight:800;color:#e8eefc;letter-spacing:.3px">
      等待分析任务
    </div>
    <div style="color:#8298b8;font-size:13px;margin-top:6px">
      完成左侧配置后点击「开始分析」，这里会实时呈现违规统计与分析报告
    </div>

    <div style="display:flex;gap:12px;flex-wrap:wrap;justify-content:center;margin-top:24px">
      <div style="flex:1;min-width:190px;max-width:250px;text-align:left;padding:14px 16px;border-radius:13px;
                  background:rgba(34,211,238,.06);border:1px solid rgba(34,211,238,.20)">
        <div style="color:#22d3ee;font-size:11.5px;font-weight:800;letter-spacing:.14em">STEP 01</div>
        <div style="color:#d5e2f5;font-size:13.5px;font-weight:600;margin:5px 0 3px">选择数据来源</div>
        <div style="color:#7f93b5;font-size:12px;line-height:1.6">
          填视频流地址、视频文件或图片目录；没素材就点「生成演示图片」。
        </div>
      </div>
      <div style="flex:1;min-width:190px;max-width:250px;text-align:left;padding:14px 16px;border-radius:13px;
                  background:rgba(168,85,247,.06);border:1px solid rgba(168,85,247,.22)">
        <div style="color:#c084fc;font-size:11.5px;font-weight:800;letter-spacing:.14em">STEP 02</div>
        <div style="color:#d5e2f5;font-size:13.5px;font-weight:600;margin:5px 0 3px">写识别规则</div>
        <div style="color:#7f93b5;font-size:12px;line-height:1.6">
          每节一个判定维度，写清合法取值与违规取值，点「校验规则」可即时检查。
        </div>
      </div>
      <div style="flex:1;min-width:190px;max-width:250px;text-align:left;padding:14px 16px;border-radius:13px;
                  background:rgba(45,212,167,.06);border:1px solid rgba(45,212,167,.22)">
        <div style="color:#34d399;font-size:11.5px;font-weight:800;letter-spacing:.14em">STEP 03</div>
        <div style="color:#d5e2f5;font-size:13.5px;font-weight:600;margin:5px 0 3px">查看报告</div>
        <div style="color:#7f93b5;font-size:12px;line-height:1.6">
          逐帧判定 + 分时段汇总；报告可一键下载 HTML / Markdown / CSV / JSON。
        </div>
      </div>
    </div>
  </div>
</div>
"""


# --------------------------------------------------------------------------
# 站点图标
# --------------------------------------------------------------------------
def ensure_favicon() -> str | None:
    """生成一个青色盾牌图标作为 favicon（失败时返回 None，不影响启动）。"""
    path = os.path.join(CACHE_DIR, "favicon.png")
    if os.path.exists(path):
        return path
    try:
        from PIL import Image, ImageDraw

        size = 128
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([6, 6, size - 6, size - 6], radius=26, fill=(8, 14, 28, 255),
                               outline=(34, 211, 238, 255), width=4)
        # 盾牌外形
        draw.polygon(
            [(64, 24), (100, 38), (100, 70), (64, 106), (28, 70), (28, 38)],
            fill=(34, 211, 238, 38), outline=(34, 211, 238, 255),
        )
        # 对勾
        draw.line([(46, 66), (60, 80), (86, 50)], fill=(45, 212, 167, 255), width=9, joint="curve")
        img.save(path)
        return path
    except Exception:
        return None
