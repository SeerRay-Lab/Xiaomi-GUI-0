# -*- coding: utf-8 -*-
"""内嵌实时镜像视图：嵌入 ChatFeed 顶部，共享单一帧流。"""
from __future__ import annotations

import logging
from typing import Callable, Iterator, Optional

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from gui.styles import tokens as t
from gui.workers.screen_stream_worker import ScreenStreamWorker

logger = logging.getLogger(__name__)


class LiveMirrorViewport(QFrame):
    """常驻在 ChatFeed 顶部的实时屏幕视图。"""

    status_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {t.NEUTRAL_100};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_MD}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._status_label = QLabel("等待设备连接")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setFixedHeight(24)
        self._status_label.setStyleSheet(
            f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; "
            f"background: {t.NEUTRAL_0}; border: none; "
            f"border-bottom: 1px solid {t.NEUTRAL_200};"
        )
        layout.addWidget(self._status_label)

        self._image_label = QLabel("实时镜像")
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setStyleSheet(
            f"color: {t.NEUTRAL_400}; font-size: {t.FONT_SM}px; "
            f"background: {t.NEUTRAL_100}; border: none;"
        )
        layout.addWidget(self._image_label, 1)

        self._last_pixmap: Optional[QPixmap] = None
        self._worker: Optional[ScreenStreamWorker] = None

    def start(self, frame_iter_factory: Callable[[threading.Event], Iterator[QImage]]) -> None:
        """启动流。若已有流在跑则先停掉。"""
        if self._worker is not None:
            self.stop()

        self._status_label.setText("连接中...")
        self._worker = ScreenStreamWorker(frame_iter_factory, parent=self)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.status_changed.connect(self._on_status)
        self._worker.start()

    def stop(self) -> None:
        """安全停止：disconnect → stop_event → wait → 清理引用。"""
        if self._worker is None:
            return
        try:
            self._worker.frame_ready.disconnect(self._on_frame)
        except (TypeError, RuntimeError):
            pass
        try:
            self._worker.status_changed.disconnect(self._on_status)
        except (TypeError, RuntimeError):
            pass

        self._worker.stop()
        self._worker.wait(6000)
        self._worker = None
        self._status_label.setText("已停止")

    def is_streaming(self) -> bool:
        return self._worker is not None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_scaled()

    def _on_frame(self, img: QImage) -> None:
        self._last_pixmap = QPixmap.fromImage(img)
        self._refresh_scaled()

    def _on_status(self, status: str) -> None:
        if status == "connected":
            self._status_label.setText("已连接，等待首帧")
        elif status == "disconnected":
            self._status_label.setText("已断开")
        elif status.startswith("error:"):
            self._status_label.setText(f"异常：{status[6:]}")
        elif status.startswith("warning:"):
            self._status_label.setText(status[8:])
        else:
            self._status_label.setText(status)
        self.status_changed.emit(status)

    def _refresh_scaled(self) -> None:
        if self._last_pixmap is None:
            return
        pw = self._last_pixmap.width()
        ph = self._last_pixmap.height()
        if pw <= 0 or ph <= 0:
            return

        # 获取父容器可用高度，与 ScreenshotViewer 同理
        parent = self.parentWidget()
        if parent is not None:
            avail_h = max(parent.height() - self._status_label.height() - 28, 100)
        else:
            avail_h = max(self.height() - self._status_label.height(), 100)

        # 根据手机屏幕宽高比和可用高度计算目标宽度
        target_w = int(avail_h * pw / ph)
        target_h = avail_h

        self._image_label.setFixedWidth(target_w)
        self._image_label.setFixedHeight(target_h)
        self.setFixedWidth(target_w)

        scaled = self._last_pixmap.scaled(
            target_w, target_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)
        if self._status_label.text() == "已连接，等待首帧":
            self._status_label.setText("串流中")
