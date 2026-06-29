# -*- coding: utf-8 -*-
"""Adapter 共享的 message 组装逻辑。"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from model.device_info import resolve_device_info
from model.response_parser import get_content

logger = logging.getLogger(__name__)


def _download_image(image_url: str) -> Optional[str]:
    import base64
    try:
        resp = requests.get(image_url, timeout=30)
        if resp.status_code == 200:
            return base64.b64encode(resp.content).decode("utf-8")
    except Exception as e:
        logger.error(f"Error downloading image {image_url}: {e}")
    return None


def build_messages_standard(
    *,
    system: str,
    history: list,
    query: str,
    image_base64: Optional[str],
    foreground_app: str,
    device_type: str,
    add_info: str,
    max_query: int,
    max_turn: int,
    max_history_images: int,
) -> list[dict]:
    """标准的 OpenAI 兼容 message 列表组装（<think>/<action>/<tool_call> 格式）。"""
    messages: list[dict] = [{"role": "system", "content": system}]

    # 历史 messages
    history_msgs, last_query, last_func = _build_history(
        history, max_query, max_turn, max_history_images
    )
    messages.extend(history_msgs)

    # 当前 user message
    device_info, screen_info = resolve_device_info(device_type)
    extra_info = f"当前在{device_info}设备，{screen_info}下进行操作,处在{foreground_app or '未知'}界面中"

    current_query = f"{add_info}\n{query}" if add_info else query
    if last_query == query and last_func != "Request":
        current_query = extra_info
    else:
        current_query = f"{extra_info}\n用户请求：{query}"

    user_content: list = [{"type": "text", "text": current_query}]
    if image_base64:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
        })

    messages.append({"role": "user", "content": user_content})
    return messages


def _build_history(
    history: list, max_query: int, max_turn: int, max_history_images: int
) -> tuple[list, str, str]:
    """把 history 展开成 OpenAI messages；返回 (messages, last_query, last_func)。"""
    history_message: list = []
    last_query = ""
    last_func = ""

    if not history:
        return [], last_query, last_func

    for history_item in history[-max_query:]:
        history_query = history_item["query"]
        history_steps = history_item["steps"][-max_turn:]
        last_query = history_query

        for idx, h in enumerate(history_steps):
            user_content = history_query if idx == 0 else ""
            assistant_content = (
                h.get("raw_model_output")
                or h.get("model_response")
                or get_content(h, is_history=True)
            )
            user_msg = {
                "role": "user",
                "content": user_content,
                "image_url": h.get("image_url", "") or h.get("url_signed", "") or h.get("url_low", ""),
            }
            assistant_msg = {"role": "assistant", "content": assistant_content}
            history_message.append([user_msg, assistant_msg])
            plan = h.get("plan", {})
            last_func = plan.get("func", "") if isinstance(plan, dict) else ""

    messages: list = []
    for idx in range(len(history_message)):
        user_msg, assistant_msg = history_message[idx]
        image_url = user_msg.get("image_url", "")
        take_image = (
            max_history_images > 0
            and image_url
            and idx >= len(history_message) - max_history_images
        )

        if take_image:
            base64_img = _download_image(image_url)
            if base64_img:
                content_list = []
                if user_msg["content"]:
                    content_list.append({"type": "text", "text": user_msg["content"]})
                content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"},
                })
                messages.append({"role": "user", "content": content_list})
            else:
                messages.append({"role": "user", "content": user_msg["content"]})
        else:
            messages.append({"role": "user", "content": user_msg["content"]})

        messages.append(assistant_msg)

    return messages, last_query, last_func
