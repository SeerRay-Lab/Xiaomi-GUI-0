# -*- coding: utf-8 -*-
"""屏幕镜像对话框：订阅 Guiness APP 的 /stream WebSocket，实时展示 JPEG 帧。

设计原则：
- 独立非模态窗口——用户开着它同时继续在主窗口敲命令
- 帧接收跑在 QThread，主线程只收 Signal 刷 QPixmap
- 不接管设备尺寸，窗口可自由缩放，图片按等比例（KeepAspectRatio）贴合
"""
from __future__ import annotations

import logging
import threading
from typing import Iterator, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from device.wifi_backend import WifiBackend
from gui.styles import tokens as t
from gui.workers.screen_stream_worker import ScreenStreamWorker

logger = logging.getLogger(__name__)


def _wifi_frame_factory(endpoint: str, token: str, fps: int, quality: int, scale: float):
    """返回一个帧迭代器工厂，供 ScreenStreamWorker 消费。"""

    def factory(stop_event: threading.Event) -> Iterator[QImage]:
        backend: Optional[WifiBackend] = None
        try:
            backend = WifiBackend(endpoint=endpoint, token=token, timeout=5.0)
            for frame in backend.stream_screen(
                fps=fps,
                quality=quality,
                scale=scale,
                stop_event=stop_event,
            ):
                if stop_event.is_set():
                    break
                img = QImage.fromData(frame, "JPEG")
                if not img.isNull():
                    yield img
        finally:
            try:
                if backend is not None:
                    backend.close()
            except Exception:
                pass

    return factory


class ScreenMirrorDialog(QDialog):
    """非模态屏幕镜像窗口。"""

    def __init__(
        self,
        endpoint: str,
        token: str,
        *,
        fps: int = 12,
        quality: int = 55,
        scale: float = 1.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("屏幕共享 - Guiness")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.setModal(False)
        self.resize(360, 720)
        self.setMinimumSize(240, 400)

        self._last_pixmap: Optional[QPixmap] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部状态条
        header = QWidget()
        header.setStyleSheet(
            f"background: {t.NEUTRAL_0}; border-bottom: 1px solid {t.NEUTRAL_200};"
        )
        header_h = QHBoxLayout(header)
        header_h.setContentsMargins(12, 8, 12, 8)
        self._status_label = QLabel("连接中...")
        self._status_label.setStyleSheet(
            f"color: {t.NEUTRAL_700}; font-size: {t.FONT_XS}px; "
            f"font-weight: {t.WEIGHT_SEMI}; background: transparent;"
        )
        header_h.addWidget(self._status_label, 1)

        self._btn_close = QPushButton("停止")
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.setStyleSheet(f"""
            QPushButton {{
                background: {t.NEUTRAL_0};
                color: {t.DANGER};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
                padding: 4px 12px;
                font-weight: {t.WEIGHT_SEMI};
                font-size: {t.FONT_XS}px;
            }}
            QPushButton:hover {{
                background: {t.DANGER_SOFT};
                border-color: {t.DANGER};
            }}
        """)
        self._btn_close.clicked.connect(self.close)
        header_h.addWidget(self._btn_close)
        root.addWidget(header)

        # 图像区
        self._image_label = QLabel("等待首帧...")
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setStyleSheet(
            f"background: {t.NEUTRAL_100}; color: {t.NEUTRAL_500}; "
            f"font-size: {t.FONT_SM}px;"
        )
        self._image_label.setMinimumSize(200, 360)
        root.addWidget(self._image_label, 1)

        # 启动 worker
        frame_factory = _wifi_frame_factory(endpoint, token, fps, quality, scale)
        self._worker = ScreenStreamWorker(frame_factory, parent=self)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.status_changed.connect(self._on_status)
        self._worker.start()

    # ── 事件 ──

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self._worker.frame_ready.disconnect(self._on_frame)
        except (TypeError, RuntimeError):
            pass
        try:
            self._worker.status_changed.disconnect(self._on_status)
        except (TypeError, RuntimeError):
            pass

        self._worker.stop()
        if not self._worker.wait(200):
            logger.info("screen stream worker 未即刻退出，转后台自终（不阻塞主线程）")
            self._worker.setParent(None)
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_scaled()

    # ── 槽 ──

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
        else:
            self._status_label.setText(status)

    def _refresh_scaled(self) -> None:
        if self._last_pixmap is None:
            return
        size = self._image_label.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        scaled = self._last_pixmap.scaled(
            size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)
        if self._status_label.text() == "已连接，等待首帧":
            self._status_label.setText("串流中")
