# -*- coding: utf-8 -*-
"""模型 Adapter 热插拔架构。

每个模型系列对应一个 Adapter 子类，封装：
  - system_prompt：该系列使用的 system prompt
  - build_messages：message 列表组装方式
  - parse_response：模型输出解析为标准 action dict
  - payload_extras：发给 API 的额外参数

运行时通过 get_adapter(model_name) 按 preset_models.yaml 中的映射自动选择。
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import yaml

from model.device_info import resolve_device_info

logger = logging.getLogger(__name__)

_ADAPTERS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROMPTS_DIR = os.path.join(_ADAPTERS_DIR, "prompts")


class AdapterBase(ABC):
    """所有 adapter 的基类。"""

    name: str = ""

    def system_prompt(self, device_type: str = "phone") -> str:
        path = os.path.join(_PROMPTS_DIR, f"{self.name}.txt")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @abstractmethod
    def build_messages(
        self,
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
        ...

    @abstractmethod
    def parse_response(self, content: str, message: Optional[dict] = None) -> dict:
        ...

    def payload_extras(self) -> dict:
        return {"temperature": 0.0, "top_p": 0.01}


# ── Registry ──────────────────────────────────────────────────

ADAPTER_REGISTRY: dict[str, AdapterBase] = {}

_MODEL_TO_ADAPTER: dict[str, str] = {}


def _load_model_mapping() -> None:
    """从 preset_models.yaml 加载 model_name → adapter 映射。"""
    global _MODEL_TO_ADAPTER
    path = os.path.join(os.path.dirname(_ADAPTERS_DIR), "preset_models.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        models = data.get("models", {})
        for model_id, info in models.items():
            if isinstance(info, dict):
                adapter_name = info.get("adapter", "")
                if adapter_name:
                    _MODEL_TO_ADAPTER[model_id] = adapter_name
    except Exception as e:
        logger.warning(f"加载 preset_models.yaml 失败: {e}")


def register_adapter(adapter: AdapterBase) -> None:
    ADAPTER_REGISTRY[adapter.name] = adapter


def get_adapter(model_name: str) -> AdapterBase:
    """根据模型名获取对应的 adapter 实例。"""
    if not _MODEL_TO_ADAPTER:
        _load_model_mapping()

    adapter_name = _MODEL_TO_ADAPTER.get(model_name, "")

    if not adapter_name:
        for key, name in _MODEL_TO_ADAPTER.items():
            if key in model_name or model_name in key:
                adapter_name = name
                break

    if adapter_name and adapter_name in ADAPTER_REGISTRY:
        return ADAPTER_REGISTRY[adapter_name]

    if "realgui" in model_name.lower():
        return ADAPTER_REGISTRY.get("realgui", _fallback_adapter)
    return _fallback_adapter


def get_model_list() -> list[dict]:
    """返回所有支持的模型列表，供 GUI 下拉使用。"""
    if not _MODEL_TO_ADAPTER:
        _load_model_mapping()
    path = os.path.join(os.path.dirname(_ADAPTERS_DIR), "preset_models.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        models = data.get("models", {})
        result = []
        for model_id, info in models.items():
            if isinstance(info, dict):
                result.append({
                    "id": model_id,
                    "display_name": info.get("display_name", model_id),
                    "adapter": info.get("adapter", ""),
                })
        return result
    except Exception:
        return []


class _FallbackAdapter(AdapterBase):
    """兜底 adapter：用 custom prompt 格式。"""
    name = "fallback"

    def system_prompt(self, device_type: str = "phone") -> str:
        path = os.path.join(_PROMPTS_DIR, "gemini.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def build_messages(self, **kwargs) -> list[dict]:
        from model.adapters._common import build_messages_standard
        return build_messages_standard(**kwargs)

    def parse_response(self, content: str, message=None) -> dict:
        from model.response_parser import parse_model_response
        return parse_model_response(content, message=message)


_fallback_adapter = _FallbackAdapter()


def _register_all() -> None:
    from model.adapters.gemini import GeminiAdapter
    from model.adapters.claude import ClaudeAdapter
    from model.adapters.gpt import GptAdapter
    from model.adapters.doubao import DoubaoAdapter
    from model.adapters.autoglm import AutoglmAdapter
    from model.adapters.step_gui import StepGuiAdapter
    from model.adapters.realgui import RealguiAdapter

    for cls in (GeminiAdapter, ClaudeAdapter, GptAdapter, DoubaoAdapter,
                AutoglmAdapter, StepGuiAdapter, RealguiAdapter):
        register_adapter(cls())


_register_all()
