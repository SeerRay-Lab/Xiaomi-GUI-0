# -*- coding: utf-8 -*-
"""步骤卡片：左侧截图 + 右侧动作/思考/原始回复（水平布局）"""
import json

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
    QWidget, QSizePolicy, QPushButton,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Signal

from gui.widgets.screenshot_viewer import ScreenshotViewer
from gui.styles import tokens as t


# 动作徽章按"语义"归类到 4 档；而不是每个动作一种颜色。
_BADGE_PRIMARY = {"Click", "Tap", "LongPress", "Type", "Search", "Open", "Back", "Home"}
_BADGE_ACCENT  = {"Swipe", "Wait"}
_BADGE_SUCCESS = {"Complete", "End", "Speak"}
_BADGE_DANGER  = {"Fail"}


def _badge_colors(func: str) -> tuple[str, str]:
    """返回 (fg, bg)：徽章前景+淡底。纯中性底色 + 单色文字，扁平。"""
    if func in _BADGE_SUCCESS:
        return t.SUCCESS, t.SUCCESS_SOFT
    if func in _BADGE_DANGER:
        return t.DANGER, t.DANGER_SOFT
    if func in _BADGE_ACCENT:
        return t.ACCENT, t.ACCENT_SOFT
    # primary 和未分类：深灰文字 + 浅灰底，保持与其它徽章同一"浅底+文字色"风格
    return t.NEUTRAL_900, t.NEUTRAL_100


