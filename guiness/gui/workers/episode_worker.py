# -*- coding: utf-8 -*-
"""QThread 单 episode 执行器：信号驱动，非轮询。"""
import copy
import os
import logging
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from gui.chat_manager import Conversation, ChatManager

logger = logging.getLogger(__name__)


class EpisodeWorker(QThread):
    """在子线程中运行单个 EpisodeRunner，通过 Qt Signal 推送进度。"""

    step_completed = Signal(str, dict)    # (conv_id, step_data)
    episode_started = Signal(str)          # conv_id
    episode_finished = Signal(str, str)    # (conv_id, "done"|"stopped")
    episode_error = Signal(str, str)       # (conv_id, error_msg)
    init_progress = Signal(str, str)       # (conv_id, message) 初始化进度

    def __init__(
        self,
        conv: Conversation,
        manager: ChatManager,
        parent=None,
        *,
        turn_query: str | None = None,
        turn_app: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._conv = conv
        self._manager = manager
        # 继续发送时用最新 turn 的 query 覆盖 conv.query（避免把最早那轮又跑一遍）
        self._turn_query = turn_query if turn_query is not None else conv.query
        self._turn_app = turn_app if turn_app is not None else conv.app

    def run(self) -> None:
        conv = self._conv
        if not self._manager.acquire_device():
            self.episode_error.emit(conv.id, "设备正在被其他对话使用，请等待")
            return

        try:
            conv.status = "running"
            self._do_run()
        except Exception as e:
            logger.exception(f"Episode error for {conv.id}")
            conv.status = "error"
            conv.error = str(e)
            self._manager.save()
            self.episode_error.emit(conv.id, str(e))
        finally:
            self._close_backend()
            self._manager.release_device()

    def _close_backend(self) -> None:
        try:
            if hasattr(self, "_backend") and self._backend is not None:
                self._backend.close()
        except Exception as e:
            logger.debug(f"关闭 backend 时出错（忽略）: {e}")

    def _do_run(self) -> None:
        conv = self._conv

        from utils.config_loader import get_config
        from core import build_components, build_runner, resolve_device_id

        config = copy.deepcopy(get_config())

        # 覆盖模型配置
        model_cfg = dict(config.get("model", {}))
        model_cfg["source"] = conv.model_source
        if conv.model_source == "mify":
            model_cfg["model_name"] = conv.model_name
            if conv.api_key:
                model_cfg["mify_api_key"] = conv.api_key
        else:
            model_cfg["custom_url"] = conv.custom_url
            if conv.model_name:
                model_cfg["custom_model_name"] = conv.model_name
        config["model"] = model_cfg

        device_cfg = config.get("device", {})
        mode = (device_cfg.get("mode") or "usb").lower()
        if mode == "wifi":
            preferred = conv.device_id or device_cfg.get("wifi_endpoint", "")
        else:
            preferred = conv.device_id or device_cfg.get("name", "")
        device_id = resolve_device_id(preferred, mode=mode)
        device_type = device_cfg.get("device_type", "phone")

        comps = build_components(
            device_id=device_id,
            device_type=device_type,
            model_config=model_cfg,
            mode=mode,
            token=device_cfg.get("token", ""),
            on_progress=lambda msg: self.init_progress.emit(conv.id, msg),
        )
        self._backend = comps.backend

        from gui.paths import data_dir
        # 多轮目录隔离：所有轮次共用 conv 根目录，runner 内每轮写到 <safe_app>/<conv.id>_t<N>/
        # 重要：runner 把 episode_id 中的 ":" / "/" 替成 "_"，所以 episode_id 用 "_t<N>" 后缀
        # 这样 turn 1 和 turn 2 的 task.json 不会互相覆盖；删除会话时 rmtree conv 根即可
        conv_root = os.path.join(data_dir(), "output", conv.id)
        os.makedirs(conv_root, exist_ok=True)
        # 仅首次设定 conv.output_dir，后续轮不再覆盖；删除会话用它定位 conv 根
        if not conv.output_dir:
            conv.output_dir = os.path.abspath(conv_root)
        turn_idx = max(1, len(conv.turns))  # 第 N 轮（1-based）
        run_date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        episode_id = f"{conv.id}_t{turn_idx}"

        # step_offset：让本轮的 step 1..M 在 conv.steps 中映射成 offset+1..offset+M
        # 与 ChatManager.start_turn 写入的字段一致；首轮 offset=0
        try:
            step_offset = int(conv.turns[-1].get("step_offset", 0)) if conv.turns else 0
        except (ValueError, TypeError):
            step_offset = 0

        max_steps = config.get("operation", {}).get("max_steps", 100)

        def on_step(step_record: dict) -> None:
            raw_step = int(step_record.get("step", 0) or 0)
            # 跨轮单调编号：turn 2 的 step 1 → conv.steps 中显示为 step (offset+1)
            global_step = raw_step + step_offset
            step_data = {
                "conv_id": conv.id,
                "step": global_step,
                "turn": turn_idx,
                "max_steps": max_steps,
                "screenshot_path": step_record.get("screenshot", ""),
                "thought": step_record.get("thought", ""),
                "action": step_record.get("plan", step_record.get("action", {})),
                "foreground_app": step_record.get("foreground_app", ""),
                "exec_success": step_record.get("exec_success", True),
                "raw_model_output": step_record.get("raw_model_output", ""),
                "infer_time": step_record.get("infer_time", 0),
                "status": step_record.get("status", "done"),
            }

            with self._manager._lock:
                existing_idx = -1
                for idx, s in enumerate(conv.steps):
                    if s.get("step") == global_step:
                        existing_idx = idx
                        break

                if existing_idx >= 0:
                    conv.steps[existing_idx] = step_data
                else:
                    conv.steps.append(step_data)
                    if conv.turns:
                        conv.turns[-1]["step_count"] = int(conv.turns[-1].get("step_count", 0)) + 1

            self._manager.save()
            self.step_completed.emit(conv.id, step_data)

        self.init_progress.emit(conv.id, "初始化完成，开始执行...")
        self.episode_started.emit(conv.id)

        runner = build_runner(
            components=comps,
            config=config,
            output_dir=conv_root,
            date_str=run_date_str,
            stop_check=conv.is_stop_requested,
            on_step_complete=on_step,
            approve_check=conv.is_approved,
            approve_reset=conv.reset_approval,
        )

        task_data = {
            "episode_id": episode_id,
            "query": self._turn_query,
            "app": self._turn_app,
        }
        result = runner.run(task_data)

        if conv.is_stop_requested():
            conv.status = "stopped"
            self._manager.save()
            self.episode_finished.emit(conv.id, "stopped")
            return

        # 模型以 Request 结束 → 等用户回复，不当作 done
        with self._manager._lock:
            last_action = conv.steps[-1].get("action") if conv.steps else {}
        last_func = (last_action or {}).get("func", "") if isinstance(last_action, dict) else ""
        if last_func == "Request":
            conv.status = "awaiting_user"
            self._manager.save()
            self.episode_finished.emit(conv.id, "awaiting_user")
            return

        conv.status = "done"
        self._manager.save()
        self.episode_finished.emit(conv.id, "done")
