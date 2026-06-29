# -*- coding: utf-8 -*-
"""单个 Episode 的执行引擎：截图 → 推理 → 动作分发 → 记录。

引擎只负责产生 step_record，不再直接打印——所有渲染都走 Reporter（终端染色、
Qt 信号、Web 推送等）或 on_step_complete 回调。
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import time
import logging
from typing import Callable, Optional

from action.action_space import normalize_action
from reporter.base import NullReporter, Reporter
from utils.image_utils import compress_image

logger = logging.getLogger(__name__)

# 达成这些 func 则提前终止 Episode 循环（即使其中部分不在 action_executor 的 handler 表）
_TERMINAL_FUNCS = ("Complete", "End", "Speak", "Fail", "Request")
# 这些 func 不送去 executor 执行（纯"宣告"类动作），runner 直接跳过 execute
_NO_EXECUTE_FUNCS = ("Request",)


class EpisodeRunner:
    def __init__(
        self,
        config,
        backend,
        action_executor,
        inference_client,
        output_dir=None,
        date_str=None,
        stop_check: Optional[Callable[[], bool]] = None,
        on_step_complete: Optional[Callable[[dict], None]] = None,
        reporter: Optional[Reporter] = None,
        approve_check: Optional[Callable[[], bool]] = None,
        approve_reset: Optional[Callable[[], None]] = None,
    ):
        self.config = config
        self.backend = backend
        self.executor = action_executor
        self.inference = inference_client
        self.output_dir = output_dir
        self.date_str = date_str
        self._stop_check = stop_check
        self._on_step_complete = on_step_complete
        self.reporter: Reporter = reporter or NullReporter()
        self._approve_check = approve_check
        self._approve_reset = approve_reset

        self.op_config = self.config.get("operation", {})
        self.max_steps = self.op_config.get("max_steps", 100)
        self.sleep_per_action = self.op_config.get("sleep_seconds_per_act", 1)
        self.sleep_per_screen = self.op_config.get("screen_sleep_time", 0.65)
        self.max_history_images = self.op_config.get("max_history_images", 0)
        self.max_turn = self.op_config.get("max_turn", 10)
        self.back_times = self.op_config.get("back_times", 6)

        self.use_compress = self.op_config.get("use_compress", True)
        self.compress_config = self.config.get("compress", {}) or {}
        self.device_type = self.config.get("device", {}).get("device_type", "phone")

        self.task_config = self.config.get("task", {})
        self.save_dir = self.task_config.get("save_dir", "data/output")

    # ======================================================================
    # Public entry
    # ======================================================================
    def _stopped(self) -> bool:
        return bool(self._stop_check and self._stop_check())

    def _interruptible_sleep(self, seconds: float) -> bool:
        """按 100ms 片段 sleep，一旦 stop_check 成立立即返回 True。"""
        if seconds <= 0:
            return self._stopped()
        slept = 0.0
        step = 0.1
        while slept < seconds:
            if self._stopped():
                return True
            time.sleep(min(step, seconds - slept))
            slept += step
        return self._stopped()

    def run(self, episode_task: dict) -> dict:
        """执行一个 Episode，返回完整的 episode 数据记录。"""
        ctx = self._prepare_episode(episode_task)
        self.reporter.on_episode_start(episode_task)

        history: list = []
        counters = {"continue_wait": 0, "continue_swipe": 0, "consecutive_errors": 0}
        step = 0
        is_end = False

        while not is_end and step < self.max_steps:
            if self._stopped():
                logger.info("收到停止请求，终止当前 Episode")
                break
            step += 1
            is_end = self._run_step(ctx, step, history, counters)

        self._finalize_episode(ctx, stopped=self._stopped())
        self.reporter.on_episode_finish(ctx.episode)
        return ctx.episode

    # ======================================================================
    # Phase 1: prepare
    # ======================================================================
    def _prepare_episode(self, episode_task: dict) -> "_EpisodeContext":
        episode = copy.deepcopy(episode_task)
        episode_id = episode.get("episode_id", "Unknown")
        query = episode.get("query", "")
        app_name = episode.get("app", "未知")

        logger.debug(f"开始执行 Task: {query} [ID: {episode_id}]")

        dev_info = self.backend.device_info()
        episode["phone"] = dev_info.name
        episode["os"] = "Android"
        episode["os_version"] = dev_info.os_version
        screen_res = [dev_info.width, dev_info.height]
        episode["screen_resolution"] = screen_res
        episode["data"] = []
        episode["steps"] = []

        if self.output_dir:
            safe_app = app_name.replace("/", "_").replace("\\", "_")
            safe_eid = episode_id.replace(":", "_").replace("/", "_")
            sub_dir = os.path.join(self.output_dir, safe_app, safe_eid)
            os.makedirs(sub_dir, exist_ok=True)
        else:
            sub_dir = tempfile.mkdtemp(prefix=f"eval_{episode_id}_")

        return _EpisodeContext(
            episode=episode,
            episode_id=episode_id,
            query=query,
            sub_dir=sub_dir,
            screen_res=screen_res,
        )

    # ======================================================================
    # Phase 2: per-step loop body
    # ======================================================================
    def _run_step(
        self,
        ctx: "_EpisodeContext",
        step: int,
        history: list,
        counters: dict,
    ) -> bool:
        """执行一步，返回 True 表示应终止整个 Episode。"""
        ts = int(time.time())
        raw_png = os.path.join(ctx.sub_dir, f"{step}.png")

        screenshot_start = time.time()
        try:
            self.backend.get_screenshot(raw_png)
        except Exception as e:
            logger.error(f"截图失败，终止本步: {e}")
            counters["consecutive_errors"] = counters.get("consecutive_errors", 0) + 1
            if counters["consecutive_errors"] >= 3:
                logger.error("连续 3 次截图/推理失败，终止 Episode")
                return True
            return False
        screenshot_t = time.time() - screenshot_start

        xml_path = os.path.join(ctx.sub_dir, f"{step}.xml")
        try:
            self.backend.dump_hierarchy(xml_path)
        except Exception as e:
            logger.debug(f"dump_hierarchy 失败（跳过）: {e}")

        if self._stopped():
            return True

        compressed_path, img_size = compress_image(
            raw_png,
            compress=self.use_compress,
            compress_config=self.compress_config,
        )
        local_img_path = compressed_path or raw_png

        fg = self.backend.get_foreground_info()
        foreground_app, foreground_pkg = fg.app_name, fg.package

        if self._stopped():
            return True

        add_info = "页面已经滑动到底部" if counters["continue_swipe"] > 2 else ""

        inf_start = time.time()
        completion = self.inference.request_action(
            image_path=local_img_path,
            query=ctx.query,
            add_info=add_info,
            system=None,
            history=history,
            max_turn=self.max_turn,
            max_history_images=self.max_history_images,
            foreground_app=foreground_app,
            device_type=self.device_type,
        )
        infer_t = time.time() - inf_start

        # 连续错误计数：API 持续失败时提前终止，避免空转 max_steps 轮
        if completion.pop("_is_error", False):
            counters["consecutive_errors"] += 1
            if counters["consecutive_errors"] >= 3:
                logger.error("连续 3 次推理失败，终止 Episode")
                completion["func"] = "Fail"
                completion["thought"] = "连续推理失败，自动终止"
        else:
            counters["consecutive_errors"] = 0

        w, h = ctx.screen_res
        action_data = normalize_action(completion, width=w, height=h)

        usage = action_data.pop("usage", None)
        plan = {k: v for k, v in action_data.items()
                if k not in ("raw_model_output", "thought", "action")}
        step_record = {
            "step": step,
            "source": getattr(self.inference, "model_name", "understandPlanner"),
            "query": ctx.query,
            "foreground_app": foreground_app,
            "foreground_app_package": foreground_pkg,
            "plan": plan,
            "thought": action_data.get("thought", ""),
            "action": action_data.get("action", ""),
            "screenshot": raw_png,
            "pixel": [w, h],
            "image_width": img_size[0] if img_size else w,
            "image_height": img_size[1] if img_size else h,
            "timestamp": ts,
            "raw_model_output": action_data.get("raw_model_output", ""),
            "infer_time": round(infer_t, 1),
            "usage": usage,
            # reporter-only 字段，不落盘
            "screenshot_time": round(screenshot_t, 2),
        }
        ctx.episode["data"].append(step_record)
        ctx.episode["steps"].append(step_record)

        act_type = action_data.get("func", "")

        # History 维护：排除 Wait
        if act_type != "Wait":
            h_record = copy.deepcopy(step_record)
            h_record["image_url"] = ""
            if history and history[-1]["query"] == ctx.query:
                history[-1]["steps"].append(h_record)
            else:
                history.append({"query": ctx.query, "steps": [h_record]})

        counters["continue_swipe"] = counters["continue_swipe"] + 1 if act_type == "Swipe" else 0
        counters["continue_wait"] = counters["continue_wait"] + 1 if act_type == "Wait" else 0

        # inference 可能耗时较长：一出来先检查停止，避免白白 execute 一次
        if self._stopped():
            return True

        # Step-by-step confirmation mode
        is_step_by_step = self.config.get("operation", {}).get("step_by_step", False)
        if is_step_by_step and act_type not in _TERMINAL_FUNCS and act_type != "Wait":
            step_record["status"] = "waiting_approval"
            self.reporter.on_step_complete(step_record)
            if self._on_step_complete:
                try:
                    self._on_step_complete(step_record)
                except Exception as cb_err:
                    logger.warning(f"Step callback error: {cb_err}")

            logger.info("分步模式：等待用户确认动作...")
            while not self._stopped():
                if self._approve_check and self._approve_check():
                    if self._approve_reset:
                        self._approve_reset()
                    break
                time.sleep(0.1)

            if self._stopped():
                return True

            step_record["status"] = "done"

        if act_type in _NO_EXECUTE_FUNCS:
            # Request 等宣告类动作：不动设备，直接记录成功
            exec_success = True
        else:
            exec_success = self.executor.execute(action_data)
        step_record["exec_success"] = exec_success

        self.reporter.on_step_complete(step_record)

        if self._on_step_complete:
            try:
                self._on_step_complete(step_record)
            except Exception as cb_err:
                logger.warning(f"Step callback error: {cb_err}")

        # 可中断 sleep：停止信号 100ms 内生效
        if self._interruptible_sleep(self.sleep_per_screen):
            return True

        return act_type in _TERMINAL_FUNCS

    # ======================================================================
    # Phase 3: finalize
    # ======================================================================
    def _finalize_episode(self, ctx: "_EpisodeContext", stopped: bool = False) -> None:
        try:
            save_json = os.path.join(ctx.sub_dir, "task.json")
            persisted = copy.deepcopy(ctx.episode)
            # 运行时字段不落盘
            for step in persisted.get("data", []):
                step.pop("screenshot_time", None)
            for step in persisted.get("steps", []):
                step.pop("screenshot_time", None)
            content = json.dumps(persisted, ensure_ascii=False, indent=2)
            # 原子写：tmpfile + fsync + replace，防止进程中断导致半写文件
            import tempfile as _tmpfile
            fd, tmp_path = _tmpfile.mkstemp(
                prefix=".task.", suffix=".tmp", dir=ctx.sub_dir
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, save_json)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error(f"保存 task.json 失败: {e}")

        if not self.output_dir:
            try:
                shutil.rmtree(ctx.sub_dir, ignore_errors=True)
                logger.info("已清理本地临时数据，本轮所有产物全部归档至 JFS/S3。")
            except Exception as e:
                logger.error(f"清理临时工作目录失败: {e}")
        else:
            logger.debug(f"评测产物已保留在本地: {ctx.sub_dir}")

        # 用户点了停止：不走 back 循环、不做结尾 sleep，立即返回让上层标 stopped
        if stopped:
            logger.debug("收到停止信号，跳过 back 循环和结尾 sleep")
            return

        # 回到初始状态：back_times <= 0 表示保持在任务完成页
        if self.back_times > 0:
            for _ in range(self.back_times):
                if self._stopped():
                    return
                self.backend.back()
                if self._interruptible_sleep(0.5):
                    return
        else:
            logger.debug("back_times=0，保持在任务完成页面")

        self._interruptible_sleep(self.sleep_per_action)


class _EpisodeContext:
    """Episode 执行期间的只读上下文容器。"""
    __slots__ = ("episode", "episode_id", "query", "sub_dir", "screen_res")

    def __init__(self, episode, episode_id, query, sub_dir, screen_res):
        self.episode = episode
        self.episode_id = episode_id
        self.query = query
        self.sub_dir = sub_dir
        self.screen_res = screen_res
