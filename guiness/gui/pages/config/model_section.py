# -*- coding: utf-8 -*-
"""ConfigPage 的「模型」章节：统一的模型选择 + URL + API Key。"""
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QSizePolicy,
)


def build_model_section(page) -> QGroupBox:
    from model.inference_client import PRESET_MODELS

    grp = QGroupBox("模型")
    lay = QVBoxLayout()
    lay.setSpacing(12)

    # 模型选择（带筛选）
    row_model = QHBoxLayout()
    row_model.setSpacing(12)
    lbl_model = QLabel("模型")
    lbl_model.setFixedWidth(80)
    row_model.addWidget(lbl_model)

    page._fields["model.model_name"] = QComboBox()
    page._fields["model.model_name"].setEditable(True)
    page._fields["model.model_name"].setInsertPolicy(QComboBox.NoInsert)
    page._fields["model.model_name"].lineEdit().setPlaceholderText("输入关键字筛选...")
    page._fields["model.model_name"].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    for m in PRESET_MODELS:
        page._fields["model.model_name"].addItem(m["display_name"], m["id"])
    row_model.addWidget(page._fields["model.model_name"])
    lay.addLayout(row_model)

    # 端点 URL
    row_url = QHBoxLayout()
    row_url.setSpacing(12)
    lbl_url = QLabel("端点 URL")
    lbl_url.setFixedWidth(80)
    row_url.addWidget(lbl_url)
    page._fields["model.url"] = QLineEdit()
    page._fields["model.url"].setPlaceholderText("推理服务地址，如 http://model.mify.ai.srv")
    row_url.addWidget(page._fields["model.url"])
    lay.addLayout(row_url)

    # API Key
    row_key = QHBoxLayout()
    row_key.setSpacing(12)
    lbl_key = QLabel("API Key")
    lbl_key.setFixedWidth(80)
    row_key.addWidget(lbl_key)
    page._fields["model.api_key"] = QLineEdit()
    page._fields["model.api_key"].setEchoMode(QLineEdit.Password)
    page._fields["model.api_key"].setPlaceholderText("Bearer token（可选）")
    row_key.addWidget(page._fields["model.api_key"])
    lay.addLayout(row_key)

    grp.setLayout(lay)
    return grp


def sync_model_group(page) -> None:
    """加载后根据 model_name 选中 combo 对应项。"""
    combo = page._fields.get("model.model_name")
    if combo is None:
        return
    model_name = combo.currentData()
    if not model_name:
        model_name = combo.currentText()
    idx = combo.findData(model_name)
    if idx >= 0:
        combo.setCurrentIndex(idx)
