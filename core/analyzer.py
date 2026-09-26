"""多模态模型分析器：把「图像 + 规则 + 提示词模板」送给视觉语言模型，取回结构化判定。"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

from .config import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_MAX_IMAGE_SIDE,
    DEFAULT_WORKERS,
    Frame,
    FrameResult,
    ModelConfig,
)
from .prompt import build_variable_values, render_template
from .rules import RuleSet

logger = logging.getLogger(__name__)

JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
THINK_TAG_RE = re.compile(r"</?think>", re.IGNORECASE)
SUMMARY_KEYS = ("判定依据总述", "依据总述", "判定依据", "summary")


# --------------------------------------------------------------------------
# 网络客户端：显式直连，避免继承到失效的会话级代理
# --------------------------------------------------------------------------
def build_http_client(conf: ModelConfig):
    """构建 HTTP 客户端。

    关键点：默认 `trust_env=False`，即**不读取** HTTP_PROXY / HTTPS_PROXY 等环境变量。
    若服务进程继承到临时或已失效的代理（例如被回收的会话代理），所有请求都会
    变成 APIConnectionError: Connection error —— 显式直连可彻底规避。
    """
    import httpx

    kwargs: Dict[str, Any] = {
        "timeout": float(conf.timeout),
        "trust_env": False,
        "follow_redirects": True,
    }
    proxy = (conf.proxy or "").strip()
    if proxy:
        try:
            return httpx.Client(proxy=proxy, **kwargs)
        except TypeError:                                   # httpx < 0.26
            return httpx.Client(proxies=proxy, **kwargs)
    return httpx.Client(**kwargs)


def describe_connection_error(exc: Exception, conf: ModelConfig) -> str:
    """把网络类异常翻译成可操作的排查建议。"""
    name = type(exc).__name__
    text = str(exc)
    if "Connection error" in text or "ConnectError" in name or "APIConnectionError" in name:
        if conf.proxy:
            head = f"无法连接模型服务（当前已配置代理 {conf.proxy}）：{text}"
            tips = [
                "1) 确认代理程序正在运行、端口填写正确；",
                "2) 若不需代理，清空界面中的「网络代理」后重试。",
            ]
        else:
            head = f"无法连接模型服务（当前为直连，已忽略系统代理环境变量）：{text}"
            tips = [
                f"1) 先在本机终端验证网络：curl -I {conf.base_url}",
                "2) 若公司网络必须走代理，请在界面「网络代理」中填写，如 http://127.0.0.1:7890；",
                "3) 确认 BaseURL 末尾带 /v1/，且本机 DNS / 防火墙未拦截；",
                "4) 若刚启动服务，稍等 2 秒后重试一次。",
            ]
        return head + "\n排查建议：\n" + "\n".join(tips)
    if "Timeout" in name or "timed out" in text.lower():
        return f"请求超时（{conf.timeout}s）：{text}\n建议：调高 timeout，或降低并发数、减小图像长边。"
    if "401" in text or "AuthenticationError" in name:
        return f"鉴权失败，请检查 API Key 是否正确或已过期：{text}"
    if "404" in text or "NotFoundError" in name:
        return f"接口或模型不存在，请检查 BaseURL 与模型名：{text}"
    if "429" in text or "RateLimit" in name:
        return f"触发限流：{text}\n建议：降低并发数后重试。"
    return f"{name}: {text}"


# --------------------------------------------------------------------------
# 图像处理
# --------------------------------------------------------------------------
def encode_image(path: str, max_side: int = DEFAULT_MAX_IMAGE_SIDE,
                 quality: int = DEFAULT_JPEG_QUALITY) -> str:
    """把本地图片编码为 data URL，长边超过 max_side 时等比缩放。"""
    with Image.open(path) as img:
        img = img.convert("RGB")
        if max_side and max(img.size) > max_side:
            ratio = max_side / float(max(img.size))
            new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
            img = img.resize(new_size, Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def encode_thumbnail(path: str, max_side: int = 320, quality: int = 60) -> str:
    """生成用于报告内嵌的小缩略图 data URL。"""
    try:
        return encode_image(path, max_side=max_side, quality=quality)
    except Exception:
        return ""


# --------------------------------------------------------------------------
# JSON 解析
# --------------------------------------------------------------------------
def _strip_wrappers(text: str) -> str:
    text = THINK_TAG_RE.sub("", text or "").strip()
    fence = JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    return text.strip()


def _balanced_json_slice(text: str) -> Optional[str]:
    """从文本中截出第一个结构完整的 {...} 片段。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def _repair_json(text: str) -> str:
    """修复常见的非严格 JSON：尾随逗号、中文引号、单引号键值。"""
    text = text.replace("，", ",").replace("：", ":") if text.count("，") > 0 and '"' not in text else text
    text = re.sub(r",\s*([}\]])", r"\1", text)          # 去掉尾随逗号
    text = text.replace("“", '"').replace("”", '"')      # 中文双引号
    return text


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """尽最大努力从模型输出中抽出 JSON 对象。"""
    cleaned = _strip_wrappers(text)
    candidates: List[str] = []
    if cleaned:
        candidates.append(cleaned)
        sliced = _balanced_json_slice(cleaned)
        if sliced:
            candidates.append(sliced)
    for raw in candidates:
        for candidate in (raw, _repair_json(raw)):
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    return None


