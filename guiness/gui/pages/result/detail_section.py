# -*- coding: utf-8 -*-
"""ResultPage 右侧详情面板：query banner + 截图 + 步骤信息 + 评分。"""
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QGroupBox,
    QFrame, QStackedWidget, QPushButton, QComboBox,
)
from PySide6.QtCore import Qt

from gui.widgets.screenshot_viewer import ScreenshotViewer
from gui.styles import tokens as t


def build_right_stack(page) -> QStackedWidget:
    stack = QStackedWidget()

    # Page 0 — empty state
    stack.addWidget(_build_empty_page())

    # Page 1 — detail
    stack.addWidget(_build_detail_page(page))

    stack.setCurrentIndex(0)
    return stack


def _build_empty_page() -> QWidget:
    empty_page = QWidget()
    empty_lay = QVBoxLayout(empty_page)
    empty_lay.setAlignment(Qt.AlignCenter)

    empty_icon = QLabel("📋")
    empty_icon.setStyleSheet("font-size: 48px; background: transparent;")
    empty_icon.setAlignment(Qt.AlignCenter)
    empty_lay.addWidget(empty_icon)

    empty_text = QLabel("选择左侧的评测 Episode 查看详情")
    empty_text.setStyleSheet(
        f"color: {t.NEUTRAL_500}; font-size: {t.FONT_SM}px; background: transparent;"
    )
    empty_text.setAlignment(Qt.AlignCenter)
    empty_lay.addWidget(empty_text)

    return empty_page


def _build_detail_page(page) -> QWidget:
    detail_page = QWidget()
    right_layout = QVBoxLayout(detail_page)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(10)

    # Query banner
    page._query_banner = QLabel("")
    page._query_banner.setWordWrap(True)
    page._query_banner.setTextInteractionFlags(
        Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
    )
    page._query_banner.setCursor(Qt.IBeamCursor)
    page._query_banner.setStyleSheet(f"""
        background: {t.NEUTRAL_100};
        border: 1px solid {t.NEUTRAL_200};
        border-radius: {t.RADIUS_MD}px;
        padding: 10px 14px;
        font-size: {t.FONT_SM}px;
        font-weight: {t.WEIGHT_SEMI};
        color: {t.NEUTRAL_900};
    """)
    page._query_banner.setVisible(False)
    right_layout.addWidget(page._query_banner)

    # Screenshot + nav
    screenshot_row = QVBoxLayout()
    screenshot_row.setSpacing(6)

    page._screenshot_viewer = ScreenshotViewer()
    screenshot_row.addWidget(page._screenshot_viewer, 1)

    nav_bar = QHBoxLayout()
    nav_bar.setSpacing(10)

    page._btn_prev = QPushButton("< 上一步")
    page._btn_prev.setObjectName("ghostButton")
    page._btn_prev.setFixedWidth(90)
    page._btn_prev.clicked.connect(lambda: prev_step(page))
    nav_bar.addWidget(page._btn_prev)

    page._step_indicator = QLabel("Step 0 / 0")
    page._step_indicator.setAlignment(Qt.AlignCenter)
    page._step_indicator.setStyleSheet(
        f"font-weight: {t.WEIGHT_SEMI}; color: {t.NEUTRAL_700}; "
        f"font-size: {t.FONT_SM}px; background: transparent;"
    )
    nav_bar.addWidget(page._step_indicator, 1)

    page._btn_next = QPushButton("下一步 >")
    page._btn_next.setObjectName("ghostButton")
    page._btn_next.setFixedWidth(90)
    page._btn_next.clicked.connect(lambda: next_step(page))
    nav_bar.addWidget(page._btn_next)

    screenshot_row.addLayout(nav_bar)
    right_layout.addLayout(screenshot_row, 3)

    # Step info card
    info_grp = QGroupBox("步骤详情")
    info_lay = QVBoxLayout()
    info_lay.setContentsMargins(10, 10, 10, 10)
    page._info_text = QTextEdit()
    page._info_text.setReadOnly(True)
    page._info_text.setMinimumHeight(120)
    page._info_text.setMaximumHeight(320)
    info_lay.addWidget(page._info_text)
    info_grp.setLayout(info_lay)
    right_layout.addWidget(info_grp, 1)

    # Scoring card
    score_frame = QFrame()
    score_frame.setStyleSheet(f"""
        QFrame {{
            background: {t.NEUTRAL_0};
            border: 1px solid {t.NEUTRAL_200};
            border-radius: {t.RADIUS_MD}px;
            padding: 8px;
        }}
    """)
    score_lay = QHBoxLayout(score_frame)
    score_lay.setSpacing(12)
    score_lay.setContentsMargins(14, 8, 14, 8)

    lbl = QLabel("评分")
    lbl.setStyleSheet(
        f"font-weight: {t.WEIGHT_SEMI}; color: {t.NEUTRAL_900}; "
        f"font-size: {t.FONT_SM}px; border: none; background: transparent;"
    )
    score_lay.addWidget(lbl)

    page._score_combo = QComboBox()
    page._score_combo.addItems(["未评分", "0 - 失败", "1 - 成功", "0.5 - 部分完成"])
    page._score_combo.setMinimumWidth(150)
    score_lay.addWidget(page._score_combo)

    page._btn_save_score = QPushButton("保存评分")
    page._btn_save_score.setFixedWidth(100)
    page._btn_save_score.clicked.connect(page._save_score)
    score_lay.addWidget(page._btn_save_score)

    page._score_status = QLabel("")
    page._score_status.setStyleSheet(
        f"color: {t.NEUTRAL_500}; font-size: {t.FONT_XS}px; "
        f"border: none; background: transparent;"
    )
    score_lay.addWidget(page._score_status)

    score_lay.addStretch()

    page._episode_summary = QLabel("")
    page._episode_summary.setObjectName("accentLabel")
    page._episode_summary.setStyleSheet("border: none; background: transparent;")
    score_lay.addWidget(page._episode_summary)

    right_layout.addWidget(score_frame)

    return detail_page


