# -*- coding: utf-8 -*-
"""
Guiness 设计 token —— 单一 source of truth。

本次只实现光模式。暗色模式若需增加，将 tokens 改成按主题命名的字典，
并让 gui/styles/theme.py::build_stylesheet 接收 theme 参数选择。
"""

# ── 基础灰阶 ───────────────────────────────────────────────
# 唯一的中性色梯子；所有背景/边框/文字均从这里挑。
NEUTRAL_0   = "#ffffff"   # 主背景
NEUTRAL_50  = "#fafafa"   # 次级 surface（侧栏、局部底色）
NEUTRAL_100 = "#f5f5f5"   # 输入框底、非强调按钮填充、hover 目标色
NEUTRAL_200 = "#e5e5e5"   # 主要边框
NEUTRAL_300 = "#d4d4d4"   # 强调边框 / hover 边框
NEUTRAL_400 = "#a3a3a3"   # 占位符、禁用文本
NEUTRAL_500 = "#737373"   # tertiary 文本（meta/timestamp）
NEUTRAL_700 = "#525252"   # secondary 文本
NEUTRAL_900 = "#0a0a0a"   # primary 文本 / 主 CTA 填充

# ── Accent ─────────────────────────────────────────────────
# 单 accent，用在：焦点边框、运行中状态点、主进度条、选中态高亮。
ACCENT       = "#2563eb"   # blue-600
ACCENT_HOVER = "#1d4ed8"   # blue-700
ACCENT_SOFT  = "#dbeafe"   # blue-100，极淡背景（focus ring 底色/高亮 banner）

# ── 状态色 ─────────────────────────────────────────────────
SUCCESS = "#16a34a"
DANGER  = "#dc2626"
DANGER_HOVER = "#b91c1c"   # red-700（stop 按钮 hover 加深）
WARNING = "#d97706"

# 状态色的极淡底（用于 SystemMessage 四态 pill 等）
SUCCESS_SOFT = "#dcfce7"
DANGER_SOFT  = "#fee2e2"
WARNING_SOFT = "#fef3c7"
ACCENT_INFO_SOFT = ACCENT_SOFT

# ── Action 徽章色（step_card） ─────────────────────────────
# 从原 7 色收敛到 4 类；按动作性质分组，而不是每个动作一种颜色。
BADGE_PRIMARY = NEUTRAL_900   # Tap / Type / Open / Back / Home / Enter（常规）
BADGE_ACCENT  = ACCENT        # Swipe / Wait（过程性）
BADGE_SUCCESS = SUCCESS       # Complete / End / Speak
BADGE_DANGER  = DANGER        # Fail

# ── 字号（5 阶） ───────────────────────────────────────────
FONT_XS = 12   # caption / meta / timestamp / 状态标签
FONT_SM = 13   # body default（QWidget、输入框、按钮）
FONT_MD = 15   # 强调 body（user 消息、step 内容、配置项标题）
FONT_LG = 18   # section 标题 / 小对话框标题
FONT_XL = 24   # 页面级标题

# ── 字重（2 档） ───────────────────────────────────────────
WEIGHT_REGULAR = 400
WEIGHT_SEMI    = 600

# ── 圆角（2 档） ───────────────────────────────────────────
RADIUS_SM = 6    # 输入框、小按钮、chips、徽章、scrollbar
RADIUS_MD = 10   # 卡片、对话框、气泡、GroupBox、侧栏 item

# ── 间距（4px 基线） ───────────────────────────────────────
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_6 = 24
SPACE_8 = 32

# ── 字体栈 ─────────────────────────────────────────────────
FONT_FAMILY = '"SF Pro Display", "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif'


def qss_vars() -> dict:
    """将 tokens 展开成 QSS 模板占位符字典。供 build_stylesheet 使用。"""
    return {
        # colors
        "neutral_0": NEUTRAL_0,
        "neutral_50": NEUTRAL_50,
        "neutral_100": NEUTRAL_100,
        "neutral_200": NEUTRAL_200,
        "neutral_300": NEUTRAL_300,
        "neutral_400": NEUTRAL_400,
        "neutral_500": NEUTRAL_500,
        "neutral_700": NEUTRAL_700,
        "neutral_900": NEUTRAL_900,
        "accent": ACCENT,
        "accent_hover": ACCENT_HOVER,
        "accent_soft": ACCENT_SOFT,
        "success": SUCCESS,
        "danger": DANGER,
        "danger_hover": DANGER_HOVER,
        "warning": WARNING,
        # fonts
        "font_family": FONT_FAMILY,
        "font_xs": FONT_XS,
        "font_sm": FONT_SM,
        "font_md": FONT_MD,
        "font_lg": FONT_LG,
        "font_xl": FONT_XL,
        "weight_regular": WEIGHT_REGULAR,
        "weight_semi": WEIGHT_SEMI,
        # radii
        "radius_sm": RADIUS_SM,
        "radius_md": RADIUS_MD,
    }
