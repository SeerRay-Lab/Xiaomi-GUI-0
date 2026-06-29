# -*- coding: utf-8 -*-
"""CLI 终端渲染器：把引擎产出的 step_record 渲染成带 ANSI 颜色的进度。

合并了原 `run_eval.py` 顶部和 `runner/episode_runner.py` 顶部两份几乎重复的
`_C` / `_step_*` / `_progress_bar` 实现。
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, Optional


# ─── ANSI 颜色 ───────────────────────────────────────────────
class _C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"


_ACTION_COLORS = {
    # 历史上 runner 用 "Click"、action_space 注册 "Tap"——两个名字都兼容染色
    "Tap":       _C.GREEN,
    "Click":     _C.GREEN,
    "LongPress": _C.YELLOW,
    "Swipe":     _C.BLUE,
    "Type":      _C.MAGENTA,
    "Back":      _C.CYAN,
    "Home":      _C.CYAN,
    "Wait":      _C.DIM,
    "Complete":  _C.GREEN,
    "Fail":      _C.RED,
    "End":       _C.GREEN,
    "Speak":     _C.CYAN,
}


# ──────────── 通用小工具（模块级，供 run_eval.py 初始化阶段也能用） ────────────
def ok(msg: str) -> None:
    print(f"  {_C.GREEN}✔{_C.RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {_C.CYAN}ℹ{_C.RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {_C.YELLOW}⚠{_C.RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {_C.RED}✖{_C.RESET} {msg}")


def banner() -> None:
    print()
    print(f"  {_C.BOLD}{_C.CYAN}╔══════════════════════════════════════════╗{_C.RESET}")
    print(f"  {_C.BOLD}{_C.CYAN}║       Online Evaluation System           ║{_C.RESET}")
    print(f"  {_C.BOLD}{_C.CYAN}╚══════════════════════════════════════════╝{_C.RESET}")
    print()


def section(title: str) -> None:
    print()
    print(f"  {_C.BOLD}{_C.BLUE}── {title} ─────────────────────────────{_C.RESET}")


def kv(key: str, value: Any) -> None:
    print(f"  {_C.DIM}{key:<16}{_C.RESET} {value}")


def progress_bar(current: int, total: int, width: int = 30) -> str:
    filled = int(width * current / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = int(100 * current / total) if total else 0
    return f"{_C.GREEN}{bar}{_C.RESET} {pct:>3}% ({current}/{total})"


# ──────────── Step 卡片渲染 ────────────
def _step_header(step: int, max_steps: int) -> None:
    label = f" Step {step}/{max_steps} "
    side = 18
    print(f"        {_C.CYAN}{'┄' * side}{_C.BOLD}{_C.WHITE}{label}{_C.RESET}{_C.CYAN}{'┄' * side}{_C.RESET}")


def _step_footer() -> None:
    print(f"        {_C.DIM}{'┄' * 44}{_C.RESET}")
    print()


def _step_row(icon: str, key: str, value: Any) -> None:
    print(f"        {icon} {_C.DIM}{key:<8}{_C.RESET} {value}")


def format_action(action_data: dict) -> str:
    func = action_data.get("func", "Unknown")
    color = _ACTION_COLORS.get(func, _C.WHITE)
    parts = [f"{color}{_C.BOLD}{func}{_C.RESET}"]
    if func in ("Tap", "Click", "LongPress"):
        x, y = action_data.get("x", "?"), action_data.get("y", "?")
        parts.append(f"({x}, {y})")
    elif func == "Swipe":
        x1, y1 = action_data.get("x1", "?"), action_data.get("y1", "?")
        x2, y2 = action_data.get("x2", "?"), action_data.get("y2", "?")
        parts.append(f"({x1},{y1}) → ({x2},{y2})")
    elif func == "Type":
        text = action_data.get("text", "")
        display = text if len(text) <= 30 else text[:27] + "..."
        parts.append(f'"{display}"')
    return " ".join(parts)


# ──────────── Reporter ────────────
class CliReporter:
    """终端样式 Reporter：实现 reporter.base.Reporter 协议。"""

    def __init__(self, max_steps: int = 100) -> None:
        self.max_steps = max_steps

    def on_episode_start(self, task: dict) -> None:
        # 引擎不需要再打印任何标题——调用方（run_eval.py）负责 [i/N] 行
        pass

    def on_step_complete(self, step_record: dict) -> None:
        step = step_record.get("step", 0)
        action = step_record.get("action", {}) or {}
        thought = step_record.get("thought", "") or ""
        foreground_app = step_record.get("foreground_app", "")
        screenshot_t = step_record.get("screenshot_time", 0.0)
        infer_t = step_record.get("infer_time", 0.0)
        exec_success = step_record.get("exec_success")

        _step_header(step, self.max_steps)
        if thought:
            display_thought = thought if len(thought) <= 50 else thought[:47] + "..."
            _step_row("💭", "Thought", display_thought)
        _step_row("⚡", "Action", format_action(action))
        _step_row("📱", "App", f"{_C.DIM}{foreground_app}{_C.RESET}")
        _step_row(
            "⏱️",
            "耗时",
            f"{_C.DIM}截图 {screenshot_t:.1f}s · 推理 {infer_t:.1f}s{_C.RESET}",
        )
        if exec_success is True:
            _step_row("✅", "状态", f"{_C.GREEN}执行成功{_C.RESET}")
        elif exec_success is False:
            _step_row("❌", "状态", f"{_C.RED}执行失败{_C.RESET}")
        _step_footer()

    def on_episode_finish(self, result: dict) -> None:
        pass
