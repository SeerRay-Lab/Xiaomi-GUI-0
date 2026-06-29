# -*- coding: utf-8 -*-
"""App 注册表：标准名 / 包名 / 别名映射。

数据源在 `apps/data/*.yaml`，本模块只做装载与派生映射构建。公共 API 保持
与原 `utils.app_registry` 兼容：`get_alias_to_package`、`get_package_to_std`、
`get_all_known_packages`。
"""
from apps.registry import (  # noqa: F401
    DATA_DIR,
    get_alias_to_package,
    get_all_known_packages,
    get_package_to_std,
    is_car_task,
    reload,
)

__all__ = [
    "DATA_DIR",
    "get_alias_to_package",
    "get_all_known_packages",
    "get_package_to_std",
    "is_car_task",
    "reload",
]
