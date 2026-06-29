# -*- coding: utf-8 -*-
"""AutoGLM-9B adapter — do()/finish() 格式，坐标 0-1000。"""
from __future__ import annotations

import ast
import logging
import re
from datetime import datetime
from typing import Optional

from model.adapters import AdapterBase
from model.adapters._common import build_messages_standard
from model.device_info import resolve_device_info

logger = logging.getLogger(__name__)

_ACTION_MAP = {
    "Tap": "Tap",
    "Long Press": "LongPress",
    "Double Tap": "Tap",
    "Swipe": "Swipe",
    "Type": "Type",
    "Type_Name": "Type",
    "Launch": "Open",
    "Back": "Back",
    "Home": "Home",
    "Wait": "Wait",
    "Take_over": "Request",
    "Interact": "Request",
    "Note": "Wait",
    "Call_API": "Wait",
}


class AutoglmAdapter(AdapterBase):
    name = "autoglm"

    def system_prompt(self, device_type: str = "phone") -> str:
        prompt = super().system_prompt(device_type)
        return prompt.replace("{date}", datetime.now().strftime("%Y-%m-%d"))

    def build_messages(self, **kwargs) -> list[dict]:
        return build_messages_standard(**kwargs)

    def parse_response(self, content: str, message: Optional[dict] = None) -> dict:
        return _parse_autoglm_response(content, message)

    def payload_extras(self) -> dict:
        return {"temperature": 0.0, "top_p": 0.01, "top_k": 1}


def _parse_autoglm_response(content: str, message: dict | None = None) -> dict:
    if not content or not isinstance(content, str):
        return {"thought": "模型返回为空", "func": "Wait", "action": "", "raw_model_output": ""}

    raw = content.strip()
    thinking, action_str = _split_thinking_action(raw)
    if not action_str:
        return {"thought": thinking or "无法解析动作", "func": "Wait", "action": "", "raw_model_output": raw}

    try:
        result = _parse_action_string(action_str.strip())
        return _convert_to_guiness(result, thinking, raw)
    except Exception as e:
        logger.warning(f"autoglm action 解析失败: {e}, action_str={action_str[:100]}")
        return {"thought": thinking or "动作解析失败", "func": "Wait", "action": "", "raw_model_output": raw}


def _split_thinking_action(content: str) -> tuple[str, str]:
    idx = content.find('finish(message=')
    if idx != -1:
        return _strip_think_tags(content[:idx].strip()), content[idx:]

    idx = content.find('do(action=')
    if idx != -1:
        return _strip_think_tags(content[:idx].strip()), content[idx:]

    answer_match = re.search(r'<answer>(.*?)</answer>', content, re.DOTALL)
    if answer_match:
        before = content[:answer_match.start()]
        return _strip_think_tags(before.strip()), answer_match.group(1).strip()

    think_match = re.search(r'<think>(.*?)</think>(.*)', content, re.DOTALL)
    if think_match:
        remainder = think_match.group(2).strip()
        if remainder:
            return think_match.group(1).strip(), remainder

    return "", ""


def _strip_think_tags(text: str) -> str:
    return re.sub(r'</?think>', '', text).strip()


def _parse_action_string(action_str: str) -> dict:
    action_str = action_str.strip()

    if action_str.startswith('finish('):
        return {"_type": "finish", "message": _extract_finish_message(action_str)}

    if re.match(r'do\(action="Type', action_str):
        return _parse_type_action(action_str)

    if action_str.startswith('do('):
        return _parse_do_with_ast(action_str)

    raise ValueError(f"无法识别的 action 格式: {action_str[:80]}")


def _extract_finish_message(action_str: str) -> str:
    try:
        escaped = action_str.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        tree = ast.parse(escaped, mode='eval')
        if isinstance(tree.body, ast.Call):
            for kw in tree.body.keywords:
                if kw.arg == "message":
                    return ast.literal_eval(kw.value)
    except Exception:
        pass
    match = re.search(r'finish\(message=["\'](.+?)["\']\s*\)', action_str, re.DOTALL)
    if match:
        return match.group(1)
    content = action_str[len('finish(message='):]
    if content.startswith('"') or content.startswith("'"):
        content = content[1:]
    if content.endswith(')'):
        content = content[:-1]
    if content.endswith('"') or content.endswith("'"):
        content = content[:-1]
    return content


def _parse_type_action(action_str: str) -> dict:
    action_match = re.match(r'do\(action="(Type(?:_Name)?)"', action_str)
    action_name = action_match.group(1) if action_match else "Type"
    text_match = re.search(r'text=["\'](.+?)["\']\s*\)', action_str, re.DOTALL)
    text = text_match.group(1) if text_match else ""
    return {"_type": "do", "action": action_name, "text": text}


def _parse_do_with_ast(action_str: str) -> dict:
    escaped = action_str.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    try:
        tree = ast.parse(escaped, mode='eval')
        if not isinstance(tree.body, ast.Call):
            raise ValueError("不是函数调用")
        result = {"_type": "do"}
        for kw in tree.body.keywords:
            result[kw.arg] = ast.literal_eval(kw.value)
        return result
    except Exception:
        return _parse_do_with_regex(action_str)


def _parse_do_with_regex(action_str: str) -> dict:
    result = {"_type": "do"}
    for pattern, key in [
        (r'action="([^"]+)"', "action"),
        (r'element=\[(\d+)\s*,\s*(\d+)\]', "element"),
        (r'start=\[(\d+)\s*,\s*(\d+)\]', "start"),
        (r'end=\[(\d+)\s*,\s*(\d+)\]', "end"),
        (r'text="([^"]*)"', "text"),
        (r'app="([^"]*)"', "app"),
        (r'message="([^"]*)"', "message"),
    ]:
        m = re.search(pattern, action_str)
        if m:
            if key in ("element", "start", "end"):
                result[key] = [int(m.group(1)), int(m.group(2))]
            else:
                result[key] = m.group(1)
    return result


def _convert_to_guiness(parsed: dict, thinking: str, raw: str) -> dict:
    base = {"thought": thinking, "action": "", "raw_model_output": raw}

    if parsed.get("_type") == "finish":
        base["func"] = "Complete"
        base["text"] = parsed.get("message", "任务完成")
        return base

    action_name = parsed.get("action", "")
    func = _ACTION_MAP.get(action_name, "Wait")
    base["func"] = func

    if action_name in ("Tap", "Double Tap"):
        element = parsed.get("element", [500, 500])
        base["position"] = [round(element[0] / 1000.0, 3), round(element[1] / 1000.0, 3)]
        base["times"] = 2 if action_name == "Double Tap" else 1
    elif action_name == "Long Press":
        element = parsed.get("element", [500, 500])
        base["position"] = [round(element[0] / 1000.0, 3), round(element[1] / 1000.0, 3)]
    elif action_name == "Swipe":
        start = parsed.get("start", [500, 200])
        end = parsed.get("end", [500, 800])
        base["start_position"] = [round(start[0] / 1000.0, 3), round(start[1] / 1000.0, 3)]
        base["end_position"] = [round(end[0] / 1000.0, 3), round(end[1] / 1000.0, 3)]
    elif action_name in ("Type", "Type_Name"):
        base["text"] = parsed.get("text", "")
        base["position"] = [0.5, 0.5]
    elif action_name == "Launch":
        base["app"] = parsed.get("app", "")
    elif action_name in ("Take_over", "Interact"):
        base["text"] = parsed.get("message", "需要用户介入")

    return base
