# -*- coding: utf-8 -*-
"""会话管理：每个对话对应一次 Android 评测任务（PySide6 版本）"""
import json
import logging
import os
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from gui.paths import data_dir

logger = logging.getLogger(__name__)


_HISTORY_DIR = os.path.join(data_dir(), "history")
_HISTORY_FILE = os.path.join(_HISTORY_DIR, "conversations.json")
_OUTPUT_ROOT = os.path.realpath(os.path.join(data_dir(), "output"))


@dataclass
class Conversation:
    id: str
    query: str
    app: str = ""
    model_source: str = "mify"
    model_name: str = ""
    custom_url: str = ""
    api_key: str = ""
    device_id: str = ""
    created_at: str = ""
    status: str = "pending"  # pending | running | done | error | stopped
    steps: list = field(default_factory=list)
    output_dir: str = ""
    error: str = ""
    # 多轮对话：每一轮 = 一次发送的 query + 这一轮产生的 step 数
    # 首轮由 create_conversation 初始化；"继续发送"时 append 一条
    step_by_step: bool = False
    turns: list = field(default_factory=list)
    _stop_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _approve_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def request_stop(self) -> None:
        """通知 runner 线程尽快停下。幂等。"""
        self._stop_event.set()

    def is_stop_requested(self) -> bool:
        """runner 的 stop_check 回调：是否已被要求停止。"""
        return self._stop_event.is_set()

    def reset_stop(self) -> None:
        """再次发送前清掉上一次的停止标志。"""
        self._stop_event.clear()

    def approve_step(self) -> None:
        """通知 runner 确认并继续执行步骤动作。"""
        self._approve_event.set()

    def is_approved(self) -> bool:
        """runner 检查是否已确认。"""
        return self._approve_event.is_set()

    def reset_approval(self) -> None:
        """重置步骤确认事件。"""
        self._approve_event.clear()


def _conv_to_dict(conv: Conversation) -> dict:
    """序列化 Conversation 到可 JSON 保存的 dict。"""
    return {
        "id": conv.id,
        "query": conv.query,
        "app": conv.app,
        "model_source": conv.model_source,
        "model_name": conv.model_name,
        "custom_url": conv.custom_url,
        "api_key": conv.api_key,
        "device_id": conv.device_id,
        "created_at": conv.created_at,
        "status": conv.status,
        "steps": conv.steps,
        "turns": conv.turns,
        "output_dir": conv.output_dir,
        "error": conv.error,
        "step_by_step": conv.step_by_step,
    }


def _dict_to_conv(d: dict) -> Conversation:
    """从 dict 反序列化 Conversation。"""
    conv = Conversation(
        id=d.get("id", ""),
        query=d.get("query", ""),
        app=d.get("app", ""),
        model_source=d.get("model_source", "mify"),
        model_name=d.get("model_name", ""),
        custom_url=d.get("custom_url", ""),
        api_key=d.get("api_key", ""),
        device_id=d.get("device_id", ""),
        created_at=d.get("created_at", ""),
        status=d.get("status", "done"),
        steps=list(d.get("steps", [])),
        turns=list(d.get("turns", [])),
        output_dir=d.get("output_dir", ""),
        error=d.get("error", ""),
        step_by_step=bool(d.get("step_by_step", False)),
    )
    # 旧历史记录没有 turns：用首轮 query + 全量 steps 兜底
    if not conv.turns and conv.query:
        conv.turns = [{
            "query": conv.query,
            "app": conv.app,
            "created_at": conv.created_at,
            "step_count": len(conv.steps),
        }]
    return conv


