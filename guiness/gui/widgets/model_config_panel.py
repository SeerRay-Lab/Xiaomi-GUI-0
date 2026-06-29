# -*- coding: utf-8 -*-
"""主屏欢迎页：问候语 + 示例 query chips。

点击 chip 会把 query 填到下面的输入框，由用户决定是否发送。
设备配置与模型配置已迁移到 SettingsDialog（左下"设置"按钮）。
保留 get_model_config / get_selected_device / get_device_config 等
公共方法用于兼容 gui/app.py——数据全部从 config.yaml 读取。
"""
import os

import yaml
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from gui.paths import config_file_path
from gui.styles import tokens as t


# 示例 query：两列、三行。覆盖常见设备任务场景；点击后仅填入输入框
# 不自动发送，用户可继续编辑
_EXAMPLE_QUERIES: list[str] = [
    "打开设置，把 WiFi 打开",
    "在微信里给张三发条消息：「收到」",
    "截图并告诉我当前在哪个页面",
    "打开相册，查看最新的一张照片",
    "把手机调成静音模式",
    "打开淘宝，搜索蓝牙耳机",
]


class ModelConfigPanel(QWidget):
    """主屏欢迎页。设备 / 模型配置已搬到 SettingsDialog。"""

    open_settings_requested = Signal()
    example_query_selected = Signal(str)  # 点击示例 chip 时发射

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {t.NEUTRAL_50};")

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setAlignment(Qt.AlignHCenter)

        root.addStretch(2)

        # 大标题
        greeting = QLabel("有什么我能帮你的吗？")
        greeting.setStyleSheet(
            f"color: {t.NEUTRAL_900}; font-size: {t.FONT_XL + 6}px; "
            f"font-weight: {t.WEIGHT_SEMI}; background: transparent;"
        )
        greeting.setAlignment(Qt.AlignCenter)
        root.addWidget(greeting)

        # 副标题
        subtitle = QLabel("输入指令，自动在 Android 设备上执行并查看每一步结果")
        subtitle.setStyleSheet(
            f"color: {t.NEUTRAL_500}; font-size: {t.FONT_SM}px; "
            f"background: transparent;"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        root.addSpacing(12)
        root.addWidget(subtitle)

        root.addSpacing(32)

        # 示例 chip 网格（2 列自适应）
        chips_container = QWidget()
        chips_container.setStyleSheet("background: transparent;")
        chips_container.setMaximumWidth(720)
        chips_layout = QVBoxLayout(chips_container)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(12)

        for i in range(0, len(_EXAMPLE_QUERIES), 2):
            row = QHBoxLayout()
            row.setSpacing(12)
            for j in range(2):
                if i + j >= len(_EXAMPLE_QUERIES):
                    row.addStretch()
                    continue
                q = _EXAMPLE_QUERIES[i + j]
                chip = self._make_chip(q)
                row.addWidget(chip, stretch=1)
            chips_layout.addLayout(row)

        root.addWidget(chips_container, alignment=Qt.AlignCenter)
        root.addStretch(3)

    # ── 样式 ──

    def _make_chip(self, query: str) -> QPushButton:
        btn = QPushButton(f"  {query}")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setMinimumHeight(56)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.NEUTRAL_0};
                color: {t.NEUTRAL_700};
                border: 1px solid {t.NEUTRAL_100};
                border-radius: {t.RADIUS_MD}px;
                padding: 12px 18px;
                font-size: {t.FONT_SM}px;
                font-weight: {t.WEIGHT_REGULAR};
                text-align: left;
            }}
            QPushButton:hover {{
                background: {t.NEUTRAL_0};
                border-color: {t.ACCENT};
                color: {t.NEUTRAL_900};
            }}
            QPushButton:pressed {{
                background: {t.NEUTRAL_50};
            }}
        """)
        btn.clicked.connect(lambda _=False, q=query: self.example_query_selected.emit(q))
        return btn

    # ── 公共接口（保留兼容 gui/app.py）──

    def get_model_config(self) -> dict:
        cfg = self._read_config()
        model_cfg = cfg.get("model") or {}
        source = model_cfg.get("source", "mify")
        if source == "custom":
            return {
                "source": "custom",
                "custom_url": str(model_cfg.get("custom_url", "")).strip(),
                "model_name": (
                    str(model_cfg.get("custom_model_name", "")).strip()
                    or str(model_cfg.get("model_name", "")).strip()
                ),
            }
        return {
            "source": "mify",
            "model_name": str(model_cfg.get("model_name", "")).strip(),
            "api_key": str(model_cfg.get("mify_api_key", "")).strip(),
        }

    def get_selected_device(self) -> str:
        dev = self._read_device()
        mode = (dev.get("mode") or "usb").lower()
        if mode == "wifi":
            return str(dev.get("wifi_endpoint") or "").strip()
        return str(dev.get("name") or "").strip()

    def get_device_config(self) -> dict:
        dev = self._read_device()
        return {
            "mode": (dev.get("mode") or "usb").lower(),
            "name": str(dev.get("name") or "").strip(),
            "wifi_endpoint": str(dev.get("wifi_endpoint") or "").strip(),
            "token": str(dev.get("token") or "").strip(),
        }

    def update_devices(self, devices: list[str]) -> None:
        return

    def set_wifi_status(self, endpoint: str) -> None:
        return

    # ── 内部 ──

    @staticmethod
    def _read_config() -> dict:
        path = config_file_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _read_device(self) -> dict:
        cfg = self._read_config()
        dev = cfg.get("device")
        return dev if isinstance(dev, dict) else {}
