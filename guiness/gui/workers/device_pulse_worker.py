# -*- coding: utf-8 -*-
"""设备状态心跳线程：每秒真实探测一次，emit (connected, label) 给 GUI。

- WiFi：HTTP GET <endpoint>/ping，超时 0.8s。返回任何 HTTP 响应均视为在线。
- USB：调 adb_controller.list_all_devices()，且 config.device.name 必须在列表里
  才算连上（否则视为"配置的设备没插"）。空 name 容忍——任意一台在线即视为连接。
- 每 tick 自己 reload config，所以 mode/endpoint/serial 变更无需重启 worker。
- WiFi 探测命中时附带异步获取型号；型号缓存 1 分钟（避免每秒打 /info）。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

AUTH_HEADER = "X-Guiness-Token"
PING_TIMEOUT = 0.8
INFO_CACHE_TTL = 60.0  # 秒；型号信息不需要每秒拉
INTERVAL = 1.0


class DevicePulseWorker(QThread):
    """每 1s 探测一次设备可达性。"""

    status_changed = Signal(bool, str)  # (connected, label)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop = False
        # 防止信号抖动：同状态不重复 emit
        self._last_emit: Optional[tuple[bool, str]] = None
        # endpoint 型号缓存：(endpoint, token) -> (model, fetched_at)
        self._model_cache: dict[tuple[str, str], tuple[str, float]] = {}

    def stop(self) -> None:
        self._stop = True

    def last_status(self) -> Optional[tuple[bool, str]]:
        """返回最近一次 emit 的状态；首次心跳前为 None。"""
        return self._last_emit

    def run(self) -> None:
        while not self._stop:
            start = time.monotonic()
            try:
                connected, label = self._probe_once()
                self._maybe_emit(connected, label)
            except Exception:
                logger.exception("device pulse 探测异常")
                self._maybe_emit(False, "")
            # 节拍：扣掉本轮已耗，剩下的睡满 1s
            elapsed = time.monotonic() - start
            remaining = INTERVAL - elapsed
            if remaining > 0:
                # 睡眠分片，便于快速响应 stop
                slept = 0.0
                while slept < remaining and not self._stop:
                    step = min(0.1, remaining - slept)
                    time.sleep(step)
                    slept += step

    def _maybe_emit(self, connected: bool, label: str) -> None:
        cur = (connected, label)
        if cur != self._last_emit:
            self._last_emit = cur
            self.status_changed.emit(connected, label)

    def _probe_once(self) -> tuple[bool, str]:
        try:
            from utils.config_loader import get_config
            cfg = (get_config().get("device") or {})
        except Exception:
            return False, ""
        mode = (cfg.get("mode") or "usb").lower()
        if mode == "wifi":
            return self._probe_wifi(cfg)
        return self._probe_usb(cfg)

    def _probe_wifi(self, cfg: dict) -> tuple[bool, str]:
        endpoint = (cfg.get("wifi_endpoint") or "").strip()
        token = (cfg.get("token") or "").strip()
        if not endpoint:
            return False, ""
        url = endpoint.rstrip("/") + "/ping"
        headers = {AUTH_HEADER: token} if token else {}
        try:
            resp = requests.get(url, headers=headers, timeout=PING_TIMEOUT)
            # 401 也算"端点活着但 token 错"——视为不可用
            if resp.status_code >= 400:
                return False, ""
        except Exception:
            return False, ""
        # 在线 → 看缓存里有没有型号；没有就异步拉一次（不阻塞下次 tick）
        label = self._get_model_cached(endpoint, token)
        return True, label

    def _probe_usb(self, cfg: dict) -> tuple[bool, str]:
        try:
            from device.adb_controller import list_all_devices
            devices = list_all_devices() or []
        except Exception:
            return False, ""
        if not devices:
            return False, ""
        name = (cfg.get("name") or "").strip()
        if name and name not in devices:
            return False, ""
        return True, ""

    def _get_model_cached(self, endpoint: str, token: str) -> str:
        """同步阻塞拉一次型号（限速到 1/min）。失败返回空串。"""
        key = (endpoint, token)
        now = time.monotonic()
        cached = self._model_cache.get(key)
        if cached is not None:
            value, ts = cached
            if now - ts < INFO_CACHE_TTL:
                return value
        # 注意：这次请求会延后本 tick 的 emit。/device_info 一般 < 200ms，可接受。
        try:
            headers = {AUTH_HEADER: token} if token else {}
            resp = requests.get(
                endpoint.rstrip("/") + "/device_info",
                headers=headers,
                timeout=PING_TIMEOUT,
            )
            data = resp.json() if resp.ok else {}
            model = ""
            if isinstance(data, dict):
                model = str(data.get("model", "")).strip()
            self._model_cache[key] = (model, now)
            return model
        except Exception:
            self._model_cache[key] = ("", now)
            return ""
