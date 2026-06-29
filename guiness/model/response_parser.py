# -*- coding: utf-8 -*-
"""模型响应解析：把 <think>/<action>/<tool_call> 文本还原为标准 action dict。

模型输出格式（参考 prompts/custom.txt）：
  <think>reasoning</think>
  <action>natural language description</action>
  <tool_call>{"name": "Tap", "position": [0.5, 0.3], "times": 1}</tool_call>

兼容旧格式 <thought>/<answer>。
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


# 与 action_space 对齐：决定 get_content() 往历史里写哪些字段。
FUNC_REQUIRED_DICT: dict[str, list[str]] = {
    "Open": ["app"],
    "Tap": ["position", "times"],
    "Type": ["position", "text"],
    "Search": ["position", "text"],
    "LongPress": ["position"],
    "Swipe": ["start_position", "end_position"],
    "Wait": [],
    "Speak": ["text"],
    "Request": ["text"],
    "ToolUse": ["type"],
    "Complete": [],
    "Fail": ["type", "reason"],
    "Back": [],
}


def get_content(label: dict, is_history: bool = False) -> str:
    """生成 assistant content：`<think>...</think><action>...</action><tool_call>...</tool_call>`。

    仅保留 FUNC_REQUIRED_DICT 中声明的必需字段，与训练数据预处理一致。
    """
    thought = label.get("thought", "")
    think = thought.split("<action>")[0].strip() if "<action>" in thought else thought.strip()
    action_desc = label.get("action", "")
    if not action_desc and "<action>" in thought:
        action_desc = thought.split("<action>")[1].split("</action>")[0].strip()

    func = label.get("func", "")
    tool_call: dict = {"name": func}
    for key in FUNC_REQUIRED_DICT.get(func, []):
        if label.get(key):
            tool_call[key] = label[key]

    parts = [f"<think>{think}</think>"]
    if action_desc:
        parts.append(f"<action>{action_desc}</action>")
    parts.append(f"<tool_call>{json.dumps(tool_call, ensure_ascii=False)}</tool_call>")
    return "".join(parts)


def _try_parse_json(text: str):
    """尝试解析 JSON，容错若干不规范格式（单引号、key 无引号等）。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(text.replace("'", '"'))
    except json.JSONDecodeError:
        pass
    # key 无引号：{func: "Tap"} → {"func": "Tap"}
    try:
        fixed = re.sub(r'(?<=[{,])\s*(\w+)\s*:', r' "\1":', text)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # key 和中文 value 都无引号
    try:
        fixed = re.sub(r'(?<=[{,])\s*(\w+)\s*:\s*([^\s\d\[\]{}"\'][^,}\]]*)', r' "\1": "\2"', text)
        fixed = re.sub(r'(?<=[{,])\s*(\w+)\s*:', r' "\1":', fixed)
        return json.loads(fixed)
    except (json.JSONDecodeError, Exception):
        pass
    # 最外层 {...}
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match and match.group() != text:
        return _try_parse_json(match.group())
    return None


def _extract_tag(text: str, open_tag: str, close_tag: str) -> str:
    """从文本中提取指定标签的内容。"""
    if open_tag in text:
        parts = text.split(open_tag, 1)
        if len(parts) > 1:
            inner = parts[1].split(close_tag, 1)[0].strip()
            return inner
    return ""


def _strip_code_fence(text: str) -> str:
    """去掉 markdown code fence 包裹。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rfind("```") > -1:
            text = text[: text.rfind("```")]
    return text.strip()


def parse_model_response(response, message=None) -> dict:
    """把模型原始文本解析成 action dict；解析失败回退为 Wait。

    支持的输出格式（按优先级）：
    1. 新格式: <think>...</think><action>...</action><tool_call>{JSON}</tool_call>
    2. 旧格式: <think>...</think><answer>{JSON}</answer>
    3. 旧格式: <thought>...</thought>{JSON}
    """
    if isinstance(response, dict):
        return response

    try:
        clean_response = response.strip()

        # --- 提取 think content ---
        think_content = ""
        for open_tag, close_tag in (("<analyze>", "</analyze>"), ("<think>", "</think>"), ("<thought>", "</thought>")):
            think_content = _extract_tag(clean_response, open_tag, close_tag)
            if think_content:
                break

        # 有些 provider 不回 <think> 而是在 message 里带 reasoning_*
        if not think_content and message and isinstance(message, dict):
            for key in message.keys():
                if "reasoning" in key.lower():
                    value = message[key]
                    if isinstance(value, str):
                        think_content = value.strip()
                    break

        # --- 提取 action description ---
        action_desc = _extract_tag(clean_response, "<action>", "</action>")

        # --- 提取 command JSON ---
        command_json = None

        # 优先: <tool_call>...</tool_call>
        tool_call_content = _extract_tag(clean_response, "<tool_call>", "</tool_call>")
        if tool_call_content:
            tool_call_content = _strip_code_fence(tool_call_content)
            command_json = _try_parse_json(tool_call_content)

        # 兼容: <answer>...</answer>
        if not command_json:
            answer_content = _extract_tag(clean_response, "<answer>", "</answer>")
            if answer_content:
                answer_content = _strip_code_fence(answer_content)
                command_json = _try_parse_json(answer_content)

        # 兜底: </analyze> 或 </think> 或 </thought> 之后的裸 JSON
        if not command_json:
            remaining = clean_response
            if "</analyze>" in remaining:
                remaining = remaining.split("</analyze>", 1)[-1].strip()
            elif "</thought>" in remaining:
                remaining = remaining.split("</thought>", 1)[-1].strip()
            elif "</think>" in remaining:
                remaining = remaining.split("</think>", 1)[-1].strip()
            if "</action>" in remaining:
                remaining = remaining.split("</action>", 1)[-1].strip()
            remaining = _strip_code_fence(remaining)
            if remaining:
                command_json = _try_parse_json(remaining)

        if command_json:
            result = dict(command_json)
            # "name" → "func" 兼容：新 prompt 用 name，下游用 func
            if "name" in result and "func" not in result:
                result["func"] = result.pop("name")
            # thought 可能直接在 JSON 里（旧格式兼容）
            if not think_content and result.get("thought"):
                think_content = result["thought"]
            result["thought"] = think_content
            result["action"] = action_desc
            result["raw_model_output"] = response if isinstance(response, str) else str(response)
            return result

        logger.warning("解析 command_json 失败, 将执行 Wait")
        result = {"thought": think_content or "预测错误，等待。", "func": "Wait", "action": action_desc}
        result["raw_model_output"] = response if isinstance(response, str) else str(response)
        return result

    except Exception as e:
        logger.error(f"response format error: {str(e)[:100]}...")
        result = {"thought": "解析异常，等待。", "func": "Wait", "action": ""}
        result["raw_model_output"] = response if isinstance(response, str) else str(response)
        return result
