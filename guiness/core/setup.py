# -*- coding: utf-8 -*-
"""组件工厂：消灭 CLI / GUI 两份重复的 Backend/Inference/Executor 装配。

`run_eval.py` 与 `gui/workers/episode_worker.py` 都走这里。
USB/WiFi 两条设备通路在 `build_backend` 里统一分发。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from action.action_executor import ActionExecutor
    from device.backend import DeviceBackend
    from model.inference_client import InferenceClient
    from reporter.base import Reporter
    from runner.episode_runner import EpisodeRunner


ProgressCallback = Callable[[str], None]


@dataclass
class Components:
    """一个 Episode 运行所需的三个运行时组件。"""
    backend: "DeviceBackend"
    inference: "InferenceClient"
    executor: "ActionExecutor"


def resolve_device_id(preferred: str = "", *, mode: str = "usb") -> str:
    """按优先级选择设备 ID。

    usb: preferred → adb 扫描第一个。无设备时抛 RuntimeError。
    wifi: 直接返回 preferred（上层传 endpoint 字符串），不扫 adb。
    """
    if mode == "wifi":
        if not preferred:
            raise RuntimeError("WiFi 模式必须提供 endpoint（如 http://192.168.1.10:8765）")
        return preferred

    if preferred:
        return preferred
    from device.adb_controller import list_all_devices
    devices = list_all_devices()
    if not devices:
        raise RuntimeError("未检测到 ADB 设备，请检查 USB 连接和授权")
    return devices[0]


def build_backend(
    mode: str,
    device_id: str,
    device_type: str,
    *,
    token: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> "DeviceBackend":
    """按模式构造对应 DeviceBackend。"""
    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    if mode == "wifi":
        from device.wifi_backend import WifiBackend
        _progress("正在连接 WiFi 设备...")
        backend = WifiBackend(endpoint=device_id, token=token or "", device_type=device_type)
        backend.connect()
        return backend

    # usb (默认)
    from device.adb_backend import AdbBackend
    _progress("正在连接 ADB 设备...")
    backend = AdbBackend(device_id=device_id, device_type=device_type)
    backend.connect()
    _progress("正在初始化 UI 自动化服务...")
    # AdbBackend 内部已经构造 AutomatorDevice；此条日志仅为保持阶段展示习惯
    return backend


def build_components(
    device_id: str,
    device_type: str,
    model_config: dict,
    *,
    mode: str = "usb",
    token: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Components:
    """装配 Backend / Inference / Executor。

    on_progress 可选，GUI 通过它把"正在连接 ADB..."这类阶段消息转成 Qt Signal，
    CLI 可以直接不传或用简短的 logger.info 适配。
    """
    from action.action_executor import ActionExecutor
    from model.inference_client import InferenceClient

    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    backend = build_backend(
        mode=mode,
        device_id=device_id,
        device_type=device_type,
        token=token,
        on_progress=on_progress,
    )

    _progress("正在配置推理客户端...")
    inference = InferenceClient(config=model_config)

    executor = ActionExecutor(
        backend=backend,
        device_type=device_type,
    )

    return Components(
        backend=backend,
        inference=inference,
        executor=executor,
    )


def build_runner(
    components: Components,
    config: dict,
    output_dir: str,
    date_str: str,
    stop_check: Optional[Callable[[], bool]] = None,
    on_step_complete: Optional[Callable[[dict], None]] = None,
    reporter: Optional["Reporter"] = None,
    approve_check: Optional[Callable[[], bool]] = None,
    approve_reset: Optional[Callable[[], None]] = None,
) -> "EpisodeRunner":
    """组装 EpisodeRunner，回调签名与 EpisodeRunner 保持一致。"""
    from runner.episode_runner import EpisodeRunner
    return EpisodeRunner(
        config=config,
        backend=components.backend,
        action_executor=components.executor,
        inference_client=components.inference,
        output_dir=output_dir,
        date_str=date_str,
        stop_check=stop_check,
        on_step_complete=on_step_complete,
        reporter=reporter,
        approve_check=approve_check,
        approve_reset=approve_reset,
    )
