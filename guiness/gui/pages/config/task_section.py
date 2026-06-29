# -*- coding: utf-8 -*-
"""ConfigPage 的「评测任务」章节：可编辑表格 + JSONL 导入。"""
import json

from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
)

from gui.paths import project_root
from gui.styles import tokens as t


def build_task_section(page) -> QGroupBox:
    grp = QGroupBox("评测任务")
    lay = QVBoxLayout()
    lay.setSpacing(10)

    # Top bar
    bar = QHBoxLayout()
    info = QLabel("每行一条任务，填写查询指令和目标 App")
    info.setObjectName("subtitle")
    bar.addWidget(info)
    bar.addStretch()

    btn_import = QPushButton("导入 JSONL")
    btn_import.setObjectName("ghostButton")
    btn_import.setFixedWidth(110)
    btn_import.clicked.connect(lambda: import_jsonl(page))
    bar.addWidget(btn_import)

    btn_add = QPushButton("+ 添加任务")
    btn_add.setFixedWidth(110)
    btn_add.clicked.connect(lambda: add_task_row(page))
    bar.addWidget(btn_add)

    lay.addLayout(bar)

    # Table
    page._task_table = QTableWidget(0, 3)
    page._task_table.setHorizontalHeaderLabels(["查询指令 (Query)", "App", ""])
    page._task_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    page._task_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
    page._task_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
    page._task_table.setColumnWidth(1, 160)
    page._task_table.setColumnWidth(2, 60)
    page._task_table.setAlternatingRowColors(True)
    page._task_table.verticalHeader().setVisible(False)
    page._task_table.verticalHeader().setDefaultSectionSize(38)
    page._task_table.setMinimumHeight(160)
    page._task_table.setStyleSheet(f"""
        QTableWidget::item:selected {{
            background: {t.ACCENT_SOFT};
            color: {t.NEUTRAL_900};
        }}
        QTableWidget::item:focus {{
            border: 1px solid {t.ACCENT};
            background: {t.ACCENT_SOFT};
        }}
    """)
    lay.addWidget(page._task_table)

    page._task_hint = QLabel("点击「+ 添加任务」或「导入 JSONL」添加评测任务")
    page._task_hint.setStyleSheet(
        f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; "
        f"padding: 4px 0; background: transparent;"
    )
    page._task_hint.setVisible(True)
    lay.addWidget(page._task_hint)

    grp.setLayout(lay)
    return grp


def add_task_row(page, query: str = "", app: str = "") -> None:
    row = page._task_table.rowCount()
    page._task_table.insertRow(row)
    page._task_table.setItem(row, 0, QTableWidgetItem(query))
    page._task_table.setItem(row, 1, QTableWidgetItem(app))

    btn_del = QPushButton("删除")
    btn_del.setObjectName("dangerButton")
    btn_del.setFixedSize(52, 28)
    btn_del.clicked.connect(lambda _=None, b=btn_del: _remove_row(page, b))
    page._task_table.setCellWidget(row, 2, btn_del)
    update_task_hint(page)


def _remove_row(page, btn) -> None:
    for r in range(page._task_table.rowCount()):
        if page._task_table.cellWidget(r, 2) is btn:
            page._task_table.removeRow(r)
            update_task_hint(page)
            return


def update_task_hint(page) -> None:
    page._task_hint.setVisible(page._task_table.rowCount() == 0)


def import_jsonl(page) -> None:
    path, _ = QFileDialog.getOpenFileName(
        page, "导入任务文件", project_root(),
        "JSONL Files (*.jsonl);;JSON Files (*.json);;All Files (*)",
    )
    if not path:
        return
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                add_task_row(page, obj.get("query", ""), obj.get("app", ""))
                count += 1
            except json.JSONDecodeError:
                pass
    if count:
        page._save_status.setText(f"已导入 {count} 条任务")


def get_tasks(page) -> list[dict]:
    tasks: list[dict] = []
    for row in range(page._task_table.rowCount()):
        q_item = page._task_table.item(row, 0)
        a_item = page._task_table.item(row, 1)
        query = q_item.text().strip() if q_item else ""
        app = a_item.text().strip() if a_item else ""
        if query:
            tasks.append({
                "episode_id": f"task_{row + 1:03d}",
                "query": query,
                "app": app,
            })
    return tasks
