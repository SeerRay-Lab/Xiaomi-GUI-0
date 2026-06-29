# -*- coding: utf-8 -*-
"""评测运行进度汇报层。

引擎 (EpisodeRunner) 只负责产生 step_record；渲染（ANSI 终端、Qt 信号、Web 推送 ...）
都走 Reporter 协议，避免核心代码被 print/颜色码/终端细节污染。
"""
from reporter.base import Reporter, NullReporter
from reporter.cli_reporter import CliReporter

__all__ = ["Reporter", "NullReporter", "CliReporter"]
