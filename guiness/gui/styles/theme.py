# -*- coding: utf-8 -*-
"""读取 theme.qss 模板并用 tokens 填充。"""
import os

from gui.styles.tokens import qss_vars


_QSS_PATH = os.path.join(os.path.dirname(__file__), "theme.qss")


def build_stylesheet() -> str:
    with open(_QSS_PATH, "r", encoding="utf-8") as f:
        tmpl = f.read()
    return tmpl.format_map(qss_vars())