# --------------------------------------------------------------------------
# 取值匹配与违规判定
# --------------------------------------------------------------------------
def match_value(raw: Any, candidates: List[str]) -> str:
    """把模型返回的取值归一到规则声明的合法取值。"""
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    ordered = sorted([c for c in candidates if c], key=len, reverse=True)
    for candidate in ordered:
        if text == candidate:
            return candidate
    for candidate in ordered:
        if candidate in text:
            return candidate
    return text


def detect_violations(parsed: Dict[str, Any], ruleset: RuleSet) -> Tuple[List[str], Dict[str, str]]:
    """对照规则判断每个字段的取值，返回（违规字段列表, 归一后的取值表）。"""
    violations: List[str] = []
    normalized: Dict[str, str] = {}
    for rule in ruleset.fields:
        raw = None
        for key in (rule.name, rule.name.strip(), rule.name.replace(" ", "")):
            if key in parsed:
                raw = parsed[key]
                break
        if raw is None:                                  # 宽松匹配：忽略空格/标点
            target = re.sub(r"[\s，。？?、：:]", "", rule.name)
            for k, v in parsed.items():
                if re.sub(r"[\s，。？?、：:]", "", str(k)) == target:
                    raw = v
                    break
        if raw is None:
            continue
        value = match_value(raw, rule.allowed_values)
        normalized[rule.name] = value
        if not rule.violation_values:
            continue
        hit = value in rule.violation_values or any(
            v and v in str(raw) for v in rule.violation_values
        )
        if hit:
            violations.append(rule.name)
    return violations, normalized


