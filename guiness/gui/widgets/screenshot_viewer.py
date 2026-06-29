# -*- coding: utf-8 -*-
"""
截图查看器：显示截图并在上方叠加动作标注（Tap 圆点、Swipe 箭头等）。
点击截图可弹出全屏大图。
"""
import os
from PySide6.QtWidgets import (
    QLabel, QVBoxLayout, QWidget, QScrollArea, QDialog, QHBoxLayout,
    QPushButton, QApplication,
)
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QFont

from gui.styles import tokens as t


# 与 step_card 徽章同一套语义分类：Tap/Click/LongPress/Type 用 accent 蓝，
# Swipe 用中性深灰避免喧宾夺主，Complete/Fail 用成功/危险色。
_ACTION_COLORS = {
    "Click":     QColor(t.ACCENT),
    "Tap":       QColor(t.ACCENT),
    "LongPress": QColor(t.ACCENT),
    "Swipe":     QColor(t.NEUTRAL_700),
    "Type":      QColor(t.ACCENT),
    "Search":    QColor(t.ACCENT),
    "Back":      QColor(t.NEUTRAL_500),
    "Complete":  QColor(t.SUCCESS),
    "Fail":      QColor(t.DANGER),
}


class _ImageZoomDialog(QDialog):
    """全屏大图弹窗，点击任意位置或按 Escape 关闭。"""

    def __init__(self, pixmap: QPixmap, action: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("截图预览")
        self.setModal(True)
        self.setStyleSheet(f"background: {t.NEUTRAL_900};")
        # 取屏幕 85% 大小
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            self.resize(int(geom.width() * 0.85), int(geom.height() * 0.85))
        else:
            self.resize(1200, 800)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 在弹窗里绘制带标注的大图
        display = pixmap.scaled(
            self.width() - 40, self.height() - 40,
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        if action:
            display = _draw_action_overlay(pixmap, display, action)

        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setPixmap(display)
        label.setStyleSheet("background: transparent;")
        layout.addWidget(label)

    def mousePressEvent(self, event) -> None:
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.accept()
        super().keyPressEvent(event)


def _draw_action_overlay(orig_pixmap: QPixmap, display: QPixmap, action: dict) -> QPixmap:
    """在 display pixmap 上绘制动作标注。坐标从 orig_pixmap 映射到 display。"""
    canvas = QPixmap(display)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)

    w, h = canvas.width(), canvas.height()
    orig_w, orig_h = orig_pixmap.width(), orig_pixmap.height()
    func = action.get("func", "")
    color = _ACTION_COLORS.get(func, QColor(t.ACCENT))

    def to_display(x, y):
        if isinstance(x, float) and 0 < x <= 1.0:
            return x * w, y * h
        scale_x = w / orig_w if orig_w > 0 else 1
        scale_y = h / orig_h if orig_h > 0 else 1
        return x * scale_x, y * scale_y

    if func in ("Click", "Tap", "LongPress", "Search", "Type"):
        pos = action.get("position", [])
        if len(pos) >= 2:
            cx, cy = to_display(pos[0], pos[1])
            cx, cy = int(cx), int(cy)
            pen = QPen(color, 3)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 60)))
            painter.drawEllipse(QPointF(cx, cy), 28, 28)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(cx, cy), 7, 7)
            label = func
            if func in ("Search", "Type"):
                text = action.get("text", "")
                if text:
                    preview = text if len(text) <= 16 else text[:16] + "…"
                    label = f"{func}: {preview}"
            painter.setFont(QFont("PingFang SC", 12, QFont.Bold))
            painter.setPen(QPen(Qt.white))
            painter.drawText(cx + 32, cy + 5, label)

    elif func == "Swipe":
        sp = action.get("start_position", [])
        ep = action.get("end_position", [])
        if len(sp) >= 2 and len(ep) >= 2:
            x1, y1 = to_display(sp[0], sp[1])
            x2, y2 = to_display(ep[0], ep[1])
            pen = QPen(color, 3, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(x2, y2), 10, 10)

    painter.end()
    return canvas


