# -*- coding: utf-8 -*-
"""用户消息气泡 + 系统状态消息"""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy, QMenu, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics

from gui.styles import tokens as t


def _context_menu_qss() -> str:
    return f"""
        QMenu {{
            background: {t.NEUTRAL_0};
            border: 1px solid {t.NEUTRAL_200};
            border-radius: {t.RADIUS_SM}px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 24px;
            color: {t.NEUTRAL_900};
            border-radius: {t.RADIUS_SM}px;
        }}
        QMenu::item:selected {{
            background: {t.NEUTRAL_100};
        }}
        QMenu::item:disabled {{
            color: {t.NEUTRAL_400};
        }}
    """


class ConfigSummary(QFrame):
    """对话顶部的设备+模型配置摘要。"""

    def __init__(self, conv, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.addStretch()

        tags = []
        if conv.device_id:
            tags.append(("设备", conv.device_id))
        if conv.model_source == "mify":
            tags.append(("模型", conv.model_name or "mify"))
        else:
            name = conv.model_name or "UIAgent"
            tags.append(("端点", name))

        inner = QFrame()
        inner.setObjectName("configSummaryInner")
        inner.setStyleSheet(f"""
            QFrame#configSummaryInner {{
                background: {t.NEUTRAL_100};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
                padding: 6px 12px;
            }}
        """)
        hlayout = QHBoxLayout(inner)
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(16)

        for key, value in tags:
            tag = QLabel(f"{key}: {value}")
            tag.setStyleSheet(
                f"color: {t.NEUTRAL_700}; font-size: {t.FONT_XS}px; "
                f"font-weight: {t.WEIGHT_SEMI}; background: transparent;"
            )
            hlayout.addWidget(tag)

        layout.addWidget(inner)
        layout.addStretch()


class UserMessageBubble(QFrame):
    """右对齐的用户消息气泡。

    实现细节：QLabel 开 wordWrap 会让 sizeHint 变成"最小合理宽度"，
    导致短文本也被收缩到比单行还窄而强制换行。解决办法——自己用
    QFontMetrics 量文字单行像素宽：
    - 单行宽 ≤ max_w：关 wordWrap，bubble 固定成文字宽，漂亮贴合
    - 单行宽 > max_w：开 wordWrap，bubble 固定成 max_w，内部换行
    """

    _BUBBLE_MAX_W = 680   # 气泡内容区最大宽度（不含左右 padding）
    _H_PADDING = 18 * 2   # 与下方 QFrame#userBubbleInner 的 padding 保持一致

    def __init__(self, query: str, app: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("userBubble")
        self.setStyleSheet("QFrame#userBubble { background: transparent; border: none; }")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 8, 4)
        layout.addStretch()

        bubble = QFrame()
        bubble.setObjectName("userBubbleInner")
        bubble.setStyleSheet(f"""
            QFrame#userBubbleInner {{
                background: {t.NEUTRAL_900};
                border: none;
                border-radius: {t.RADIUS_MD}px;
                padding: 12px 18px;
            }}
        """)
        blayout = QVBoxLayout(bubble)
        blayout.setContentsMargins(0, 0, 0, 0)
        blayout.setSpacing(4)

        text_label = QLabel(query)
        text_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        text_label.setCursor(Qt.IBeamCursor)
        text_label.setContextMenuPolicy(Qt.CustomContextMenu)
        text_label.customContextMenuRequested.connect(
            lambda pos, lbl=text_label: self._show_context_menu(lbl, pos)
        )
        text_label.setStyleSheet(
            f"color: {t.NEUTRAL_0}; font-size: {t.FONT_MD}px; "
            f"font-weight: {t.WEIGHT_REGULAR}; background: transparent;"
        )

        # 量文字单行宽，按 max_w 决定是否换行
        from PySide6.QtGui import QFont as _QFont
        _font = text_label.font()
        _font.setPixelSize(t.FONT_MD)
        text_label.setFont(_font)
        fm = QFontMetrics(_font)
        single_line_w = fm.horizontalAdvance(query.replace("\n", " "))
        if single_line_w <= self._BUBBLE_MAX_W:
            text_label.setWordWrap(False)
            bubble.setMaximumWidth(single_line_w + self._H_PADDING + 2)
        else:
            text_label.setWordWrap(True)
            bubble.setMaximumWidth(self._BUBBLE_MAX_W + self._H_PADDING)

        bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        blayout.addWidget(text_label)

        if app:
            app_label = QLabel(f"App: {app}")
            app_label.setStyleSheet(
                f"color: {t.NEUTRAL_400}; font-size: {t.FONT_XS}px; background: transparent;"
            )
            blayout.addWidget(app_label)

        layout.addWidget(bubble)

        self._query = query

    def _show_context_menu(self, label: QLabel, pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(_context_menu_qss())

        selected = label.selectedText()
        act_copy_sel = menu.addAction("复制选中")
        act_copy_sel.setEnabled(bool(selected))
        act_copy_all = menu.addAction("复制全部")

        action = menu.exec(label.mapToGlobal(pos))
        if action == act_copy_sel:
            QApplication.clipboard().setText(selected)
        elif action == act_copy_all:
            QApplication.clipboard().setText(self._query)


class SystemMessage(QFrame):
    """居中的系统状态消息。"""

    _STYLE_MAP = {
        "info":    (t.NEUTRAL_700, t.NEUTRAL_100, t.NEUTRAL_200),
        "success": (t.SUCCESS, t.SUCCESS_SOFT, t.SUCCESS_SOFT),
        "error":   (t.DANGER, t.DANGER_SOFT, t.DANGER_SOFT),
        "warning": (t.WARNING, t.WARNING_SOFT, t.WARNING_SOFT),
    }

    def __init__(self, text: str, msg_type: str = "info", parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.addStretch()

        fg, bg, bd = self._STYLE_MAP.get(msg_type, self._STYLE_MAP["info"])
        label = QLabel(text)
        label.setStyleSheet(f"""
            QLabel {{
                color: {fg}; font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI};
                padding: 6px 16px;
                background: {bg}; border: 1px solid {bd};
                border-radius: {t.RADIUS_SM}px;
            }}
        """)
        layout.addWidget(label)
        layout.addStretch()
