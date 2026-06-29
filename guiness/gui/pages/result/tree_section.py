# -*- coding: utf-8 -*-
"""ResultPage 左侧目录树：日期 / App / Episode 三层。"""
import json
import os

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt


def build_tree_panel(page) -> QWidget:
    left = QWidget()
    lay = QVBoxLayout(left)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    page._tree = QTreeWidget()
    page._tree.setHeaderLabels(["评测数据"])
    page._tree.setMinimumWidth(280)
    page._tree.setAlternatingRowColors(True)
    page._tree.itemClicked.connect(lambda item, col: on_tree_item_clicked(page, item, col))
    lay.addWidget(page._tree)

    return left


def refresh_tree(page) -> None:
    from gui.pages.result_page import _data_dir
    page._tree.clear()
    data_dir = _data_dir()
    if not os.path.isdir(data_dir):
        page._summary_label.setText("无数据")
        return

    dates = sorted(
        [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))],
        reverse=True,
    )

    total_episodes = 0
    scored_count = 0

    for date_name in dates:
        date_path = os.path.join(data_dir, date_name)
        date_item = QTreeWidgetItem([date_name])
        date_item.setData(0, Qt.UserRole, {"type": "date", "path": date_path})

        apps = sorted([
            a for a in os.listdir(date_path)
            if os.path.isdir(os.path.join(date_path, a))
        ])

        date_ep_count = 0
        for app_name in apps:
            app_path = os.path.join(date_path, app_name)
            app_item = QTreeWidgetItem([app_name])
            app_item.setData(0, Qt.UserRole, {"type": "app", "path": app_path})

            episodes = sorted([
                e for e in os.listdir(app_path)
                if os.path.isdir(os.path.join(app_path, e))
            ])

            for ep_name in episodes:
                ep_path = os.path.join(app_path, ep_name)
                ep_item = QTreeWidgetItem([ep_name])
                ep_item.setData(0, Qt.UserRole, {"type": "episode", "path": ep_path})
                total_episodes += 1
                date_ep_count += 1

                task_json = os.path.join(ep_path, "task.json")
                if os.path.exists(task_json):
                    try:
                        with open(task_json, "r", encoding="utf-8") as f:
                            ep_data = json.load(f)
                        query = ep_data.get("query", "")
                        score = ep_data.get("eval_score")
                        steps = ep_data.get("data", [])

                        parts = []
                        if score is not None:
                            scored_count += 1
                            badge = {0: "[X]", 0.5: "[~]", 1: "[O]"}.get(score, "")
                            parts.append(badge)

                        if query:
                            q_display = query if len(query) <= 30 else query[:27] + "..."
                            parts.append(q_display)
                        else:
                            parts.append(ep_name)

                        parts.append(f"({len(steps)}步)")
                        ep_item.setText(0, " ".join(parts))
                    except (json.JSONDecodeError, KeyError):
                        pass

                app_item.addChild(ep_item)

            app_item.setText(0, f"{app_name} ({len(episodes)})")
            date_item.addChild(app_item)

        date_item.setText(0, f"{date_name} ({date_ep_count})")
        page._tree.addTopLevelItem(date_item)

    if total_episodes > 0:
        page._summary_label.setText(
            f"{len(dates)} 个日期，{total_episodes} 条评测，{scored_count} 条已评分"
        )
    else:
        page._summary_label.setText("无数据")


def on_tree_item_clicked(page, item: QTreeWidgetItem, _column: int) -> None:
    data = item.data(0, Qt.UserRole)
    if not data:
        return
    if data.get("type") != "episode":
        return
    ep_path = data.get("path", "")
    page._load_episode(ep_path)
    from gui.pages.result import detail_section
    detail_section.go_to_step(page, 0)
    page._right_stack.setCurrentIndex(1)
