# -*- coding: utf-8 -*-
"""
Online Evaluation Tool - GUI 入口
"""
import sys
import os
import logging

# 确保项目根目录在 path 中
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from gui.app import ChatMainWindow as MainWindow
from gui.paths import data_dir, resource_path
from gui.styles import build_stylesheet


def _setup_logging() -> None:
    log_dir = os.path.join(data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "app.log")
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt))
    root.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter(fmt))
    root.addHandler(sh)

    logging.getLogger().info(f"日志文件: {log_file}")


def _install_exception_hook():
    """捕获未处理异常，写入日志后再退出。"""
    _original = sys.excepthook
    def _hook(exc_type, exc_value, exc_tb):
        logging.getLogger().critical("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))
        _original(exc_type, exc_value, exc_tb)
    sys.excepthook = _hook


def main() -> None:
    _setup_logging()
    _install_exception_hook()
    try:
        from gui.cleanup import run_startup_cleanup
        run_startup_cleanup()
    except Exception:
        logging.getLogger().exception("启动清理失败")
    app = QApplication(sys.argv)
    app.setApplicationName("Guiness")
    app.setOrganizationName("XiaoAI")

    # 设置应用图标
    icon_path = resource_path(os.path.join("resources", "icon_256.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 加载样式表
    app.setStyleSheet(build_stylesheet())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