def go_to_step(page, index: int) -> None:
    if not page._current_episode_data:
        return
    steps = page._current_episode_data.get("data", [])
    if not steps:
        page._step_indicator.setText("无步骤数据")
        return

    index = max(0, min(index, len(steps) - 1))
    page._current_step_index = index
    step = steps[index]

    page._step_indicator.setText(f"Step {index + 1} / {len(steps)}")
    page._btn_prev.setEnabled(index > 0)
    page._btn_next.setEnabled(index < len(steps) - 1)

    _display_step_screenshot(page, page._current_episode_path, step)
    _display_step_info(page, step)


def prev_step(page) -> None:
    go_to_step(page, page._current_step_index - 1)


def next_step(page) -> None:
    go_to_step(page, page._current_step_index + 1)


def _display_step_screenshot(page, ep_path: str, step_data: dict) -> None:
    step_num = step_data.get("step", 1)
    action = step_data.get("action", {})

    jpg_path = os.path.join(ep_path, f"{step_num}.jpg")
    png_path = os.path.join(ep_path, f"{step_num}.png")
    img_path = jpg_path if os.path.exists(jpg_path) else png_path

    page._screenshot_viewer.load_image(img_path, action)


def _display_step_info(page, step_data: dict) -> None:
    action = step_data.get("action", {})
    thought = step_data.get("thought", "") or action.get("thought", "")
    func = action.get("func", "?")
    fg_app = step_data.get("foreground_app", "")

    lines = []
    lines.append(f"<b>Action:</b> <span style='color:{t.ACCENT}'>{func}</span>")

    if func in ("Click", "Tap", "LongPress"):
        pos = action.get("position", [])
        if pos and len(pos) >= 2:
            lines.append(f"<b>Position:</b> [{pos[0]:.3f}, {pos[1]:.3f}]")
    elif func == "Swipe":
        sp = action.get("start_position", [])
        ep = action.get("end_position", [])
        if sp and ep and len(sp) >= 2 and len(ep) >= 2:
            lines.append(
                f"<b>Swipe:</b> [{sp[0]:.3f}, {sp[1]:.3f}] → [{ep[0]:.3f}, {ep[1]:.3f}]"
            )
    elif func in ("Type", "Search", "Speak"):
        lines.append(f"<b>Text:</b> {action.get('text', '')}")
    elif func == "Open":
        lines.append(f"<b>App:</b> {action.get('app', '')}")
    elif func == "Fail":
        lines.append(f"<b>Type:</b> <span style='color:{t.DANGER}'>{action.get('type', '')}</span>")
        lines.append(f"<b>Reason:</b> {action.get('reason', '')}")

    if fg_app:
        lines.append(f"<b>前台App:</b> {fg_app}")

    if thought:
        lines.append(f"<br><b style='color:{t.NEUTRAL_900}'>思考过程</b>")
        escaped = thought.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if len(escaped) > 600:
            truncated = escaped[:600]
            for sep in ("。", ".", "，", "\n"):
                idx = truncated.rfind(sep)
                if idx > 400:
                    truncated = truncated[:idx + 1]
                    break
            escaped = (
                truncated
                + f"<br><span style='color:{t.NEUTRAL_400}'>(... 已截断，共 "
                + str(len(thought)) + " 字符)</span>"
            )
        formatted = escaped.replace("\n", "<br>")
        lines.append(f"<span style='color:{t.NEUTRAL_700}; font-size:{t.FONT_XS}px'>{formatted}</span>")

    page._info_text.setHtml("<br>".join(lines))
