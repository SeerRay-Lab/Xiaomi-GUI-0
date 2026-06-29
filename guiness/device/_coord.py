# -*- coding: utf-8 -*-
"""backend 间共享的坐标/方向工具。

旧实现散落在 ADBController.modify_coordinate 和 action_executor._SWIPE_DIRECTIONS，
WiFi backend 也要同一套规则（归一化坐标 + 方向表驱动），集中到这里一份。
"""
from __future__ import annotations

from typing import Tuple

# Swipe 四方向：起点相对坐标 (x, y) + 位移向量（单位 = 屏宽/10）。
SWIPE_DIRECTIONS: dict[str, tuple[tuple[float, float], tuple[int, int]]] = {
    "up":    ((0.5, 0.75), (0, -2)),
    "down":  ((0.5, 0.25), (0,  2)),
    "left":  ((0.75, 0.5), (-1, 0)),
    "right": ((0.25, 0.5), ( 1, 0)),
}


def normalize_point(x, y, width: int, height: int) -> Tuple[int, int]:
    """把归一化/百分比/像素坐标统一压成屏内像素。

    - [0, 1.02]         按比例
    - (1.02, 1000] 且屏宽/高 > 1000 按千分比
    - 其余视为像素
    """
    if isinstance(x, list):
        y = x[1]
        x = x[0]

    x, y = float(x), float(y)

    if width <= 0 or height <= 0:
        return int(x), int(y)

    if 0 <= x <= 1.02:
        x = width * x
    elif 1.02 < x <= 1000 and width > 1000:
        x = width * (x / 1000.0)

    if 0 <= y <= 1.02:
        y = height * y
    elif 1.02 < y <= 1000 and height > 1000:
        y = height * (y / 1000.0)

    x = max(0, min(int(x), max(width - 1, 0)))
    y = max(0, min(int(y), max(height - 1, 0)))
    return x, y


def resolve_direction_swipe(
    direction: str,
    width: int,
    height: int,
) -> Tuple[int, int, int, int]:
    """给定方向，返回 (x1, y1, x2, y2) 像素坐标。"""
    if direction not in SWIPE_DIRECTIONS:
        raise ValueError(f"不支持的滑动方向: {direction}")

    start_rel, offset_units = SWIPE_DIRECTIONS[direction]
    unit_dist = int(width / 10) if width > 0 else 0
    x1, y1 = normalize_point(start_rel[0], start_rel[1], width, height)
    x2 = x1 + offset_units[0] * unit_dist
    y2 = y1 + offset_units[1] * unit_dist
    return x1, y1, x2, y2
