# -*- coding: utf-8 -*-
"""把 data/output/<date>/<app>/<episode_id>/task.json 反向合成 Conversation。

用途：用户手工把别人的评测产物拷进 data/output 后，启动 GUI 应该能在侧边栏看到。
ChatManager._load_history 之后调用 sync_from_output()，扫描磁盘上有但内存里没有的
episode_id，注入为 Conversation 并落盘。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Iterable, Optional

from gui.chat_manager import Conversation
from gui.paths import data_dir

logger = logging.getLogger(__name__)


# 模块级索引：episode_id -> 本机 episode 目录。GUI 启动时由 ChatManager 调用
# refresh_episode_index() 填充；step_card 渲染时用 resolve_screenshot_path() 查询。
# 这是显示截图时的唯一真相之源——不依赖 conversations.json 里写的路径。
_EPISODE_INDEX: dict[str, str] = {}


def _output_root() -> str:
    return os.path.realpath(os.path.join(data_dir(), "output"))


def _parse_date_str(date_dir: str) -> Optional[datetime]:
    """data/output 下子目录名形如 2026-05-21_11-24-18，解析失败返回 None。"""
    try:
        return datetime.strptime(date_dir, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def _step_to_chat_step(
    raw: dict, episode_id: str, episode_dir: str, max_steps: int,
) -> dict:
    """把 task.json.data[i] 拍成 chat history 期望的 step_data 形态。

    与 EpisodeWorker.on_step 中的 step_data shape 对齐，保证 step_card 渲染一致。
    """
    cand = raw.get("screenshot", "")
    if cand:
        local = cand if os.path.isabs(cand) else os.path.join(episode_dir, cand)
    else:
        local = ""
    # plan 是标准字段；兼容旧数据中 action 字段
    raw_action = raw.get("plan")
    if not isinstance(raw_action, dict):
        raw_action = raw.get("action") if isinstance(raw.get("action"), dict) else {}
    return {
        "conv_id": episode_id,
        "step": raw.get("step", 0),
        "max_steps": max_steps,
        "screenshot_path": local,
        "thought": raw.get("thought", ""),
        "action": raw_action,
        "foreground_app": raw.get("foreground_app", ""),
        "exec_success": raw.get("exec_success", True),
        "raw_model_output": raw.get("raw_model_output", ""),
        "infer_time": raw.get("infer_time", 0),
    }


def _task_json_to_conversation(
    task_json_path: str,
    date_dir: str,
    default_max_steps: int = 100,
) -> Optional[Conversation]:
    try:
        with open(task_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.warning("跳过坏 task.json：%s", task_json_path)
        return None
    if not isinstance(data, dict):
        return None

    episode_dir = os.path.dirname(task_json_path)

    episode_id = (data.get("episode_id") or "").strip()
    if not episode_id:
        episode_id = os.path.basename(episode_dir)

    raw_steps = data.get("data") or data.get("steps") or []
    if not isinstance(raw_steps, list):
        raw_steps = []

    # max_steps：task.json 不直接存，按已有 step 数兜底，至少 default
    max_steps = max(default_max_steps, len(raw_steps))

    steps = [
        _step_to_chat_step(s, episode_id, episode_dir, max_steps)
        for s in raw_steps if isinstance(s, dict)
    ]

    query = (data.get("query") or "").strip()
    app = (data.get("app") or "").strip()

    # created_at 用 date_dir 名解析；解析失败回退到 mtime
    dt = _parse_date_str(os.path.basename(date_dir))
    if dt is None:
        try:
            dt = datetime.fromtimestamp(os.path.getmtime(task_json_path))
        except OSError:
            dt = datetime.now()
    created_at = dt.strftime("%H:%M:%S")

    # 单轮兜底：task.json 里没有 turns
    turns = [{
        "query": query,
        "app": app,
        "created_at": created_at,
        "step_count": len(steps),
    }]

    # status：最后一步 action.func 决定
    status = "done"
    if steps:
        last_func = (steps[-1].get("action") or {}).get("func", "")
        if last_func == "Fail":
            status = "error"
        elif last_func == "Request":
            status = "awaiting_user"

    conv = Conversation(
        id=episode_id,
        query=query,
        app=app,
        model_source=data.get("model_source", "mify"),
        model_name=data.get("model_name", ""),
        custom_url="",
        api_key="",
        device_id="",
        created_at=created_at,
        status=status,
        steps=steps,
        turns=turns,
        output_dir=os.path.abspath(date_dir),
    )
    return conv


def _walk_task_jsons(root: str) -> Iterable[tuple[str, str]]:
    """yield (task_json_path, date_name)。

    episode_runner 的 sub_dir = output_dir / safe_app / episode_id。
    当 app="" 时 join 折叠成 output_dir / episode_id（2 层）。两种都要识别。
    """
    for date_name in os.listdir(root):
        date_dir = os.path.join(root, date_name)
        if not os.path.isdir(date_dir):
            continue
        for child in os.listdir(date_dir):
            child_dir = os.path.join(date_dir, child)
            if not os.path.isdir(child_dir):
                continue
            tj2 = os.path.join(child_dir, "task.json")  # 2 层
            if os.path.isfile(tj2):
                yield tj2, date_name
            try:
                grandchildren = os.listdir(child_dir)
            except OSError:
                continue
            for grand in grandchildren:
                gd = os.path.join(child_dir, grand)
                if os.path.isdir(gd):
                    tj3 = os.path.join(gd, "task.json")
                    if os.path.isfile(tj3):
                        yield tj3, date_name


def refresh_episode_index(output_root: Optional[str] = None) -> dict[str, str]:
    """重扫 data/output，刷新 _EPISODE_INDEX。返回当前快照。

    幂等。GUI 启动时调用一次；扫描成本主要是 listdir，不读 task.json 内容
    （episode_id 直接用目录名——episode_runner 写盘时目录名就 = episode_id）。
    """
    root = output_root or _output_root()
    index: dict[str, str] = {}
    if os.path.isdir(root):
        for tj_path, _date in _walk_task_jsons(root):
            ep_dir = os.path.dirname(tj_path)
            eid = os.path.basename(ep_dir)
            index.setdefault(eid, ep_dir)
    _EPISODE_INDEX.clear()
    _EPISODE_INDEX.update(index)
    return dict(index)


def episode_dir(episode_id: str) -> Optional[str]:
    """按 episode_id 查本机 episode 目录。无则 None。"""
    if not episode_id:
        return None
    return _EPISODE_INDEX.get(episode_id)


def resolve_screenshot_path(episode_id: str, recorded_path: str) -> str:
    """把 step 里写死的 screenshot_path 重映射到本机真实路径。

    规则：
      1) 取 basename(recorded_path) 作为文件名（如 "1.jpg"）；
      2) 在 _EPISODE_INDEX 中找 episode_id 对应的本机目录；
      3) 拼 episode_dir/basename。文件不存在时尝试同名 .png 兜底（jpg 是
         运行时压缩产物，被删时原 png 可能还在）。
      4) 完全找不到 → 退回原路径，让 viewer 显示"截图文件不存在"。
    """
    if not recorded_path:
        return ""
    fname = os.path.basename(recorded_path)
    ep_dir = episode_dir(episode_id)
    if not ep_dir:
        return recorded_path
    candidate = os.path.join(ep_dir, fname)
    if os.path.isfile(candidate):
        return candidate
    stem, ext = os.path.splitext(fname)
    if ext.lower() == ".jpg":
        png = os.path.join(ep_dir, stem + ".png")
        if os.path.isfile(png):
            return png
    elif ext.lower() == ".png":
        jpg = os.path.join(ep_dir, stem + ".jpg")
        if os.path.isfile(jpg):
            return jpg
    return candidate


def discover_conversations(
    output_root: Optional[str] = None,
) -> Iterable[tuple[Conversation, datetime]]:
    """yield (Conversation, created_dt)，按 created_dt 升序。

    遍历 data/output/<date>/<app>/<episode_id>/task.json。
    """
    root = output_root or _output_root()
    if not os.path.isdir(root):
        return []

    found: list[tuple[Conversation, datetime]] = []
    seen_eids: set[str] = set()

    for tj_path, date_name in _walk_task_jsons(root):
        date_dir = os.path.join(root, date_name)
        conv = _task_json_to_conversation(tj_path, date_dir)
        if conv is None or conv.id in seen_eids:
            continue
        seen_eids.add(conv.id)
        dt = _parse_date_str(date_name) or datetime.fromtimestamp(
            os.path.getmtime(tj_path)
        )
        found.append((conv, dt))

    found.sort(key=lambda x: x[1])
    return found
