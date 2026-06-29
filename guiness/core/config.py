# -*- coding: utf-8 -*-
"""项目配置加载入口。

历史上 `utils.config_loader` 承担两件事：
  1) 从 YAML 文件读出 dict
  2) 作为进程级全局单例给所有模块使用

问题出在 (2)：像 `utils/image_utils.compress_image` 深处会回到 `get_compress_config()`，
调用点无法得知依赖；而 `InferenceClient.__init__` 的 `config or get_model_config()`
又让两种初始化风格混存。

本模块把读文件 (`load_config_file`) 从单例 (`get_config`) 中剥离出来，并保留
单例接口作为 GUI 便利使用（reload_config 仍可用）。新代码应走显式 dict 传参，
禁止再在库内部偷偷回到 get_*_config() 里。
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from typing import Optional

import yaml

_CONFIG_FILENAME = "config.yaml"

# ============================================================================
# 纯函数：不缓存，显式 I/O。新代码优先用这个。
# ============================================================================

def default_config_path() -> str:
    """返回默认的 config.yaml 路径。

    打包后走用户可写目录（与 GUI 保存路径一致），避免 `_MEIPASS` 临时目录
    导致的「读写不同文件 → token 丢失」问题。委托给 `gui.paths.config_file_path`
    统一解析；若 GUI 模块在纯 CLI 场景不可导入，回退到手写路径。
    """
    if getattr(sys, "frozen", False):
        try:
            from gui.paths import config_file_path  # 延迟导入避免循环
            return config_file_path()
        except Exception:
            pass
        # 回退：直接拼用户目录
        home = os.path.expanduser("~")
        if sys.platform == "darwin":
            base_dir = os.path.join(home, "Library", "Application Support", "Guiness")
        elif os.name == "nt":
            base_dir = os.path.join(os.environ.get("APPDATA", home), "Guiness")
        else:
            base_dir = os.path.join(
                os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config")),
                "Guiness",
            )
        os.makedirs(base_dir, exist_ok=True)
        user_path = os.path.join(base_dir, _CONFIG_FILENAME)
        if not os.path.exists(user_path):
            template = os.path.join(
                getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)),
                _CONFIG_FILENAME,
            )
            try:
                if os.path.exists(template):
                    import shutil
                    shutil.copyfile(template, user_path)
            except Exception:
                pass
        return user_path
    # 开发模式：core/config.py → repo root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, _CONFIG_FILENAME)


def load_config_file(config_path: Optional[str] = None) -> dict:
    """读取一次 YAML，返回 dict。不做缓存。

    调用方不存在时直接抛 FileNotFoundError；不做回退到 example 的逻辑，
    保持失败显式。
    """
    if config_path is None:
        config_path = default_config_path()

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"配置文件未找到: {config_path}\n"
            f"请复制 config.yaml.example 为 config.yaml 并填入真实配置"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(f"配置文件顶层必须是字典: {config_path}")

    return data


# ============================================================================
# 单例便利：老代码 & GUI 继续用。内部库代码禁止再调下面这些。
# ============================================================================

_config: Optional[dict] = None
# 保护 _config 的 None↔dict 切换，以及 save_config_atomic 的并发写
_config_lock = threading.RLock()


def get_config(config_path: Optional[str] = None) -> dict:
    """加载并返回全局配置字典（进程级单例）。

    适合 GUI 主窗口 / CLI 顶层使用。库级代码请改用显式传 dict。
    """
    global _config
    with _config_lock:
        if _config is not None:
            return _config
        _config = load_config_file(config_path)
        return _config


def reload_config(config_path: Optional[str] = None) -> dict:
    """强制重新加载（GUI 保存配置后刷新用）。"""
    global _config
    with _config_lock:
        _config = None
    return get_config(config_path)


def save_config_atomic(cfg: dict, config_path: Optional[str] = None) -> None:
    """原子地把配置写回 yaml 并刷新单例缓存。

    为什么必须原子：GUI 有多个保存入口（SettingsDialog、ConfigPage），且 app.py
    有一个 5s 周期的 QTimer 会调 get_config() 读同一个文件。用直白的
    `open(path, "w") + yaml.dump` 会让读者撞上半写文件，或者两个 writer
    同一时刻 truncate + write，把用户刚填的 api_key/token 静默丢掉。

    做法：
      1. 写到同目录下的 `.tmp` 文件
      2. flush + fsync，保证物理落盘
      3. os.replace() 原子替换目标；POSIX 和 Windows 都保证读者要么看到旧版本
         要么看到新版本，绝不会看到 0 字节或半写
      4. 锁住整个过程，避免两个 writer 产生 `.tmp` 互相覆盖
    """
    if config_path is None:
        config_path = default_config_path()
    parent = os.path.dirname(os.path.abspath(config_path))
    os.makedirs(parent, exist_ok=True)

    with _config_lock:
        # NamedTemporaryFile + delete=False：我们自己管生命周期（rename 成目标）
        fd, tmp_path = tempfile.mkstemp(
            prefix=".config.yaml.", suffix=".tmp", dir=parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.dump(
                    cfg, f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, config_path)
        except Exception:
            # 失败要清理 tmp，不然 parent 会越攒越多 .tmp 孤儿
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

        # 让下次 get_config 从新文件重读；锁内重置，避免读者看到 stale 缓存
        global _config
        _config = None


# ============================================================================
# 便捷访问函数（保持向后兼容；内部库禁用）
# ============================================================================

def get_device_config() -> dict:
    return get_config().get("device", {}) or {}


def get_model_config() -> dict:
    return get_config().get("model", {}) or {}


def get_s3_config() -> dict:
    return get_config().get("s3", {}) or {}


def get_operation_config() -> dict:
    return get_config().get("operation", {}) or {}


def get_compress_config() -> dict:
    return get_config().get("compress", {}) or {}


def get_task_config() -> dict:
    return get_config().get("task", {}) or {}


def get_prompt_config() -> dict:
    return get_config().get("prompt", {}) or {}


def get_display_config() -> dict:
    return get_config().get("display", {}) or {}
