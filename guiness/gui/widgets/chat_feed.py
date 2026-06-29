# -*- coding: utf-8 -*-
"""滚动聊天流：动态添加消息控件"""
from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, Signal, QVariantAnimation
from PySide6.QtGui import QColor

from gui.widgets.message_bubble import ConfigSummary, UserMessageBubble, SystemMessage
from gui.widgets.step_card import StepCard
from gui.styles import tokens as t


class _DotWidget(QLabel):
    """单个可动画的圆点。"""

    def __init__(self, size: int = 8, color: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._opacity = 0.3
        self._color = color or t.NEUTRAL_500
        self._size = size
        self._apply_style()

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, val: float) -> None:
        self._opacity = val
        self._apply_style()

    dot_opacity = Property(float, _get_opacity, _set_opacity)

    def _apply_style(self) -> None:
        r = self._size // 2
        self.setStyleSheet(
            f"background: {self._color}; border-radius: {r}px; "
            f"opacity: {self._opacity};"
        )
        # QSS opacity 不一定生效，用透明度颜色兜底
        c = QColor(self._color)
        c.setAlphaF(self._opacity)
        self.setStyleSheet(
            f"background: {c.name(QColor.HexArgb)}; border-radius: {r}px;"
        )


class ThinkingIndicator(QFrame):
    """骨架屏步骤卡片：呼吸渐变动画。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("skeletonCard")
        self.setStyleSheet(f"""
            QFrame#skeletonCard {{
                background: {t.NEUTRAL_0};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_MD}px;
                padding: 16px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(18)

        # 左侧截图骨架
        self._pic_skeleton = QWidget()
        self._pic_skeleton.setFixedSize(300, 320)
        self._pic_skeleton.setStyleSheet(f"background: {t.NEUTRAL_100}; border-radius: {t.RADIUS_SM}px;")
        layout.addWidget(self._pic_skeleton)

        # 右侧文本骨架
        right = QVBoxLayout()
        right.setSpacing(14)
        right.setAlignment(Qt.AlignTop)

        # 模拟标题、动作、思考过程的多行骨架
        self._t1 = QLabel("正在初始化...")
        self._t1.setObjectName("skeletonTitle")
        self._t1.setStyleSheet(f"""
            QLabel#skeletonTitle {{
                color: {t.NEUTRAL_700};
                font-size: {t.FONT_XS}px;
                font-weight: {t.WEIGHT_SEMI};
                background: {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
                padding: 4px 8px;
            }}
        """)
        self._t1.setFixedWidth(180)
        right.addWidget(self._t1)

        self._t2 = QWidget()
        self._t2.setFixedHeight(18)
        self._t2.setStyleSheet(f"background: {t.NEUTRAL_100}; border-radius: {t.RADIUS_SM}px;")
        right.addWidget(self._t2)

        self._t3 = QWidget()
        self._t3.setFixedHeight(60)
        self._t3.setStyleSheet(f"background: {t.NEUTRAL_100}; border-radius: {t.RADIUS_SM}px;")
        right.addWidget(self._t3)

        layout.addLayout(right, stretch=1)

        # 呼吸动画 (breathing animation)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(1200)
        self._anim.setStartValue(0.2)
        self._anim.setKeyValueAt(0.5, 0.6)
        self._anim.setEndValue(0.2)
        self._anim.setLoopCount(-1)

        def set_opacity(val):
            # 将动画数值应用为子部件的背景透明度
            style = f"background: rgba(229, 231, 235, {val}); border-radius: {t.RADIUS_SM}px;"
            self._pic_skeleton.setStyleSheet(style)
            self._t2.setStyleSheet(style)
            self._t3.setStyleSheet(style)
            
        self._anim.valueChanged.connect(set_opacity)
        self._anim.start()

    def set_text(self, text: str) -> None:
        self._t1.setText(text)

    def stop(self) -> None:
        if hasattr(self, "_anim") and self._anim is not None:
            try:
                self._anim.stop()
            except Exception:
                pass


