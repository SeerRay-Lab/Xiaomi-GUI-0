# -*- coding: utf-8 -*-
"""侧边栏：对话列表 + 新建对话 + 设备状态 + 设置入口"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMenu, QLineEdit, QComboBox,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPixmap, QAction

from gui.chat_manager import Conversation
from gui.paths import resource_path
from gui.styles import tokens as t


_STATUS_COLORS = {
    "pending": t.NEUTRAL_400,
    "running": t.ACCENT,
    "done": t.SUCCESS,
    "error": t.DANGER,
    "stopped": t.NEUTRAL_500,
    "awaiting_user": t.WARNING,
}


class ConversationItem(QFrame):
    """侧边栏中的单条对话。"""

    clicked = Signal(str)
    delete_clicked = Signal(str)
    clear_all_clicked = Signal()

    def __init__(self, conv: Conversation, parent=None) -> None:
        super().__init__(parent)
        self.conv_id = conv.id
        self._active = False
        self._query_text = conv.query
        self._app_text = conv.app
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(62)
        self._update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        self._set_status(conv.status)
        row1.addWidget(self._dot, alignment=Qt.AlignVCenter)

        query_display = conv.query if len(conv.query) <= 22 else conv.query[:20] + "..."
        self._query_label = QLabel(query_display)
        self._query_label.setStyleSheet(
            f"color: {t.NEUTRAL_900}; font-size: {t.FONT_SM}px; "
            f"font-weight: {t.WEIGHT_SEMI}; background: transparent;"
        )
        row1.addWidget(self._query_label, stretch=1)

        layout.addLayout(row1)

        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        self._meta_label = QLabel(f"{conv.created_at}  {len(conv.steps)} 步")
        self._meta_label.setStyleSheet(
            f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; "
            f"padding-left: 16px; background: transparent;"
        )
        layout.addWidget(self._meta_label)

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update_style()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {t.NEUTRAL_0};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                color: {t.NEUTRAL_900};
                font-size: {t.FONT_XS}px;
                border-radius: {t.RADIUS_SM}px;
            }}
            QMenu::item:selected {{
                background: {t.DANGER_SOFT};
                color: {t.DANGER};
            }}
        """)
        delete_action = QAction("删除此条对话", self)
        delete_action.triggered.connect(
            lambda: self.delete_clicked.emit(self.conv_id)
        )
        menu.addAction(delete_action)

        clear_all_action = QAction("清空所有历史对话", self)
        clear_all_action.triggered.connect(self.clear_all_clicked.emit)
        menu.addAction(clear_all_action)

        menu.exec(event.globalPos())
        event.accept()

    def update_status(self, status: str, step_count: int = 0, query: str = None, app: str = None) -> None:
        self._set_status(status)
        meta_text = self._meta_label.text().split("  ")[0]
        self._meta_label.setText(f"{meta_text}  {step_count} 步")
        if query is not None:
            self._query_text = query
            query_display = query if len(query) <= 22 else query[:20] + "..."
            self._query_label.setText(query_display)
        if app is not None:
            self._app_text = app

    def _set_status(self, status: str) -> None:
        color = _STATUS_COLORS.get(status, t.NEUTRAL_400)
        self._dot.setStyleSheet(f"background: {color}; border-radius: 4px;")

    def _update_style(self) -> None:
        if self._active:
            self.setStyleSheet(f"""
                ConversationItem {{
                    background: {t.NEUTRAL_100};
                    border: 1px solid {t.NEUTRAL_200};
                    border-radius: {t.RADIUS_MD}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                ConversationItem {{
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: {t.RADIUS_MD}px;
                }}
                ConversationItem:hover {{
                    background: {t.NEUTRAL_100};
                }}
            """)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.conv_id)
            event.accept()
            return
        super().mousePressEvent(event)


