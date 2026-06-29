# -*- coding: utf-8 -*-
"""device_type → (设备类型, 屏幕形态) 中文描述表。

原 `InferenceClient._resolve_device_info` 硬编码 5 行字典，抽到独立模块以便
将来按实际产线增减不影响客户端代码。
"""
from __future__ import annotations

_DEVICE_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "phone": ("手机", "手机全屏"),
    "car": ("车载", "车机全屏"),
    "car-pin": ("车载", "车机pin屏"),
    "car-full": ("车载", "车机全屏"),
    "pad": ("平板", "平板全屏"),
}

_FALLBACK: tuple[str, str] = ("手机", "手机全屏")


def resolve_device_info(device_type: str) -> tuple[str, str]:
    """返回 (设备类型中文, 屏幕形态中文)，未知类型回退到手机全屏。"""
    return _DEVICE_DESCRIPTIONS.get(device_type, _FALLBACK)
