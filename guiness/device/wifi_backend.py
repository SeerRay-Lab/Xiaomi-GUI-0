# -*- coding: utf-8 -*-
"""WiFi 设备后端：通过 HTTP 与运行在手机上的 Guiness 自研 APP 通信。

APP 内 AccessibilityService 做手势注入、MediaProjection 做截图。鉴权走
`X-Guiness-Token` 头；明文 HTTP，仅限可信局域网。

字段命名与 Android 侧 `server/Protocol.kt` 一一对应（camelCase），有任何改动需
两端同步。
"""
from __future__ import annotations

import logging
import threading
from typing import Iterator, Literal, Optional, Tuple
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

try:
    # urllib3 v2.x
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    from requests.packages.urllib3.util.retry import Retry  # type: ignore

from device._coord import normalize_point, resolve_direction_swipe
from device.backend import (
    CapabilityUnsupported,
    DeviceInfo,
    ForegroundInfo,
)

logger = logging.getLogger(__name__)

AUTH_HEADER = "X-Guiness-Token"
PROTOCOL_VERSION = "1"

# 常见 keyevent 代码 → APP 认识的字符串
_KEY_CODE_TO_NAME = {
    3: "HOME",
    4: "BACK",
    66: "ENTER",
    67: "DELETE",
    187: "RECENTS",
}


