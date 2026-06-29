# -*- coding: utf-8 -*-
"""启动时清理旧产物，保留 2 天。

清理范围：
  1. data/logs/app.log 体积超过阈值时滚动，超过 2 天的 .log.* 归档删除
  2. data/history/conversations.json 中无对应 output 的过期会话
  3. 系统 tempfile.gettempdir() 下名为 eval_* 的残留临时目录

data/output/ 不自动清理（用户手动管理）。
由 main.py 在 _setup_logging 之后调一次。失败仅记 warning，不阻塞启动。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from typing import Iterable

from gui.paths import data_dir

logger = logging.getLogger(__name__)

RETENTION_DAYS = 2
LOG_MAX_BYTES = 20 * 1024 * 1024  # 单个 app.log 超过 20MB 滚动一次


def run_startup_cleanup() -> None:
    """统一入口：执行所有清理动作。任一项失败不影响其他项。"""
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    base = data_dir()

    for fn, label in (
        (lambda: _clean_history(os.path.join(base, "history", "conversations.json"), cutoff), "history"),
        (lambda: _clean_logs(os.path.join(base, "logs"), cutoff), "logs"),
        (lambda: _clean_tmp_residue(cutoff), "tmp"),
    ):
        try:
            fn()
        except Exception:
            logger.exception("启动清理失败：%s", label)


def _clean_history(history_file: str, cutoff: datetime) -> None:
    """从 conversations.json 中移除磁盘上 output_dir 已不存在的过期会话。

    旧 created_at 字段只有 HH:MM:SS 没日期，所以判定 cutoff 用 output_dir 是否还在。
    output 目录已被 _clean_output_dirs 清掉的会话，这里把对应 entry 也摘掉。
    """
    if not os.path.isfile(history_file):
        return
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.exception("读取 conversations.json 失败")
        return
    if not isinstance(data, list):
        return
    kept: list = []
    dropped = 0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        out = entry.get("output_dir") or ""
        # output 目录被 _clean_output_dirs 清掉的过期会话 → 摘掉
        if out and not os.path.isdir(out):
            dropped += 1
            continue
        # 其余（output 还在、或本就没 output 字段）保留
        kept.append(entry)
    if dropped == 0:
        return
    tmp_path = history_file + ".cleanup.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, history_file)
        logger.info("启动清理：从历史中移除 %d 条 output 已不存在的会话", dropped)
    except Exception:
        logger.exception("写入清理后的 conversations.json 失败")
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _clean_logs(log_dir: str, cutoff: datetime) -> None:
    """滚动主日志文件，删除 2 天前的归档。"""
    if not os.path.isdir(log_dir):
        return
    main_log = os.path.join(log_dir, "app.log")
    # 主日志体积超阈值，重命名为 app.log.<timestamp>，下次启动会自动新建
    if os.path.isfile(main_log):
        try:
            size = os.path.getsize(main_log)
            if size > LOG_MAX_BYTES:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                rotated = os.path.join(log_dir, f"app.log.{stamp}")
                os.rename(main_log, rotated)
                logger.info("启动清理：主日志已滚动（%d bytes → %s）", size, rotated)
        except OSError:
            logger.exception("滚动主日志失败")
    # 清理旧归档
    cutoff_ts = cutoff.timestamp()
    removed = 0
    for name in os.listdir(log_dir):
        if name == "app.log":
            continue
        path = os.path.join(log_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            if os.path.getmtime(path) < cutoff_ts:
                os.remove(path)
                removed += 1
        except OSError:
            pass
    if removed:
        logger.info("启动清理：删除了 %d 个过期日志归档", removed)


def _clean_tmp_residue(cutoff: datetime) -> None:
    """清理系统 tmp 下 EpisodeRunner 异常退出留下的 eval_*_ 目录。

    runner/episode_runner.py 用 tempfile.mkdtemp(prefix=f"eval_{episode_id}_") 建本地临时目录；
    正常 _finalize_episode 会清掉，异常路径会泄漏。
    """
    tmp_root = tempfile.gettempdir()
    if not os.path.isdir(tmp_root):
        return
    cutoff_ts = cutoff.timestamp()
    removed = 0
    try:
        names: Iterable[str] = os.listdir(tmp_root)
    except OSError:
        return
    for name in names:
        if not name.startswith("eval_"):
            continue
        path = os.path.join(tmp_root, name)
        if not os.path.isdir(path):
            continue
        try:
            if os.path.getmtime(path) >= cutoff_ts:
                continue
            shutil.rmtree(path)
            removed += 1
        except OSError:
            pass
    if removed:
        logger.info("启动清理：删除了 %d 个 tmp 残留目录", removed)


