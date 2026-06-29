import logging
from android_world.env import json_action

logger = logging.getLogger(__name__)

APP_REGISTRY = {
    "simple calendar pro": "com.simplemobiletools.calendar.pro",
    "settings": "com.android.settings",
    "markor": "net.gsantner.markor",
    "broccoli": "com.flauschcode.broccoli",
    "broccoli recipe app": "com.flauschcode.broccoli",
    "recipe app": "com.flauschcode.broccoli",
    "pro expense": "com.arduia.expense",
    "expense": "com.arduia.expense",
    "simple sms messenger": "com.simplemobiletools.smsmessenger",
    "sms": "com.simplemobiletools.smsmessenger",
    "opentracks": "de.dennisguse.opentracks",
    "open tracks": "de.dennisguse.opentracks",
    "sports tracker": "de.dennisguse.opentracks",
    "tasks": "org.tasks",
    "clock": "com.google.android.deskclock",
    "joplin": "net.cozic.joplin",
    "retro music": "code.name.monkey.retromusic",
    "simple gallery pro": "com.simplemobiletools.gallery.pro",
    "camera": "com.android.camera2",
    "chrome": "com.android.chrome",
    "contacts": "com.google.android.contacts",
    "osmand": "net.osmand",
    "vlc": "org.videolan.vlc",
    "audio recorder": "com.dimowner.audiorecorder",
    "files": "com.google.android.documentsui",
    "simple draw pro": "com.simplemobiletools.draw.pro",
}


def _rel_to_abs(
    rel_pos: list[float], screen_w: int, screen_h: int
) -> tuple[int, int]:
    x_val, y_val = rel_pos[0], rel_pos[1]
    x = int(x_val * screen_w) if x_val <= 1 else int(x_val)
    y = int(y_val * screen_h) if y_val <= 1 else int(y_val)
    x = max(0, min(x, screen_w - 1))
    y = max(0, min(y, screen_h - 1))
    return x, y


CN_TO_EN_APP_MAP = {
    "相机": "camera",
    "摄像头": "camera",
    "照相机": "camera",
    "设置": "settings",
    "系统设置": "settings",
    "日历": "simple calendar pro",
    "简单日历": "simple calendar pro",
    "短信": "sms",
    "信息": "sms",
    "消息": "sms",
    "简单短信": "sms",
    "备忘录": "markor",
    "笔记": "markor",
    "记事本": "markor",
    "文件": "files",
    "文件管理器": "files",
    "文件管理": "files",
    "联系人": "contacts",
    "通讯录": "contacts",
    "时钟": "clock",
    "闹钟": "clock",
    "浏览器": "chrome",
    "音乐": "retro music",
    "音乐播放器": "retro music",
    "录音机": "audio recorder",
    "录音": "audio recorder",
    "音频录制": "audio recorder",
    "地图": "osmand",
    "导航": "osmand",
    "画图": "simple draw pro",
    "画板": "simple draw pro",
    "绘图": "simple draw pro",
    "任务": "tasks",
    "待办": "tasks",
    "待办事项": "tasks",
    "图库": "simple gallery pro",
    "相册": "simple gallery pro",
    "视频播放器": "vlc",
    "视频": "vlc",
    "食谱": "broccoli",
    "菜谱": "broccoli",
    "记账": "expense",
    "账单": "expense",
    "支出": "expense",
    "费用": "expense",
    "运动": "sports tracker",
    "运动追踪": "sports tracker",
    "运动记录": "sports tracker",
}


def _normalize_app_name(app_name: str) -> str:
    """Try to resolve app name to a known name or package."""
    lower = app_name.lower().strip()
    # Direct match in registry
    if lower in APP_REGISTRY:
        return lower
    # Chinese to English mapping
    if lower in CN_TO_EN_APP_MAP:
        return CN_TO_EN_APP_MAP[lower]
    # Partial match in registry
    for key in APP_REGISTRY:
        if lower in key or key in lower:
            return key
    # Partial match in Chinese map
    for cn, en in CN_TO_EN_APP_MAP.items():
        if cn in lower or lower in cn:
            return en
    return app_name


