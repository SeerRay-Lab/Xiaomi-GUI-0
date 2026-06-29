# -*- coding: utf-8 -*-
"""底部输入栏：多行查询输入 + 发送/停止按钮

Enter 发送，Shift+Enter 换行，高度自适应 1~4 行。
"""
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QPlainTextEdit, QPushButton,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeyEvent, QFontMetrics

from gui.styles import tokens as t


_MAX_VISIBLE_LINES = 4
_MIN_VISIBLE_LINES = 1


class _AutoResizeTextEdit(QPlainTextEdit):
    """支持 Enter 发送、Shift+Enter 换行、高度自适应的文本框。"""

    submit_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTabChangesFocus(True)
        self.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        self._line_height = QFontMetrics(self.font()).lineSpacing()
        self._adjust_height()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.submit_requested.emit()
            return
        super().keyPressEvent(event)

    def _adjust_height(self) -> None:
        doc_height = self.document().size().height()
        self._line_height = max(QFontMetrics(self.font()).lineSpacing(), 1)
        line_count = max(int(doc_height / self._line_height), _MIN_VISIBLE_LINES)
        line_count = min(line_count, _MAX_VISIBLE_LINES)
        # content height + margins + border
        margins = self.contentsMargins()
        new_h = int(line_count * self._line_height + margins.top() + margins.bottom() + 16)
        self.setFixedHeight(max(new_h, 42))


class InputBar(QFrame):
    """底部输入栏。"""

    send_requested = Signal(str, str)
    stop_requested = Signal()
    resume_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inputBar")
        self.setMinimumHeight(60)
        self.setMaximumHeight(160)
        self.setStyleSheet(f"""
            QFrame#inputBar {{
                background: {t.NEUTRAL_0};
                border-top: 1px solid {t.NEUTRAL_200};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        input_qss = f"""
            QPlainTextEdit {{
                background: {t.NEUTRAL_100};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
                padding: 8px 14px;
                color: {t.NEUTRAL_900};
                font-size: {t.FONT_SM}px;
            }}
            QPlainTextEdit:focus {{ border-color: {t.ACCENT}; background: {t.NEUTRAL_0}; }}
        """

        self._query_input = _AutoResizeTextEdit()
        self._query_input.setPlaceholderText("输入指令，如：打开设置（Shift+Enter 换行）")
        self._query_input.setStyleSheet(input_qss)
        self._query_input.submit_requested.connect(self._on_send)
        layout.addWidget(self._query_input, stretch=1)

        btn_h = 42

        self._btn_send = QPushButton("发送")
        self._btn_send.setObjectName("sendButton")
        self._btn_send.setFixedSize(88, btn_h)
        self._btn_send.setStyleSheet(f"""
            QPushButton#sendButton {{
                background: {t.NEUTRAL_900}; color: {t.NEUTRAL_0};
                border: none; border-radius: {t.RADIUS_SM}px;
                font-weight: {t.WEIGHT_SEMI}; font-size: {t.FONT_SM}px;
            }}
            QPushButton#sendButton:hover {{ background: {t.NEUTRAL_700}; }}
            QPushButton#sendButton:disabled {{ background: {t.NEUTRAL_200}; color: {t.NEUTRAL_400}; }}
        """)
        self._btn_send.clicked.connect(self._on_send)
        layout.addWidget(self._btn_send)

        self._btn_stop = QPushButton("停止")
        self._btn_stop.setObjectName("stopButton")
        self._btn_stop.setFixedSize(88, btn_h)
        self._btn_stop.setStyleSheet(f"""
            QPushButton#stopButton {{
                background: {t.NEUTRAL_0}; color: {t.DANGER};
                border: 1px solid {t.NEUTRAL_200}; border-radius: {t.RADIUS_SM}px;
                font-weight: {t.WEIGHT_SEMI}; font-size: {t.FONT_SM}px;
            }}
            QPushButton#stopButton:hover {{ background: {t.NEUTRAL_100}; border-color: {t.DANGER}; }}
            QPushButton#stopButton:disabled {{ background: {t.NEUTRAL_100}; color: {t.NEUTRAL_400}; border-color: {t.NEUTRAL_200}; }}
        """)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self.stop_requested.emit)
        layout.addWidget(self._btn_stop)

        # "继续"按钮：默认隐藏，仅在 conversation stopped/awaiting_user 时出现
        self._btn_resume = QPushButton("继续")
        self._btn_resume.setObjectName("resumeButton")
        self._btn_resume.setFixedSize(88, btn_h)
        self._btn_resume.setStyleSheet(f"""
            QPushButton#resumeButton {{
                background: {t.NEUTRAL_0}; color: {t.ACCENT};
                border: 1px solid {t.ACCENT}; border-radius: {t.RADIUS_SM}px;
                font-weight: {t.WEIGHT_SEMI}; font-size: {t.FONT_SM}px;
            }}
            QPushButton#resumeButton:hover {{ background: {t.ACCENT_SOFT}; }}
        """)
        self._btn_resume.setVisible(False)
        self._btn_resume.clicked.connect(self.resume_requested.emit)
        layout.addWidget(self._btn_resume)

    def _on_send(self) -> None:
        query = self._query_input.toPlainText().strip()
        if not query:
            return
        self.send_requested.emit(query, "")
        self._query_input.clear()

    def set_running(self, is_running: bool) -> None:
        self._btn_send.setEnabled(not is_running)
        self._btn_stop.setEnabled(is_running)
        self._btn_stop.setText("停止")
        if is_running:
            self._btn_resume.setVisible(False)

    def set_resumable(self, resumable: bool) -> None:
        """显示/隐藏"继续"按钮。stopped / awaiting_user 时置 True。"""
        self._btn_resume.setVisible(resumable)

    def set_stopping(self) -> None:
        """用户点了停止：按钮立刻置灰 + 显示"正在停止..."，防止重复点击。"""
        self._btn_stop.setEnabled(False)
        self._btn_stop.setText("正在停止…")

    def set_focus(self) -> None:
        self._query_input.setFocus()

    def set_query_text(self, text: str) -> None:
        """外部填充：把示例 query 放到输入框并聚焦，不自动发送。"""
        self._query_input.setPlainText(text)
        self._query_input.setFocus()
        cursor = self._query_input.textCursor()
        cursor.movePosition(cursor.End)
        self._query_input.setTextCursor(cursor)
