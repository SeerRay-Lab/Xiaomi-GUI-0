# -*- coding: utf-8 -*-
"""PC 端回拨 HTTP 服务。

手机扫完二维码，主动 POST 到 PC 的 /pair 把自己的 IP/Token 回传。PC 这边起一个
极简 HTTP 服务专门收这个 POST，校验过 token 之后通过 Qt signal 通知 UI。

为什么用 http.server 而不是 Ktor/FastAPI：
- 零额外依赖，Python 标准库就够
- 只有两个路由（GET /ping, POST /pair），简单粗暴反而清晰
- Python 侧本来就没有 HTTP 服务栈，不想为这个引 Flask/FastAPI

端口：默认 9876，占用则尝试 +1 … +9；全失败返回 None，上层回退到手动 IP 输入。
"""
from __future__ import annotations

import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

from gui.pairing.payload import PAYLOAD_VERSION, PairResult

logger = logging.getLogger(__name__)

DEFAULT_PORT = 9876
_PORT_RETRY = 10  # 9876 → 9885 依次尝试


class PairingServer:
    """PC 配对服务器。

    用法：
        server = PairingServer(token="301295", on_paired=lambda r: ...)
        ip, port = server.start()   # 返回实际绑定的 (ip, port)；全失败抛 OSError
        ...
        server.stop()

    线程模型：
        ThreadingHTTPServer 自带一个线程处理每次请求；主线程里跑 server.serve_forever()
        用一个独立 daemon 线程隔离，避免阻塞 Qt 主循环。
    """

    def __init__(
        self,
        token: str,
        on_paired: Callable[[PairResult], None],
        preferred_port: int = DEFAULT_PORT,
    ) -> None:
        self._token = token
        self._on_paired = on_paired
        self._preferred_port = preferred_port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ── 生命周期 ───────────────────────────────────────────────────

    def start(self) -> int:
        """启动 HTTP server，返回实际端口。端口全失败抛 OSError。"""
        last_err: Optional[Exception] = None
        for offset in range(_PORT_RETRY):
            port = self._preferred_port + offset
            try:
                httpd = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(self))
                self._httpd = httpd
                self._thread = threading.Thread(
                    target=httpd.serve_forever,
                    name=f"PairingServer-{port}",
                    daemon=True,
                )
                self._thread.start()
                logger.info(f"配对服务已启动 port={port}")
                return port
            except OSError as e:
                last_err = e
                logger.debug(f"端口 {port} 绑定失败: {e}")
                continue
        raise OSError(f"配对服务端口全部占用（{self._preferred_port}..{self._preferred_port + _PORT_RETRY - 1}）: {last_err}")

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception as e:
                logger.warning(f"关闭配对服务异常: {e}")
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("配对服务已停止")

    # ── 内部：校验 + 回调 ──────────────────────────────────────────

    def _verify_and_fire(self, body: dict) -> tuple[bool, str]:
        """校验手机 POST 过来的 payload。成功返回 (True, '')，失败返回 (False, reason)。"""
        if body.get("v") != PAYLOAD_VERSION:
            return False, f"版本不匹配: {body.get('v')}"
        if body.get("token") != self._token:
            return False, "token 校验失败"
        try:
            result = PairResult(
                phone_ip=str(body["phoneIp"]),
                phone_port=int(body["phonePort"]),
                phone_token=str(body["phoneToken"]),
                phone_name=str(body.get("phoneName") or ""),
            )
        except (KeyError, TypeError, ValueError) as e:
            return False, f"字段缺失或类型错误: {e}"

        try:
            self._on_paired(result)
        except Exception as e:
            logger.exception("on_paired 回调异常")
            return False, f"服务内部错误: {e}"
        return True, ""


def _make_handler(server: PairingServer):
    """工厂：生成一个闭包类，让 handler 能访问外部 PairingServer 实例。"""

    class _Handler(BaseHTTPRequestHandler):
        # 静默 http.server 默认的 stderr 日志
        def log_message(self, fmt: str, *args) -> None:
            logger.debug("pairing http: " + fmt % args)

        def do_GET(self):
            if self.path == "/ping":
                self._json(200, {"ok": True, "service": "guiness-pairing"})
            else:
                self._json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if self.path != "/pair":
                self._json(404, {"ok": False, "error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 8192:
                self._json(400, {"ok": False, "error": "invalid content length"})
                return
            try:
                raw = self.rfile.read(length)
                body = json.loads(raw.decode("utf-8"))
            except Exception as e:
                self._json(400, {"ok": False, "error": f"invalid json: {e}"})
                return

            ok, reason = server._verify_and_fire(body)
            if ok:
                self._json(200, {"ok": True})
            else:
                self._json(403, {"ok": False, "error": reason})

        def _json(self, code: int, obj: dict) -> None:
            payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return _Handler


def get_local_ip() -> str:
    """返回本机在局域网里最合适对外的 IPv4。

    原理：开一个 UDP socket 去"连"一个外部地址（不实际发包），让操作系统的路由
    表告诉我们会从哪个网卡出去。比 `gethostbyname(gethostname())` 靠谱得多，后者
    在很多 Linux 上会返 127.0.1.1。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()
