# -*- coding: utf-8 -*-
"""配置页：模型选择（mify / 自定义端点互斥）+ 任务编辑 + 高级设置（可折叠）。

为控制单文件规模，章节构建拆到 `gui/pages/config/` 下，本文件只保留：
  - __init__ 组装
  - _load_config / _save_config / _validate 等状态相关逻辑
"""
import json
import os
import yaml

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QPushButton, QScrollArea, QLabel,
    QCheckBox, QFrame,
)
from PySide6.QtGui import QPalette, QColor

from gui.paths import config_file_path, project_root
from gui.pages.config import model_section, task_section, advanced_section
from gui.styles import tokens as tok


class ConfigPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fields: dict[str, QWidget] = {}

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 20, 24, 16)
        root_layout.setSpacing(0)

        # ── Page header ──
        header = QHBoxLayout()
        header.setSpacing(12)
        title = QLabel("评测配置")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()
        root_layout.addLayout(header)
        root_layout.addSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 8, 0)

        layout.addWidget(model_section.build_model_section(self))
        layout.addWidget(task_section.build_task_section(self))
        layout.addWidget(advanced_section.build_advanced_section(self))
        layout.addStretch()

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

        # ── Bottom bar: Save ──
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet(f"""
            QFrame {{
                background: {tok.NEUTRAL_0};
                border: 1px solid {tok.NEUTRAL_200};
                border-radius: {tok.RADIUS_MD}px;
                padding: 4px;
            }}
        """)
        bottom = QHBoxLayout(bottom_frame)
        bottom.setContentsMargins(14, 8, 14, 8)
        bottom.setSpacing(12)

        self._save_status = QLabel("")
        self._save_status.setStyleSheet(
            f"color: {tok.NEUTRAL_500}; font-size: {tok.FONT_XS}px; "
            f"border: none; background: transparent;"
        )
        bottom.addWidget(self._save_status)

        bottom.addStretch()

        self._btn_save = QPushButton("保存配置")
        self._btn_save.setFixedWidth(160)
        self._btn_save.clicked.connect(self._save_config)
        bottom.addWidget(self._btn_save)

        root_layout.addSpacing(8)
        root_layout.addWidget(bottom_frame)

        self._load_config()
        self._set_placeholder_colors()

    def _set_placeholder_colors(self) -> None:
        placeholder_color = QColor(tok.NEUTRAL_400)
        for widget in self._fields.values():
            if isinstance(widget, QLineEdit):
                pal = widget.palette()
                pal.setColor(QPalette.PlaceholderText, placeholder_color)
                widget.setPalette(pal)
            elif isinstance(widget, QComboBox) and widget.isEditable():
                le = widget.lineEdit()
                if le:
                    pal = le.palette()
                    pal.setColor(QPalette.PlaceholderText, placeholder_color)
                    le.setPalette(pal)

    # ━━━━━━━━━━ Load / Save ━━━━━━━━━━

    def _load_config(self) -> None:
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
                widget.setText(str(val) if val else "")
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(val) if val else 0)
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(val) if val else 0.0)
            elif isinstance(widget, QComboBox):
                # 若 combo 为 userData 驱动（itemData 非 None），优先按 data 匹配
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
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(val))

        model_section.sync_model_group(self)
        advanced_section.sync_return_home_state(self)

        # Tasks
        task_file = cfg.get("task", {}).get("task_file", "")
        if task_file and os.path.exists(task_file):
            self._task_table.setRowCount(0)
            with open(task_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        task_section.add_task_row(
                            self, obj.get("query", ""), obj.get("app", "")
                        )
                    except json.JSONDecodeError:
                        pass

        if self._task_table.rowCount() == 0:
            task_section.add_task_row(self)
        task_section.update_task_hint(self)

        try:
            advanced_section.refresh_devices(self)
        except Exception:
            pass

    def _clear_field_errors(self) -> None:
        for widget in self._fields.values():
            if isinstance(widget, (QLineEdit, QComboBox)):
                widget.setStyleSheet("")

    def _highlight_field_error(self, field_key: str) -> None:
        widget = self._fields.get(field_key)
        if widget:
            widget.setStyleSheet(f"border: 1px solid {tok.DANGER};")

    def _validate(self) -> str | None:
        self._clear_field_errors()

        url = self._fields.get("model.url")
        if url and not url.text().strip():
            self._highlight_field_error("model.url")
            return "端点 URL 不能为空"

        if not task_section.get_tasks(self):
            return "至少需要一条评测任务"

        mode_combo = self._fields.get("device.mode")
        mode = mode_combo.currentData() if mode_combo is not None else "usb"
        if mode == "wifi":
            ep = self._fields["device.wifi_endpoint"].text().strip()
            if not ep:
                self._highlight_field_error("device.wifi_endpoint")
                return "WiFi 模式下 IP 不能为空"

        return None

    def _save_config(self) -> None:
        err = self._validate()
        if err:
            self._save_status.setText(f"保存失败: {err}")
            self._save_status.setStyleSheet(
                f"color: {tok.DANGER}; font-size: {tok.FONT_XS}px; background: transparent;"
            )
            return

        self._clear_field_errors()

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
                target[field_name] = widget.text()
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
            elif isinstance(widget, QCheckBox):
                target[field_name] = widget.isChecked()

        if "model" not in cfg:
            cfg["model"] = {}
        # model_name 从 combo itemData 取
        model_combo = self._fields.get("model.model_name")
        if model_combo:
            data = model_combo.currentData()
            cfg["model"]["model_name"] = data if data else model_combo.currentText()

        tasks = task_section.get_tasks(self)
        task_file = os.path.join(project_root(), "config", "tasks.jsonl")
        os.makedirs(os.path.dirname(task_file), exist_ok=True)
        with open(task_file, "w", encoding="utf-8") as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

        if "task" not in cfg:
            cfg["task"] = {}
        cfg["task"]["task_file"] = task_file

        from utils.config_loader import save_config_atomic
        save_config_atomic(cfg, path)

        self._save_status.setText(f"已保存（{len(tasks)} 条任务）")
        self._save_status.setStyleSheet(
            f"color: {tok.SUCCESS}; font-size: {tok.FONT_XS}px; background: transparent;"
        )