class StepCard(QFrame):
    """单步结果卡片：左侧截图，右侧信息。

    整卡可折叠：点击 header 的箭头 / 标题行即收起/展开下方 body。
    ChatFeed 在追加新 step 时会把上一张卡折叠，避免滚动瀑布。
    """
    approved = Signal(str)
    stopped = Signal(str)

    def __init__(self, step_data: dict, parent=None) -> None:
        super().__init__(parent)
        self._step_num = step_data.get("step", 0)
        # plan 是标准字段；兼容旧数据中 action 字段。统一归一化为 action 供渲染使用。
        if not isinstance(step_data.get("action"), dict):
            plan = step_data.get("plan")
            step_data = dict(step_data)
            step_data["action"] = plan if isinstance(plan, dict) else {}
        self.setObjectName("stepCard")
        self.setStyleSheet(f"""
            QFrame#stepCard {{
                background: {t.NEUTRAL_0};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_MD}px;
                padding: 16px;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        self._expanded = True
        self._header = self._build_header(step_data)
        outer.addWidget(self._header)

        self._body = QWidget()
        self._body.setStyleSheet("background: transparent;")
        body = QHBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(18)

        recorded_path = step_data.get("screenshot_path", "")
        action = step_data.get("action", {})
        # 显示时按 conv_id 在本机 output 索引里重新解析路径——避免 conversations.json
        # 里写死的别人电脑绝对路径让本机渲染失败。EpisodeWorker 实时写入的 step
        # 也走这条路径，因为 _EPISODE_INDEX 在启动时已包含本机所有 episode。
        from gui.output_sync import resolve_screenshot_path
        screenshot_path = resolve_screenshot_path(
            step_data.get("conv_id", ""), recorded_path,
        )
        if step_data.get("_display_mode") != "mirror" and (screenshot_path or recorded_path):
            viewer = ScreenshotViewer()
            viewer.setMinimumWidth(300)
            viewer.setMaximumWidth(420)
            viewer.setMinimumHeight(320)
            viewer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            viewer.load_image(screenshot_path or recorded_path, action)
            body.addWidget(viewer)

        # Right panel
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)
        right_panel.setAlignment(Qt.AlignTop)

        action_detail = self._format_action_detail(action)
        if action_detail:
            detail_label = QLabel(action_detail)
            detail_label.setWordWrap(True)
            detail_label.setStyleSheet(
                f"color: {t.NEUTRAL_700}; font-size: {t.FONT_MD}px; "
                f"padding: 2px 0; background: transparent;"
            )
            right_panel.addWidget(detail_label)

        if step_data.get("exec_success") is False:
            fail_label = QLabel("执行失败")
            fail_label.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FONT_SM}px; font-weight: {t.WEIGHT_SEMI}; "
                f"background: {t.DANGER_SOFT}; border-radius: {t.RADIUS_SM}px; padding: 4px 10px;"
            )
            right_panel.addWidget(fail_label)

        # 如果是等待确认状态，渲染高质感的确认/中止按钮面板
        status = step_data.get("status", "")
        if status == "waiting_approval":
            approve_panel = QWidget()
            approve_panel.setStyleSheet("background: transparent;")
            h_layout = QHBoxLayout(approve_panel)
            h_layout.setContentsMargins(0, 4, 0, 4)
            h_layout.setSpacing(10)

            btn_approve = QPushButton("确认执行")
            btn_approve.setCursor(Qt.PointingHandCursor)
            btn_approve.setStyleSheet(f"""
                QPushButton {{
                    background: {t.ACCENT};
                    color: {t.NEUTRAL_0};
                    border: none;
                    border-radius: {t.RADIUS_SM}px;
                    padding: 8px 16px;
                    font-weight: {t.WEIGHT_SEMI};
                    font-size: {t.FONT_SM}px;
                }}
                QPushButton:hover {{ background: "#1D4ED8"; }}
                QPushButton:disabled {{ background: {t.NEUTRAL_300}; color: {t.NEUTRAL_500}; }}
            """)

            btn_stop = QPushButton("中止任务")
            btn_stop.setCursor(Qt.PointingHandCursor)
            btn_stop.setStyleSheet(f"""
                QPushButton {{
                    background: {t.NEUTRAL_0};
                    color: {t.DANGER};
                    border: 1px solid {t.NEUTRAL_200};
                    border-radius: {t.RADIUS_SM}px;
                    padding: 8px 16px;
                    font-weight: {t.WEIGHT_SEMI};
                    font-size: {t.FONT_SM}px;
                }}
                QPushButton:hover {{ background: {t.DANGER_SOFT}; border-color: {t.DANGER}; }}
                QPushButton:disabled {{ background: {t.NEUTRAL_0}; color: {t.NEUTRAL_400}; border-color: {t.NEUTRAL_200}; }}
            """)

            conv_id = step_data.get("conv_id", "")
            def on_approve():
                btn_approve.setEnabled(False)
                btn_approve.setText("正在执行...")
                btn_stop.setEnabled(False)
                self.approved.emit(conv_id)

            def on_stop():
                btn_approve.setEnabled(False)
                btn_stop.setEnabled(False)
                self.stopped.emit(conv_id)

            btn_approve.clicked.connect(on_approve)
            btn_stop.clicked.connect(on_stop)

            h_layout.addWidget(btn_approve)
            h_layout.addWidget(btn_stop)
            h_layout.addStretch()
            right_panel.addWidget(approve_panel)

        thought = step_data.get("thought", "")
        if thought:
            right_panel.addWidget(self._build_collapsible("思考过程", thought, expanded=True))

        action_json = self._format_action_json(action)
        if action_json:
            right_panel.addWidget(self._build_collapsible("动作", action_json, expanded=True))

        raw_output = step_data.get("raw_model_output", "")
        if raw_output:
            right_panel.addWidget(
                self._build_collapsible("模型原始回复", raw_output, expanded=False)
            )

        right_panel.addStretch()
        body.addLayout(right_panel, stretch=1)
        outer.addWidget(self._body)

    # ── 折叠/展开 ──

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self._chevron.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

        # Smooth height expand/collapse animation using maximumHeight
        self._body.setVisible(True)
        # Calculate start and target height
        target_h = self._body.sizeHint().height() if expanded else 0
        start_h = 0 if expanded else self._body.height()

        if hasattr(self, "_anim") and self._anim is not None:
            try:
                self._anim.stop()
            except Exception:
                pass

        self._anim = QPropertyAnimation(self._body, b"maximumHeight")
        self._anim.setDuration(250)
        self._anim.setStartValue(start_h)
        self._anim.setEndValue(target_h)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)

        if not expanded:
            def on_finished():
                if not self._expanded:
                    self._body.setVisible(False)
            self._anim.finished.connect(on_finished)
        else:
            def on_finished_expand():
                if self._expanded:
                    self._body.setMaximumHeight(16777215)  # Restores maximum height
            self._anim.finished.connect(on_finished_expand)

        self._anim.start()

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle(self, checked: bool = False) -> None:
        self.set_expanded(not self._expanded)

    def set_status(self, status: str) -> None:
        """外部调用：更新 header 上的状态徽章（running/done/error）。"""
        self._apply_status(status)

    def mousePressEvent(self, event) -> None:
        # 点击 header 区域（收起状态下整个 header 都可点）即切换
        if not self._expanded and self._header.geometry().contains(event.pos()):
            self.toggle()
            return
        super().mousePressEvent(event)

    def _build_header(self, step_data: dict) -> QWidget:
        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        widget.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(8)

        # 折叠/展开箭头
        self._chevron = QToolButton()
        self._chevron.setArrowType(Qt.DownArrow)
        self._chevron.setAutoRaise(True)
        self._chevron.setFixedSize(22, 22)
        self._chevron.setCursor(Qt.PointingHandCursor)
        self._chevron.setStyleSheet("""
            QToolButton { background: transparent; border: none; padding: 0; }
        """)
        self._chevron.clicked.connect(self.toggle)
        layout.addWidget(self._chevron)

        step = step_data.get("step", 0)
        max_steps = step_data.get("max_steps", 100)
        step_label = QLabel(f"Step {step}/{max_steps}")
        step_label.setStyleSheet(f"""
            QLabel {{
                background: {t.NEUTRAL_100}; color: {t.NEUTRAL_700};
                font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI};
                padding: 4px 10px; border-radius: {t.RADIUS_SM}px;
            }}
        """)
        step_label.setFixedHeight(24)
        layout.addWidget(step_label)

        action = step_data.get("action", {})
        func = action.get("func", "")
        action_text = action.get("action") or func
        if action_text:
            fg, bg = _badge_colors(func)
            badge = QLabel(action_text)
            badge.setStyleSheet(f"""
                QLabel {{
                    background: {bg}; color: {fg};
                    font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI};
                    padding: 4px 10px; border-radius: {t.RADIUS_SM}px;
                }}
            """)
            badge.setFixedHeight(24)
            layout.addWidget(badge)

        fg_app = step_data.get("foreground_app", "")
        if fg_app:
            app_label = QLabel(fg_app)
            app_label.setStyleSheet(
                f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; background: transparent;"
            )
            layout.addWidget(app_label)

        layout.addStretch()

        # 状态徽章：操作中 / 等待确认 / 完成 / 失败
        self._status_label = QLabel()
        self._status_label.setFixedHeight(24)
        layout.addWidget(self._status_label)
        initial_status = step_data.get("status", "done")
        if step_data.get("exec_success") is False:
            initial_status = "error"
        self._apply_status(initial_status)

        infer_time = step_data.get("infer_time", 0)
        if infer_time:
            time_label = QLabel(f"{infer_time}s")
            time_label.setStyleSheet(f"""
                QLabel {{
                    background: {t.NEUTRAL_100}; color: {t.NEUTRAL_500};
                    font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI};
                    padding: 4px 10px; border-radius: {t.RADIUS_SM}px;
                }}
            """)
            time_label.setFixedHeight(24)
            layout.addWidget(time_label)

        return widget

    def _apply_status(self, status: str) -> None:
        """status: running / done / error / waiting_approval —— 更新右上角小圆点 + 文案。"""
        mapping = {
            "running": ("● 操作中", t.ACCENT,  t.ACCENT_SOFT),
            "done":    ("● 完成",   t.SUCCESS, t.SUCCESS_SOFT),
            "error":   ("● 失败",   t.DANGER,  t.DANGER_SOFT),
            "waiting_approval": ("● 等待确认", t.ACCENT, t.ACCENT_SOFT),
        }
        text, fg, bg = mapping.get(status, mapping["done"])
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"""
            QLabel {{
                background: {bg}; color: {fg};
                font-size: {t.FONT_XS}px; font-weight: {t.WEIGHT_SEMI};
                padding: 4px 10px; border-radius: {t.RADIUS_SM}px;
            }}
        """)

    def _build_collapsible(
        self, title: str, text: str, *, expanded: bool = True,
    ) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vlayout = QVBoxLayout(container)
        vlayout.setContentsMargins(0, 4, 0, 0)
        vlayout.setSpacing(6)

        toggle = QToolButton()
        toggle.setText(f"  {title}")
        toggle.setCheckable(True)
        toggle.setChecked(expanded)
        toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        toggle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toggle.setFixedHeight(28)
        toggle.setStyleSheet(f"""
            QToolButton {{
                background: transparent; border: none;
                color: {t.NEUTRAL_700}; font-size: {t.FONT_SM}px; font-weight: {t.WEIGHT_SEMI};
                text-align: left; padding-left: 2px;
            }}
            QToolButton:hover {{ color: {t.NEUTRAL_900}; }}
        """)

        content = QLabel(text)
        content.setWordWrap(True)
        content.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        content.setStyleSheet(f"""
            QLabel {{
                color: {t.NEUTRAL_700}; font-size: {t.FONT_SM}px;
                padding: 10px 12px;
                background: {t.NEUTRAL_50};
                border: 1px solid {t.NEUTRAL_200};
                border-radius: {t.RADIUS_SM}px;
            }}
        """)
        content.setVisible(expanded)

        def _toggle(checked: bool) -> None:
            toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
            content.setVisible(checked)

        toggle.clicked.connect(_toggle)

        vlayout.addWidget(toggle)
        vlayout.addWidget(content)
        return container

    @staticmethod
    def _format_action_json(action: dict) -> str:
        if not action:
            return ""
        display = {k: v for k, v in action.items()
                   if k not in ("thought", "raw_model_output")}
        if not display:
            return ""
        try:
            return json.dumps(display, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(display)

    @staticmethod
    def _format_action_detail(action: dict) -> str:
        parts = []
        func = action.get("func", "")
        if func in ("Click", "Tap", "LongPress"):
            pos = action.get("position")
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                x, y = pos[0], pos[1]
            else:
                x, y = action.get("x"), action.get("y")
            if x is not None and y is not None:
                parts.append(f"位置: ({x}, {y})")
        elif func == "Swipe":
            sp = action.get("start_position", [])
            ep = action.get("end_position", [])
            x1 = sp[0] if len(sp) > 0 else action.get("x1", "?")
            y1 = sp[1] if len(sp) > 1 else action.get("y1", "?")
            x2 = ep[0] if len(ep) > 0 else action.get("x2", "?")
            y2 = ep[1] if len(ep) > 1 else action.get("y2", "?")
            parts.append(f"({x1},{y1}) -> ({x2},{y2})")
        elif func == "Type":
            text = action.get("text", "")
            display = text if len(text) <= 40 else text[:37] + "..."
            parts.append(f'"{display}"')
        elif func == "Open":
            app = action.get("app", "")
            if app:
                parts.append(app)
        return "  ".join(parts)
