# -*- coding: utf-8 -*-
"""
可插拔动作执行器
将 Action Space 分发到 DeviceBackend 执行。不直接感知 USB/WiFi 差异。
"""
import time
import logging

from action.action_space import validate_action
from apps.registry import get_alias_to_package

logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    执行动作分发与具体的设备操作。
    使用注册模式，可以方便地添加、替换、Mock某个动作的实现。
    """
    def __init__(self, backend, device_type="phone"):
        self.backend = backend
        self.device_type = device_type

        self.open_timeout = 4  # app启动跳过广告的等待时间

        # 动作路由表
        self._handlers = {}
        self._register_default_handlers()

    def execute(self, action: dict, **kwargs) -> bool:
        """
        执行一个标准动作字典。
        """
        is_valid, msg = validate_action(action)
        if not is_valid:
            logger.error(f"Action 验证失败: {msg} - {action}")
            return False

        func = action.get("func")
        handler = self._handlers.get(func)

        if handler:
            try:
                msg = handler(action, **kwargs)
                logger.info(f"动作执行: [{func}] {msg}")
                return True
            except Exception as e:
                logger.error(f"动作[{func}]执行异常: {e}", exc_info=True)
                return False
        else:
            logger.error(f"未实现动作处理器: {func}")
            return False

    def register_handler(self, func_name: str, handler):
        self._handlers[func_name] = handler

    # ==================== 默认行为处理实现 ====================

    def _register_default_handlers(self):
        self.register_handler("Tap", self._handle_tap)
        self.register_handler("LongPress", self._handle_long_press)
        self.register_handler("Swipe", self._handle_swipe)
        self.register_handler("Type", self._handle_type)
        self.register_handler("Search", self._handle_search)
        self.register_handler("Open", self._handle_open)
        self.register_handler("Back", self._handle_back)
        self.register_handler("Wait", self._handle_wait)
        self.register_handler("Complete", self._handle_complete)
        self.register_handler("Fail", self._handle_fail)
        self.register_handler("Speak", self._handle_speak)
        self.register_handler("ToolUse", self._handle_tool_use)

    def _handle_tap(self, action, **kwargs):
        pos = action["position"]
        times = int(action.get("times", 1))

        for _ in range(times):
            self.backend.tap(pos[0], pos[1])
            if times > 1:
                time.sleep(0.3)
        return f"点击 {pos} 共 {times} 次"

    def _handle_long_press(self, action, **kwargs):
        pos = action["position"]
        self.backend.long_press(pos[0], pos[1])
        return f"长按 {pos}"

    def _handle_swipe(self, action, **kwargs):
        start = action.get("start_position")
        end = action.get("end_position")
        pos = action.get("position")

        if start and end and len(start) >= 2 and len(end) >= 2:
            self.backend.swipe(start[0], start[1], end[0], end[1], duration_ms=1500)
            return f"从 {start} 滑动到 {end}"

        if pos and isinstance(pos, str):
            self.backend.swipe_direction(pos)
            return f"向 {pos} 滑动"

        raise ValueError(f"Swipe 参数不足: {action}")

    def _handle_type(self, action, **kwargs):
        pos = action.get("position")
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            pos = None
        text = action.get("text", "")
        self.backend.input_text(text, clear=True, enter=False, position=pos)
        return f"输入文本: {text}"

    def _handle_search(self, action, **kwargs):
        pos = action.get("position")
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            pos = None
        text = action.get("text", "")
        self.backend.input_text(text, clear=True, enter=True, position=pos)
        return f"搜索: {text}"

    def _handle_open(self, action, **kwargs):
        app_name = action["app"]
        alias_to_pkg = get_alias_to_package(self.device_type)
        package = alias_to_pkg.get(app_name.lower()) or alias_to_pkg.get(app_name)

        if package:
            if "小程序" in app_name:
                self.backend.open_deeplink(package)
            else:
                self.backend.open_app(package)
            time.sleep(self.open_timeout)
            return f"打开应用 {app_name} ({package})"

        logger.warning(f"未能解析应用包名: {app_name}")
        return f"未知应用，未能打开: {app_name}"

    def _handle_back(self, action, **kwargs):
        self.backend.back()
        return "返回上一级"

    def _handle_wait(self, action, **kwargs):
        return "等待操作"

    def _handle_complete(self, action, **kwargs):
        logger.info(f"== 目标达成 == {action.get('thought', '')}")
        return "宣告完成"

    def _handle_fail(self, action, **kwargs):
        reason = action.get("reason", "")
        err_type = action.get("type", "Unknown")
        logger.warning(f"触发 Fail ({err_type}): {reason}")
        return f"宣告失败 - {err_type}: {reason}"

    def _handle_speak(self, action, **kwargs):
        text = action.get("text", "")
        return f"Speak: {text}"

    def _handle_tool_use(self, action, **kwargs):
        tool = action.get("tool", "") or action.get("type", "")
        logger.info(f"使用工具: {tool}")
        return f"使用外部工具: {tool}"
