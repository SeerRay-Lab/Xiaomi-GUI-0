# -*- coding: utf-8 -*-
"""大模型推理客户端。

通过 Adapter 热插拔架构支持不同模型系列的 system prompt、message 组装和响应解析。
运行时根据 model_name 自动选择对应的 Adapter。
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

import requests

from model.adapters import get_adapter, get_model_list

logger = logging.getLogger(__name__)


def _load_preset_models() -> list[dict]:
    """加载支持的模型列表，供 GUI 下拉使用。"""
    return get_model_list()


PRESET_MODELS: list[dict] = _load_preset_models()


def _encode_local_image(image_path: str) -> Optional[str]:
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Encode image error: {e}")
        return None


class InferenceClient:
    def __init__(self, config: dict):
        if not config:
            raise ValueError("InferenceClient 需要显式传入 model config dict")
        self.config = config
        self._apply_config(self.config)

    def _apply_config(self, config: dict) -> None:
        self.model_name = config.get("model_name", "")
        self.model_name_override = config.get("model_name_override", "")
        self.api_key = config.get("api_key", "") or config.get("mify_api_key", "")
        self.provider_id = (
            config.get("provider_id", "")
            or config.get("model_provider_id", "")
            or config.get("mify_provider_id", "")
        )
        raw_url = (
            config.get("url", "")
            or config.get("custom_url", "")
            or config.get("mify_base_url", "")
        )
        base_url = raw_url.rstrip("/") if raw_url else ""
        if base_url and not base_url.endswith("/v1/chat/completions"):
            self.url = f"{base_url}/v1/chat/completions"
        else:
            self.url = base_url

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        provider_id = self.provider_id
        if not provider_id and "model.mify.ai.srv" in self.url and "gemini" in self.model_name.lower():
            provider_id = "vertex_ai"
        if provider_id:
            headers["X-Model-Provider-Id"] = provider_id
        return headers

    def request_action(
        self,
        image_path: str,
        query: str,
        add_info: str = "",
        system: Optional[str] = None,
        history: Optional[list] = None,
        max_query: int = 3,
        max_turn: int = 3,
        foreground_app: str = "",
        max_history_images: int = 0,
        device_type: str = "phone",
    ) -> dict:
        """向大模型请求下一步动作，返回解析后的 action dict。"""
        adapter = get_adapter(self.model_name)

        effective_system = system or adapter.system_prompt(device_type)

        image_base64 = _encode_local_image(image_path) if image_path else None
        if image_path and not image_base64:
            logger.error(f"截图编码失败: {image_path}，本步推理将缺少图片信息")

        messages = adapter.build_messages(
            system=effective_system,
            history=history or [],
            query=query,
            image_base64=image_base64,
            foreground_app=foreground_app,
            device_type=device_type,
            add_info=add_info,
            max_query=max_query,
            max_turn=max_turn,
            max_history_images=max_history_images,
        )

        effective_model = self.model_name_override or self.model_name
        payload = {
            "model": effective_model,
            "messages": messages,
            **adapter.payload_extras(),
        }

        if not self.url:
            logger.error("API Error: URL 为空，无法发送请求")
            return {"thought": "模型 URL 未配置", "func": "Fail", "raw_model_output": "", "_is_error": True}

        try:
            logger.info(f"请求模型: {self.url} (Model: {effective_model}, Adapter: {adapter.name})")
            resp = requests.post(self.url, headers=self._build_headers(), json=payload, timeout=120)
        except requests.Timeout:
            logger.error("API Error: Timeout")
            return {"thought": "请求超时", "func": "Wait", "raw_model_output": "", "_is_error": True}
        except Exception as e:
            logger.error(f"error in request_for_collect: {e}")
            return {"thought": "预测错误，等待", "func": "Wait", "raw_model_output": "", "_is_error": True}

        if resp.status_code != 200:
            logger.error(f"API Error: {resp.status_code} - {resp.text[:200]}")
            return {"thought": f"网络请求错误 {resp.status_code}", "func": "Wait", "raw_model_output": "", "_is_error": True}

        try:
            res_json = resp.json()
            message = res_json["choices"][0]["message"]
            content = message.get("content") or message.get("reasoning_content")
            logger.debug(f"模型输出成功，content长度: {len(content) if content else 0}")
            result = adapter.parse_response(content, message=message)
            usage = res_json.get("usage")
            if usage:
                result["usage"] = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }
            return result
        except (KeyError, IndexError):
            logger.error(f"Response struct error. Raw: {str(resp.json())[:100]}...")
            return {"thought": "接口返回结构异常", "func": "Wait", "raw_model_output": ""}
