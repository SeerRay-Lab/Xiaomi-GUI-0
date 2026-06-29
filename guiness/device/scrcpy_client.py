# -*- coding: utf-8 -*-
"""scrcpy 视频流客户端：设备端 H.264 硬编码 -> PC 端 PyAV 解码。

只做视频（control=false / audio=false），画面源换成 scrcpy 流以获得远高于
screencap 的流畅度。

链路：
  adb push scrcpy-server.jar -> /data/local/tmp
  adb forward tcp:<port> -> localabstract:scrcpy_<scid>
  adb shell CLASSPATH=... app_process / com.genymobile.scrcpy.Server <ver> ...
  socket connect -> 读 dummy byte -> 裸 H.264 流 -> PyAV 解码 RGB 帧

依赖：PyAV（H.264 解码）、scrcpy-server.jar（vendor/scrcpy/ 或环境变量）。
不可用时由调用方降级回 screencap。
"""
from __future__ import annotations

import logging
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple

logger = logging.getLogger(__name__)

SCRCPY_VERSION = "3.3.4"
_REMOTE_JAR = "/data/local/tmp/scrcpy-server.jar"

_STARTUP_INFO = None
_CREATE_FLAGS = 0
if sys.platform == "win32":
    _STARTUP_INFO = subprocess.STARTUPINFO()
    _STARTUP_INFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _STARTUP_INFO.wShowWindow = 0
    _CREATE_FLAGS = subprocess.CREATE_NO_WINDOW


class ScrcpyUnavailable(RuntimeError):
    """scrcpy 链路不可用。"""


def _find_server_jar() -> str:
    """定位 scrcpy-server jar。"""
    # 环境变量最优先
    env_path = os.environ.get("SCRCPY_SERVER_PATH", "")
    if env_path and os.path.isfile(env_path):
        return env_path

    # PyInstaller bundle
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        cand = os.path.join(meipass, "scrcpy", "scrcpy-server.jar")
        if os.path.isfile(cand):
            return cand
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cand = os.path.join(exe_dir, "scrcpy", "scrcpy-server.jar")
        if os.path.isfile(cand):
            return cand

    # 开发态：本仓库 vendor/ 目录
    repo_root = Path(__file__).resolve().parents[1]
    cand = repo_root / "vendor" / "scrcpy" / "scrcpy-server.jar"
    if cand.is_file():
        return str(cand)

    # 系统安装
    sys_paths = [
        "/opt/homebrew/share/scrcpy/scrcpy-server",
        "/usr/local/share/scrcpy/scrcpy-server",
        "/usr/share/scrcpy/scrcpy-server",
    ]
    for p in sys_paths:
        if os.path.isfile(p):
            return p
    return ""


def is_available() -> bool:
    """scrcpy 链路是否可用（PyAV + server jar）。"""
    if not _find_server_jar():
        return False
    try:
        import av  # noqa: F401
    except Exception:
        return False
    return True


class ScrcpyClient:
    """单设备 scrcpy 视频流客户端。"""

    def __init__(
        self,
        serial: str,
        *,
        adb_path: str = "adb",
        max_size: int = 1280,
        bit_rate: int = 8_000_000,
        max_fps: int = 30,
    ) -> None:
        self._serial = serial
        self._adb_path = adb_path
        self._max_size = max_size
        self._bit_rate = bit_rate
        self._max_fps = max_fps
        self._scid = f"{secrets.randbelow(0x7FFFFFFF):08x}"
        self._port = self._pick_port()
        self._server: Optional[subprocess.Popen] = None
        self._sock: Optional[socket.socket] = None
        self._forwarded = False

    @staticmethod
    def _pick_port() -> int:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def _adb(self, *args: str, **kw):
        return subprocess.run(
            [self._adb_path, "-s", self._serial, *args],
            capture_output=True,
            startupinfo=_STARTUP_INFO, creationflags=_CREATE_FLAGS,
            **kw,
        )

    def start(self) -> Tuple[int, int]:
        """建立链路。失败抛 ScrcpyUnavailable。"""
        jar = _find_server_jar()
        if not jar:
            raise ScrcpyUnavailable("找不到 scrcpy-server jar")
        try:
            import av  # noqa: F401
        except Exception as e:
            raise ScrcpyUnavailable(f"PyAV 不可用: {e}")

        r = self._adb("push", jar, _REMOTE_JAR)
        if r.returncode != 0:
            raise ScrcpyUnavailable(f"push server jar 失败: {r.stderr.decode(errors='replace')[:160]}")

        r = self._adb("forward", f"tcp:{self._port}", f"localabstract:scrcpy_{self._scid}")
        if r.returncode != 0:
            raise ScrcpyUnavailable(f"adb forward 失败: {r.stderr.decode(errors='replace')[:160]}")
        self._forwarded = True

        server_cmd = [
            self._adb_path, "-s", self._serial, "shell",
            f"CLASSPATH={_REMOTE_JAR}", "app_process", "/",
            "com.genymobile.scrcpy.Server", SCRCPY_VERSION,
            f"scid={self._scid}",
            "tunnel_forward=true",
            "audio=false",
            "control=false",
            "cleanup=true",
            f"max_size={self._max_size}",
            f"video_bit_rate={self._bit_rate}",
            f"max_fps={self._max_fps}",
            "send_frame_meta=false",
        ]
        self._server = subprocess.Popen(
            server_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            startupinfo=_STARTUP_INFO, creationflags=_CREATE_FLAGS,
        )
        threading.Thread(target=self._drain_server_log, daemon=True).start()

        deadline = time.monotonic() + 8.0
        sock = None
        while time.monotonic() < deadline:
            if self._server.poll() is not None:
                raise ScrcpyUnavailable("scrcpy server 进程提前退出")
            try:
                s = socket.create_connection(("127.0.0.1", self._port), timeout=2)
            except OSError:
                time.sleep(0.15)
                continue
            try:
                s.settimeout(1.0)
                dummy = s.recv(1)
            except OSError:
                dummy = b""
            if dummy == b"\x00":
                sock = s
                break
            try:
                s.close()
            except Exception:
                pass
            time.sleep(0.15)
        if sock is None:
            raise ScrcpyUnavailable("scrcpy 握手超时（未收到 dummy byte）——请在设备上允许屏幕录制")
        self._sock = sock
        return (self._max_size, self._max_size)

    def _drain_server_log(self) -> None:
        if self._server is None or self._server.stdout is None:
            return
        for line in self._server.stdout:
            logger.debug("[scrcpy-server] %s", line.decode(errors="replace").rstrip())

    def stream_frames(
        self, *, stop_event: Optional[threading.Event] = None
    ) -> Iterator:
        """逐帧 yield PyAV VideoFrame。"""
        import av

        if self._sock is None:
            raise ScrcpyUnavailable("链路未建立，先调用 start()")
        codec = av.CodecContext.create("h264", "r")
        self._sock.settimeout(1.0)
        while stop_event is None or not stop_event.is_set():
            try:
                data = self._sock.recv(1 << 16)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            try:
                for pkt in codec.parse(data):
                    for frame in codec.decode(pkt):
                        if stop_event is not None and stop_event.is_set():
                            return
                        yield frame
            except Exception as e:
                logger.warning(f"H.264 解码异常: {e}")
                continue

    def close(self) -> None:
        try:
            if self._sock is not None:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        try:
            if self._server is not None and self._server.poll() is None:
                self._server.terminate()
        except Exception:
            pass
        self._server = None
        if self._forwarded:
            try:
                self._adb("forward", "--remove", f"tcp:{self._port}")
            except Exception:
                pass
            self._forwarded = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
