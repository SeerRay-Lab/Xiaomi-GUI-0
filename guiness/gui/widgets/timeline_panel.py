# -*- coding: utf-8 -*-
"""时间轴面板：动态展示运行中的任务步骤"""
from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
)
from PySide6.QtCore import Qt
from gui.styles import tokens as t


class TimelineNode(QWidget):
    """时间轴的单个状态节点。"""

    def __init__(
        self,
        step_num: int,
        action_name: str,
        thought: str,
        status: str = "completed",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self._step_num = step_num

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        # 左侧圆点
        dot_col = QWidget()
        dot_col.setFixedWidth(16)
        dot_col.setStyleSheet("background: transparent;")
        col_lay = QVBoxLayout(dot_col)
        col_lay.setContentsMargins(0, 4, 0, 0)
        col_lay.setSpacing(0)

        self.dot = QWidget()
        self.dot.setFixedSize(12, 12)
        
        col_lay.addWidget(self.dot, alignment=Qt.AlignTop | Qt.AlignHCenter)
        layout.addWidget(dot_col)

        # 右侧步骤文字信息
        text_box = QWidget()
        text_box.setStyleSheet("background: transparent;")
        text_lay = QVBoxLayout(text_box)
        text_lay.setContentsMargins(0, 0, 0, 0)
        text_lay.setSpacing(2)

        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setMinimumWidth(0)
        self.desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        text_lay.addWidget(self.title)
        text_lay.addWidget(self.desc)
        text_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_box.setMinimumWidth(0)
        layout.addWidget(text_box, stretch=1)

        self.update_node(action_name, thought, status)

    def update_node(self, action_name: str, thought: str, status: str) -> None:
        is_pending = status == "pending"
        
        # 更新颜色
        if status == "completed":
            self.dot.setStyleSheet(f"background: {t.SUCCESS}; border-radius: 6px;")
        elif status == "waiting_approval":
            self.dot.setStyleSheet(f"background: {t.WARNING if hasattr(t, 'WARNING') else '#F59E0B'}; border-radius: 6px;")
        elif status == "running":
            self.dot.setStyleSheet(f"background: {t.ACCENT}; border-radius: 6px;")
        else:
            self.dot.setStyleSheet(f"background: {t.NEUTRAL_300}; border-radius: 6px;")

        self.title.setText(f"第 {self._step_num} 步: {action_name}")
        self.title.setStyleSheet(f"""
            color: {t.NEUTRAL_900 if not is_pending else t.NEUTRAL_400};
            font-size: {t.FONT_SM}px;
            font-weight: {t.WEIGHT_SEMI};
            background: transparent;
        """)

        self.desc.setText(thought)
        self.desc.setStyleSheet(f"""
            color: {t.NEUTRAL_500 if not is_pending else t.NEUTRAL_400};
            font-size: {t.FONT_XS}px;
            background: transparent;
        """)


class TimelinePanel(QScrollArea):
    """可视化时间轴/工作流面板。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f"""
            QScrollArea {{
                background: {t.NEUTRAL_50};
                border: none;
                border-left: 1px solid {t.NEUTRAL_200};
            }}
        """)

        self._container = QWidget()
        self._container.setStyleSheet(f"background: {t.NEUTRAL_50};")
        self._container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(18, 20, 18, 20)
        self._layout.setSpacing(16)

        # 头部标题
        header = QLabel("执行工作流")
        header.setStyleSheet(f"""
            color: {t.NEUTRAL_900};
            font-size: {t.FONT_MD}px;
            font-weight: {t.WEIGHT_SEMI};
            background: transparent;
            padding-bottom: 4px;
        """)
        self._layout.addWidget(header)

        self.setWidget(self._container)
        
        self._placeholder = None
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        if self._placeholder is not None:
            return
        self._placeholder = QWidget()
        self._placeholder.setStyleSheet("background: transparent;")
        pl_lay = QVBoxLayout(self._placeholder)
        pl_lay.setAlignment(Qt.AlignCenter)
        pl_lay.setContentsMargins(20, 80, 20, 80)
        pl_lay.setSpacing(12)

        icon = QLabel("📋")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 36px; background: transparent;")

        title = QLabel("等待生成执行工作流")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"""
            color: {t.NEUTRAL_500};
            font-size: {t.FONT_SM}px;
            font-weight: {t.WEIGHT_SEMI};
            background: transparent;
        """)

        desc = QLabel("任务启动后将在此处动态展示\n操作步骤与思考时间轴")
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"""
            color: {t.NEUTRAL_400};
            font-size: {t.FONT_XS}px;
            background: transparent;
        """)

        pl_lay.addWidget(icon)
        pl_lay.addWidget(title)
        pl_lay.addWidget(desc)
        
        self._layout.addWidget(self._placeholder)

    def _hide_placeholder(self) -> None:
        if self._placeholder is not None:
            self._layout.removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None

    def clear(self) -> None:
        self._hide_placeholder()
        while self._layout.count() > 1:
            item = self._layout.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()
        self._show_placeholder()

    def add_step(self, step_data: dict) -> None:
        self._hide_placeholder()
        
        # 获取动作语义
        action = step_data.get("action")
        if not isinstance(action, dict):
            action = {}
        func = action.get("func", "Wait")
        action_text = action.get("action") or func
        thought = step_data.get("thought", "")
        step = step_data.get("step", 0)
        status = step_data.get("status", "done")

        node_status = "completed"
        if status == "waiting_approval":
            node_status = "waiting_approval"
        elif status == "running":
            node_status = "running"

        # 检查是否已存在此步骤的节点
        existing_node = None
        for i in range(1, self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if isinstance(w, TimelineNode) and getattr(w, "_step_num", None) == step:
                existing_node = w
                break

        if existing_node is not None:
            existing_node.update_node(action_text, thought, node_status)
        else:
            # 将先前的节点设为 completed，然后再添加最新节点
            for i in range(1, self._layout.count()):
                node = self._layout.itemAt(i).widget()
                if isinstance(node, TimelineNode):
                    node.dot.setStyleSheet(f"background: {t.SUCCESS}; border-radius: 6px;")

            new_node = TimelineNode(
                step_num=step,
                action_name=action_text,
                thought=thought,
                status=node_status,
            )
            self._layout.addWidget(new_node)
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def load_conversation(self, conv) -> None:
        self.clear()
        steps = list(getattr(conv, "steps", []) or [])
        for s in steps:
            self.add_step(s)
