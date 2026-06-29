# -*- coding: utf-8 -*-
"""设置对话框：左侧选项卡导航 + 右侧内容面板。

布局模式仿 VS Code / macOS 系统偏好设置：
左栏为垂直 Tab 列表，右侧为对应面板（设备 / 模型 / 操作参数 / 前台App / 图片压缩）。
数据全部落到 config.yaml，与主界面 ModelConfigPanel 共享同一事实源。
"""
import os

import yaml
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QPushButton, QFrame, QWidget,
    QScrollArea, QLineEdit, QRadioButton, QButtonGroup,
    QListWidget, QListWidgetItem, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from gui.paths import config_file_path
from gui.styles import tokens as t


def _dialog_qss() -> str:
    return f"""
QDialog#settingsDialog {{
    background: {t.NEUTRAL_50};
}}

/* ── 左侧导航 ── */
QListWidget#navList {{
    background: transparent;
    border: none;
    outline: none;
    padding: 4px 0;
    font-size: {t.FONT_SM}px;
}}
QListWidget#navList::item {{
    padding: 10px 18px;
    border-radius: {t.RADIUS_SM}px;
    margin: 2px 8px;
    color: {t.NEUTRAL_700};
    font-weight: {t.WEIGHT_SEMI};
}}
QListWidget#navList::item:hover {{
    background: {t.NEUTRAL_100};
    color: {t.NEUTRAL_900};
}}
QListWidget#navList::item:selected {{
    background: {t.ACCENT_SOFT};
    color: {t.ACCENT};
}}

/* ── 右侧面板区 ── */
QScrollArea#panelScroll {{
    background: transparent;
    border: none;
}}
QScrollArea#panelScroll > QWidget > QWidget {{
    background: transparent;
}}

/* ── 面板标题 ── */
QLabel#panelTitle {{
    color: {t.NEUTRAL_900};
    font-size: {t.FONT_LG}px;
    font-weight: {t.WEIGHT_SEMI};
    background: transparent;
}}
QLabel#panelDesc {{
    color: {t.NEUTRAL_500};
    font-size: {t.FONT_XS}px;
    background: transparent;
}}

/* ── 字段标签 ── */
QLabel#fieldLabel {{
    color: {t.NEUTRAL_700};
    font-size: {t.FONT_XS}px;
    font-weight: {t.WEIGHT_SEMI};
    background: transparent;
    padding-bottom: 2px;
}}

/* ── 输入控件 ── */
QDialog#settingsDialog QSpinBox,
QDialog#settingsDialog QDoubleSpinBox,
QDialog#settingsDialog QComboBox,
QDialog#settingsDialog QLineEdit {{
    background: {t.NEUTRAL_100};
    border: 1px solid {t.NEUTRAL_200};
    border-radius: {t.RADIUS_SM}px;
    padding: 8px 14px;
    color: {t.NEUTRAL_900};
    font-size: {t.FONT_SM}px;
    min-height: 22px;
    selection-background-color: {t.ACCENT};
    selection-color: {t.NEUTRAL_0};
}}
QDialog#settingsDialog QSpinBox:hover,
QDialog#settingsDialog QDoubleSpinBox:hover,
QDialog#settingsDialog QComboBox:hover,
QDialog#settingsDialog QLineEdit:hover {{
    border-color: {t.NEUTRAL_300};
    background: {t.NEUTRAL_0};
}}
QDialog#settingsDialog QSpinBox:focus,
QDialog#settingsDialog QDoubleSpinBox:focus,
QDialog#settingsDialog QComboBox:focus,
QDialog#settingsDialog QLineEdit:focus {{
    border-color: {t.ACCENT};
    background: {t.NEUTRAL_0};
}}
QDialog#settingsDialog QSpinBox::up-button,
QDialog#settingsDialog QSpinBox::down-button,
QDialog#settingsDialog QDoubleSpinBox::up-button,
QDialog#settingsDialog QDoubleSpinBox::down-button {{
    width: 0;
    border: none;
}}
QDialog#settingsDialog QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 28px;
    border-left: 1px solid {t.NEUTRAL_200};
    border-top-right-radius: {t.RADIUS_SM}px;
    border-bottom-right-radius: {t.RADIUS_SM}px;
    background: {t.NEUTRAL_100};
}}
QDialog#settingsDialog QComboBox::down-arrow {{
    width: 10px;
    height: 10px;
    image: none;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 5px solid {t.NEUTRAL_700};
}}
QDialog#settingsDialog QComboBox QAbstractItemView {{
    background-color: {t.NEUTRAL_0};
    border: 1px solid {t.NEUTRAL_300};
    border-radius: {t.RADIUS_SM}px;
    color: {t.NEUTRAL_900};
    selection-background-color: {t.ACCENT_SOFT};
    selection-color: {t.ACCENT};
    padding: 4px;
    outline: 0;
}}
QDialog#settingsDialog QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    min-height: 26px;
    background-color: {t.NEUTRAL_0};
}}

/* ── CheckBox / RadioButton ── */
QDialog#settingsDialog QCheckBox,
QDialog#settingsDialog QRadioButton {{
    color: {t.NEUTRAL_900};
    font-size: {t.FONT_SM}px;
    font-weight: {t.WEIGHT_SEMI};
    spacing: 10px;
    background: transparent;
}}
QDialog#settingsDialog QCheckBox::indicator,
QDialog#settingsDialog QRadioButton::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {t.NEUTRAL_300};
    background: {t.NEUTRAL_0};
}}
QDialog#settingsDialog QCheckBox::indicator {{ border-radius: {t.RADIUS_SM}px; }}
QDialog#settingsDialog QRadioButton::indicator {{ border-radius: 9px; }}
QDialog#settingsDialog QCheckBox::indicator:hover,
QDialog#settingsDialog QRadioButton::indicator:hover {{
    border-color: {t.ACCENT};
}}
QDialog#settingsDialog QCheckBox::indicator:checked,
QDialog#settingsDialog QRadioButton::indicator:checked {{
    background: {t.ACCENT};
    border-color: {t.ACCENT};
    image: none;
}}

/* ── 按钮 ── */
QPushButton#primaryBtn {{
    background: {t.NEUTRAL_900};
    color: {t.NEUTRAL_0};
    border: none;
    border-radius: {t.RADIUS_SM}px;
    padding: 10px 28px;
    font-size: {t.FONT_SM}px;
    font-weight: {t.WEIGHT_SEMI};
    min-height: 22px;
}}
QPushButton#primaryBtn:hover {{
    background: {t.NEUTRAL_700};
}}
QPushButton#primaryBtn:pressed {{
    background: {t.NEUTRAL_700};
}}
QPushButton#secondaryBtn,
QPushButton#ghostBtn {{
    background: {t.NEUTRAL_0};
    color: {t.NEUTRAL_700};
    border: 1px solid {t.NEUTRAL_200};
    border-radius: {t.RADIUS_SM}px;
    padding: 10px 24px;
    font-size: {t.FONT_SM}px;
    font-weight: {t.WEIGHT_SEMI};
    min-height: 22px;
}}
QPushButton#ghostBtn {{
    padding: 6px 14px;
}}
QPushButton#secondaryBtn:hover,
QPushButton#ghostBtn:hover {{
    background: {t.NEUTRAL_100};
    color: {t.NEUTRAL_900};
    border-color: {t.NEUTRAL_300};
}}

/* ── 分隔线 ── */
QFrame#cardSep {{
    background: {t.NEUTRAL_200};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

/* ── 分组框 ── */
QFrame#sectionFrame {{
    background: {t.NEUTRAL_0};
    border: 1px solid {t.NEUTRAL_200};
    border-radius: {t.RADIUS_MD}px;
}}

/* ── 表格 ── */
QDialog#settingsDialog QTableWidget {{
    background: {t.NEUTRAL_0};
    border: 1px solid {t.NEUTRAL_200};
    border-radius: {t.RADIUS_SM}px;
    gridline-color: {t.NEUTRAL_200};
    font-size: {t.FONT_SM}px;
    color: {t.NEUTRAL_900};
    selection-background-color: {t.ACCENT_SOFT};
    selection-color: {t.NEUTRAL_900};
}}
QDialog#settingsDialog QHeaderView::section {{
    background: {t.NEUTRAL_100};
    border: none;
    border-bottom: 1px solid {t.NEUTRAL_200};
    border-right: 1px solid {t.NEUTRAL_200};
    padding: 6px 8px;
    font-size: {t.FONT_XS}px;
    font-weight: {t.WEIGHT_SEMI};
    color: {t.NEUTRAL_700};
}}
"""


