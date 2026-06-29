# -*- coding: utf-8 -*-
"""结果查看页：左侧目录树 + 右侧截图/步骤详情/评分。

章节拆分在 `gui/pages/result/`，本文件只保留组装 + episode/评分等状态逻辑。
"""
import json
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton,
)
from PySide6.QtCore import Qt

from gui.paths import data_dir as _data_root_dir
from gui.pages.result import tree_section, detail_section
from gui.styles import tokens as t


def _data_dir() -> str:
    return os.path.join(_data_root_dir(), "output")


class ResultPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_episode_path: str = ""
        self._current_episode_data: dict | None = None
        self._current_step_index: int = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("评测结果")
        title.setObjectName("sectionTitle")
        header.addWidget(title)

        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(
            f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; background: transparent;"
        )
        header.addWidget(self._summary_label)

        header.addStretch()

        btn_refresh = QPushButton("刷新")
        btn_refresh.setObjectName("ghostButton")
        btn_refresh.setFixedWidth(80)
        btn_refresh.clicked.connect(self.refresh_tree)
        header.addWidget(btn_refresh)

        root.addLayout(header)

        # ── Main splitter ──
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(tree_section.build_tree_panel(self))

        self._right_stack = detail_section.build_right_stack(self)
        splitter.addWidget(self._right_stack)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        root.addWidget(splitter, 1)

        self.refresh_tree()

    # ── Public API used by buttons / outside ──

    def refresh_tree(self) -> None:
        tree_section.refresh_tree(self)

    # ── Episode loading ──

    def _load_episode(self, ep_path: str) -> None:
        if ep_path == self._current_episode_path and self._current_episode_data:
            return

        self._current_episode_path = ep_path
        task_json = os.path.join(ep_path, "task.json")
        if not os.path.exists(task_json):
            self._info_text.setPlainText("task.json 未找到")
            self._query_banner.setVisible(False)
            return

        with open(task_json, "r", encoding="utf-8") as f:
            ep_data = json.load(f)

        self._current_episode_data = ep_data
        self._current_step_index = 0
        self._score_status.setText("")

        # Query banner
        query = ep_data.get("query", "")
        app = ep_data.get("app", "")
        if query:
            banner_parts = [f"<b>Query:</b> {query}"]
            if app:
                banner_parts.append(f"<b>App:</b> {app}")
            self._query_banner.setText("    ".join(banner_parts))
            self._query_banner.setVisible(True)
        else:
            self._query_banner.setVisible(False)

        # Episode summary
        steps = ep_data.get("data", [])
        phone = ep_data.get("phone", "")
        summary_parts = [f"{len(steps)} 步"]
        if app:
            summary_parts.append(app)
        if phone:
            summary_parts.append(f"设备: {phone}")
        self._episode_summary.setText(" | ".join(summary_parts))

        # Score combo
        score = ep_data.get("eval_score")
        if score is None:
            self._score_combo.setCurrentIndex(0)
        elif score == 0:
            self._score_combo.setCurrentIndex(1)
        elif score == 1:
            self._score_combo.setCurrentIndex(2)
        elif score == 0.5:
            self._score_combo.setCurrentIndex(3)
        else:
            self._score_combo.setCurrentIndex(0)

    # ── Scoring ──

    def _save_score(self) -> None:
        if not self._current_episode_path or not self._current_episode_data:
            self._score_status.setText("请先选择一个 Episode")
            self._score_status.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_XS}px; "
                f"border: none; background: transparent;"
            )
            return

        idx = self._score_combo.currentIndex()
        score_map = {0: None, 1: 0, 2: 1, 3: 0.5}
        score = score_map.get(idx)

        if score is None:
            self._score_status.setText("请选择有效评分")
            self._score_status.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_XS}px; "
                f"border: none; background: transparent;"
            )
            return

        task_json = os.path.join(self._current_episode_path, "task.json")
        if not os.path.exists(task_json):
            self._score_status.setText("task.json 不存在")
            self._score_status.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_XS}px; "
                f"border: none; background: transparent;"
            )
            return

        try:
            with open(task_json, "r", encoding="utf-8") as f:
                ep_data = json.load(f)

            ep_data["eval_score"] = score

            with open(task_json, "w", encoding="utf-8") as f:
                json.dump(ep_data, f, ensure_ascii=False, indent=2)

            self._current_episode_data = ep_data
            score_text = {0: "失败", 0.5: "部分完成", 1: "成功"}.get(score, str(score))
            self._score_status.setText(f"已保存: {score_text}")
            self._score_status.setStyleSheet(
                f"color: {t.SUCCESS}; font-size: {t.FONT_XS}px; "
                f"border: none; background: transparent;"
            )
        except Exception as e:
            self._score_status.setText(f"保存失败: {e}")
            self._score_status.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_XS}px; "
                f"border: none; background: transparent;"
            )
