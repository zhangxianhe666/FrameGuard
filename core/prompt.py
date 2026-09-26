"""提示词模板引擎：把 {{变量}} 注入到模板中。

设计借鉴了「变量占位 + 运行时注入」的提示词组织方式：
模板文件里用 {{VAR}} 占位，运行时由变量表填充，从而实现
「同一套提示词逻辑，适配不同图像 / 不同识别规则 / 不同摄像机」。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import PROMPT_DIR

# 匹配 {{ 变量名 }}，变量名允许中文、字母、数字、下划线
VAR_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


@dataclass
class PromptVariable:
    """一个模板变量的定义。"""

    name: str
    label: str
    description: str = ""
    default: str = ""
    auto: bool = True   # True 表示由程序自动填充（如图像、时间），False 表示用户填写


@dataclass
class RenderedPrompt:
    """渲染后的提示词 + 渲染元信息。"""

    text: str
    used: Dict[str, str] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# 变量注册表：界面据此展示可用变量，并做校验
# --------------------------------------------------------------------------
VARIABLES: List[PromptVariable] = [
    PromptVariable(
        name="IMAGE_WORKPLACE_MONITOR",
        label="监控图像",
        description="待分析的工作场所监控图像。以图片附件形式随消息发送，模板中由程序自动置入占位说明。",
        default="【本帧监控图像已作为图片附件随本条消息提供，请直接查看附件图片】",
    ),
    PromptVariable(
        name="RECOGNITION_RULES",
        label="员工状态识别规则",
        description="用户自定义的识别规则全文，是模型判定的唯一依据，决定输出字段名与合法取值。",
        default="",
        auto=False,
    ),
    PromptVariable(
        name="FRAME_TIME",
        label="图像时间",
        description="本帧图像的拍摄 / 采集时间，由程序自动填充。",
        default="",
    ),
    PromptVariable(
        name="CAMERA_NAME",
        label="点位名称",
        description="摄像机编号或点位名称 / 图片来源标识，由程序自动填充。",
        default="未命名点位",
    ),
    PromptVariable(
        name="EXTRA_CONTEXT",
        label="补充上下文",
        description="额外的场景说明（如「该画面为夜间红外模式」「该区域为配电房」），可选。",
        default="无",
        auto=False,
    ),
]


def variable_map() -> Dict[str, PromptVariable]:
    return {v.name: v for v in VARIABLES}


def render_template(template: str, values: Dict[str, Any], strict: bool = False) -> RenderedPrompt:
    """把模板中的 {{VAR}} 替换为 values 中对应的值。

    - 变量缺失时：strict=True 抛错；否则保留原占位符并记入 missing。
    - 未在模板中出现的变量会被忽略（记入 unused，便于排查）。
    """
    used: Dict[str, str] = {}
    missing: List[str] = []

    def _replace(match: "re.Match[str]") -> str:
        name = match.group(1).strip()
        if name in values and values[name] is not None:
            used[name] = str(values[name])
            return str(values[name])
        if strict:
            raise KeyError(f"提示词模板缺少变量：{name}")
        missing.append(name)
        return match.group(0)

    text = VAR_PATTERN.sub(_replace, template)
    return RenderedPrompt(text=text, used=used, missing=missing)


def list_template_variables(template: str) -> List[str]:
    """列出模板中出现的所有变量名（按出现顺序去重）。"""
    seen: List[str] = []
    for match in VAR_PATTERN.finditer(template):
        name = match.group(1).strip()
        if name not in seen:
            seen.append(name)
    return seen


# --------------------------------------------------------------------------
# 默认提示词模板（与参考实现保持一致的结构）
# --------------------------------------------------------------------------
DEFAULT_TEMPLATE = """你是一位专业的职场安全合规图像分析专员，具备精准的人员行为识别、场景合规判定能力，能够严格对照给定规则客观完成图像内容分析，不会加入主观臆测内容。你的任务是对照提供的员工状态识别规则，仔细分析指定的工作场所监控图像，完成员工状态识别并按要求输出结果。

## 输入说明
- 待分析的工作场所监控图像：{{IMAGE_WORKPLACE_MONITOR}}
- 员工状态识别规则：{{RECOGNITION_RULES}}（该内容明确了需要识别的所有员工状态维度、每个维度的判定标准、对应输出字段名称及合法取值范围，是你完成判定的唯一依据）
- 图像采集时间：{{FRAME_TIME}}
- 摄像机点位：{{CAMERA_NAME}}
- 补充上下文：{{EXTRA_CONTEXT}}

## 工作流程
1.  **规则梳理**：首先完整、准确理解给定的员工状态识别规则，逐条梳理清楚所有需要判定的状态项，明确每个状态项的判定边界、合法输出值，确保不遗漏任何一个需要判定的维度。
2.  **图像观察**：仔细、全面观察待分析的监控图像，覆盖画面所有区域（包括角落、边缘位置），准确识别图像中所有可见的人员数量、人员动作、穿戴物品、周边工具/设备、场景状态等客观事实，不遗漏任何细节。
3.  **逐项判定**：严格对照识别规则中的每一项判定标准，基于图像中可见的客观事实逐一完成每个状态项的判定：
    - 如果图像内容完全符合某状态项的"是"类判定条件，则将该状态项判定为对应值；
    - 如果图像内容符合某状态项的"否"类判定条件，则将该状态项判定为对应值；
    - 如果规则中明确了无相关判定对象时的默认取值，需严格按照规则要求填写默认值；
    - 若图像中没有出现规则所描述的对象（例如画面中无人），则严格按规则给出的默认取值填写，不得凭空推断。
    - 严禁基于画面外的猜测、个人日常经验做出不符合图像事实的判定。
4.  **依据整理**：在完成所有判定后，整理所有判定对应的客观事实，形成清晰的判定依据，依据必须具体描述图像中可见的内容，不能使用模糊、笼统的表述。

## 输出格式要求
1.  所有识别结果必须输出为标准合法的JSON格式字符串，不得输出JSON以外的任何解释、说明内容。
2.  JSON结构第一层为对象，必须包含以下内容：
    - 第一个字段为`判定依据总述`：字符串类型，清晰描述你观察到的图像客观事实，说明所有判定对应的画面依据；
    - 后续字段严格对应识别规则中要求的所有状态项字段，字段名与规则要求完全一致，字段值为规则中规定的合法取值。
3.  JSON中的字符串值需严格遵循JSON语法规范，如有特殊字符需正确转义。

请严格按照上述流程和格式要求，基于提供的图像和识别规则完成分析，仅输出符合要求的JSON内容，不要输出任何 markdown 代码块标记。"""


def load_default_template() -> str:
    path = os.path.join(PROMPT_DIR, "workplace_safety.md")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    return DEFAULT_TEMPLATE


def build_variable_values(
    rules_text: str,
    frame_time: str = "",
    camera_name: str = "",
    extra_context: str = "",
    user_values: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """组装一次渲染所需的全部变量值。"""
    values: Dict[str, str] = {
        "IMAGE_WORKPLACE_MONITOR": variable_map()["IMAGE_WORKPLACE_MONITOR"].default,
        "RECOGNITION_RULES": rules_text,
        "FRAME_TIME": frame_time or "未提供",
        "CAMERA_NAME": camera_name or "未命名点位",
        "EXTRA_CONTEXT": extra_context.strip() or "无",
    }
    if user_values:
        values.update({k: v for k, v in user_values.items() if v is not None})
    return values