def convert_to_json_action(
    parsed: dict, screen_w: int, screen_h: int
) -> tuple[json_action.JSONAction, bool]:
    """Convert a parsed action dict to JSONAction.

    Returns (action, is_terminal).
    """
    func = parsed.get("func", "Wait")
    is_terminal = False

    try:
        if func == "Tap":
            pos = parsed.get("position", [0.5, 0.5])
            times = int(parsed.get("times", 1))
            x, y = _rel_to_abs(pos, screen_w, screen_h)
            if times == 2:
                action = json_action.JSONAction(
                    action_type=json_action.DOUBLE_TAP, x=x, y=y
                )
            else:
                action = json_action.JSONAction(
                    action_type=json_action.CLICK, x=x, y=y
                )
            return action, False

        elif func == "LongPress":
            pos = parsed.get("position", [0.5, 0.5])
            x, y = _rel_to_abs(pos, screen_w, screen_h)
            action = json_action.JSONAction(
                action_type=json_action.LONG_PRESS, x=x, y=y
            )
            return action, False

        elif func == "Swipe":
            start = parsed.get("start_position", [0.5, 0.5])
            end = parsed.get("end_position", [0.5, 0.5])
            sx, sy = _rel_to_abs(start, screen_w, screen_h)
            ex, ey = _rel_to_abs(end, screen_w, screen_h)
            action = json_action.JSONAction(
                action_type=json_action.SWIPE,
                start_position=(sx, sy),
                end_position=(ex, ey),
                press_duration=-1,
            )
            return action, False

        elif func == "Type":
            pos = parsed.get("position", [0.5, 0.5])
            text = parsed.get("text", "")
            x, y = _rel_to_abs(pos, screen_w, screen_h)
            action = json_action.JSONAction(
                action_type=json_action.INPUT_TEXT,
                x=x,
                y=y,
                text=text,
                clear_text=False,
            )
            return action, False

        elif func == "Search":
            pos = parsed.get("position", [0.5, 0.5])
            text = parsed.get("text", "")
            x, y = _rel_to_abs(pos, screen_w, screen_h)
            action = json_action.JSONAction(
                action_type=json_action.INPUT_TEXT,
                x=x,
                y=y,
                text=text,
                clear_text=True,
            )
            return action, False

        elif func == "Open":
            app_name = parsed.get("app", "")
            normalized = _normalize_app_name(app_name)
            pkg = APP_REGISTRY.get(normalized, normalized)
            action = json_action.JSONAction(
                action_type=json_action.OPEN_APP, app_name=pkg
            )
            return action, False

        elif func == "Back":
            action = json_action.JSONAction(
                action_type=json_action.NAVIGATE_BACK
            )
            return action, False

        elif func in ("GoHome", "Home"):
            action = json_action.JSONAction(
                action_type=json_action.NAVIGATE_HOME
            )
            return action, False

        elif func == "Wait":
            action = json_action.JSONAction(action_type=json_action.WAIT)
            return action, False

        elif func == "Complete":
            action = json_action.JSONAction(
                action_type=json_action.STATUS, goal_status="complete"
            )
            return action, True

        elif func == "Fail":
            action = json_action.JSONAction(
                action_type=json_action.STATUS, goal_status="infeasible"
            )
            return action, True

        elif func == "Speak":
            text = parsed.get("text", "")
            action = json_action.JSONAction(
                action_type=json_action.ANSWER, text=text
            )
            return action, True

        elif func == "Request":
            action = json_action.JSONAction(action_type=json_action.WAIT)
            return action, False

        else:
            logger.warning(f"Unknown func: {func}, falling back to Wait")
            action = json_action.JSONAction(action_type=json_action.WAIT)
            return action, False

    except Exception as e:
        logger.error(f"Action conversion error: {e}")
        action = json_action.JSONAction(action_type=json_action.UNKNOWN)
        return action, False
