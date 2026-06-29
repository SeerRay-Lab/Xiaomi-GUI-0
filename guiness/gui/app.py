# -*- coding: utf-8 -*-
"""
ChatGPT 式对话主窗口：侧边栏 + 聊天流 + 输入栏
"""
import logging
import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QSplitter, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal

logger = logging.getLogger(__name__)

from gui.chat_manager import ChatManager
from gui.widgets.sidebar import Sidebar
from gui.widgets.chat_feed import ChatFeed
from gui.widgets.input_bar import InputBar
from gui.widgets.model_config_panel import ModelConfigPanel
from gui.widgets.timeline_panel import TimelinePanel
from gui.workers.episode_worker import EpisodeWorker
from gui.workers.preflight_worker import PreflightWorker
from gui.workers.device_pulse_worker import DevicePulseWorker
from gui.styles import tokens as t


class ChatMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("")
        self.resize(1280, 860)
        self.setMinimumSize(960, 640)

        self._manager = ChatManager()
        self._current_conv_id: str | None = None
        self._workers: dict[str, EpisodeWorker] = {}
        self._sending = False
        self._preflight: PreflightWorker | None = None
        self._device_pulse: DevicePulseWorker | None = None

        # ── 中心布局 ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {t.NEUTRAL_200};
            }}
            QSplitter::handle:hover {{
                background: {t.ACCENT};
            }}
        """)
        self.setCentralWidget(splitter)

        # 侧边栏
        self._sidebar = Sidebar()
        self._sidebar.new_chat_requested.connect(self._on_new_chat)
        self._sidebar.conversation_selected.connect(self._on_switch_conv)
        self._sidebar.delete_requested.connect(self._on_delete_conv)
        self._sidebar.clear_all_requested.connect(self._on_clear_all_history)
        self._sidebar.settings_requested.connect(self._on_open_settings)
        self._sidebar.mirror_requested.connect(self._on_open_mirror)
        self._sidebar.display_mode_changed.connect(self._on_display_mode_changed)
        splitter.addWidget(self._sidebar)

        self._mirror_dialog = None
        self._display_mode = "image"

        # 右侧区域
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 内容切换: 配置面板 / 聊天流与时间轴
        self._stack = QStackedWidget()
        self._config_panel = ModelConfigPanel()
        self._config_panel.open_settings_requested.connect(self._on_open_settings)
        self._config_panel.example_query_selected.connect(self._on_example_query)
        
        self._chat_feed = ChatFeed()
        self._chat_feed.step_approved.connect(self._on_step_approved)
        self._chat_feed.step_stopped.connect(self._on_step_stopped)
        
        self._timeline_panel = TimelinePanel()
        
        # 聊天流与时间轴合并为一个 Splitter 放在 index 1
        self._chat_splitter = QSplitter(Qt.Horizontal)
        self._chat_splitter.setHandleWidth(1)
        self._chat_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {t.NEUTRAL_200};
            }}
            QSplitter::handle:hover {{
                background: {t.ACCENT};
            }}
        """)
        self._chat_splitter.addWidget(self._chat_feed)
        self._chat_splitter.addWidget(self._timeline_panel)
        # 初始大小：聊天流 75%，时间轴 25%
        self._chat_splitter.setSizes([750, 250])
        self._chat_splitter.setStretchFactor(0, 3)
        self._chat_splitter.setStretchFactor(1, 1)

        self._stack.addWidget(self._config_panel)     # index 0
        self._stack.addWidget(self._chat_splitter)    # index 1
        right_layout.addWidget(self._stack, stretch=1)

        # 输入栏
        self._input_bar = InputBar()
        self._input_bar.send_requested.connect(self._on_send)
        self._input_bar.stop_requested.connect(self._on_stop)
        self._input_bar.resume_requested.connect(self._on_resume)
        right_layout.addWidget(self._input_bar)

        splitter.addWidget(right)

        # 初始比例：侧边栏 280，右侧占满剩余
        splitter.setSizes([280, 1000])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # ── 加载历史对话 ──
        self._load_history()

        # ── 设备状态心跳：每秒一次真实探测，驱动 sidebar 连接状态 ──
        self._device_pulse = DevicePulseWorker(parent=self)
        self._device_pulse.status_changed.connect(self._on_device_status_changed)
        self._device_pulse.start()

        # ── UI 副作用刷新（USB 设备下拉、wifi 文案）：节奏宽松一些即可 ──
        self._device_ui_timer = QTimer(self)
        self._device_ui_timer.setInterval(3000)
        self._device_ui_timer.timeout.connect(self._refresh_device_ui)
        self._device_ui_timer.start()
        QTimer.singleShot(300, self._refresh_device_ui)

        # ── 显示模式初始化（延迟到事件循环启动后，避免 widget 未 realize 时崩溃） ──
        QTimer.singleShot(500, self._init_display_mode)

    # ── 发送 ──

    def _on_send(self, query: str, app: str) -> None:
        # 有任务运行中 / 正在创建 / preflight 已在路上时都拒绝二次触发
        if self._workers or self._sending or self._preflight is not None:
            return
        self._sending = True
        try:
            model_config = self._config_panel.get_model_config()
            device_cfg = self._config_panel.get_device_config()

            # 立即 disable 发送按钮并显示"检测连接中"，避免用户误以为卡住了
            self._input_bar.set_running(True)

            # 判断：当前是否有一个"已结束/等待回复"的对话 → 继续发送，不开新对话
            continue_in = None
            if self._current_conv_id:
                conv = self._manager.get(self._current_conv_id)
                if conv is not None and conv.status in (
                    "done", "stopped", "error", "awaiting_user",
                ):
                    continue_in = self._current_conv_id

            # 保存 pending 参数，preflight 通过后再创建/追加会话
            self._pending_send = (query, app, model_config, device_cfg, continue_in)

            preflight = PreflightWorker(
                device_cfg=device_cfg,
                model_cfg=model_config,
                parent=self,
            )
            preflight.finished_with_result.connect(self._on_preflight_finished)
            self._preflight = preflight
            preflight.start()
        finally:
            self._sending = False

    def _on_preflight_finished(self, result) -> None:
        """preflight 结果回调：失败弹框，成功才起 EpisodeWorker。"""
        preflight = self._preflight
        self._preflight = None
        if preflight is not None:
            preflight.quit()
            preflight.wait(1000)

        pending = getattr(self, "_pending_send", None)
        self._pending_send = None

        if not result.all_ok:
            # 回退 UI 状态，弹错误
            self._input_bar.set_running(False)
            lines = []
            if not result.phone_ok:
                lines.append(f"• 手机：{result.phone_msg}")
            if not result.model_ok:
                lines.append(f"• 模型：{result.model_msg}")
            QMessageBox.warning(
                self,
                "连接检测失败",
                "任务未开始。请先解决以下问题：\n\n" + "\n".join(lines),
            )
            return

        if pending is None:
            self._input_bar.set_running(False)
            return

        query, app, model_config, device_cfg, continue_in = pending
        model_config["device_id"] = (
            device_cfg.get("wifi_endpoint")
            if device_cfg.get("mode") == "wifi"
            else device_cfg.get("name", "")
        )

        from utils.config_loader import get_config
        is_step_by_step = bool(get_config().get("operation", {}).get("step_by_step", False))

        is_continue_turn = False
        if continue_in:
            # 追加一轮到既有对话 —— 不清空 chat_feed，不新建 sidebar 条目
            conv = self._manager.get(continue_in)
            if conv is None:
                # 保险：conv 突然没了 → 降级到新建
                conv = self._manager.create_conversation(query, app, model_config)
                conv.step_by_step = is_step_by_step
                self._sidebar.add_conversation(conv)
                self._chat_feed.clear()
                self._timeline_panel.clear()
                self._chat_feed.add_config_summary(conv)
            else:
                self._manager.start_turn(conv.id, query, app)
                is_continue_turn = True
                conv.step_by_step = is_step_by_step
                self._sidebar.update_conversation(conv.id, "pending", len(conv.steps), query, app)
            self._sidebar.set_active(conv.id)
            self._current_conv_id = conv.id
            self._stack.setCurrentIndex(1)
            # 不 clear：新的 user bubble 会直接追加到已有 feed 下方
            self._chat_feed.add_user_message(query, app)
            self._chat_feed.show_thinking()
            self._input_bar.set_running(True)
        else:
            conv = self._manager.create_conversation(query, app, model_config)
            conv.step_by_step = is_step_by_step
            self._sidebar.add_conversation(conv)
            self._sidebar.set_active(conv.id)
            self._current_conv_id = conv.id

            self._stack.setCurrentIndex(1)
            self._chat_feed.clear()
            self._timeline_panel.clear()
            self._chat_feed.add_config_summary(conv)
            self._chat_feed.add_user_message(query, app)
            self._chat_feed.show_thinking()
            self._input_bar.set_running(True)

        # worker 构造/启动失败时必须回滚 UI + chat_manager 状态——否则脏 turn 持久化、
        # 输入栏锁死，用户只能强退。继续轮才回滚 turn；新建会话则直接交给后续 _load_history
        # 在重启时把 status=pending → stopped
        try:
            if continue_in and conv is self._manager.get(continue_in):
                worker = EpisodeWorker(
                    conv, self._manager, parent=self,
                    turn_query=query, turn_app=app,
                )
            else:
                worker = EpisodeWorker(conv, self._manager, parent=self)

            worker.init_progress.connect(self._on_init_progress)
            worker.episode_started.connect(self._on_episode_started)
            worker.step_completed.connect(self._on_step_completed)
            worker.episode_finished.connect(self._on_episode_finished)
            worker.episode_error.connect(self._on_episode_error)
            self._workers[conv.id] = worker
            worker.start()
        except Exception as e:
            logger.exception("启动 EpisodeWorker 失败：%s", e)
            if is_continue_turn:
                self._manager.rollback_turn(conv.id)
                self._sidebar.update_conversation(
                    conv.id, "stopped", len(conv.steps),
                )
            else:
                conv.status = "stopped"
                self._manager.save()
                self._sidebar.update_conversation(conv.id, "stopped", 0)
            self._chat_feed.hide_thinking()
            self._input_bar.set_running(False)
            QMessageBox.critical(self, "启动失败", f"无法启动任务：{e}")

    # ── 步骤审批 ──

    def _on_step_approved(self, conv_id: str) -> None:
        conv = self._manager.get(conv_id)
        if conv:
            conv.approve_step()
            if conv_id == self._current_conv_id:
                self._chat_feed.show_thinking()
                self._chat_feed.update_thinking_text("正在执行动作...")

    def _on_step_stopped(self, conv_id: str) -> None:
        if conv_id == self._current_conv_id:
            self._on_stop()

    # ── 停止 ──

    def _on_stop(self) -> None:
        if self._current_conv_id:
            # 先设停止标志，UI 立刻反馈"正在停止…"；runner 会在下一次检查点退出
            self._manager.stop(self._current_conv_id)
            self._input_bar.set_stopping()
            self._chat_feed.add_system_message("正在停止...", "warning")

    # ── 继续（不打字直接 resume 上一轮 query）──

    def _on_resume(self) -> None:
        if self._workers or self._sending or self._preflight is not None:
            return
        if not self._current_conv_id:
            return
        conv = self._manager.get(self._current_conv_id)
        if conv is None or conv.status not in ("stopped", "awaiting_user", "error", "done"):
            return
        # 取上一轮 query 作为"继续"用的指令；awaiting_user 时用户其实应该输入
        # 新 query，但也允许不输入 → 用原 query 重跑
        last_turn = conv.turns[-1] if conv.turns else None
        q = (last_turn.get("query") if last_turn else "") or conv.query
        if not q:
            return
        # 清掉上一次的 stop 标志，沿用 "continue_in" 的进入路径
        conv.reset_stop()
        conv.status = "pending"
        self._manager.save()

        self._sidebar.update_conversation(conv.id, "pending", len(conv.steps), conv.query, conv.app)
        self._chat_feed.add_system_message("继续执行...", "info")
        self._chat_feed.show_thinking()
        self._input_bar.set_running(True)

        worker = EpisodeWorker(
            conv, self._manager, parent=self,
            turn_query=q, turn_app=conv.app,
        )
        worker.init_progress.connect(self._on_init_progress)
        worker.episode_started.connect(self._on_episode_started)
        worker.step_completed.connect(self._on_step_completed)
        worker.episode_finished.connect(self._on_episode_finished)
        worker.episode_error.connect(self._on_episode_error)
        self._workers[conv.id] = worker
        worker.start()

    # ── 删除对话 ──

    def _on_delete_conv(self, conv_id: str) -> None:
        # 运行中的对话不允许删除
        if conv_id in self._workers:
            return
        reply = QMessageBox.question(
            self, "删除对话", "确定删除吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._manager.delete(conv_id)
        self._sidebar.remove_conversation(conv_id)
        if conv_id == self._current_conv_id:
            self._on_new_chat()

    def _on_clear_all_history(self) -> None:
        # 运行中不允许清空
        if self._workers:
            QMessageBox.warning(self, "清空历史记录", "当前有评测任务正在运行，请先停止任务！")
            return
        reply = QMessageBox.question(
            self, "清空历史记录",
            "确定要清空所有历史对话记录吗？此操作会彻底删除所有本地评测产物与截图，且不可恢复！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        
        # 遍历删除所有本地历史
        for conv in self._manager.list_all():
            self._manager.delete(conv.id)
            self._sidebar.remove_conversation(conv.id)
            
        self._on_new_chat()

    # ── 新对话 ──

    def _on_new_chat(self) -> None:
        self._current_conv_id = None
        self._sidebar.set_active("")
        self._stack.setCurrentIndex(0)
        self._input_bar.set_running(False)
        self._input_bar.set_resumable(False)
        self._input_bar.set_focus()
        self._timeline_panel.clear()

    # ── 切换对话 ──

    def _on_switch_conv(self, conv_id: str) -> None:
        conv = self._manager.get(conv_id)
        if not conv:
            return
        self._current_conv_id = conv_id
        self._sidebar.set_active(conv_id)
        self._stack.setCurrentIndex(1)
        self._chat_feed.load_conversation(conv)
        self._timeline_panel.load_conversation(conv)
        self._input_bar.set_running(conv.status == "running")
        # 切到一个已停止/等待中的会话：露出"继续"按钮
        self._input_bar.set_resumable(
            conv.status in ("stopped", "awaiting_user", "error")
        )

    # ── Worker 信号处理 ──

    def _on_init_progress(self, conv_id: str, message: str) -> None:
        if conv_id == self._current_conv_id:
            self._chat_feed.update_thinking_text(message)

    def _on_episode_started(self, conv_id: str) -> None:
        self._sidebar.update_conversation(conv_id, "running")
        if conv_id == self._current_conv_id:
            self._chat_feed.add_system_message("正在执行...", "info")

    def _on_step_completed(self, conv_id: str, step_data: dict) -> None:
        conv = self._manager.get(conv_id)
        step_count = len(conv.steps) if conv else 0
        self._sidebar.update_conversation(conv_id, "running", step_count)
        if conv_id == self._current_conv_id:
            self._chat_feed.add_step_card(step_data)
            self._timeline_panel.add_step(step_data)

    def _on_episode_finished(self, conv_id: str, status: str) -> None:
        conv = self._manager.get(conv_id)
        step_count = len(conv.steps) if conv else 0
        self._sidebar.update_conversation(conv_id, status, step_count)

        if conv_id == self._current_conv_id:
            if status == "done":
                self._chat_feed.add_system_message(
                    f"已完成，共 {step_count} 步", "success"
                )
            elif status == "stopped":
                self._chat_feed.add_system_message("已停止，可点继续或重新发指令", "warning")
            elif status == "awaiting_user":
                # 从最后一步的 action.text 里取出模型问的问题
                q = ""
                if conv and conv.steps:
                    act = conv.steps[-1].get("action") or {}
                    q = (act.get("text") or "").strip()
                msg = f"模型在向你提问：{q}" if q else "模型在向你提问，请在下方输入回复"
                self._chat_feed.add_system_message(msg, "info")
            self._input_bar.set_running(False)
            # stopped / awaiting_user 都可以再继续，显示"继续"按钮
            self._input_bar.set_resumable(status in ("stopped", "awaiting_user"))

        self._cleanup_worker(conv_id)

    def _on_episode_error(self, conv_id: str, error: str) -> None:
        conv = self._manager.get(conv_id)
        step_count = len(conv.steps) if conv else 0
        self._sidebar.update_conversation(conv_id, "error", step_count)

        if conv_id == self._current_conv_id:
            self._chat_feed.add_system_message(f"错误: {error}", "error")
            self._input_bar.set_running(False)
            self._input_bar.set_resumable(True)

        self._cleanup_worker(conv_id)

    def _cleanup_worker(self, conv_id: str) -> None:
        worker = self._workers.pop(conv_id, None)
        if worker:
            worker.quit()
            worker.wait(2000)
        # 没有运行中的 worker 时，恢复发送按钮
        if not self._workers:
            self._input_bar.set_running(False)

    # ── 加载历史 ──

    def _load_history(self) -> None:
        """启动时从磁盘加载历史对话到侧边栏。"""
        for conv in self._manager.list_all():
            self._sidebar.add_conversation(conv)

    # ── 设备检测 ──

    def _on_device_status_changed(self, connected: bool, label: str) -> None:
        """DevicePulseWorker 心跳结果，直接驱动 sidebar 显示。"""
        self._sidebar.set_device_status(bool(connected), label or "")

    def _refresh_device_ui(self) -> None:
        """副作用刷新：仅更新 USB 设备下拉与 wifi 文案，不决定连接状态。"""
        from utils.config_loader import get_config
        device_cfg = (get_config().get("device") or {})
        mode = (device_cfg.get("mode") or "usb").lower()

        if mode == "wifi":
            endpoint = (device_cfg.get("wifi_endpoint") or "").strip()
            self._config_panel.set_wifi_status(endpoint)
            return

        try:
            from device.adb_controller import list_all_devices
            devices = list_all_devices()
        except Exception:
            devices = []
        self._config_panel.update_devices(devices)

    # ── 窗口关闭 ──

    def closeEvent(self, event) -> None:
        """关闭窗口前停止所有运行中的 worker 线程。"""
        # 停止 preflight 线程
        if self._preflight is not None:
            try:
                self._preflight.finished_with_result.disconnect(self._on_preflight_finished)
            except Exception:
                pass
            self._preflight.quit()
            if not self._preflight.wait(1000):
                self._preflight.setParent(None)
            self._preflight = None

        # 停止设备心跳线程
        if self._device_pulse is not None:
            try:
                self._device_pulse.status_changed.disconnect(self._on_device_status_changed)
            except Exception:
                pass
            self._device_pulse.stop()
            if not self._device_pulse.wait(1500):
                self._device_pulse.setParent(None)
            self._device_pulse = None

        # 关闭屏幕镜像窗口并清理其线程
        if self._mirror_dialog is not None:
            try:
                self._mirror_dialog.close()
            except Exception:
                pass
            self._mirror_dialog = None

        # 停止内嵌镜像视图
        self._chat_feed.hide_mirror_viewport()

        # 停止主要 episode worker 线程
        for conv_id in list(self._workers.keys()):
            conv = self._manager.get(conv_id)
            if conv:
                conv.request_stop()
        for worker in list(self._workers.values()):
            worker.wait(5000)
        self._workers.clear()
        super().closeEvent(event)

    # ── 示例 query ──

    def _on_example_query(self, query: str) -> None:
        """主屏点击示例 chip：填到输入框，不自动发送。"""
        self._input_bar.set_query_text(query)

    # ── 设置 ──

    def _on_open_settings(self) -> None:
        from gui.widgets.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.exec()

    # ── 屏幕共享 ──

    def _on_open_mirror(self) -> None:
        """侧边栏触发屏幕共享：从 config.yaml 读 endpoint/token，打开镜像弹窗。"""
        from utils.config_loader import get_config
        device_cfg = (get_config().get("device") or {})
        mode = (device_cfg.get("mode") or "usb").lower()
        endpoint = str(device_cfg.get("wifi_endpoint") or "").strip()
        token = str(device_cfg.get("token") or "").strip()
        from PySide6.QtWidgets import QMessageBox
        if mode != "wifi":
            QMessageBox.warning(
                self, "屏幕共享",
                "屏幕共享仅支持 WiFi 模式，请在「设置」切换到 WiFi 并完成配对",
            )
            return
        if not endpoint:
            QMessageBox.warning(
                self, "屏幕共享",
                "请先在「设置」中配置 WiFi 端点与 Token",
            )
            return
        # 心跳判定：未连接时直接拒开，避免开窗后阻塞 ws 握手 2s 才显示错误
        if self._device_pulse is not None:
            last = self._device_pulse.last_status()
            if last is not None and last[0] is False:
                QMessageBox.warning(
                    self, "屏幕共享",
                    "当前设备未连接，请检查手机端 Guiness 控制器是否已开启，且 PC 与手机在同一局域网",
                )
                return
        if self._mirror_dialog is not None and self._mirror_dialog.isVisible():
            self._mirror_dialog.raise_()
            self._mirror_dialog.activateWindow()
            return
        try:
            from gui.widgets.screen_mirror_dialog import ScreenMirrorDialog
            self._mirror_dialog = ScreenMirrorDialog(
                endpoint=endpoint,
                token=token,
                parent=self,
            )
            self._mirror_dialog.show()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "屏幕共享", f"打开失败：{e}")

    # ── 显示模式（图片 / 实时镜像）──

    def _init_display_mode(self) -> None:
        try:
            from utils.config_loader import get_config
            display_cfg = (get_config().get("display") or {})
            mode = display_cfg.get("mode", "image")
            if mode not in ("image", "mirror"):
                mode = "image"
            self._display_mode = mode
            self._sidebar.set_display_mode(mode)
            self._chat_feed.set_display_mode(mode)
            self._sidebar.set_mirror_button_visible(mode != "mirror")
            if mode == "mirror":
                self._start_mirror_viewport()
        except Exception as e:
            logger.error(f"初始化显示模式失败: {e}", exc_info=True)
            self._display_mode = "image"

    def _on_display_mode_changed(self, mode: str) -> None:
        changed = (mode != self._display_mode)
        self._display_mode = mode
        self._chat_feed.set_display_mode(mode)
        self._sidebar.set_mirror_button_visible(mode != "mirror")
        if changed:
            self._persist_display_mode(mode)
        if mode == "mirror":
            vp = self._chat_feed._mirror_viewport
            if vp is None or vp._worker is None:
                self._start_mirror_viewport()
        else:
            self._chat_feed.hide_mirror_viewport()

    def _start_mirror_viewport(self) -> None:
        try:
            factory = self._build_frame_factory()
            self._chat_feed.show_mirror_viewport(factory)
        except Exception as e:
            logger.error(f"启动实时镜像失败: {e}", exc_info=True)
            QMessageBox.warning(self, "实时镜像", f"启动失败：{e}")
            self._display_mode = "image"
            self._sidebar.set_display_mode("image")
            self._chat_feed.set_display_mode("image")
            self._sidebar.set_mirror_button_visible(True)

    def _build_frame_factory(self):
        """根据当前 device.mode 构造帧迭代器工厂。"""
        import threading
        from typing import Iterator
        from PySide6.QtGui import QImage
        from utils.config_loader import get_config

        cfg = get_config()
        device_cfg = cfg.get("device") or {}
        display_cfg = cfg.get("display") or {}
        mirror_cfg = display_cfg.get("mirror") or {}

        mode = (device_cfg.get("mode") or "usb").lower()
        fps = int(mirror_cfg.get("fps", 15))
        quality = int(mirror_cfg.get("quality", 70))
        scale = float(mirror_cfg.get("scale", 1.0))

        if mode == "wifi":
            endpoint = str(device_cfg.get("wifi_endpoint") or "").strip()
            token = str(device_cfg.get("token") or "").strip()
            if not endpoint:
                return None

            def wifi_factory(stop_event: threading.Event) -> Iterator[QImage]:
                from device.wifi_backend import WifiBackend
                backend = None
                try:
                    backend = WifiBackend(endpoint=endpoint, token=token, timeout=5.0)
                    for frame in backend.stream_screen(
                        fps=fps, quality=quality, scale=scale, stop_event=stop_event,
                    ):
                        if stop_event.is_set():
                            break
                        img = QImage.fromData(frame, "JPEG")
                        if not img.isNull():
                            yield img
                finally:
                    try:
                        if backend is not None:
                            backend.close()
                    except Exception:
                        pass

            return wifi_factory
        else:
            serial = str(device_cfg.get("name") or "").strip()
            adb_max_size = int(mirror_cfg.get("adb_max_size", 1280))
            adb_bit_rate = int(mirror_cfg.get("adb_bit_rate", 8_000_000))

            def adb_factory(stop_event: threading.Event) -> Iterator[QImage]:
                import subprocess, sys, time as _time
                from PySide6.QtGui import QImage

                # 优先 scrcpy H.264 流（低延迟 ~30-50ms）
                try:
                    from device.scrcpy_client import ScrcpyClient, ScrcpyUnavailable
                    client = ScrcpyClient(
                        serial or "",
                        max_size=adb_max_size,
                        bit_rate=adb_bit_rate,
                        max_fps=fps,
                    )
                    client.start()
                    try:
                        for frame in client.stream_frames(stop_event=stop_event):
                            if stop_event.is_set():
                                break
                            arr = frame.to_ndarray(format="rgb24")
                            h, w = arr.shape[0], arr.shape[1]
                            img = QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
                            yield img
                    finally:
                        client.close()
                    return
                except Exception as e:
                    logger.warning(f"scrcpy 不可用，降级到 screencap: {e}")

                # 降级：screencap PNG（延迟高但兼容性好）
                _si = None
                _cf = 0
                if sys.platform == "win32":
                    _si = subprocess.STARTUPINFO()
                    _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    _si.wShowWindow = 0
                    _cf = subprocess.CREATE_NO_WINDOW

                adb_cmd = ["adb"]
                if serial:
                    adb_cmd = ["adb", "-s", serial]

                interval = 0.25
                while not stop_event.is_set():
                    t0 = _time.time()
                    try:
                        r = subprocess.run(
                            adb_cmd + ["exec-out", "screencap", "-p"],
                            capture_output=True, timeout=3,
                            startupinfo=_si, creationflags=_cf,
                        )
                        data = r.stdout
                        if data:
                            png_magic = b'\x89PNG\r\n\x1a\n'
                            idx = data.find(png_magic)
                            if idx > 0:
                                data = data[idx:]
                            if data[:8] == png_magic:
                                img = QImage()
                                if img.loadFromData(data, "PNG"):
                                    yield img
                    except Exception:
                        pass
                    elapsed = _time.time() - t0
                    wait = interval - elapsed
                    if wait > 0:
                        stop_event.wait(wait)

            return adb_factory

    def _persist_display_mode(self, mode: str) -> None:
        from utils.config_loader import get_config, save_config_atomic
        cfg = get_config().copy()
        display = cfg.setdefault("display", {})
        display["mode"] = mode
        save_config_atomic(cfg)