class ChatManager:
    """线程安全的会话管理器，含设备锁和持久化。"""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._order: list[str] = []
        # _lock：保护内存态（_conversations / _order）。读多写多，持锁时间必须短，
        # 绝不能跨磁盘 I/O——EpisodeWorker 每步触发一次 save，UI 同时在读 list_all，
        # 锁住 fsync 会造成每步 10-100ms 的 UI 卡顿
        self._lock = threading.RLock()
        # _io_lock：串行化磁盘写。不保护内存，只防两个 writer 的 .tmp 互相 rename
        self._io_lock = threading.Lock()
        self._device_lock = threading.Lock()
        self._load_history()
        self._sync_from_output()

    def create_conversation(
        self, query: str, app: str = "", model_config: dict | None = None
    ) -> Conversation:
        with self._lock:
            conv_id = str(uuid.uuid4())[:8]
            while conv_id in self._conversations:
                conv_id = str(uuid.uuid4())[:8]
        mc = model_config or {}
        now = datetime.now().strftime("%H:%M:%S")
        conv = Conversation(
            id=conv_id,
            query=query,
            app=app,
            model_source=mc.get("source", "mify"),
            model_name=mc.get("model_name", ""),
            custom_url=mc.get("custom_url", ""),
            api_key=mc.get("api_key", ""),
            device_id=mc.get("device_id", ""),
            created_at=now,
            turns=[{
                "query": query,
                "app": app,
                "created_at": now,
                "step_count": 0,
                # 跨 turn step 单调编号：turn N 的 step 写入 conv.steps 时偏移
                # 加上 step_offset，避免 turn 2 的 step 1 撞到 turn 1 的 step 1
                "step_offset": 0,
            }],
        )
        with self._lock:
            self._conversations[conv_id] = conv
            self._order.append(conv_id)
        self._save_history()
        return conv

    def start_turn(self, conv_id: str, query: str, app: str = "") -> Optional[dict]:
        """在既有对话中追加一轮 query，返回新 turn dict。status 复位为 pending。"""
        with self._lock:
            conv = self._conversations.get(conv_id)
            if conv is None:
                return None
            turn = {
                "query": query,
                "app": app,
                "created_at": datetime.now().strftime("%H:%M:%S"),
                "step_count": 0,
                # 新一轮的 step 在 conv.steps 里从 step_offset+1 开始编号
                "step_offset": len(conv.steps),
            }
            conv.turns.append(turn)
            conv.query = query  # 兼容字段：侧边栏标题用它
            conv.app = app
            conv.status = "pending"
            conv.error = ""
            conv.reset_stop()
        self._save_history()
        return turn

    def rollback_turn(self, conv_id: str) -> None:
        """worker 启动失败回滚：把 start_turn append 的最末 turn 撤掉，恢复 status。

        仅在 conv.turns 长度 > 1 且 status 仍是 pending（worker 还没改成 running）
        时回滚；否则保持现状不动，避免误删合法 turn。
        """
        with self._lock:
            conv = self._conversations.get(conv_id)
            if conv is None:
                return
            if len(conv.turns) > 1 and conv.status == "pending":
                conv.turns.pop()
                conv.status = "stopped"
                conv.error = ""
                # 恢复 query 到上一 turn，保持 sidebar 标题一致
                last = conv.turns[-1]
                conv.query = last.get("query", conv.query)
                conv.app = last.get("app", conv.app)
        self._save_history()

    def get(self, conv_id: str) -> Optional[Conversation]:
        with self._lock:
            return self._conversations.get(conv_id)

    def list_all(self) -> list[Conversation]:
        with self._lock:
            return [self._conversations[cid] for cid in self._order
                    if cid in self._conversations]

    def delete(self, conv_id: str) -> bool:
        with self._lock:
            if conv_id not in self._conversations:
                return False
            conv = self._conversations.pop(conv_id)
            if conv_id in self._order:
                self._order.remove(conv_id)
        self._remove_output_dir(conv.output_dir)
        self._save_history()
        return True

    @staticmethod
    def _remove_output_dir(output_dir: str) -> None:
        """删掉会话对应的 data/output/<timestamp> 目录。

        安全防线：只删真实位于 _OUTPUT_ROOT 下的目录——防止 output_dir 字段
        被手工编辑 / 旧版本写入奇怪路径时误删用户别处的文件。
        """
        if not output_dir:
            return
        try:
            target = os.path.realpath(output_dir)
        except Exception:
            return
        if not target.startswith(_OUTPUT_ROOT + os.sep):
            logger.warning("跳过删除 output_dir=%r：不在 %s 下", output_dir, _OUTPUT_ROOT)
            return
        if not os.path.isdir(target):
            return
        try:
            shutil.rmtree(target)
            logger.info("已删除 output 目录：%s", target)
        except Exception:
            logger.exception("删除 output 目录失败：%s", target)

    def stop(self, conv_id: str) -> bool:
        with self._lock:
            conv = self._conversations.get(conv_id)
            if conv and conv.status == "running":
                conv.request_stop()
                return True
            return False

    def save(self) -> None:
        """外部调用：保存当前状态到磁盘。"""
        self._save_history()

    def acquire_device(self) -> bool:
        return self._device_lock.acquire(blocking=False)

    def release_device(self) -> None:
        try:
            self._device_lock.release()
        except RuntimeError:
            pass

    def _save_history(self) -> None:
        """将所有对话持久化到 JSON 文件。

        每步都会触发一次（EpisodeWorker.on_step → self._manager.save()）。
        两步走，锁拆开：
          1) 在 _lock 内只做 snapshot（纯内存拷贝），立刻释放 → 不阻塞 UI 读
          2) 在 _io_lock 内做磁盘写（.tmp + fsync + os.replace） → 保证原子，
             且两个 writer 的 .tmp 不会互相覆盖
        两个锁无嵌套关系，不会死锁
        """
        try:
            os.makedirs(_HISTORY_DIR, exist_ok=True)
            with self._lock:
                data = [_conv_to_dict(self._conversations[cid])
                        for cid in self._order if cid in self._conversations]
            with self._io_lock:
                fd, tmp_path = tempfile.mkstemp(
                    prefix=".conversations.", suffix=".tmp", dir=_HISTORY_DIR,
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp_path, _HISTORY_FILE)
                except Exception:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    raise
        except Exception:
            logger.exception("保存对话历史失败")

    def _sync_from_output(self) -> None:
        """让 data/output 成为对话列表的真相之源。

        - 先刷新 episode 索引：step_card 渲染时按此索引重映射 screenshot_path
          到本机绝对路径（不依赖 conversations.json 里写死的路径）。
        - 然后做两件事：
          1) 新增：磁盘上有 task.json 但内存里没有对应 episode_id → 反向合成
             Conversation 注入，按 created_dt 升序 append 到 _order，保证侧边栏
             insertWidget(0) 后最新的在顶部。
          2) 清除：内存里有但磁盘扫不到 task.json → 从对话列表移除。避免
             conversations.json 拷贝过来时残留指向不存在文件的"鬼对话"。
        """
        try:
            from gui.output_sync import discover_conversations, refresh_episode_index
        except Exception:
            logger.exception("output_sync 不可用，跳过磁盘同步")
            return
        try:
            refresh_episode_index()
            discovered = list(discover_conversations())
        except Exception:
            logger.exception("扫描 data/output 失败")
            return

        disk_ids = {conv.id for conv, _ in discovered}
        added = 0
        removed = 0
        with self._lock:
            for conv, _dt in discovered:
                if conv.id in self._conversations:
                    continue
                self._conversations[conv.id] = conv
                self._order.append(conv.id)
                added += 1
            stale_ids = [cid for cid in list(self._conversations.keys())
                         if cid not in disk_ids]
            for cid in stale_ids:
                self._conversations.pop(cid, None)
                if cid in self._order:
                    self._order.remove(cid)
                removed += 1
        if added or removed:
            logger.info(
                "data/output 同步：新增 %d 条，移除 %d 条", added, removed,
            )
            self._save_history()

    def _load_history(self) -> None:
        """从 JSON 文件加载历史对话。"""
        if not os.path.exists(_HISTORY_FILE):
            return
        try:
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            for d in data:
                conv = _dict_to_conv(d)
                # 恢复时将 running/pending 状态修正为 stopped（上次未正常退出
                # 或 worker 启动失败留下脏状态），避免 sidebar 永远显示等待 +
                # _on_resume 因 status 不在白名单里静默拒绝
                if conv.status in ("running", "pending"):
                    conv.status = "stopped"
                self._conversations[conv.id] = conv
                self._order.append(conv.id)
        except Exception:
            logger.exception("加载对话历史失败")
