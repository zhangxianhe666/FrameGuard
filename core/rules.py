"""识别规则解析：从规则文本中提取字段名、合法取值、违规取值与判定标准。

规则书写约定（推荐格式）：

    ## 识别规则

    ### 1. 是否所有人员都佩戴安全帽
    - 字段名：是否所有人员都佩戴安全帽
    - 合法取值：是 / 否
    - 违规取值：否
    - 判定标准：观察图像中所有可见人员的头部……

其中「字段名 / 合法取值 / 违规取值」为可选项：
  - 未写「字段名」时，取小节标题作为字段名；
  - 未写「违规取值」时，程序会依据字段命名语义自动推断（并在界面中标注为「自动推断」）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# 小节标题：### 1. 标题 / ### 标题 / ## 标题
HEADING_RE = re.compile(r"^#{2,4}\s*(?:\d+[.、)）:：]\s*)?(.+?)\s*$", re.MULTILINE)
# 键值行：- 字段名：xxx
KV_RE = re.compile(
    r"^\s*[-*+>]?\s*(字段名|字段|名称|合法取值|取值范围|可选值|违规取值|违规值|判定标准|判定依据|说明)\s*[:：]\s*(.*)$",
    re.MULTILINE,
)
# 小节编号前缀，如 "1. " "1、" "（1）"
INDEX_PREFIX_RE = re.compile(r"^(?:第?\s*\d+\s*[.、)）:：]|[(（]\s*\d+\s*[)）])\s*")

KEY_ALIASES = {
    "字段名": "name",
    "字段": "name",
    "名称": "name",
    "合法取值": "allowed",
    "取值范围": "allowed",
    "可选值": "allowed",
    "违规取值": "violation",
    "违规值": "violation",
    "判定标准": "criteria",
    "判定依据": "criteria",
    "说明": "criteria",
}

# 取值范围分隔符：/ 、 ， , ｜ | ；
SPLIT_RE = re.compile(r"\s*[/、,，|｜;；]\s*")

# 语义推断用的关键词
_UNDESIRED_HINTS = [
    "是否存在", "是否有", "有无",
    "违规", "违章", "吸烟", "抽烟", "烟火", "明火",
    "手机", "玩手机", "接打电话", "打电话",
    "打瞌睡", "睡觉", "睡岗", "瞌睡",
    "离岗", "脱岗", "串岗", "擅自离开",
    "聚集", "扎堆", "追逐", "打闹", "嬉戏", "奔跑",
    "攀爬", "翻越", "跨越", "倚靠",
    "无人", "缺岗", "缺席", "空岗",
    "未佩戴", "未穿戴", "未穿", "未戴", "未按", "未规范", "未正", "未使用", "未覆盖", "未关闭", "未上锁",
    "危险", "隐患", "杂物", "堵塞", "占用", "阻挡",
    "饮酒", "醉酒", "进食", "吃东西",
]
_DESIRED_HINTS = [
    "所有人员都", "是否都", "都佩", "都穿", "都戴",
    "是否正确", "是否规范", "是否合规", "是否正常", "是否完好", "是否有效",
    "是否牢固", "是否齐全", "是否整洁", "是否到位", "是否关闭", "是否上锁",
    "是否在岗", "是否在位", "是否佩戴", "是否穿着", "是否穿戴",
]


@dataclass
class RuleField:
    """单个判定维度。"""

    name: str
    allowed_values: List[str] = field(default_factory=list)
    violation_values: List[str] = field(default_factory=list)
    criteria: str = ""
    inferred: bool = False        # 违规取值是否为语义自动推断
    index: int = 0

    def describe(self) -> str:
        parts = [f"字段名：{self.name}"]
        if self.allowed_values:
            parts.append("合法取值：" + " / ".join(self.allowed_values))
        if self.violation_values:
            tag = "（自动推断）" if self.inferred else ""
            parts.append("违规取值：" + " / ".join(self.violation_values) + tag)
        if self.criteria:
            parts.append("判定标准：" + self.criteria)
        return "\n".join(parts)


@dataclass
class RuleSet:
    """解析后的规则集合。"""

    raw_text: str
    fields: List[RuleField] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def field_names(self) -> List[str]:
        return [f.name for f in self.fields]

    @property
    def violation_map(self) -> Dict[str, List[str]]:
        return {f.name: f.violation_values for f in self.fields}

    @property
    def fields_without_violation(self) -> List[str]:
        return [f.name for f in self.fields if not f.violation_values]

    def as_text(self) -> str:
        """把解析结果还原成规整的规则文本，用于回填到提示词。"""
        chunks = []
        for i, f in enumerate(self.fields, 1):
            chunks.append(f"### {i}. {f.name}\n{f.describe()}")
        return "\n\n".join(chunks) if chunks else self.raw_text


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def _split_values(text: str) -> List[str]:
    if not text:
        return []
    values = [v.strip().strip("`\"'[]()（）") for v in SPLIT_RE.split(text)]
    return [v for v in values if v and v not in {"无", "无相关判定对象", "不适用"}]


def infer_violation_values(name: str, allowed: List[str]) -> List[str]:
    """依据字段命名语义推断违规取值。

    例：
      「是否存在人员在岗使用手机」 → 违规值「是」
      「是否所有人员都佩戴安全帽」 → 违规值「否」
    """
    normalized_allowed = [a for a in allowed] if allowed else ["是", "否"]
    has_yes_no = any(a in {"是", "否"} for a in normalized_allowed)
    if not has_yes_no:
        return []
    for hint in _UNDESIRED_HINTS:
        if hint in name:
            return ["是"]
    for hint in _DESIRED_HINTS:
        if hint in name:
            return ["否"]
    return []


def parse_rules(text: str) -> RuleSet:
    """把规则文本解析为 RuleSet。"""
    text = (text or "").strip()
    ruleset = RuleSet(raw_text=text)
    if not text:
        ruleset.warnings.append("识别规则为空，无法提取判定字段。")
        return ruleset

    # 1) 按小节切分
    sections: List[Tuple[str, str]] = []
    matches = list(HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        title = INDEX_PREFIX_RE.sub("", m.group(1).strip()).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((title, text[start:end]))

    # 没有小节标题时，退化为整体解析（只取键值行）
    if not sections:
        sections = [("", text)]

    seen_names: Dict[str, int] = {}
    for idx, (title, body) in enumerate(sections, 1):
        kv: Dict[str, str] = {}
        for m in KV_RE.finditer(body):
            key = KEY_ALIASES.get(m.group(1).strip())
            value = m.group(2).strip()
            if key and value and key not in kv:
                kv[key] = value

        name = kv.get("name") or title
        if not name:
            continue
        name = INDEX_PREFIX_RE.sub("", name).strip()
        if len(name) > 60:                      # 明显是说明性长句，不作为字段
            continue
        if any(tok in name for tok in ("输入说明", "工作流程", "输出格式", "示例", "输出示例")):
            continue

        allowed = _split_values(kv.get("allowed", ""))
        violation = _split_values(kv.get("violation", ""))
        inferred = False
        if not violation:
            violation = infer_violation_values(name, allowed)
            inferred = bool(violation)

        # 去重（同名小节只保留首次出现）
        if name in seen_names:
            continue
        seen_names[name] = idx

        ruleset.fields.append(
            RuleField(
                name=name,
                allowed_values=allowed,
                violation_values=violation,
                criteria=kv.get("criteria", "").strip(),
                inferred=inferred,
                index=len(ruleset.fields) + 1,
            )
        )

    if not ruleset.fields:
        ruleset.warnings.append(
            "未能从规则文本中解析出判定字段。请按「### 标题 + - 字段名：…」的格式书写规则。"
        )
    if ruleset.fields_without_violation:
        ruleset.warnings.append(
            "以下字段未配置违规取值且无法自动推断，报告中将仅记录判定值、不计入违规统计："
            + "、".join(ruleset.fields_without_violation)
        )
    if any(f.inferred for f in ruleset.fields):
        inferred_names = [f.name for f in ruleset.fields if f.inferred]
        ruleset.warnings.append(
            "以下字段的违规取值为语义自动推断结果，建议在规则中显式写明「- 违规取值：…」："
            + "、".join(inferred_names)
        )
    return ruleset


def load_rules_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()
