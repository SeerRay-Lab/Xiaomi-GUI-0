# -*- coding: utf-8 -*-
"""扫码配对弹窗。

流程：
1. 打开时起 PairingServer（9876 端口，占用回退到 9877-9885）
2. 生成 6 位数字 token，拼成 PairingPayload，渲染成二维码
3. 显示二维码 + 倒计时 60s + token/端口文本，让用户用手机 APP 扫
4. 手机扫完 POST /pair → 回调里发 Qt signal → UI 自动关闭弹窗
5. 关闭时无论成功失败都 stop server，避免端口泄露

上层（advanced_section）连 `paired` 信号拿到 PairResult，把 IP/Token 回填到
wifi_endpoint/wifi_token 两个 QLineEdit，然后自动触发"测试连接"。

线程：PairingServer 的 HTTP handler 跑在独立线程；我们用 QTimer 把回调转发到
Qt 主线程再操作 UI，避免跨线程改 widget。
"""
from __future__ import annotations

import logging
import socket
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.pairing import PairingPayload, PairingServer, PairResult, build_qr_image
from gui.pairing.server import get_local_ip
from gui.styles import tokens as t

logger = logging.getLogger(__name__)

EXPIRE_SECONDS = 60
QR_BOX_SIZE = 8  # 每个码点像素大小


class PairingDialog(QDialog):
    """扫码配对弹窗。成功后通过 paired signal 回传 PairResult。"""

    paired = Signal(object)  # 参数是 PairResult，用 object 避免 Qt 元类型注册麻烦
    _paired_from_http_sig = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫码配对")
        self.setModal(True)
        self.setFixedSize(360, 480)

        self._server: Optional[PairingServer] = None
        self._payload: Optional[PairingPayload] = None
        self._remaining = EXPIRE_SECONDS
        self._result: Optional[PairResult] = None

        self._build_ui()
        self._start_server()

        # 每秒刷新倒计时
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()

        self._paired_from_http_sig.connect(self._accept_paired)

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        title = QLabel("用手机 Guiness 控制器扫码配对")
        title.setStyleSheet(f"color: {t.NEUTRAL_900}; font-size: {t.FONT_MD}px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedHeight(260)
        self._qr_label.setStyleSheet("background: white; border-radius: 8px;")
        root.addWidget(self._qr_label)

        self._info_label = QLabel("准备中…")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_label.setStyleSheet(
            f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px;"
        )
        self._info_label.setWordWrap(True)
        root.addWidget(self._info_label)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px;"
        )
        root.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

    # ── Server 生命周期 ───────────────────────────────────────────

    def _start_server(self) -> None:
        pc_ip = get_local_ip()
        pc_name = socket.gethostname()
        self._payload = PairingPayload.create(
            pc_ip=pc_ip,
            pc_port=0,  # 先占位，start 后回填
            pc_name=pc_name,
            expire_seconds=EXPIRE_SECONDS,
        )

        try:
            self._server = PairingServer(
                token=self._payload.token,
                on_paired=self._on_paired_from_http,
            )
            actual_port = self._server.start()
        except OSError as e:
            logger.error(f"启动配对服务失败: {e}")
            self._info_label.setText("无法启动本地配对服务（端口被占用）\n请使用下方手动输入 IP/Token")
            self._info_label.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_XS}px;"
            )
            return

        # 端口确认了，重新生成载荷 + 二维码
        self._payload.pc_port = actual_port
        self._render_qr()

    def _render_qr(self) -> None:
        payload = self._payload
        if payload is None:
            return
        qimg = build_qr_image(payload.to_json(), box_size=QR_BOX_SIZE)
        if qimg is None:
            self._info_label.setText(
                "未安装 qrcode 库\n请先执行：pip install qrcode"
            )
            self._info_label.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_XS}px;"
            )
            return
        self._qr_label.setPixmap(QPixmap.fromImage(qimg))
        self._info_label.setText(
            f"PC {payload.pc_name}  {payload.pc_ip}:{payload.pc_port}"
        )
        self._status_label.setText(f"剩余时间 {self._remaining} 秒")

    # ── 回调 / 倒计时 ─────────────────────────────────────────────

    def _on_paired_from_http(self, result: PairResult) -> None:
        """HTTP handler 线程里调来。通过 signal 投递到 Qt 主线程。"""
        logger.info(f"收到配对: {result.endpoint()}")
        self._paired_from_http_sig.emit(result)

    def _accept_paired(self, result: PairResult) -> None:
        self._result = result
        self._status_label.setText(f"✓ 已配对 {result.phone_name or result.phone_ip}")
        self._status_label.setStyleSheet(
            f"color: {t.SUCCESS}; font-size: {t.FONT_XS}px; font-weight: 600;"
        )
        self.paired.emit(result)
        # 留 400ms 让用户看到"已配对"再关
        QTimer.singleShot(400, self.accept)

    def _on_tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self._tick_timer.stop()
            self._status_label.setText("二维码已过期，请关闭后重试")
            self._status_label.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_XS}px;"
            )
            return
        if self._result is None and self._server is not None:
            self._status_label.setText(f"剩余时间 {self._remaining} 秒")

    # ── 关闭清理 ───────────────────────────────────────────────────

    def result_payload(self) -> Optional[PairResult]:
        """弹窗关闭后给上层拿结果。"""
        return self._result

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API 命名)
        self._cleanup()
        super().closeEvent(event)

    def done(self, result_code: int) -> None:  # noqa: D401
        self._cleanup()
        super().done(result_code)

    def _cleanup(self) -> None:
        if self._tick_timer.isActive():
            self._tick_timer.stop()
        if self._server is not None:
            try:
                self._server.stop()
            except Exception as e:
                logger.warning(f"关配对服务异常: {e}")
            self._server = None