# --------------------------------------------------------------------------
# 分析器
# --------------------------------------------------------------------------
class VLMAnalyzer:
    """封装与多模态模型的交互。"""

    def __init__(self, model_config: ModelConfig, workers: int = DEFAULT_WORKERS,
                 max_image_side: int = DEFAULT_MAX_IMAGE_SIDE):
        from openai import OpenAI

        self.conf = model_config
        self.workers = max(1, int(workers))
        self.max_image_side = max_image_side
        # 显式传入 http_client（trust_env=False），不使用环境变量里的代理
        self._http_client = build_http_client(model_config)
        self._client = OpenAI(
            base_url=model_config.base_url,
            api_key=model_config.api_key,
            timeout=model_config.timeout,
            max_retries=0,
            http_client=self._http_client,
        )

    # ---------------------------------------------------------------- 单帧
    def analyze_frame(
        self,
        frame: Frame,
        ruleset: RuleSet,
        template: str,
        extra_context: str = "",
        user_values: Optional[Dict[str, Any]] = None,
        retries: int = 2,
    ) -> FrameResult:
        """分析单帧图像，返回结构化结果。"""
        started = time.time()
        result = FrameResult(frame=frame)
        try:
            data_url = encode_image(frame.path, max_side=self.max_image_side)
        except Exception as exc:
            result.error = f"图像读取失败：{exc}"
            result.latency = time.time() - started
            return result

        values = build_variable_values(
            rules_text=ruleset.as_text(),
            frame_time=frame.time_str(),
            camera_name=frame.source or "未命名点位",
            extra_context=extra_context,
            user_values=user_values,
        )
        rendered = render_template(template, values)
        prompt_text = rendered.text
        if rendered.missing:
            prompt_text += (
                "\n\n（注：模板中未提供取值的变量：" + "、".join(rendered.missing) + "，请忽略。）"
            )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        if frame.note:
            messages.insert(0, {"role": "system", "content": frame.note})

        last_error = ""
        for attempt in range(retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.conf.model,
                    messages=messages,
                    temperature=self.conf.temperature,
                    max_tokens=self.conf.max_tokens,
                )
                message = response.choices[0].message
                content = (message.content or "").strip()
                reasoning = getattr(message, "reasoning_content", None) or ""
                raw = content or reasoning
                result.raw = raw
                if getattr(response, "usage", None):
                    result.usage = response.usage.model_dump() if hasattr(response.usage, "model_dump") else dict(response.usage)
                parsed = extract_json(content) or extract_json(reasoning)
                if parsed is None:
                    last_error = "模型输出中未找到合法 JSON"
                    if attempt < retries:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    result.error = last_error
                    result.latency = time.time() - started
                    return result
                result.parsed = parsed
                result.violations, normalized = detect_violations(parsed, ruleset)
                result.parsed.update({f"__归一取值__{k}": v for k, v in normalized.items()})
                result.ok = True
                result.latency = time.time() - started
                return result
            except Exception as exc:                       # noqa: BLE001
                last_error = describe_connection_error(exc, self.conf)
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
        result.error = last_error
        result.latency = time.time() - started
        return result

    # ------------------------------------------------------------ 批量并发
    def analyze_frames(
        self,
        frames: List[Frame],
        ruleset: RuleSet,
        template: str,
        extra_context: str = "",
        user_values: Optional[Dict[str, Any]] = None,
        retries: int = 2,
        on_progress: Optional[Callable[[int, int, FrameResult], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> List[FrameResult]:
        """并发分析多帧，保持与输入相同的顺序。返回结果列表。"""
        results: List[Optional[FrameResult]] = [None] * len(frames)
        if not frames:
            return []

        def task(pos_frame: Tuple[int, Frame]) -> Tuple[int, FrameResult]:
            pos, frame = pos_frame
            return pos, self.analyze_frame(
                frame, ruleset, template, extra_context, user_values, retries=retries
            )

        done = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(task, item): item[0] for item in enumerate(frames)}
            for future in as_completed(futures):
                pos, result = future.result()
                results[pos] = result
                done += 1
                if on_progress:
                    on_progress(done, len(frames), result)
                if should_stop and should_stop():
                    for f in futures:
                        f.cancel()
                    break

        return [r for r in results if r is not None]

    # -------------------------------------------------------------- 连通性
    def test_connection(self) -> Tuple[bool, str]:
        """用一张程序生成的图片测试模型连通性与图像输入能力。"""
        try:
            img = Image.new("RGB", (640, 400), (32, 40, 56))
            from PIL import ImageDraw

            draw = ImageDraw.Draw(img)
            draw.rectangle([60, 240, 580, 360], fill=(70, 85, 110))
            draw.ellipse([260, 100, 380, 220], fill=(240, 196, 92))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            payload = base64.b64encode(buffer.getvalue()).decode("ascii")
            data_url = f"data:image/jpeg;base64,{payload}"

            response = self._client.chat.completions.create(
                model=self.conf.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "这张图里有一个圆形和一个矩形，请用一句话说明圆形和矩形分别是什么颜色。"},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                temperature=0.0,
                max_tokens=256,
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                reasoning = getattr(response.choices[0].message, "reasoning_content", "") or ""
                content = reasoning.strip()
            return True, f"连接成功（模型：{response.model}）\n模型回复：{content[:300]}"
        except Exception as exc:                            # noqa: BLE001
            return False, describe_connection_error(exc, self.conf)


def list_models(conf: ModelConfig) -> Tuple[bool, List[str], str]:
    """查询接口支持的模型列表（部分网关不支持，失败时不影响主流程）。"""
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=conf.base_url,
            api_key=conf.api_key,
            timeout=conf.timeout,
            http_client=build_http_client(conf),
        )
        data = client.models.list()
        return True, sorted(m.id for m in data.data), ""
    except Exception as exc:                                # noqa: BLE001
        return False, [], describe_connection_error(exc, conf)