class ChatFeed(QWidget):
    """可滚动的聊天消息流，支持左右双栏（镜像 | 文本）布局。"""
    step_approved = Signal(str)
    step_stopped = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {t.NEUTRAL_50};")

        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._outer_layout.setSpacing(0)

        # ── 顶部行：ConfigSummary ──
        self._top_row = QWidget()
        self._top_row.setStyleSheet(f"background: {t.NEUTRAL_50};")
        self._top_layout = QVBoxLayout(self._top_row)
        self._top_layout.setContentsMargins(32, 28, 32, 0)
        self._top_layout.setSpacing(20)
        self._outer_layout.addWidget(self._top_row)

        # ── 分栏区：left=镜像 | right=聊天流 ──
        self._split_row = QWidget()
        self._split_hbox = QHBoxLayout(self._split_row)
        self._split_hbox.setContentsMargins(0, 16, 0, 0)
        self._split_hbox.setSpacing(20)

        # 左栏：实时镜像（mirror 模式可见），宽度由内容决定
        self._left_pane = QWidget()
        self._left_pane_layout = QVBoxLayout(self._left_pane)
        self._left_pane_layout.setContentsMargins(32, 0, 0, 28)
        self._left_pane_layout.setSpacing(0)
        self._left_pane.setVisible(False)
        self._split_hbox.addWidget(self._left_pane, stretch=0)

        # 右栏：可滚动聊天内容
        self._right_scroll = QScrollArea()
        self._right_scroll.setWidgetResizable(True)
        self._right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._right_scroll.setObjectName("chatFeed")
        self._right_scroll.setStyleSheet(f"""
            QScrollArea#chatFeed {{ background: {t.NEUTRAL_50}; border: none; }}
        """)

        self._container = QWidget()
        self._container.setStyleSheet(f"background: {t.NEUTRAL_50};")
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignTop)
        self._layout.setContentsMargins(16, 0, 16, 28)
        self._layout.setSpacing(20)
        self._right_scroll.setWidget(self._container)

        self._split_hbox.addWidget(self._right_scroll, stretch=1)
        self._outer_layout.addWidget(self._split_row, stretch=1)

        self._thinking: ThinkingIndicator | None = None
        self._display_mode: str = "image"
        self._mirror_viewport = None

    def add_config_summary(self, conv) -> None:
        self._top_layout.addWidget(ConfigSummary(conv))

    def add_user_message(self, query: str, app: str = "") -> None:
        self._top_layout.addWidget(UserMessageBubble(query, app))

    def add_step_card(self, step_data: dict) -> None:
        self._remove_thinking()
        step_data = {**step_data, "_display_mode": self._display_mode}

        step_num = step_data.get("step", 0)
        existing_card = None
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if isinstance(w, StepCard) and getattr(w, "_step_num", None) == step_num:
                existing_card = w
                break

        if existing_card is not None:
            new_card = StepCard(step_data)
            new_card.approved.connect(self.step_approved.emit)
            new_card.stopped.connect(self.step_stopped.emit)

            idx = self._layout.indexOf(existing_card)
            self._layout.removeWidget(existing_card)
            existing_card.deleteLater()
            self._layout.insertWidget(idx, new_card)
        else:
            for i in range(self._layout.count()):
                w = self._layout.itemAt(i).widget()
                if isinstance(w, StepCard):
                    w.set_expanded(False)
            card = StepCard(step_data)
            card.approved.connect(self.step_approved.emit)
            card.stopped.connect(self.step_stopped.emit)
            self._layout.addWidget(card)

        self._scroll_to_bottom()

    def add_system_message(self, text: str, msg_type: str = "info") -> None:
        self._remove_thinking()
        self._layout.addWidget(SystemMessage(text, msg_type))
        self._scroll_to_bottom()

    def show_thinking(self) -> None:
        """外部调用：显示思考指示器。"""
        self._show_thinking()
        self._scroll_to_bottom()

    def hide_thinking(self) -> None:
        """外部调用：隐藏思考指示器。"""
        self._remove_thinking()

    def update_thinking_text(self, text: str) -> None:
        """更新思考指示器的文字（显示初始化进度）。"""
        if self._thinking is not None:
            self._thinking.set_text(text)

    def load_conversation(self, conv) -> None:
        self.clear()
        self.add_config_summary(conv)

        # 多轮历史：按 turns 切分 steps，每轮先插入 user bubble，再铺该轮的 step 卡
        turns = list(getattr(conv, "turns", []) or [])
        if not turns:
            # 兜底：旧数据无 turns 时按单轮展开
            turns = [{
                "query": conv.query, "app": conv.app,
                "step_count": len(conv.steps),
            }]

        last_step_idx = len(conv.steps) - 1
        cursor = 0
        for ti, turn in enumerate(turns):
            bubble = UserMessageBubble(turn.get("query", ""), turn.get("app", ""))
            if ti == 0:
                self._top_layout.addWidget(bubble)
            else:
                self._layout.addWidget(bubble)
            n = int(turn.get("step_count", 0))
            for i in range(n):
                idx = cursor + i
                if idx >= len(conv.steps):
                    break
                card = StepCard(conv.steps[idx])
                card.approved.connect(self.step_approved.emit)
                card.stopped.connect(self.step_stopped.emit)
                if idx != last_step_idx:
                    card.set_expanded(False)
                self._layout.addWidget(card)
            cursor += n

        # 如果 steps 数比 turns 累计多（数据错位兜底），把尾巴的步骤也渲染出来
        while cursor < len(conv.steps):
            card = StepCard(conv.steps[cursor])
            card.approved.connect(self.step_approved.emit)
            card.stopped.connect(self.step_stopped.emit)
            if cursor != last_step_idx:
                card.set_expanded(False)
            self._layout.addWidget(card)
            cursor += 1

        if conv.status == "done":
            self.add_system_message(f"已完成，共 {len(conv.steps)} 步", "success")
        elif conv.status == "error":
            self.add_system_message(f"错误: {conv.error}", "error")
        elif conv.status == "stopped":
            self.add_system_message("已停止", "warning")
        elif conv.status == "running":
            self._show_thinking()
        self._scroll_to_bottom()

    def clear(self) -> None:
        self._remove_thinking()
        # 清空顶部行（ConfigSummary）
        i = self._top_layout.count() - 1
        while i >= 0:
            item = self._top_layout.itemAt(i)
            w = item.widget() if item else None
            if w:
                self._top_layout.takeAt(i)
                w.deleteLater()
            i -= 1
        # 清空右栏聊天内容
        i = self._layout.count() - 1
        while i >= 0:
            item = self._layout.itemAt(i)
            w = item.widget() if item else None
            if w and w is not self._mirror_viewport:
                self._layout.takeAt(i)
                w.deleteLater()
            i -= 1

    def _show_thinking(self) -> None:
        if self._thinking is not None:
            return
        self._thinking = ThinkingIndicator()
        self._layout.addWidget(self._thinking)

    def _remove_thinking(self) -> None:
        if self._thinking is not None:
            self._thinking.stop()
            self._layout.removeWidget(self._thinking)
            self._thinking.deleteLater()
            self._thinking = None

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(50, self._do_scroll)

    def _do_scroll(self) -> None:
        sb = self._right_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── 显示模式 ──

    def set_display_mode(self, mode: str) -> None:
        self._display_mode = mode

    def show_mirror_viewport(self, frame_iter_factory=None) -> None:
        """在左栏显示实时镜像视图。"""
        if self._mirror_viewport is None:
            from gui.widgets.live_mirror_viewport import LiveMirrorViewport
            self._mirror_viewport = LiveMirrorViewport(parent=self._left_pane)
            self._left_pane_layout.addWidget(self._mirror_viewport, stretch=1)
        self._left_pane.setVisible(True)
        if frame_iter_factory is not None:
            self._mirror_viewport.start(frame_iter_factory)

    def hide_mirror_viewport(self) -> None:
        """停止并隐藏左栏实时镜像视图。"""
        if self._mirror_viewport is None:
            self._left_pane.setVisible(False)
            return
        self._mirror_viewport.stop()
        self._left_pane_layout.removeWidget(self._mirror_viewport)
        self._mirror_viewport.deleteLater()
        self._mirror_viewport = None
        self._left_pane.setVisible(False)
