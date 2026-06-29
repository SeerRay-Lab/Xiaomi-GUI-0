# -*- coding: utf-8 -*-
"""核心层：跨入口（CLI/GUI）共享的组件装配与运行上下文。"""
from core.setup import (
    Components,
    build_components,
    build_runner,
    resolve_device_id,
)

__all__ = [
    "Components",
    "build_components",
    "build_runner",
    "resolve_device_id",
]