class WifiBackend:
    """WiFi 模式 backend。"""

    kind: Literal["usb", "wifi"] = "wifi"

    def __init__(
        self,
        endpoint: str,
        token: str,
        device_type: str = "phone",
        *,
        timeout: float = 5.0,
    ) -> None:
        if not endpoint:
            raise ValueError("WifiBackend endpoint 不能为空")
        self.endpoint = self._normalize_endpoint(endpoint)
        self.token = token or ""
        self.device_type = device_type
        self.timeout = timeout

        self._session = requests.Session()
        retry = Retry(
            total=1,
            backoff_factor=0.3,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)
        self._session.headers.update({AUTH_HEADER: self.token})

        self._info: Optional[DeviceInfo] = None
        self._width: int = 0
        self._height: int = 0

    # ── 属性 ──
    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    # ── 内部 ──
    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        ep = endpoint.strip().rstrip("/")
        if "://" not in ep:
            ep = "http://" + ep
        parsed = urlparse(ep)
        if parsed.port is None:
            host = parsed.hostname or ""
            ep = f"{parsed.scheme}://{host}:8765{parsed.path}"
        return ep

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.endpoint + path

    def _get(self, path: str, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", self.timeout)
        resp = self._session.get(self._url(path), timeout=timeout, **kwargs)
        if resp.status_code == 401:
            raise PermissionError("WiFi backend token 校验失败 (401)")
        resp.raise_for_status()
        return resp

    def _post(self, path: str, json: Optional[dict] = None, **kwargs) -> dict:
        timeout = kwargs.pop("timeout", self.timeout)
        resp = self._session.post(self._url(path), json=json or {}, timeout=timeout, **kwargs)
        if resp.status_code == 401:
            raise PermissionError("WiFi backend token 校验失败 (401)")
        if resp.status_code == 503:
            try:
                body = resp.json()
                msg = body.get("msg") or body.get("code") or "service unavailable"
            except Exception:
                msg = "service unavailable"
            raise RuntimeError(f"APP 暂不可用: {msg}")
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"ok": True}

    # ── 生命周期 ──
    def connect(self) -> None:
        resp = self._get("/device_info", timeout=self.timeout)
        data = resp.json()
        pv = str(data.get("protocolVersion", ""))
        if pv != PROTOCOL_VERSION:
            raise RuntimeError(
                f"协议版本不匹配：client={PROTOCOL_VERSION} server={pv}，请升级 APP 或降级 Python 端"
            )
        self._width = int(data.get("width", 0))
        self._height = int(data.get("height", 0))
        self._info = DeviceInfo(
            serial=self.endpoint,
            model=str(data.get("model", "unknown")),
            os_version=str(data.get("osVersion", "")),
            name=str(data.get("name", data.get("model", "unknown"))),
            width=self._width,
            height=self._height,
            density=int(data.get("density", 0)) or None,
            backend_kind="wifi",
        )
        logger.info(
            f"WiFi backend 已连接 endpoint={self.endpoint} "
            f"model={self._info.model} size={self._width}x{self._height}"
        )

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    def ping(self) -> bool:
        try:
            self._get("/ping", timeout=2.0)
            return True
        except Exception:
            return False

    # ── 信息 ──
    def device_info(self) -> DeviceInfo:
        if self._info is None:
            self.connect()
        assert self._info is not None
        return self._info

    def get_screenshot(self, local_path: str) -> str:
        resp = self._get("/screenshot", params={"q": 60}, timeout=self.timeout + 5)
        with open(local_path, "wb") as fh:
            fh.write(resp.content)
        return local_path

    def dump_hierarchy(self, local_path: str) -> str:
        try:
            resp = self._get("/hierarchy", timeout=self.timeout + 5)
            if resp.status_code == 200 and resp.content:
                import os
                os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
                with open(local_path, "w", encoding="utf-8") as fh:
                    fh.write(resp.text)
                return local_path
        except Exception as e:
            logger.debug(f"WiFi dump_hierarchy 不可用: {e}")
        return ""

    def get_foreground_info(self) -> ForegroundInfo:
        resp = self._get("/foreground")
        data = resp.json()
        return ForegroundInfo(
            app_name=str(data.get("appName") or data.get("pkg") or "unknown"),
            package=data.get("pkg"),
            activity=data.get("activity"),
        )

    # ── 手势 ──
    def tap(self, x, y) -> None:
        px, py = self._to_px(x, y)
        self._post("/tap", {"x": px, "y": py})

    def long_press(self, x, y, duration_ms: int = 2000) -> None:
        px, py = self._to_px(x, y)
        self._post("/long_press", {"x": px, "y": py, "durationMs": int(duration_ms)})

    def swipe(self, x1, y1, x2, y2, duration_ms: int = 400) -> None:
        sx, sy = self._to_px(x1, y1)
        ex, ey = self._to_px(x2, y2)
        self._post(
            "/swipe",
            {"x1": sx, "y1": sy, "x2": ex, "y2": ey, "durationMs": int(duration_ms)},
        )

    def swipe_direction(self, direction: str, duration_ms: int = 400) -> None:
        if self._width <= 0 or self._height <= 0:
            self.connect()
        x1, y1, x2, y2 = resolve_direction_swipe(direction, self._width, self._height)
        self._post(
            "/swipe",
            {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "durationMs": int(duration_ms)},
        )

    # ── 输入 ──
    def input_text(
        self,
        text: str,
        *,
        clear: bool = False,
        enter: bool = False,
        position: Optional[tuple] = None,
    ) -> bool:
        if not text:
            return True
        payload: dict = {"text": text, "clear": bool(clear), "enter": bool(enter)}
        if position is not None and len(position) >= 2:
            px, py = self._to_px(position[0], position[1])
            payload["position"] = [px, py]
        data = self._post("/input_text", payload, timeout=self.timeout + 2)
        return bool(data.get("ok", True))

    def press_key(self, key_code) -> None:
        if isinstance(key_code, int):
            name = _KEY_CODE_TO_NAME.get(key_code, str(key_code))
        else:
            name = str(key_code).upper().replace("KEYCODE_", "")
        self._post("/key", {"key": name})

    # ── 应用 ──
    def open_app(self, package: str) -> None:
        if not package:
            return
        self._post("/open", {"package": package})

    def open_deeplink(self, uri: str) -> None:
        if not uri:
            return
        self._post("/open_deeplink", {"uri": uri})

    def force_stop_app(self, package: str) -> bool:
        if not package:
            return False
        try:
            data = self._post("/force_stop", {"package": package})
            return bool(data.get("ok", False))
        except Exception as e:
            logger.warning(f"force_stop_app 失败: {e}")
            return False

    def force_stop_all_known_apps(self, task_type: str) -> bool:
        from apps.registry import get_all_known_packages
        try:
            targets = get_all_known_packages(task_type)
            targets = list({p.split("/")[0] for p in targets})
            whitelist = [
                "com.miui.home", "com.huawei.android.launcher",
                "com.android.systemui", "com.android.settings",
                "com.android.camera",
            ]
            data = self._post(
                "/force_stop_all",
                {"packages": targets, "whitelist": whitelist},
                timeout=self.timeout + 5,
            )
            return bool(data.get("ok", False))
        except Exception as e:
            logger.warning(f"force_stop_all_known_apps 失败: {e}")
            return False

    def back(self) -> None:
        self._post("/back")

    def home(self) -> None:
        self._post("/home")

    # ── 扩展能力：屏幕流 ──
    def stream_screen(
        self,
        *,
        fps: int = 12,
        quality: int = 55,
        scale: float = 1.0,
        stop_event: Optional[threading.Event] = None,
        recv_timeout: float = 1.0,
    ) -> Iterator[bytes]:
        """连接 APP `/stream`，作为 generator 产出原始 JPEG 字节。

        设计成同步生成器而非 asyncio——QThread 跑纯阻塞循环最简单；外部想停就
        `stop_event.set()`，下一轮 recv 超时时退出循环。`websockets.sync.client`
        会在 with 块退出时自动 close。
        """
        try:
            from websockets.sync.client import connect as ws_connect
        except ImportError as e:
            raise CapabilityUnsupported(
                "缺少依赖 websockets（pip install websockets>=12.0）"
            ) from e

        parsed = urlparse(self.endpoint)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        url = (
            f"{scheme}://{host}:{port}/stream"
            f"?fps={int(fps)}&q={int(quality)}&scale={float(scale)}"
        )
        headers = {AUTH_HEADER: self.token} if self.token else None

        logger.info(f"连接 screen stream {url}")
        # open_timeout=2.0：设备离线时 ws 握手最多阻塞 2s，避免 worker 卡在
        # OS 默认 socket 超时（macOS/Linux 通常 30-75s），主线程 closeEvent 等不到 worker 退出
        with ws_connect(
            url,
            additional_headers=headers,
            open_timeout=2.0,
            close_timeout=1,
        ) as ws:
            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                try:
                    msg = ws.recv(timeout=recv_timeout)
                except TimeoutError:
                    continue
                if isinstance(msg, (bytes, bytearray)):
                    yield bytes(msg)

    # ── 工具 ──
    def _to_px(self, x, y) -> Tuple[int, int]:
        """把可能的百分比 / 像素统一压成像素；APP 侧也会再做一次防御性归一化。"""
        if self._width <= 0 or self._height <= 0:
            self.connect()
        return normalize_point(x, y, self._width, self._height)
