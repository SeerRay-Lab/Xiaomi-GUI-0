# -*- coding: utf-8 -*-
"""豆包 Doubao-Seed adapter — Thought/Action 格式，坐标用 <point>x y</point>。"""
from __future__ import annotations

import logging
import re
from typing import Optional

from model.adapters import AdapterBase
from model.adapters._common import build_messages_standard

logger = logging.getLogger(__name__)

_ACTION_MAP = {
    "click": "Tap",
    "long_press": "LongPress",
    "type": "Type",
    "scroll": "Scroll",
    "open_app": "Open",
    "drag": "Swipe",
    "press_home": "Home",
    "press_back": "Back",
    "wait": "Wait",
    "finished": "Complete",
}


class DoubaoAdapter(AdapterBase):
    name = "doubao"

    def system_prompt(self, device_type: str = "phone") -> str:
        prompt = super().system_prompt(device_type)
        return prompt

    def build_messages(self, **kwargs) -> list[dict]:
        return build_messages_standard(**kwargs)

    def parse_response(self, content: str, message: Optional[dict] = None) -> dict:
        return _parse_doubao_response(content, message)

    def payload_extras(self) -> dict:
        return {"temperature": 0.0, "top_p": 0.01}


def _parse_doubao_response(content: str, message: dict | None = None) -> dict:
    if not content or not isinstance(content, str):
        return {"thought": "模型返回为空", "func": "Wait", "action": "", "raw_model_output": ""}

    raw = content.strip()
    thought, action_str = _split_thought_action(raw)

    if not action_str:
        return {"thought": thought or "无法解析动作", "func": "Wait", "action": "", "raw_model_output": raw}

    try:
        result = _parse_action_call(action_str.strip())
        return _convert_to_guiness(result, thought, raw)
    except Exception as e:
        logger.warning(f"doubao action 解析失败: {e}, action_str={action_str[:100]}")
        return {"thought": thought or "动作解析失败", "func": "Wait", "action": "", "raw_model_output": raw}


def _split_thought_action(content: str) -> tuple[str, str]:
    action_match = re.search(r'Action:\s*(.+)', content, re.DOTALL)
    if action_match:
        action_str = action_match.group(1).strip()
        thought_part = content[:action_match.start()].strip()
        thought = re.sub(r'^Thought:\s*', '', thought_part, flags=re.IGNORECASE).strip()
        return thought, action_str

    func_match = re.search(
        r'(click|long_press|type|scroll|open_app|drag|press_home|press_back|wait|finished)\s*\(', content
    )
    if func_match:
        return content[:func_match.start()].strip(), content[func_match.start():].strip()

    return content, ""


def _parse_point(text: str) -> list[int]:
    match = re.search(r'<point>\s*(\d+)\s+(\d+)\s*</point>', text)
    if match:
        return [int(match.group(1)), int(match.group(2))]
    nums = re.findall(r'\d+', text)
    if len(nums) >= 2:
        return [int(nums[0]), int(nums[1])]
    return [500, 500]


def _parse_action_call(action_str: str) -> dict:
    action_str = action_str.split('\n')[0].strip()

    if re.match(r'press_home\s*\(\s*\)', action_str):
        return {"_action": "press_home"}
    if re.match(r'press_back\s*\(\s*\)', action_str):
        return {"_action": "press_back"}
    if re.match(r'wait\s*\(\s*\)', action_str):
        return {"_action": "wait"}

    m = re.match(r"click\s*\(\s*point\s*=\s*['\"](.+?)['\"]\s*\)", action_str)
    if m:
        return {"_action": "click", "point": _parse_point(m.group(1))}

    m = re.match(r"long_press\s*\(\s*point\s*=\s*['\"](.+?)['\"]\s*\)", action_str)
    if m:
        return {"_action": "long_press", "point": _parse_point(m.group(1))}

    m = re.match(r"type\s*\(\s*content\s*=\s*['\"](.*)['\"]\s*\)", action_str, re.DOTALL)
    if m:
        text = m.group(1).replace('\\n', '\n').replace("\\'", "'").replace('\\"', '"')
        return {"_action": "type", "content": text}

    m = re.match(
        r"scroll\s*\(\s*point\s*=\s*['\"](.+?)['\"]\s*,\s*direction\s*=\s*['\"](\w+)['\"]\s*\)",
        action_str,
    )
    if m:
        return {"_action": "scroll", "point": _parse_point(m.group(1)), "direction": m.group(2)}

    m = re.match(r"open_app\s*\(\s*app_name\s*=\s*['\"](.+?)['\"]\s*\)", action_str)
    if m:
        return {"_action": "open_app", "app_name": m.group(1)}

    m = re.match(
        r"drag\s*\(\s*start_point\s*=\s*['\"](.+?)['\"]\s*,\s*end_point\s*=\s*['\"](.+?)['\"]\s*\)",
        action_str,
    )
    if m:
        return {"_action": "drag", "start_point": _parse_point(m.group(1)), "end_point": _parse_point(m.group(2))}

    m = re.match(r"finished\s*\(\s*content\s*=\s*['\"](.*)['\"]\s*\)", action_str, re.DOTALL)
    if m:
        text = m.group(1).replace('\\n', '\n').replace("\\'", "'").replace('\\"', '"')
        return {"_action": "finished", "content": text}

    raise ValueError(f"无法识别的 doubao action: {action_str[:80]}")


def _convert_to_guiness(parsed: dict, thought: str, raw: str) -> dict:
    base = {"thought": thought, "action": "", "raw_model_output": raw}
    action_name = parsed.get("_action", "")
    func = _ACTION_MAP.get(action_name, "Wait")
    base["func"] = func

    if action_name == "click":
        point = parsed.get("point", [500, 500])
        base["position"] = [round(point[0] / 1000.0, 3), round(point[1] / 1000.0, 3)]
        base["times"] = 1
    elif action_name == "long_press":
        point = parsed.get("point", [500, 500])
        base["position"] = [round(point[0] / 1000.0, 3), round(point[1] / 1000.0, 3)]
    elif action_name == "type":
        base["text"] = parsed.get("content", "")
        base["position"] = [0.5, 0.5]
    elif action_name == "scroll":
        point = parsed.get("point", [500, 500])
        direction = parsed.get("direction", "down")
        base["position"] = [round(point[0] / 1000.0, 3), round(point[1] / 1000.0, 3)]
        base["direction"] = direction
    elif action_name == "open_app":
        base["app"] = parsed.get("app_name", "")
    elif action_name == "drag":
        start = parsed.get("start_point", [500, 200])
        end = parsed.get("end_point", [500, 800])
        base["start_position"] = [round(start[0] / 1000.0, 3), round(start[1] / 1000.0, 3)]
        base["end_position"] = [round(end[0] / 1000.0, 3), round(end[1] / 1000.0, 3)]
    elif action_name == "finished":
        base["text"] = parsed.get("content", "")

    return base
