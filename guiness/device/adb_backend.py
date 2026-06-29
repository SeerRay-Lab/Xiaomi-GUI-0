# -*- coding: utf-8 -*-
"""USB / ADB 设备后端：把 ADBController + AutomatorDevice 收到单一接口后。

原来 ActionExecutor 和 EpisodeRunner 直接手持 `adb` + `automator` 两个对象，
`_handle_type` 里还写了两级 fallback。现在这两层全部下沉到这里，上层只看到
DeviceBackend 协议。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Iterator, Literal, Optional

from device._coord import normalize_point, resolve_direction_swipe
from device.adb_controller import ADBController
from device.automator import AutomatorDevice
from device.backend import (
    CapabilityUnsupported,
    DeviceInfo,
    ForegroundInfo,
)

logger = logging.getLogger(__name__)


class AdbBackend:
    """USB 模式：组合 ADBController（底层 shell）+ AutomatorDevice（IME 输入）。"""

    kind: Literal["usb", "wifi"] = "usb"

    def __init__(
        self,
        device_id: str = "",
        device_type: str = "phone",
        *,
        adb: Optional[ADBController] = None,
        automator: Optional[AutomatorDevice] = None,
    ) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self._adb = adb or ADBController(serial=device_id, task_type=device_type)
        self._automator = automator or AutomatorDevice(device_id)

    # ── 属性 ──
    @property
    def width(self) -> int:
        return self._adb.width

    @property
    def height(self) -> int:
        return self._adb.height

    @property
    def adb(self) -> ADBController:
        return self._adb

    @property
    def automator(self) -> AutomatorDevice:
        return self._automator

    # ── 生命周期 ──
    def connect(self) -> None:
        if self._adb.width <= 0 or self._adb.height <= 0:
            self._adb._get_device_size()
            if self._adb.width <= 0 or self._adb.height <= 0:
                raise RuntimeError(
                    f"无法获取设备屏幕尺寸（width={self._adb.width}, height={self._adb.height}），"
                    "请确认设备已连接并授权 USB 调试"
                )

    def close(self) -> None:
        pass

    def ping(self) -> bool:
        try:
            return self._adb.width > 0 and self._adb.height > 0
        except Exception:
            return False

    # ── 信息 ──
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            serial=self.device_id,
            model=self._adb.get_android_device_name(),
            os_version=self._adb.get_android_version(),
            name=self._adb.get_android_device_name(),
            width=self._adb.width,
            height=self._adb.height,
            density=None,
            backend_kind="usb",
        )

    def get_screenshot(self, local_path: str) -> str:
        return self._adb.get_screenshot(local_path)

    def dump_hierarchy(self, local_path: str) -> str:
        if self._automator is not None:
            return self._automator.dump_hierarchy(local_path)
        return ""

    def get_foreground_info(self) -> ForegroundInfo:
        app_name, pkg = self._adb.get_foreground_info()
        return ForegroundInfo(app_name=app_name, package=pkg, activity=None)

    # ── 手势 ──
    def tap(self, x, y) -> None:
        self._adb.tap_point(x, y)

    def long_press(self, x, y, duration_ms: int = 2000) -> None:
        self._adb.long_press(x, y, duration_ms=duration_ms)

    def swipe(self, x1, y1, x2, y2, duration_ms: int = 400) -> None:
        self._adb.swipe(x1, y1, x2, y2, duration=duration_ms)

    def swipe_direction(self, direction: str, duration_ms: int = 400) -> None:
        x1, y1, x2, y2 = resolve_direction_swipe(direction, self.width, self.height)
        self._adb.run_shell([
            'input', 'swipe',
            str(int(x1)), str(int(y1)),
            str(int(x2)), str(int(y2)),
            str(int(duration_ms)),
        ])

    # ── 输入 ──
    def input_text(
        self,
        text: str,
        *,
        clear: bool = False,
        enter: bool = False,
        position: Optional[tuple] = None,
    ) -> bool:
        """统一输入入口：先走 uiautomator2（可清空 / 回车），失败回退到 adb input。"""
        if not text:
            return True

        # 1. U2 优先（支持 clear + enter + 点击定位）
        if self._automator and self._automator.device is not None:
            try:
                ok = self._automator.type_text(text, enter=enter, position=position)
                if ok:
                    return True
            except Exception as e:
                logger.debug(f"U2 输入异常，尝试 ADB 回退: {e}")

        # 2. ADB fallback：点定位 → input text → 可选回车
        if position is not None and len(position) >= 2:
            self._adb.tap_point(position[0], position[1])
            time.sleep(0.5)
        self._adb.input_text(text)
        if enter:
            time.sleep(0.3)
            self._adb.press_key('KEYCODE_ENTER')
        return True

    def press_key(self, key_code) -> None:
        self._adb.press_key(key_code)

    # ── 应用 ──
    def open_app(self, package: str) -> None:
        self._adb.open_app_by_package(package)

    def open_deeplink(self, uri: str) -> None:
        self._adb.open_mini_program(uri)

    def force_stop_app(self, package: str) -> bool:
        return self._adb.force_stop_app(package)

    def force_stop_all_known_apps(self, task_type: str) -> bool:
        # ADBController 已在 __init__ 拿到 task_type；保留入参以兼容协议。
        return self._adb.force_stop_all_known_apps()

    def back(self) -> None:
        self._adb.press_key('KEYCODE_BACK')

    def home(self) -> None:
        self._adb.press_key('KEYCODE_HOME')

    # ── 扩展能力：流式投屏 ──
    def stream_screen(
        self,
        *,
        fps: int = 15,
        quality: int = 70,
        scale: float = 1.0,
        stop_event: Optional[threading.Event] = None,
        recv_timeout: float = 1.0,
        max_size: int = 1280,
        bit_rate: int = 8_000_000,
    ) -> Iterator:
        """尝试 scrcpy 实时流（H.264 → QImage），失败则降级到 screencap 轮询。

        返回 Iterator[QImage]。调用方通过 stop_event 控制停止。
        """
        from PySide6.QtGui import QImage

        try:
            yield from self._stream_scrcpy(
                stop_event=stop_event, max_size=max_size,
                bit_rate=bit_rate, max_fps=fps,
            )
            return
        except Exception as e:
            logger.warning(f"scrcpy 不可用，降级到 screencap: {e}")

        yield from self._stream_screencap(stop_event=stop_event, fps=min(fps, 4))

    def _stream_scrcpy(
        self, *, stop_event: Optional[threading.Event],
        max_size: int, bit_rate: int, max_fps: int,
    ) -> Iterator:
        from PySide6.QtGui import QImage
        from device.scrcpy_client import ScrcpyClient, ScrcpyUnavailable

        client = ScrcpyClient(
            self.device_id,
            adb_path=self._adb.adb_path,
            max_size=max_size,
            bit_rate=bit_rate,
            max_fps=max_fps,
        )
        try:
            client.start()
            for frame in client.stream_frames(stop_event=stop_event):
                rgb = frame.to_ndarray(format="rgb24")
                h, w = rgb.shape[:2]
                img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
                yield img
        finally:
            client.close()

    def _stream_screencap(
        self, *, stop_event: Optional[threading.Event], fps: int = 4,
    ) -> Iterator:
        """adb screencap PNG 轮询兜底（约 3-4 fps）。"""
        import tempfile
        from PySide6.QtGui import QImage

        interval = 1.0 / max(fps, 1)
        tmp_path = os.path.join(tempfile.gettempdir(), f"guiness_screencap_{self.device_id}.png")
        while stop_event is None or not stop_event.is_set():
            t0 = time.time()
            try:
                self._adb.get_screenshot(tmp_path)
                img = QImage(tmp_path)
                if not img.isNull():
                    yield img
            except Exception as e:
                logger.debug(f"screencap 帧失败: {e}")
            elapsed = time.time() - t0
            wait = interval - elapsed
            if wait > 0 and (stop_event is None or not stop_event.wait(wait)):
                pass
