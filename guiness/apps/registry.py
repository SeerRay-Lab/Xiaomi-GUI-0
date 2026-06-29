# -*- coding: utf-8 -*-
"""App 注册表装载 + 派生映射。

数据纯 YAML，代码只负责：
  1. 一次性读入 phone/car 两端 YAML（启动时执行）
  2. 为每端派生 4 个常用字典（alias→pkg、pkg→std、std→pkg、全量包名）
  3. 按 task_type 选择对应端
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load_yaml(path: str) -> dict:
    if not os.path.exists(path):
        logger.warning(f"App 数据文件缺失: {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层必须是 dict")
    return data


def _build_mappings(app_data: dict) -> dict:
    """从原始 {std_name: {pkg, aliases}} 一次性构建所有派生字典。"""
    std_to_pkg: dict = {}
    alias_to_pkg: dict = {}
    pkg_to_std: dict = {}

    for std_name, entry in app_data.items():
        pkg = entry["pkg"]
        std_to_pkg[std_name] = pkg
        pkg_to_std[pkg] = std_name
        for alias in entry.get("aliases", []):
            alias_to_pkg[alias] = pkg

    return {
        "std_to_pkg": std_to_pkg,
        "alias_to_pkg": alias_to_pkg,
        "pkg_to_std": pkg_to_std,
        "all_packages": list(pkg_to_std.keys()),
    }


# 启动时一次性加载并派生。后续调用复用这份只读映射。
_PHONE_MAPS = _build_mappings(_load_yaml(os.path.join(DATA_DIR, "phone.yaml")))
_CAR_MAPS = _build_mappings(_load_yaml(os.path.join(DATA_DIR, "car.yaml")))


def reload() -> None:
    """热重载两端 YAML 并重建所有派生映射。"""
    global _PHONE_MAPS, _CAR_MAPS
    _PHONE_MAPS = _build_mappings(_load_yaml(os.path.join(DATA_DIR, "phone.yaml")))
    _CAR_MAPS = _build_mappings(_load_yaml(os.path.join(DATA_DIR, "car.yaml")))


def is_car_task(task_type: Optional[str]) -> bool:
    """task_type 包含 'car' 即视为座舱任务（大小写无关）。"""
    if not task_type:
        return False
    return "car" in task_type.lower()


def _maps(task_type: Optional[str]) -> dict:
    return _CAR_MAPS if is_car_task(task_type) else _PHONE_MAPS


def get_alias_to_package(task_type: Optional[str] = None) -> dict:
    return _maps(task_type)["alias_to_pkg"]


def get_package_to_std(task_type: Optional[str] = None) -> dict:
    return _maps(task_type)["pkg_to_std"]


def get_all_known_packages(task_type: Optional[str] = None) -> list:
    return _maps(task_type)["all_packages"]
