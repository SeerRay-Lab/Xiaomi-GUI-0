# -*- coding: utf-8 -*-
"""Reporter 协议：引擎通过它对外广播执行进度。

为什么单独抽：
- 引擎里的 print/ANSI 色码让 GUI 模式执行却看不见，还污染核心代码
- CLI 和 GUI 想要的呈现完全不同（终端染色 vs Qt 信号）
- Web 推送、测试断言也可以自定义 Reporter

实现者只需选择性重写自己关心的钩子。默认 NullReporter 什么都不做，
适合 GUI 这种另走信号的场景。
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Reporter(Protocol):
    """引擎在执行阶段回调的一组钩子。

    step_record / result 字段参考 runner.episode_runner 产出。
    """

    def on_episode_start(self, task: dict) -> None: ...
    def on_step_complete(self, step_record: dict) -> None: ...
    def on_episode_finish(self, result: dict) -> None: ...


class NullReporter:
    """什么都不做。GUI 走 on_step_complete 回调时用这个占位。"""

    def on_episode_start(self, task: dict) -> None:
        pass

    def on_step_complete(self, step_record: dict) -> None:
        pass

    def on_episode_finish(self, result: dict) -> None:
        pass