class PairingInlineWidget(QWidget):
    """内嵌到主界面 WiFi 区域的扫码组件。

    和 PairingDialog 不同：不是弹窗，而是常驻在面板里；倒计时过期后支持
    「重新生成」按钮再发一张新码。配对成功发 paired 信号。
    """

    paired = Signal(object)  # PairResult，对外
    # 内部 signal：HTTP 线程 emit，主线程 slot 接，Qt 自动 QueuedConnection 跨线程
    _paired_from_http_sig = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server: Optional[PairingServer] = None
        self._payload: Optional[PairingPayload] = None
        self._remaining = EXPIRE_SECONDS
        self._result: Optional[PairResult] = None
        self._started = False

        self._build_ui()

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick)

        # 跨线程关键：HTTP 线程 emit → Qt 主线程 slot
        self._paired_from_http_sig.connect(self._accept_paired)

    # ── UI ────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedHeight(240)
        self._qr_label.setStyleSheet("background: white; border-radius: 8px;")
        root.addWidget(self._qr_label)

        self._info_label = QLabel("用手机 Guiness 控制器扫描上方二维码")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_label.setStyleSheet(
            f"color: {t.NEUTRAL_700}; font-size: {t.FONT_SM}px; "
            f"font-weight: {t.WEIGHT_SEMI}; background: transparent;"
        )
        self._info_label.setWordWrap(True)
        root.addWidget(self._info_label)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; background: transparent;"
        )
        root.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch(1)
        self._btn_regen = QPushButton("重新生成")
        self._btn_regen.setFixedWidth(100)
        self._btn_regen.setCursor(Qt.PointingHandCursor)
        self._btn_regen.setStyleSheet(
            f"QPushButton {{ background: {t.NEUTRAL_0}; color: {t.NEUTRAL_700}; "
            f"border: 1px solid {t.NEUTRAL_200}; border-radius: {t.RADIUS_SM}px; "
            f"padding: 4px 10px; font-size: {t.FONT_XS}px; }}"
            f"QPushButton:hover {{ background: {t.NEUTRAL_100}; }}"
        )
        self._btn_regen.clicked.connect(self.restart)
        btn_row.addWidget(self._btn_regen)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

    # ── 对外 API ───────────────────────────────────────────────────
    def start(self) -> None:
        """懒启动：只在真正进入 WiFi 模式后才起 server。"""
        if self._started:
            return
        self._started = True
        self._start_server()
        self._tick_timer.start()

    def stop(self) -> None:
        """切走 WiFi / 关闭页面时调用，释放端口。"""
        if not self._started:
            return
        self._started = False
        self._cleanup()

    def restart(self) -> None:
        """过期或用户点「重新生成」时用，重发一张新码。"""
        self._cleanup()
        self._remaining = EXPIRE_SECONDS
        self._result = None
        self._status_label.setText("")
        self._info_label.setText("用手机 Guiness 控制器扫描上方二维码")
        self._info_label.setStyleSheet(
            f"color: {t.NEUTRAL_700}; font-size: {t.FONT_SM}px; "
            f"font-weight: {t.WEIGHT_SEMI}; background: transparent;"
        )
        self._started = True
        self._start_server()
        if not self._tick_timer.isActive():
            self._tick_timer.start()

    # ── Server 生命周期 ───────────────────────────────────────────
    def _start_server(self) -> None:
        pc_ip = get_local_ip()
        pc_name = socket.gethostname()
        self._payload = PairingPayload.create(
            pc_ip=pc_ip,
            pc_port=0,
            pc_name=pc_name,
            expire_seconds=EXPIRE_SECONDS,
        )
        try:
            self._server = PairingServer(
                token=self._payload.token,
                on_paired=self._on_paired_from_http,
            )
            actual_port = self._server.start()
        except OSError as e:
            logger.error(f"启动配对服务失败: {e}")
            self._info_label.setText("无法启动本地配对服务（端口被占用）")
            self._info_label.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_XS}px; background: transparent;"
            )
            return

        self._payload.pc_port = actual_port
        self._render_qr()

    def _render_qr(self) -> None:
        payload = self._payload
        if payload is None:
            return
        qimg = build_qr_image(payload.to_json(), box_size=QR_BOX_SIZE)
        if qimg is None:
            self._info_label.setText("未安装 qrcode 库，请执行：pip install qrcode")
            self._info_label.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_XS}px; background: transparent;"
            )
            return
        pix = QPixmap.fromImage(qimg).scaledToHeight(
            self._qr_label.height(), Qt.SmoothTransformation
        )
        self._qr_label.setPixmap(pix)
        self._status_label.setText(
            f"{payload.pc_ip}:{payload.pc_port}  ·  剩余 {self._remaining}s"
        )

    # ── 回调 / 倒计时 ─────────────────────────────────────────────
    def _on_paired_from_http(self, result: PairResult) -> None:
        """此方法在 HTTP handler 线程中执行，不能直接碰 Qt widget。"""
        logger.info(f"内嵌 widget 收到配对: {result.endpoint()}")
        if self._result is not None:
            logger.info("已处理过这次配对，忽略重复回调")
            return
        # 关键：通过 Signal 把 result 投递到主线程 —— QTimer.singleShot 在非
        # Qt 线程里根本不工作，之前卡就卡在这
        self._paired_from_http_sig.emit(result)

    def _accept_paired(self, result: PairResult) -> None:
        logger.info(f"_accept_paired 执行: {result.endpoint()}")
        self._result = result
        # 先 emit，UI 更新放后面；就算 UI 抛异常也已经把事件传出去了
        try:
            self.paired.emit(result)
            logger.info("paired signal 已 emit")
        except Exception as e:
            logger.exception(f"paired emit 失败: {e}")
        try:
            self._tick_timer.stop()
            self._info_label.setText(f"✓ 已配对 {result.phone_name or result.phone_ip}")
            self._info_label.setStyleSheet(
                f"color: {t.SUCCESS}; font-size: {t.FONT_SM}px; "
                f"font-weight: {t.WEIGHT_SEMI}; background: transparent;"
            )
            self._status_label.setText(f"{result.endpoint()}")
        except Exception as e:
            logger.exception(f"_accept_paired UI 更新失败: {e}")

    def _on_tick(self) -> None:
        if self._result is not None:
            return
        self._remaining -= 1
        if self._remaining <= 0:
            self._tick_timer.stop()
            self._info_label.setText("二维码已过期")
            self._info_label.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_SM}px; background: transparent;"
            )
            self._status_label.setText("点「重新生成」刷新")
            if self._server is not None:
                try:
                    self._server.stop()
                except Exception:
                    pass
                self._server = None
            return
        if self._payload is not None:
            self._status_label.setText(
                f"{self._payload.pc_ip}:{self._payload.pc_port}  ·  "
                f"剩余 {self._remaining}s"
            )

    def result_payload(self) -> Optional[PairResult]:
        return self._result

    def _cleanup(self) -> None:
        if self._tick_timer.isActive():
            self._tick_timer.stop()
        if self._server is not None:
            try:
                self._server.stop()
            except Exception as e:
                logger.warning(f"关配对服务异常: {e}")
            self._server = None

    def closeEvent(self, event) -> None:  # noqa: N802
        self._cleanup()
        super().closeEvent(event)
