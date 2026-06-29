# -*- coding: utf-8 -*-
"""DeviceBackend 协议：抽象 USB(ADB) 与 WiFi(自研 APP) 两条设备通路。

上层（ActionExecutor / EpisodeRunner）只依赖这个协议，不直接接触 ADBController 或
HTTP client。新增 backend 只需实现协议即可。

扩展能力（如 stream_screen）未实现时抛 CapabilityUnsupported，由调用方判断降级。
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Iterator, Literal, Optional, Protocol, runtime_checkable


class CapabilityUnsupported(RuntimeError):
    """当 backend 不支持某个扩展能力时抛出。"""


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    model: str
    os_version: str
    name: str
    width: int
    height: int
    density: Optional[int] = None
    backend_kind: Literal["usb", "wifi"] = "usb"


@dataclass(frozen=True)
class ForegroundInfo:
    app_name: str
    package: Optional[str]
    activity: Optional[str] = None


@runtime_checkable
class DeviceBackend(Protocol):
    # ── 属性：兼容旧代码对 adb.width / adb.height 的直读 ──
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    @property
    def kind(self) -> Literal["usb", "wifi"]: ...

    # ── 生命周期 ──
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def ping(self) -> bool: ...

    # ── 核心能力（USB/WiFi 都必须实现） ──
    def device_info(self) -> DeviceInfo: ...
    def get_screenshot(self, local_path: str) -> str: ...
    def dump_hierarchy(self, local_path: str) -> str: ...
    def get_foreground_info(self) -> ForegroundInfo: ...

    def tap(self, x, y) -> None: ...
    def long_press(self, x, y, duration_ms: int = 2000) -> None: ...
    def swipe(self, x1, y1, x2, y2, duration_ms: int = 400) -> None: ...
    def swipe_direction(self, direction: str, duration_ms: int = 400) -> None: ...

    def input_text(
        self,
        text: str,
        *,
        clear: bool = False,
        enter: bool = False,
        position: Optional[tuple] = None,
    ) -> bool: ...

    def press_key(self, key_code) -> None: ...
    def open_app(self, package: str) -> None: ...
    def open_deeplink(self, uri: str) -> None: ...
    def force_stop_app(self, package: str) -> bool: ...
    def force_stop_all_known_apps(self, task_type: str) -> bool: ...
    def back(self) -> None: ...
    def home(self) -> None: ...

    # ── 扩展能力（Stage 4 才用；USB backend 抛 CapabilityUnsupported） ──
    def stream_screen(
        self,
        *,
        fps: int = 12,
        quality: int = 55,
        scale: float = 1.0,
        stop_event: Optional[threading.Event] = None,
        recv_timeout: float = 1.0,
    ) -> Iterator[bytes]: ...
