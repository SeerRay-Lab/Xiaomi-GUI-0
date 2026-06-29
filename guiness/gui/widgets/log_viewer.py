# -*- coding: utf-8 -*-
"""
日志输出控件：QPlainTextEdit + logging Handler，
将 logging 和 print 输出都重定向到 GUI。
"""
import logging
import re

from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtCore import Signal, QObject
from PySide6.QtGui import QTextCharFormat, QColor


# ANSI 转义序列清理
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class _LogBridge(QObject):
    """线程安全的信号桥：从任意线程发 log 到主线程。"""
    message = Signal(str)


class QtLogHandler(logging.Handler):
    """logging.Handler → Signal → LogViewer。"""

    def __init__(self, bridge: _LogBridge) -> None:
        super().__init__()
        self._bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self._bridge.message.emit(msg)


class LogViewer(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("logViewer")
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)

        # 信号桥
        self._bridge = _LogBridge()
        self._bridge.message.connect(self._append_line)

        # 安装 logging handler
        self._handler = QtLogHandler(self._bridge)
        self._handler.setFormatter(logging.Formatter("%(asctime)s  %(name)s  %(message)s", datefmt="%H:%M:%S"))

    @property
    def handler(self) -> QtLogHandler:
        return self._handler

    @property
    def bridge(self) -> _LogBridge:
        return self._bridge

    def append_text(self, text: str) -> None:
        """供外部直接追加文本（线程安全）。"""
        self._bridge.message.emit(text)

    def _append_line(self, text: str) -> None:
        clean = strip_ansi(text)
        self.appendPlainText(clean)
        # 自动滚到底部
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())