class SettingsDialog(QDialog):
    """高级设置弹窗 — 左侧选项卡 + 右侧面板。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setObjectName("settingsDialog")
        self.setMinimumWidth(780)
        self.setMinimumHeight(600)
        self.setStyleSheet(_dialog_qss())

        self._fields: dict[str, object] = {}
        self._preset_models: dict = {}
        self._pairing_widget = None
        self._phone_apps: dict = {}
        self._car_apps: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 主体：左侧导航 + 右侧内容 ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # 左侧导航栏
        nav_frame = QFrame()
        nav_frame.setFixedWidth(180)
        nav_frame.setStyleSheet(f"""
            QFrame {{
                background: {t.NEUTRAL_0};
                border-right: 1px solid {t.NEUTRAL_200};
            }}
        """)
        nav_lay = QVBoxLayout(nav_frame)
        nav_lay.setContentsMargins(0, 20, 0, 16)
        nav_lay.setSpacing(8)

        # 导航标题
        nav_title = QLabel("  设置")
        nav_title.setStyleSheet(f"""
            color: {t.NEUTRAL_900};
            font-size: {t.FONT_MD}px;
            font-weight: {t.WEIGHT_SEMI};
            padding: 8px 18px 12px 18px;
            background: transparent;
        """)
        nav_lay.addWidget(nav_title)

        self._nav_list = QListWidget()
        self._nav_list.setObjectName("navList")
        self._nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tab_items = ["设备", "模型", "操作参数", "前台App", "图片压缩"]
        for name in self._tab_items:
            self._nav_list.addItem(name)
        self._nav_list.setCurrentRow(0)
        nav_lay.addWidget(self._nav_list, stretch=1)

        # 底部版本标识
        ver_label = QLabel("Guiness")
        ver_label.setStyleSheet(f"""
            color: {t.NEUTRAL_400};
            font-size: {t.FONT_XS}px;
            padding: 0 18px;
            background: transparent;
        """)
        nav_lay.addWidget(ver_label)

        body.addWidget(nav_frame)

        # 右侧内容区
        right = QVBoxLayout()
        right.setContentsMargins(28, 24, 28, 16)
        right.setSpacing(0)

        self._stacked = QStackedWidget()
        self._stacked.addWidget(self._build_device_panel())
        self._stacked.addWidget(self._build_model_panel())
        self._stacked.addWidget(self._build_operation_panel())
        self._stacked.addWidget(self._build_foreground_app_panel())
        self._stacked.addWidget(self._build_compress_panel())

        right.addWidget(self._stacked, stretch=1)

        # 底部按钮区
        right.addSpacing(12)
        right.addLayout(self._build_button_row())

        body.addLayout(right, stretch=1)
        root.addLayout(body)

        # 导航联动
        self._nav_list.currentRowChanged.connect(self._stacked.setCurrentIndex)

        # 加载数据
        self._load_preset_models()
        self._load()
        self._load_apps()
        self._apply_device_mode_visibility()

    # ══════════════════════════════════════════════════════════════
    # Panel builders
    # ══════════════════════════════════════════════════════════════

    def _build_panel_header(self, title: str, desc: str) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(4)
        box.setContentsMargins(0, 0, 0, 16)
        t_lbl = QLabel(title)
        t_lbl.setObjectName("panelTitle")
        d_lbl = QLabel(desc)
        d_lbl.setObjectName("panelDesc")
        box.addWidget(t_lbl)
        box.addWidget(d_lbl)
        return box

    def _build_section_frame(self) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("sectionFrame")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        return frame, lay

    # ── 设备面板 ──────────────────────────────────────────

    def _build_device_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addLayout(self._build_panel_header(
            "设备", "选择连接方式、配对手机并测试连通性"
        ))

        scroll = QScrollArea()
        scroll.setObjectName("panelScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        clay = QVBoxLayout(content)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(14)

        # 连接方式
        frame, flay = self._build_section_frame()
        mode_box = QVBoxLayout()
        mode_box.setSpacing(6)
        mode_box.addWidget(self._field_label("连接方式"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("USB (ADB)", "usb")
        self._mode_combo.addItem("WiFi", "wifi")
        self._fields["device.mode"] = self._mode_combo
        mode_box.addWidget(self._mode_combo)
        flay.addLayout(mode_box)

        # hidden device_type holder
        device_type_holder = QComboBox()
        device_type_holder.addItems(["phone", "car", "car-pin", "car-full", "pad"])
        device_type_holder.setCurrentText("phone")
        device_type_holder.hide()
        self._fields["device.device_type"] = device_type_holder
        flay.addWidget(device_type_holder)

        # USB
        self._usb_container = QWidget()
        self._usb_container.setStyleSheet("background: transparent;")
        usb_lay = QVBoxLayout(self._usb_container)
        usb_lay.setContentsMargins(0, 0, 0, 0)
        usb_lay.setSpacing(6)
        usb_lay.addWidget(self._field_label("USB 设备（每秒自动扫描）"))
        self._device_list = QListWidget()
        self._device_list.setSelectionMode(QListWidget.SingleSelection)
        self._device_list.setMinimumHeight(110)
        self._device_list.setStyleSheet(f"""
            QListWidget {{
                background: {t.NEUTRAL_0};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
                padding: 4px;
                font-size: {t.FONT_SM}px;
                color: {t.NEUTRAL_900};
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-radius: {t.RADIUS_SM}px;
            }}
            QListWidget::item:hover {{
                background: {t.NEUTRAL_100};
            }}
            QListWidget::item:selected {{
                background: {t.ACCENT};
                color: {t.NEUTRAL_0};
            }}
        """)
        self._fields["device.name"] = self._device_list
        usb_lay.addWidget(self._device_list)
        flay.addWidget(self._usb_container)

        self._usb_refresh_timer = QTimer(self)
        self._usb_refresh_timer.setInterval(1000)
        self._usb_refresh_timer.timeout.connect(self._refresh_usb_devices)

        # WiFi
        self._wifi_container = QWidget()
        self._wifi_container.setStyleSheet("background: transparent;")
        wifi_lay = QVBoxLayout(self._wifi_container)
        wifi_lay.setContentsMargins(0, 0, 0, 0)
        wifi_lay.setSpacing(10)

        endpoint_holder = QLineEdit()
        endpoint_holder.hide()
        self._fields["device.wifi_endpoint"] = endpoint_holder
        wifi_lay.addWidget(endpoint_holder)

        token_holder = QLineEdit()
        token_holder.hide()
        self._fields["device.token"] = token_holder
        wifi_lay.addWidget(token_holder)

        from gui.widgets.pairing_dialog import PairingInlineWidget
        self._pairing_widget = PairingInlineWidget(self)
        self._pairing_widget.paired.connect(self._on_scan_paired)
        wifi_lay.addWidget(self._pairing_widget)

        test_row = QHBoxLayout()
        test_row.addStretch(1)
        btn_test = QPushButton("测试连接")
        btn_test.setObjectName("ghostBtn")
        btn_test.setFixedWidth(110)
        btn_test.setCursor(Qt.PointingHandCursor)
        btn_test.clicked.connect(self._on_test_wifi)
        test_row.addWidget(btn_test)
        wifi_lay.addLayout(test_row)

        flay.addWidget(self._wifi_container)

        self._device_status = QLabel("")
        self._device_status.setWordWrap(True)
        self._device_status.setStyleSheet(self._status_qss("info"))
        flay.addWidget(self._device_status)

        clay.addWidget(frame)
        clay.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll, stretch=1)

        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        return panel

    # ── 模型面板 ──────────────────────────────────────────

    def _build_model_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addLayout(self._build_panel_header(
            "模型", "选择模型、配置推理端点"
        ))

        scroll = QScrollArea()
        scroll.setObjectName("panelScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        clay = QVBoxLayout(content)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(14)

        frame, flay = self._build_section_frame()

        # 模型选择（下拉可选 + 输入筛选）
        model_box = QVBoxLayout()
        model_box.setSpacing(6)
        model_box.addWidget(self._field_label("模型"))
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setInsertPolicy(QComboBox.NoInsert)
        self._model_combo.setMaxVisibleItems(15)
        self._model_combo.lineEdit().setPlaceholderText("点击选择或输入筛选...")
        # 强制 popup 背景不透明（macOS 上 QSS 对 popup 无效）
        popup_view = self._model_combo.view()
        popup_view.setStyleSheet(f"""
            QListView {{
                background-color: {t.NEUTRAL_0};
                border: 1px solid {t.NEUTRAL_300};
                border-radius: {t.RADIUS_SM}px;
                padding: 4px;
                outline: 0;
            }}
            QListView::item {{
                padding: 8px 12px;
                min-height: 26px;
                color: {t.NEUTRAL_900};
                background-color: {t.NEUTRAL_0};
            }}
            QListView::item:hover {{
                background-color: {t.NEUTRAL_100};
            }}
            QListView::item:selected {{
                background-color: {t.ACCENT_SOFT};
                color: {t.ACCENT};
            }}
        """)
        popup_view.window().setWindowOpacity(1.0)
        # 启用补全器实现输入筛选
        from PySide6.QtCore import Qt as QtCore_Qt
        from PySide6.QtWidgets import QCompleter
        completer = QCompleter(self)
        completer.setFilterMode(QtCore_Qt.MatchContains)
        completer.setCaseSensitivity(QtCore_Qt.CaseInsensitive)
        self._model_combo.setCompleter(completer)
        self._fields["model.model_name"] = self._model_combo
        model_box.addWidget(self._model_combo)
        flay.addLayout(model_box)

        # adapter 指示
        self._adapter_label = QLabel("")
        self._adapter_label.setStyleSheet(
            f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; background: transparent;"
        )
        flay.addWidget(self._adapter_label)

        # 模型名称覆写
        override_box = QVBoxLayout()
        override_box.setSpacing(6)
        override_box.addWidget(self._field_label("模型名称覆写（可选）"))
        self._fields["model.model_name_override"] = QLineEdit()
        self._fields["model.model_name_override"].setPlaceholderText(
            "留空则使用上方预设名称；中转站模型名不同时在此填写实际名称"
        )
        override_box.addWidget(self._fields["model.model_name_override"])
        flay.addLayout(override_box)

        sep = QFrame()
        sep.setObjectName("cardSep")
        flay.addWidget(sep)

        # 端点 URL
        url_box = QVBoxLayout()
        url_box.setSpacing(6)
        url_box.addWidget(self._field_label("端点 URL"))
        self._fields["model.url"] = QLineEdit()
        self._fields["model.url"].setPlaceholderText("http://model.mify.ai.srv 或自定义推理服务地址")
        url_box.addWidget(self._fields["model.url"])
        flay.addLayout(url_box)

        # API Key
        key_box = QVBoxLayout()
        key_box.setSpacing(6)
        key_box.addWidget(self._field_label("API Key（可选）"))
        self._fields["model.api_key"] = QLineEdit()
        self._fields["model.api_key"].setEchoMode(QLineEdit.Password)
        self._fields["model.api_key"].setPlaceholderText("Bearer token，无鉴权时留空")
        key_box.addWidget(self._fields["model.api_key"])
        flay.addLayout(key_box)

        clay.addWidget(frame)
        clay.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll, stretch=1)

        self._model_combo.currentIndexChanged.connect(self._on_model_selected)
        return panel

    # ── 操作参数面板 ──────────────────────────────────────

    def _build_operation_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addLayout(self._build_panel_header(
            "操作参数", "控制每一步的节奏、上下文与超时"
        ))

        scroll = QScrollArea()
        scroll.setObjectName("panelScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        clay = QVBoxLayout(content)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(14)

        frame, flay = self._build_section_frame()

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        r = 0
        grid.addWidget(self._field_label("最大步数"), r, 0)
        self._fields["operation.max_steps"] = QSpinBox()
        self._fields["operation.max_steps"].setRange(1, 100)
        grid.addWidget(self._fields["operation.max_steps"], r, 1)

        grid.addWidget(self._field_label("返回次数"), r, 2)
        self._fields["operation.back_times"] = QSpinBox()
        self._fields["operation.back_times"].setRange(0, 20)
        grid.addWidget(self._fields["operation.back_times"], r, 3)

        r += 1
        grid.addWidget(self._field_label("操作间隔 (秒)"), r, 0)
        self._fields["operation.sleep_seconds_per_act"] = QDoubleSpinBox()
        self._fields["operation.sleep_seconds_per_act"].setRange(0, 30)
        self._fields["operation.sleep_seconds_per_act"].setSingleStep(0.5)
        grid.addWidget(self._fields["operation.sleep_seconds_per_act"], r, 1)

        grid.addWidget(self._field_label("截图等待 (秒)"), r, 2)
        self._fields["operation.screen_sleep_time"] = QDoubleSpinBox()
        self._fields["operation.screen_sleep_time"].setRange(0, 10)
        self._fields["operation.screen_sleep_time"].setSingleStep(0.1)
        grid.addWidget(self._fields["operation.screen_sleep_time"], r, 3)

        r += 1
        grid.addWidget(self._field_label("历史图片数"), r, 0)
        self._fields["operation.max_history_images"] = QSpinBox()
        self._fields["operation.max_history_images"].setRange(0, 20)
        grid.addWidget(self._fields["operation.max_history_images"], r, 1)

        grid.addWidget(self._field_label("历史轮数"), r, 2)
        self._fields["operation.max_turn"] = QSpinBox()
        self._fields["operation.max_turn"].setRange(0, 20)
        grid.addWidget(self._fields["operation.max_turn"], r, 3)

        r += 1
        grid.addWidget(self._field_label("打开超时 (秒)"), r, 0)
        self._fields["operation.open_timeout"] = QSpinBox()
        self._fields["operation.open_timeout"].setRange(1, 30)
        grid.addWidget(self._fields["operation.open_timeout"], r, 1)

        self._fields["operation.step_by_step"] = QCheckBox("启用分步确认模式")
        grid.addWidget(self._fields["operation.step_by_step"], r, 2, 1, 2)

        flay.addLayout(grid)

        clay.addWidget(frame)
        clay.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll, stretch=1)
        return panel

    # ── 前台App面板 ──────────────────────────────────────

    def _build_foreground_app_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addLayout(self._build_panel_header(
            "前台App", "管理手机和车机的前台应用注册表"
        ))

        scroll = QScrollArea()
        scroll.setObjectName("panelScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        clay = QVBoxLayout(content)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(14)

        frame, flay = self._build_section_frame()

        # 设备切换
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(20)
        self._app_radio_group = QButtonGroup(self)
        self._app_radio_phone = QRadioButton("手机")
        self._app_radio_car = QRadioButton("车机")
        self._app_radio_phone.setChecked(True)
        self._app_radio_group.addButton(self._app_radio_phone, 0)
        self._app_radio_group.addButton(self._app_radio_car, 1)
        toggle_row.addWidget(self._app_radio_phone)
        toggle_row.addWidget(self._app_radio_car)
        toggle_row.addStretch(1)
        flay.addLayout(toggle_row)

        # 搜索
        self._app_search = QLineEdit()
        self._app_search.setPlaceholderText("搜索应用名/包名/别名...")
        self._app_search.textChanged.connect(self._filter_app_list)
        flay.addWidget(self._app_search)

        # 表格
        self._app_table = QTableWidget()
        self._app_table.setColumnCount(3)
        self._app_table.setHorizontalHeaderLabels(["标准名", "包名", "别名"])
        self._app_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._app_table.setSelectionMode(QTableWidget.SingleSelection)
        self._app_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._app_table.verticalHeader().setVisible(False)
        self._app_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._app_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._app_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._app_table.setMaximumHeight(300)
        flay.addWidget(self._app_table)

        # 操作按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_add = QPushButton("添加应用")
        btn_add.setObjectName("ghostBtn")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._show_add_app_form)
        btn_del = QPushButton("删除选中")
        btn_del.setObjectName("ghostBtn")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.clicked.connect(self._delete_selected_app)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch(1)
        flay.addLayout(btn_row)

        # 添加表单
        self._add_app_form = QWidget()
        self._add_app_form.setStyleSheet("background: transparent;")
        self._add_app_form.setVisible(False)
        form_lay = QGridLayout(self._add_app_form)
        form_lay.setContentsMargins(0, 6, 0, 0)
        form_lay.setHorizontalSpacing(10)
        form_lay.setVerticalSpacing(8)
        form_lay.addWidget(self._field_label("标准名"), 0, 0)
        self._new_app_std = QLineEdit()
        self._new_app_std.setPlaceholderText("如: 微信")
        form_lay.addWidget(self._new_app_std, 0, 1)
        form_lay.addWidget(self._field_label("包名"), 1, 0)
        self._new_app_pkg = QLineEdit()
        self._new_app_pkg.setPlaceholderText("如: com.tencent.mm")
        form_lay.addWidget(self._new_app_pkg, 1, 1)
        form_lay.addWidget(self._field_label("别名"), 2, 0)
        self._new_app_aliases = QLineEdit()
        self._new_app_aliases.setPlaceholderText("逗号分隔，如: 微信,WeChat,weixin")
        form_lay.addWidget(self._new_app_aliases, 2, 1)
        confirm_row = QHBoxLayout()
        confirm_row.setSpacing(8)
        btn_confirm = QPushButton("确认添加")
        btn_confirm.setObjectName("ghostBtn")
        btn_confirm.setCursor(Qt.PointingHandCursor)
        btn_confirm.clicked.connect(self._confirm_add_app)
        btn_form_cancel = QPushButton("取消")
        btn_form_cancel.setObjectName("ghostBtn")
        btn_form_cancel.setCursor(Qt.PointingHandCursor)
        btn_form_cancel.clicked.connect(lambda: self._add_app_form.setVisible(False))
        confirm_row.addWidget(btn_confirm)
        confirm_row.addWidget(btn_form_cancel)
        confirm_row.addStretch(1)
        form_lay.addLayout(confirm_row, 3, 0, 1, 2)
        flay.addWidget(self._add_app_form)

        clay.addWidget(frame)
        clay.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll, stretch=1)

        self._app_radio_group.idToggled.connect(self._on_app_device_changed)
        return panel

    # ── 图片压缩面板 ──────────────────────────────────────

    def _build_compress_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addLayout(self._build_panel_header(
            "图片压缩", "上传前对截图做尺寸与质量压缩"
        ))

        scroll = QScrollArea()
        scroll.setObjectName("panelScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        clay = QVBoxLayout(content)
        clay.setContentsMargins(0, 0, 0, 0)
        clay.setSpacing(14)

        frame, flay = self._build_section_frame()

        self._fields["operation.use_compress"] = QCheckBox("启用压缩")
        flay.addWidget(self._fields["operation.use_compress"])

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        r = 0
        grid.addWidget(self._field_label("质量"), r, 0)
        self._fields["compress.quality"] = QSpinBox()
        self._fields["compress.quality"].setRange(1, 100)
        grid.addWidget(self._fields["compress.quality"], r, 1)

        grid.addWidget(self._field_label("像素因子"), r, 2)
        self._fields["compress.pixel_factor"] = QSpinBox()
        self._fields["compress.pixel_factor"].setRange(1, 100)
        grid.addWidget(self._fields["compress.pixel_factor"], r, 3)

        r += 1
        grid.addWidget(self._field_label("最小像素"), r, 0)
        self._fields["compress.min_pixels"] = QSpinBox()
        self._fields["compress.min_pixels"].setRange(1, 10000)
        grid.addWidget(self._fields["compress.min_pixels"], r, 1)

        grid.addWidget(self._field_label("最大像素"), r, 2)
        self._fields["compress.max_pixels"] = QSpinBox()
        self._fields["compress.max_pixels"].setRange(1, 10000)
        grid.addWidget(self._fields["compress.max_pixels"], r, 3)

        flay.addLayout(grid)

        clay.addWidget(frame)
        clay.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll, stretch=1)
        return panel

    # ── 底部按钮 ──────────────────────────────────────────

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.setContentsMargins(0, 4, 0, 8)
        row.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_cancel)

        btn_save = QPushButton("保存更改")
        btn_save.setObjectName("primaryBtn")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self._save_and_accept)
        row.addWidget(btn_save)

        return row

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("fieldLabel")
        return lbl

    @staticmethod
    def _status_qss(kind: str) -> str:
        color = {
            "info": t.NEUTRAL_500,
            "success": t.SUCCESS,
            "error": t.DANGER,
        }.get(kind, t.NEUTRAL_500)
        return f"color: {color}; font-size: {t.FONT_XS}px; background: transparent;"

    # ══════════════════════════════════════════════════════════════
    # Device interactions
    # ══════════════════════════════════════════════════════════════

    def _current_mode(self) -> str:
        data = self._mode_combo.currentData()
        if isinstance(data, str) and data in ("usb", "wifi"):
            return data
        text = (self._mode_combo.currentText() or "").lower()
        return "wifi" if "wifi" in text else "usb"

    def _apply_device_mode_visibility(self) -> None:
        mode = self._current_mode()
        self._usb_container.setVisible(mode == "usb")
        self._wifi_container.setVisible(mode == "wifi")
        if mode == "usb":
            if not self._usb_refresh_timer.isActive():
                self._usb_refresh_timer.start()
            self._refresh_usb_devices()
        else:
            self._usb_refresh_timer.stop()
        if self._pairing_widget is not None:
            if mode == "wifi":
                self._pairing_widget.start()
            else:
                self._pairing_widget.stop()

    def _on_mode_changed(self) -> None:
        self._apply_device_mode_visibility()

    def _refresh_usb_devices(self) -> None:
        try:
            from device.adb_controller import list_all_devices
            devices = list_all_devices() or []
        except Exception as e:
            self._device_status.setText(f"刷新失败：{e}")
            self._device_status.setStyleSheet(self._status_qss("error"))
            return

        new_serials: list[str] = ["", *devices]
        pending = getattr(self, "_pending_device_serial", None) or ""
        if pending and pending not in devices:
            new_serials.append(pending)
        cur_serials = [
            self._device_list.item(i).data(Qt.UserRole) or ""
            for i in range(self._device_list.count())
        ]
        if cur_serials == new_serials:
            self._update_device_status(devices)
            return

        sel_item = self._device_list.currentItem()
        sel_serial = sel_item.data(Qt.UserRole) if sel_item is not None else None

        self._device_list.blockSignals(True)
        self._device_list.clear()
        for s in new_serials:
            if s == "":
                label = "自动检测（任选一台在线）"
            elif s in devices:
                label = s
            else:
                label = f"{s}（离线）"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, s)
            self._device_list.addItem(it)
        if sel_serial is not None:
            for i in range(self._device_list.count()):
                if self._device_list.item(i).data(Qt.UserRole) == sel_serial:
                    self._device_list.setCurrentRow(i)
                    break
        self._device_list.blockSignals(False)

        self._restore_device_selection()
        self._update_device_status(devices)

    def _restore_device_selection(self) -> None:
        target = getattr(self, "_pending_device_serial", None)
        if target is None:
            return
        for i in range(self._device_list.count()):
            if self._device_list.item(i).data(Qt.UserRole) == target:
                self._device_list.setCurrentRow(i)
                return

    def _update_device_status(self, devices: list[str]) -> None:
        if devices:
            self._device_status.setText(f"已检测到 {len(devices)} 台设备")
            self._device_status.setStyleSheet(self._status_qss("success"))
        else:
            self._device_status.setText("未检测到 ADB 设备，请连接手机并开启 USB 调试")
            self._device_status.setStyleSheet(self._status_qss("error"))

    def _on_scan_paired(self, result) -> None:
        endpoint_edit: QLineEdit = self._fields["device.wifi_endpoint"]
        token_edit: QLineEdit = self._fields["device.token"]
        endpoint_edit.setText(result.endpoint())
        token_edit.setText(result.phone_token)
        self._device_status.setText(
            f"已通过扫码配对：{result.phone_name or result.phone_ip}，正在测试连接…"
        )
        self._device_status.setStyleSheet(self._status_qss("info"))
        self._on_test_wifi()

    def _on_test_wifi(self) -> None:
        endpoint = self._fields["device.wifi_endpoint"].text().strip()
        token = self._fields["device.token"].text().strip()
        if not endpoint:
            self._device_status.setText("测试失败：端点为空")
            self._device_status.setStyleSheet(self._status_qss("error"))
            return
        try:
            from device.wifi_backend import WifiBackend
            be = WifiBackend(endpoint=endpoint, token=token, timeout=2.5)
            be.connect()
            info = be.device_info()
            be.close()
            self._device_status.setText(
                f"连接成功：{info.model} {info.width}x{info.height}"
            )
            self._device_status.setStyleSheet(self._status_qss("success"))
        except PermissionError as e:
            self._device_status.setText(f"连接失败（Token）：{e}")
            self._device_status.setStyleSheet(self._status_qss("error"))
        except Exception as e:
            self._device_status.setText(f"连接失败：{e}")
            self._device_status.setStyleSheet(self._status_qss("error"))

    # ══════════════════════════════════════════════════════════════
    # Model interactions
    # ══════════════════════════════════════════════════════════════

    def _load_preset_models(self) -> None:
        try:
            from model.inference_client import PRESET_MODELS
            self._preset_models = PRESET_MODELS
        except Exception:
            self._preset_models = []
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        display_names = []
        for m in self._preset_models:
            self._model_combo.addItem(m["display_name"], m["id"])
            display_names.append(m["display_name"])
        # 更新 completer 的候选列表
        if self._model_combo.completer():
            from PySide6.QtCore import QStringListModel
            self._model_combo.completer().setModel(QStringListModel(display_names))
        self._model_combo.blockSignals(False)
        self._on_model_selected()

    def _on_model_selected(self) -> None:
        idx = self._model_combo.currentIndex()
        if idx >= 0 and idx < len(self._preset_models):
            adapter_name = self._preset_models[idx].get("adapter", "")
            self._adapter_label.setText(f"Adapter: {adapter_name}")
        else:
            self._adapter_label.setText("")

    # ══════════════════════════════════════════════════════════════
    # App management
    # ══════════════════════════════════════════════════════════════

    def _load_apps(self) -> None:
        from apps.registry import DATA_DIR
        for fname, attr in [("phone.yaml", "_phone_apps"), ("car.yaml", "_car_apps")]:
            path = os.path.join(DATA_DIR, fname)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                setattr(self, attr, data if isinstance(data, dict) else {})
            else:
                setattr(self, attr, {})
        self._refresh_app_table()

    def _current_app_dict(self) -> dict:
        if self._app_radio_car.isChecked():
            return self._car_apps
        return self._phone_apps

    def _refresh_app_table(self) -> None:
        apps = self._current_app_dict()
        query = self._app_search.text().strip().lower()
        self._app_table.setRowCount(0)
        for std_name, entry in apps.items():
            if not isinstance(entry, dict):
                continue
            pkg = entry.get("pkg", "")
            aliases = entry.get("aliases", [])
            aliases_str = ", ".join(str(a) for a in aliases)
            if query:
                searchable = f"{std_name} {pkg} {aliases_str}".lower()
                if query not in searchable:
                    continue
            row = self._app_table.rowCount()
            self._app_table.insertRow(row)
            self._app_table.setItem(row, 0, QTableWidgetItem(std_name))
            self._app_table.setItem(row, 1, QTableWidgetItem(pkg))
            self._app_table.setItem(row, 2, QTableWidgetItem(aliases_str))

    def _filter_app_list(self) -> None:
        self._refresh_app_table()

    def _on_app_device_changed(self, id_: int, checked: bool) -> None:
        if checked:
            self._refresh_app_table()

    def _show_add_app_form(self) -> None:
        self._new_app_std.clear()
        self._new_app_pkg.clear()
        self._new_app_aliases.clear()
        self._add_app_form.setVisible(True)

    def _confirm_add_app(self) -> None:
        std_name = self._new_app_std.text().strip()
        pkg = self._new_app_pkg.text().strip()
        if not std_name or not pkg:
            return
        aliases_text = self._new_app_aliases.text().strip()
        aliases = [a.strip() for a in aliases_text.split(",") if a.strip()] if aliases_text else [std_name]
        apps = self._current_app_dict()
        apps[std_name] = {"pkg": pkg, "aliases": aliases}
        self._add_app_form.setVisible(False)
        self._refresh_app_table()

    def _delete_selected_app(self) -> None:
        row = self._app_table.currentRow()
        if row < 0:
            return
        item = self._app_table.item(row, 0)
        if item is None:
            return
        std_name = item.text()
        apps = self._current_app_dict()
        if std_name in apps:
            del apps[std_name]
        self._refresh_app_table()

    def _save_apps_yaml(self) -> None:
        import tempfile
        from apps.registry import DATA_DIR, reload as reload_registry
        for filename, data in [("phone.yaml", self._phone_apps), ("car.yaml", self._car_apps)]:
            path = os.path.join(DATA_DIR, filename)
            header = "# phone 端 App 注册表\n" if "phone" in filename else "# car 端 App 注册表\n"
            header += "# 结构：<标准名>: {pkg: 包名, aliases: [别名1, 别名2, ...]}\n\n"
            fd, tmp = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=DATA_DIR)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(header)
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)
            except Exception:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
        reload_registry()

    # ══════════════════════════════════════════════════════════════
    # Cleanup
    # ══════════════════════════════════════════════════════════════

    def done(self, result_code: int) -> None:
        if self._pairing_widget is not None:
            try:
                self._pairing_widget.stop()
            except Exception:
                pass
        super().done(result_code)

    # ══════════════════════════════════════════════════════════════
    # Load / Save
    # ══════════════════════════════════════════════════════════════

    def _load(self) -> None:
        path = config_file_path()
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        for key, widget in self._fields.items():
            parts = key.split(".")
            val = cfg
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p, "")
                else:
                    val = ""
                    break

            if isinstance(widget, QLineEdit):
                widget.setText(str(val) if val not in (None, "") else "")
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(val) if val not in (None, "") else 0)
                except (ValueError, TypeError):
                    widget.setValue(0)
            elif isinstance(widget, QDoubleSpinBox):
                try:
                    widget.setValue(float(val) if val not in (None, "") else 0.0)
                except (ValueError, TypeError):
                    widget.setValue(0.0)
            elif isinstance(widget, QComboBox):
                has_data = widget.count() > 0 and widget.itemData(0) is not None
                idx = -1
                if has_data:
                    idx = widget.findData(val if val != "" else None)
                if idx < 0:
                    idx = widget.findText(str(val))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
                elif widget.isEditable() and val:
                    widget.setEditText(str(val))
            elif isinstance(widget, QListWidget):
                self._pending_device_serial = str(val) if val else ""
                self._restore_device_selection()
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(val))

        # 模型选择：按 model_name 在 combo 的 itemData 中查找
        model_name = (cfg.get("model") or {}).get("model_name", "")
        if model_name:
            idx = self._model_combo.findData(model_name)
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
            else:
                self._model_combo.addItem(model_name, model_name)
                self._model_combo.setCurrentIndex(self._model_combo.count() - 1)
            self._on_model_selected()

    def _save_and_accept(self) -> None:
        path = config_file_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        else:
            cfg = {}

        for key, widget in self._fields.items():
            parts = key.split(".")
            target = cfg
            for p in parts[:-1]:
                if p not in target or not isinstance(target[p], dict):
                    target[p] = {}
                target = target[p]

            field_name = parts[-1]
            if isinstance(widget, QLineEdit):
                target[field_name] = widget.text().strip()
            elif isinstance(widget, QSpinBox):
                target[field_name] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                target[field_name] = widget.value()
            elif isinstance(widget, QComboBox):
                data = widget.currentData()
                if isinstance(data, str) and data:
                    target[field_name] = data
                else:
                    target[field_name] = widget.currentText()
            elif isinstance(widget, QListWidget):
                item = widget.currentItem()
                if item is None:
                    target[field_name] = ""
                else:
                    serial = item.data(Qt.UserRole)
                    target[field_name] = serial if isinstance(serial, str) else ""
            elif isinstance(widget, QCheckBox):
                target[field_name] = widget.isChecked()

        # model: 统一写入 model_name + url + api_key
        if "model" not in cfg or not isinstance(cfg["model"], dict):
            cfg["model"] = {}
        model_data = self._model_combo.currentData()
        if model_data:
            cfg["model"]["model_name"] = model_data
        else:
            cfg["model"]["model_name"] = self._model_combo.currentText()

        from utils.config_loader import save_config_atomic
        save_config_atomic(cfg, path)

        self._save_apps_yaml()
        self.accept()

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            if self._usb_refresh_timer.isActive():
                self._usb_refresh_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)
