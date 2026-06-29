# -*- coding: utf-8 -*-
"""可折叠区域：标题 + 展开/收起内容。"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QSizePolicy
from PySide6.QtCore import Qt

from gui.styles import tokens as t


class CollapsibleSection(QWidget):
    """可折叠区域：标题 + 展开/收起内容。"""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self._expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setText(f"  {title}")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(False)
        self._toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle_btn.setArrowType(Qt.RightArrow)
        self._toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._toggle_btn.setFixedHeight(34)
        self._toggle_btn.setStyleSheet(f"""
            QToolButton {{
                background: {t.NEUTRAL_50};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
                color: {t.NEUTRAL_700};
                font-weight: {t.WEIGHT_SEMI};
                font-size: {t.FONT_SM}px;
                text-align: left;
                padding-left: 8px;
            }}
            QToolButton:hover {{
                background: {t.NEUTRAL_100};
                color: {t.NEUTRAL_900};
            }}
        """)
        self._toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self._toggle_btn)

        self._content = QWidget()
        self._content.setVisible(False)
        layout.addWidget(self._content)

    def content_layout(self) -> QVBoxLayout:
        lay = self._content.layout()
        if lay is None:
            lay = QVBoxLayout(self._content)
            lay.setContentsMargins(0, 8, 0, 0)
            lay.setSpacing(10)
        return lay

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._toggle_btn.setArrowType(
            Qt.DownArrow if self._expanded else Qt.RightArrow
        )

    def expand(self) -> None:
        self._expanded = True
        self._content.setVisible(True)
        self._toggle_btn.setChecked(True)
        self._toggle_btn.setArrowType(Qt.DownArrow)
