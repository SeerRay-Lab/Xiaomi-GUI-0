# -*- coding: utf-8 -*-
"""Step-GUI (GELab-Zero-4B) adapter — <think> + TSV 格式，坐标 0-1000。"""
from __future__ import annotations

import logging
import re
from typing import Optional

from model.adapters import AdapterBase
from model.adapters._common import build_messages_standard

logger = logging.getLogger(__name__)

_GELAB_KEEP_FIELDS: dict[str, list[str]] = {
    "CLICK": ["point"],
    "LONGPRESS": ["point"],
    "SLIDE": ["point1", "point2"],
    "TYPE": ["value"],
    "AWAKE": ["value"],
    "BACK": [],
    "WAIT": ["value"],
    "INFO": ["value"],
    "ABORT": ["value"],
    "COMPLETE": ["return"],
    "CALL_USER": ["value", "tag"],
}


class StepGuiAdapter(AdapterBase):
    name = "step_gui"

    def build_messages(self, **kwargs) -> list[dict]:
        return build_messages_standard(**kwargs)

    def parse_response(self, content: str, message: Optional[dict] = None) -> dict:
        return _parse_gelab_response(content, message)

    def payload_extras(self) -> dict:
        return {"temperature": 0.0, "top_p": 0.01, "top_k": 1}


def _scale_point(point) -> list | None:
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    try:
        return [round(float(point[0]) / 1000.0, 4), round(float(point[1]) / 1000.0, 4)]
    except (TypeError, ValueError):
        return None


def _parse_gelab_response(response, message=None) -> dict:
    if isinstance(response, dict):
        return response

    raw_text = response if isinstance(response, str) else str(response)

    try:
        text = raw_text.strip()

        # 1. 抽取 <think>...</think>
        cot = ""
        for open_tag, close_tag in (("<think>", "</think>"), ("<thought>", "</thought>")):
            if open_tag in text and close_tag in text:
                cot = text.split(open_tag, 1)[1].split(close_tag, 1)[0].strip()
                break

        # 2. 取 </think> 后的 TSV 主体
        if "</think>" in text:
            body = text.split("</think>", 1)[1].strip()
        elif "</thought>" in text:
            body = text.split("</thought>", 1)[1].strip()
        else:
            body = text

        # GELab 用 \t 切分；模型不规范时偶尔吐 \n
        if "\t" in body:
            kvs = [kv.strip() for kv in body.split("\t") if kv.strip()]
        else:
            kvs = [kv.strip() for kv in body.split("\n") if kv.strip()]

        gelab_fields: dict = {}
        for kv in kvs:
            if ":" not in kv:
                continue
            key, value = kv.split(":", 1)
            key = key.strip()
            value = value.strip()
            if "\n" in value:
                value = value.split("\n", 1)[0].strip()
            if key in ("point", "point1", "point2"):
                coords = value.replace(",", " ").split()
                if len(coords) >= 2:
                    try:
                        gelab_fields[key] = [int(coords[0]), int(coords[1])]
                    except ValueError:
                        gelab_fields[key] = value
            else:
                gelab_fields[key] = value

        # 3. 翻译到 Guiness
        gelab_action = gelab_fields.get("action", "")
        result = _translate_gelab_to_guiness(gelab_action, gelab_fields)

        # 4. thought
        thought_parts: list[str] = []
        if cot:
            thought_parts.append(cot)
        verify = gelab_fields.get("verify", "")
        note = gelab_fields.get("note", "")
        key_process = gelab_fields.get("key_process", "")
        if verify:
            thought_parts.append(f"[verify] {verify}")
        if note and note.strip().lower() != "none":
            thought_parts.append(f"[note] {note}")
        if key_process and key_process.strip().lower() != "none":
            thought_parts.append(f"[key_process] {key_process}")
        result["thought"] = "\n".join(thought_parts)

        # 5. action 摘要
        result["action"] = gelab_fields.get("explain", "")

        # 6. 保留原始字段
        result["_gelab_raw"] = gelab_fields
        result["raw_model_output"] = raw_text
        return result

    except Exception as e:
        logger.error(f"GELab response parse error: {str(e)[:200]}")
        return {
            "func": "Wait",
            "thought": "GELab 解析异常，等待。",
            "action": "",
            "raw_model_output": raw_text,
        }


def _translate_gelab_to_guiness(gelab_action: str, fields: dict) -> dict:
    a = (gelab_action or "").upper().strip()

    if a == "CLICK":
        return {"func": "Tap", "position": _scale_point(fields.get("point")), "times": 1}
    if a == "LONGPRESS":
        return {"func": "LongPress", "position": _scale_point(fields.get("point"))}
    if a == "SLIDE":
        return {
            "func": "Swipe",
            "start_position": _scale_point(fields.get("point1")),
            "end_position": _scale_point(fields.get("point2")),
        }
    if a == "TYPE":
        return {"func": "Type", "text": fields.get("value", "")}
    if a == "AWAKE":
        return {"func": "Open", "app": fields.get("value", "")}
    if a == "BACK":
        return {"func": "Back"}
    if a == "WAIT":
        return {"func": "Wait"}
    if a == "INFO":
        return {"func": "Request", "text": fields.get("value", "")}
    if a == "ABORT":
        return {"func": "Fail", "type": "TASK_CANT_FULLFILLED", "reason": fields.get("value", "")}
    if a == "COMPLETE":
        ret = (fields.get("return") or "").strip()
        if ret:
            return {"func": "Speak", "text": ret}
        return {"func": "Complete"}
    if a == "CALL_USER":
        tag = (fields.get("tag") or "").strip()
        if tag == "screenshot_issue":
            return {"func": "Fail", "type": "MANUAL_VERIFICATION_REQUIRED", "reason": fields.get("value", "")}
        return {"func": "Request", "text": fields.get("value", "")}

    logger.warning(f"未知的 GELab action: {gelab_action!r}，回退 Wait")
    return {"func": "Wait"}
