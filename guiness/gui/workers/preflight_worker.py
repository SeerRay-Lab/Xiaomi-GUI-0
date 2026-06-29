# -*- coding: utf-8 -*-
"""发送前连通性校验：手机 + 模型端点并行 ping。

在 QThread 里跑，避免 GUI 线程阻塞；两个探测独立计时，任一失败即返回
汇总结果给上层。上层拿到结果后若全部 ok 再创建 EpisodeWorker 正式跑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests
from PySide6.QtCore import QThread, Signal


logger = logging.getLogger(__name__)


@dataclass
class PreflightResult:
    phone_ok: bool
    phone_msg: str
    model_ok: bool
    model_msg: str

    @property
    def all_ok(self) -> bool:
        return self.phone_ok and self.model_ok


class PreflightWorker(QThread):
    """先 phone 后 model 串行探测。两项都 1-3s 级，加起来仍快过 episode 启动。"""

    finished_with_result = Signal(object)  # PreflightResult

    def __init__(self, device_cfg: dict, model_cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self._device_cfg = device_cfg
        self._model_cfg = model_cfg

    def run(self) -> None:
        phone_ok, phone_msg = self._check_phone()
        model_ok, model_msg = self._check_model()
        self.finished_with_result.emit(
            PreflightResult(
                phone_ok=phone_ok,
                phone_msg=phone_msg,
                model_ok=model_ok,
                model_msg=model_msg,
            )
        )

    # ── 手机 ──

    def _check_phone(self) -> tuple[bool, str]:
        mode = (self._device_cfg.get("mode") or "usb").lower()
        if mode == "wifi":
            endpoint = (self._device_cfg.get("wifi_endpoint") or "").strip()
            token = (self._device_cfg.get("token") or "").strip()
            if not endpoint:
                return False, "未配置 WiFi 端点，请在「设置」里扫码配对手机"
            if not token:
                return False, "未配置 Token，请重新扫码配对"
            try:
                from device.wifi_backend import WifiBackend
                be = WifiBackend(endpoint=endpoint, token=token, timeout=2.5)
                be.connect()
                be.close()
                return True, "手机已连接"
            except PermissionError as e:
                return False, f"手机 Token 无效：{e}。请在「设置」重新扫码配对"
            except Exception as e:
                return False, (
                    f"手机无法连通（{endpoint}）：{e}。"
                    f"请确认手机已开启 Guiness 控制器服务，且 PC 与手机在同一局域网"
                )

        # USB 模式
        try:
            from device.adb_controller import list_all_devices
            devices = list_all_devices()
        except Exception as e:
            return False, f"无法枚举 ADB 设备：{e}"
        if not devices:
            return False, "未检测到 ADB 设备。请用 USB 线连接手机并开启 USB 调试"
        name = (self._device_cfg.get("name") or "").strip()
        if name and name not in devices:
            return False, f"配置的设备序列号 {name!r} 未连接，当前在线：{', '.join(devices)}"
        return True, f"ADB 设备在线（{len(devices)} 台）"

    # ── 模型 ──

    def _check_model(self) -> tuple[bool, str]:
        source = self._model_cfg.get("source", "mify")
        if source == "mify":
            api_key = (self._model_cfg.get("api_key")
                       or self._model_cfg.get("mify_api_key") or "").strip()
            model_name = (self._model_cfg.get("model_name") or "").strip()
            if not api_key:
                return False, "未配置 mify API Key，请在「设置」的模型卡中填写"
            if not model_name:
                return False, "未选择 mify 模型"
            # 用 mify_base_url 做 TCP 可达性 + HTTP 响应探测，避免真正触发 completion
            try:
                from utils.config_loader import get_config
                base = (get_config().get("model") or {}).get(
                    "mify_base_url", "http://model.mify.ai.srv"
                )
            except Exception:
                base = "http://model.mify.ai.srv"
            return self._probe_http(base.rstrip("/"), kind="mify 平台")

        # 自定义端点
        url = (self._model_cfg.get("custom_url") or self._model_cfg.get("url") or "").strip()
        if not url:
            return False, "未配置自定义端点 URL，请在「设置」的模型卡中填写"
        base = url.rstrip("/")
        if base.endswith("/v1/chat/completions"):
            base = base[: -len("/v1/chat/completions")]
        return self._probe_http(base, kind="自定义端点")

    @staticmethod
    def _probe_http(base_url: str, *, kind: str) -> tuple[bool, str]:
        """HEAD/GET 探测 base_url 是否响应，不关心状态码——只要有 HTTP 回应就算通。"""
        try:
            resp = requests.get(base_url, timeout=3.0)
            # 服务在线就行，哪怕返回 401/404/405——至少 TCP/HTTP 是通的
            return True, f"{kind}可达（HTTP {resp.status_code}）"
        except requests.exceptions.ConnectTimeout:
            return False, f"{kind}连接超时：{base_url}（网络不通或 VPN 未开）"
        except requests.exceptions.ConnectionError as e:
            return False, f"{kind}无法连接：{base_url}（{e.__class__.__name__}）"
        except Exception as e:
            return False, f"{kind}探测失败：{e}"