class ScreenshotViewer(QWidget):
    """显示单张截图，并叠加该步骤的动作标注。点击可放大查看。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._action: dict | None = None
        self.setCursor(Qt.PointingHandCursor)

        # Enable mouse tracking
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignCenter)
        self._scroll.setMouseTracking(True)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setMouseTracking(True)
        self._label.setCursor(Qt.CrossCursor)
        self._label.installEventFilter(self)
        self._scroll.setWidget(self._label)

        layout.addWidget(self._scroll)

        # Floating coordinate overlay badge
        self._coord_label = QLabel(self)
        self._coord_label.setObjectName("coordBadge")
        self._coord_label.setStyleSheet(f"""
            QLabel#coordBadge {{
                background: rgba(23, 23, 23, 0.85);
                color: {t.NEUTRAL_100};
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: {t.RADIUS_SM}px;
                padding: 5px 10px;
                font-family: monospace;
                font-size: {t.FONT_XS}px;
                font-weight: {t.WEIGHT_SEMI};
            }}
        """)
        self._coord_label.hide()

    def eventFilter(self, watched, event) -> bool:
        if watched == self._label and self._pixmap is not None:
            # CheckMouseMove
            if event.type() == QEvent.MouseMove:
                self._update_coord(event.pos())
            elif event.type() == QEvent.Leave:
                self._coord_label.hide()
        return super().eventFilter(watched, event)

    def _update_coord(self, label_pos) -> None:
        if self._pixmap is None or self._label.pixmap() is None:
            self._coord_label.hide()
            return

        lbl_w = self._label.width()
        lbl_h = self._label.height()
        pm_w = self._label.pixmap().width()
        pm_h = self._label.pixmap().height()

        off_x = (lbl_w - pm_w) // 2
        off_y = (lbl_h - pm_h) // 2

        px_x = label_pos.x() - off_x
        px_y = label_pos.y() - off_y

        if px_x < 0 or px_x >= pm_w or px_y < 0 or px_y >= pm_h:
            self._coord_label.hide()
            return

        orig_w = self._pixmap.width()
        orig_h = self._pixmap.height()

        orig_x = int(px_x * orig_w / pm_w)
        orig_y = int(px_y * orig_h / pm_h)

        orig_x = max(0, min(orig_x, orig_w - 1))
        orig_y = max(0, min(orig_y, orig_h - 1))

        x_pct = orig_x / orig_w * 100.0
        y_pct = orig_y / orig_h * 100.0

        self._coord_label.setText(f"X: {orig_x}, Y: {orig_y} | {x_pct:.1f}%, {y_pct:.1f}%")
        self._coord_label.adjustSize()
        self._coord_label.move(
            self.width() - self._coord_label.width() - 10,
            self.height() - self._coord_label.height() - 10
        )
        self._coord_label.show()
        self._coord_label.raise_()

    def load_image(self, path: str, action: dict | None = None) -> None:
        """加载截图文件并设置动作标注。"""
        self._action = action
        if not path:
            self._pixmap = None
            self._label.setText("无截图")
            return
        if not os.path.isfile(path):
            self._pixmap = None
            self._label.setText(f"截图文件不存在：\n{path}")
            self._label.setWordWrap(True)
            return

        pm = QPixmap(path)
        if pm.isNull():
            self._pixmap = None
            self._label.setText(f"截图无法解码：\n{path}")
            self._label.setWordWrap(True)
            return
        self._pixmap = pm
        self._render()

    def clear(self) -> None:
        self._pixmap = None
        self._action = None
        self._label.clear()

    def mousePressEvent(self, event) -> None:
        if self._pixmap:
            dlg = _ImageZoomDialog(self._pixmap, self._action, self.window())
            dlg.exec()
        else:
            super().mousePressEvent(event)

    def _render(self) -> None:
        if self._pixmap is None:
            return

        vp = self._scroll.viewport()
        avail_w = max(vp.width() - 4, 100)
        avail_h = max(vp.height() - 4, 100)

        display = self._pixmap.scaled(
            avail_w,
            avail_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        if self._action:
            display = _draw_action_overlay(self._pixmap, display, self._action)

        self._label.setPixmap(display)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._pixmap:
            self._render()
