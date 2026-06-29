# -*- coding: utf-8 -*-
"""后端无关的屏幕流 worker：接收一个帧迭代器工厂，在 QThread 中消费并 emit QImage。

用于内嵌 LiveMirrorViewport 和独立弹窗 ScreenMirrorDialog 共用。
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Iterator

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

logger = logging.getLogger(__name__)


class ScreenStreamWorker(QThread):
    """在后台线程中消费帧迭代器，将 QImage 推送到主线程。

    frame_iter_factory 签名: (stop_event: threading.Event) -> Iterator[QImage]
    工厂必须在 stop_event 被 set 后尽快退出迭代。
    """

    frame_ready = Signal(QImage)
    status_changed = Signal(str)  # "connected" | "disconnected" | "error:{msg}" | "warning:{msg}"

    def __init__(
        self,
        frame_iter_factory: Callable[[threading.Event], Iterator[QImage]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._factory = frame_iter_factory
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            self.status_changed.emit("connected")
            for img in self._factory(self._stop_event):
                if self._stop_event.is_set():
                    break
                if img is not None and not img.isNull():
                    self.frame_ready.emit(img)
        except Exception as e:
            logger.warning(f"screen stream worker 退出异常: {e}")
            self.status_changed.emit(f"error:{e}")
        finally:
            self.status_changed.emit("disconnected")