class Sidebar(QWidget):
    """侧边栏。"""

    new_chat_requested = Signal()
    conversation_selected = Signal(str)
    delete_requested = Signal(str)
    clear_all_requested = Signal()
    settings_requested = Signal()
    mirror_requested = Signal()
    display_mode_changed = Signal(str)  # "image" | "mirror"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(450)
        self.setStyleSheet(f"background: {t.NEUTRAL_50};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(12)

        # Header: 图标 + 品牌名 + 新对话按钮
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_label = QLabel()
        icon_path = resource_path(os.path.join("resources", "icon_256.png"))
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path)
            if not pix.isNull():
                pix = pix.scaled(
                    24, 24,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                icon_label.setPixmap(pix)
        icon_label.setFixedSize(24, 24)
        icon_label.setStyleSheet("background: transparent;")
        header.addWidget(icon_label, alignment=Qt.AlignVCenter)

        title = QLabel("Guiness")
        title.setStyleSheet(
            f"color: {t.NEUTRAL_900}; font-size: {t.FONT_LG}px; "
            f"font-weight: {t.WEIGHT_SEMI}; background: transparent;"
        )
        header.addWidget(title, alignment=Qt.AlignVCenter)
        header.addStretch()

        btn_new = QPushButton("+ 新对话")
        btn_new.setObjectName("newChatButton")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setFixedHeight(32)
        btn_new.setStyleSheet(f"""
            QPushButton#newChatButton {{
                background: {t.NEUTRAL_900}; color: {t.NEUTRAL_0};
                border: none; border-radius: {t.RADIUS_SM}px;
                font-weight: {t.WEIGHT_SEMI}; font-size: {t.FONT_XS}px;
                padding: 0 14px;
            }}
            QPushButton#newChatButton:hover {{ background: {t.NEUTRAL_700}; }}
        """)
        btn_new.clicked.connect(self.new_chat_requested.emit)
        header.addWidget(btn_new)
        layout.addLayout(header)

        # 搜索输入框
        search_container = QWidget()
        search_container.setStyleSheet("background: transparent;")
        sc_lay = QHBoxLayout(search_container)
        sc_lay.setContentsMargins(4, 0, 4, 0)
        sc_lay.setSpacing(6)
        
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(f"font-size: 13px; color: {t.NEUTRAL_400}; background: transparent;")
        
        self._search_input = QLineEdit()
        self._search_input.setObjectName("searchBar")
        self._search_input.setPlaceholderText("搜索历史对话...")
        self._search_input.setStyleSheet(f"""
            QLineEdit#searchBar {{
                background: {t.NEUTRAL_0};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
                padding: 5px 8px;
                color: {t.NEUTRAL_900};
                font-size: {t.FONT_XS}px;
            }}
            QLineEdit#searchBar:hover {{
                border-color: {t.NEUTRAL_300};
            }}
            QLineEdit#searchBar:focus {{
                border-color: {t.ACCENT};
                background: {t.NEUTRAL_0};
            }}
        """)
        self._search_input.textChanged.connect(self._on_search_changed)
        
        sc_lay.addWidget(search_icon)
        sc_lay.addWidget(self._search_input)
        layout.addWidget(search_container)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_sidebar_menu)

        # "历史对话" section header
        section_label = QLabel("历史对话")
        section_label.setStyleSheet(
            f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; "
            f"font-weight: {t.WEIGHT_SEMI}; padding: 4px 8px 0 8px; "
            f"background: transparent; letter-spacing: 0.5px;"
        )
        layout.addWidget(section_label)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._list_layout.setContentsMargins(0, 4, 0, 4)
        self._list_layout.setSpacing(4)

        self._scroll.setWidget(self._list_container)
        layout.addWidget(self._scroll, stretch=1)

        # ── Footer: 设备状态 + 设置按钮 ──
        footer = QFrame()
        footer.setStyleSheet(f"""
            QFrame {{
                background: {t.NEUTRAL_0};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_MD}px;
            }}
        """)
        footer_lay = QVBoxLayout(footer)
        footer_lay.setContentsMargins(10, 8, 10, 8)
        footer_lay.setSpacing(6)

        # 设备状态行
        dev_row = QHBoxLayout()
        dev_row.setSpacing(6)
        self._device_label = QLabel("\U0001F4F1 检测中...")
        self._device_label.setStyleSheet(
            f"font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI}; "
            f"color: {t.NEUTRAL_500}; background: transparent;"
        )
        dev_row.addWidget(self._device_label)
        dev_row.addStretch()
        footer_lay.addLayout(dev_row)

        # 显示模式切换
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_lbl = QLabel("\U0001F4FA 显示模式")
        mode_lbl.setStyleSheet(
            f"font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI}; "
            f"color: {t.NEUTRAL_500}; background: transparent;"
        )
        mode_row.addWidget(mode_lbl)
        self._display_mode_combo = QComboBox()
        self._display_mode_combo.addItem("图片模式", "image")
        self._display_mode_combo.addItem("实时镜像", "mirror")
        self._display_mode_combo.setStyleSheet(
            f"QComboBox {{ font-size: {t.FONT_XS}px; background: {t.NEUTRAL_0}; }}"
        )
        self._display_mode_combo.currentIndexChanged.connect(
            lambda _i: self.display_mode_changed.emit(
                self._display_mode_combo.currentData()
            )
        )
        mode_row.addWidget(self._display_mode_combo, 1)
        footer_lay.addLayout(mode_row)

        # 共用的 ghost 风格（屏幕共享 + 设置）
        ghost_qss = f"""
            QPushButton {{
                background: transparent; border: none;
                color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI};
                text-align: left; padding: 4px 2px;
            }}
            QPushButton:hover {{ color: {t.NEUTRAL_900}; }}
        """

        # 屏幕共享按钮（从主屏迁过来）
        self._btn_mirror = QPushButton("\U0001F5A5  屏幕共享")
        self._btn_mirror.setCursor(Qt.PointingHandCursor)
        self._btn_mirror.setStyleSheet(ghost_qss)
        self._btn_mirror.clicked.connect(self.mirror_requested.emit)
        footer_lay.addWidget(self._btn_mirror)

        # 设置按钮
        btn_settings = QPushButton("⚙  设置")
        btn_settings.setCursor(Qt.PointingHandCursor)
        btn_settings.setStyleSheet(ghost_qss)
        btn_settings.clicked.connect(self.settings_requested.emit)
        footer_lay.addWidget(btn_settings)

        layout.addWidget(footer)

        self._items: dict[str, ConversationItem] = {}

    def add_conversation(self, conv: Conversation) -> None:
        item = ConversationItem(conv)
        item.clicked.connect(self._on_item_clicked)
        item.delete_clicked.connect(self._on_delete_clicked)
        item.clear_all_clicked.connect(self.clear_all_requested.emit)
        self._items[conv.id] = item
        self._list_layout.insertWidget(0, item)
        self._on_search_changed(self._search_input.text())

    def _on_search_changed(self, text: str) -> None:
        text = text.lower().strip()
        for item in self._items.values():
            query = getattr(item, "_query_text", "").lower()
            app = getattr(item, "_app_text", "").lower()
            if not text or text in query or text in app:
                item.show()
            else:
                item.hide()

    def _show_sidebar_menu(self, pos) -> None:
        child = self.childAt(pos)
        while child is not None and child is not self:
            if isinstance(child, ConversationItem):
                return
            child = child.parentWidget()

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {t.NEUTRAL_0};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 16px;
                color: {t.NEUTRAL_900};
                font-size: {t.FONT_XS}px;
                border-radius: {t.RADIUS_SM}px;
            }}
            QMenu::item:selected {{
                background: {t.DANGER_SOFT};
                color: {t.DANGER};
            }}
        """)
        clear_all_action = QAction("清空所有历史对话", self)
        clear_all_action.triggered.connect(self.clear_all_requested.emit)
        menu.addAction(clear_all_action)
        menu.exec(self.mapToGlobal(pos))

    def remove_conversation(self, conv_id: str) -> None:
        item = self._items.pop(conv_id, None)
        if item:
            self._list_layout.removeWidget(item)
            item.deleteLater()

    def update_conversation(self, conv_id: str, status: str, step_count: int = 0, query: str = None, app: str = None) -> None:
        item = self._items.get(conv_id)
        if item:
            item.update_status(status, step_count, query, app)
            self._on_search_changed(self._search_input.text())

    def set_active(self, conv_id: str) -> None:
        for cid, item in self._items.items():
            item.set_active(cid == conv_id)

    def _on_item_clicked(self, conv_id: str) -> None:
        self.set_active(conv_id)
        self.conversation_selected.emit(conv_id)

    def _on_delete_clicked(self, conv_id: str) -> None:
        self.delete_requested.emit(conv_id)

    # ── 设备状态 ──

    def set_device_status(self, connected: bool, label: str = "") -> None:
        """更新页脚设备状态。label 可选——若为空连接时只显示"已连接"。"""
        if connected:
            text = f"\U0001F4F1 {label}" if label else "\U0001F4F1 已连接"
            self._device_label.setText(text)
            self._device_label.setStyleSheet(
                f"font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI}; "
                f"color: {t.SUCCESS}; background: transparent;"
            )
        else:
            self._device_label.setText("\U0001F4F1 未连接")
            self._device_label.setStyleSheet(
                f"font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI}; "
                f"color: {t.DANGER}; background: transparent;"
            )

    def set_display_mode(self, mode: str) -> None:
        """从外部同步 combo 选中项（不重复 emit 信号）。"""
        self._display_mode_combo.blockSignals(True)
        idx = self._display_mode_combo.findData(mode)
        if idx >= 0:
            self._display_mode_combo.setCurrentIndex(idx)
        self._display_mode_combo.blockSignals(False)

    def set_mirror_button_visible(self, visible: bool) -> None:
        """镜像模式激活时隐藏独立屏幕共享按钮，避免双流冲突。"""
        self._btn_mirror.setVisible(visible)
