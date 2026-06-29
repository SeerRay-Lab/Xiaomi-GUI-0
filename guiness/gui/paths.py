# -*- coding: utf-8 -*-
"""集中解析仓库/用户/资源相关的路径。

历史上 6 个文件各写一份 `os.path.dirname(os.path.dirname(__file__))`
的链式 dirname 来找项目根，主入口又再实现一遍 `_get_resource_path`
处理 PyInstaller _MEIPASS；搬家一次就要改 6 处。这里把四个常用函数
收束在一处：

  - `project_root()`     源码仓库根（开发）/ 可执行文件所在目录（打包）
  - `data_dir()`         可写运行产物目录（~/Guiness/data 或 repo/data）
  - `resource_path(p)`   只读资源查询（带 _MEIPASS 兼容）
  - `config_file_path()` config.yaml 的完整路径（GUI 配置页、设置弹窗共用）
"""
from __future__ import annotations

import os
import shutil
import sys

# 本模块位于 gui/paths.py；仓库根 = 本文件父目录的父目录。
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_MODULE_DIR)


def project_root() -> str:
    """返回项目根目录。打包后用可执行文件所在目录；开发模式返回仓库根。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return _REPO_ROOT


def resource_path(relative: str) -> str:
    """查找只读资源：打包时走 `sys._MEIPASS`，开发时走仓库根。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = _REPO_ROOT
    return os.path.join(base, relative)


def _user_app_dir() -> str:
    """返回用户级可写的 Guiness 目录（跨平台）。"""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support", "Guiness")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", home), "Guiness")
    else:
        base = os.path.join(
            os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config")),
            "Guiness",
        )
    os.makedirs(base, exist_ok=True)
    return base


def data_dir() -> str:
    """返回可写的数据目录（日志、history、运行产物）。

    打包后落到 `~/Guiness/data`，开发模式落到 `<repo>/data`。目录不存在自动创建。
    """
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.expanduser("~"), "Guiness")
    else:
        base = _REPO_ROOT
    path = os.path.join(base, "data")
    os.makedirs(path, exist_ok=True)
    return path


def config_file_path() -> str:
    """返回 `config.yaml` 的完整路径。

    - 开发：仓库根
    - 打包：用户可写目录（macOS `~/Library/Application Support/Guiness/`，
      Windows `%APPDATA%/Guiness/`，Linux `~/.config/Guiness/`）。
      首次启动时把打包内的模板拷贝过去作为初始值。
    """
    if not getattr(sys, "frozen", False):
        return os.path.join(_REPO_ROOT, "config.yaml")

    user_path = os.path.join(_user_app_dir(), "config.yaml")
    if not os.path.exists(user_path):
        template = resource_path("config.yaml")
        try:
            if os.path.exists(template):
                shutil.copyfile(template, user_path)
        except Exception:
            pass
    return user_path
