# -*- coding: utf-8 -*-
"""向后兼容 shim：实际实现已迁移至 core.config。

新代码请直接从 core.config 引入；库内部代码禁止再调用 get_*_config() 这类
隐式全局读取，改为显式传 dict。
"""
from core.config import (  # noqa: F401
    default_config_path,
    get_compress_config,
    get_config,
    get_device_config,
    get_display_config,
    get_model_config,
    get_operation_config,
    get_prompt_config,
    get_s3_config,
    get_task_config,
    load_config_file,
    reload_config,
    save_config_atomic,
)
