# -*- coding: utf-8 -*-
import os
import time
import logging

logger = logging.getLogger(__name__)

# 历史上这里 except ImportError 直接 pass，打包环境下当 uiautomator2 的
# 某个子模块（比如 adbutils 的 _proto / lxml）找不到时，外部看不到根因，
# 只有下面 _uiautomator2_connect 里那句 "package not installed"——要命。
# 这里记下 _U2_IMPORT_ERROR，然后 connect 时一并带出去。
_U2_IMPORT_ERROR: str = ""
try:
    import uiautomator2 as u2
    from uiautomator2.exceptions import AdbBroadcastError
    U2_AVAILABLE = True
except BaseException as _e:
    # 注意用 BaseException：某些依赖缺失（比如 lxml 找不到 .so）会 raise
    # ModuleNotFoundError 之外的东西，甚至是 SystemExit。不拦截就会整个进程
    # 启动失败；但那时 GUI 已经弹出 main 窗口，根因没地方看。
    U2_AVAILABLE = False
    u2 = None
    AdbBroadcastError = Exception  # 占位，后面 except 用得到
    import traceback as _tb
    _U2_IMPORT_ERROR = f"{type(_e).__name__}: {_e}\n{_tb.format_exc()}"


class AutomatorDevice:
    """
    Uiautomator2 设备封装组件
    负责获取xml布局树以及直接的ui元素操作
    """
    def __init__(self, device_id=""):
        self.device = self._uiautomator2_connect(device_id)
        if self.device:
            logger.info(f"Uiautomator2 连接设备 {device_id} 成功")
        else:
            logger.warning(f"Uiautomator2 连接设备 {device_id} 失败")
            
    def _uiautomator2_connect(self, device_id):
        if not U2_AVAILABLE:
            import sys as _sys
            logger.error(
                f"uiautomator2 不可用（U2_AVAILABLE=False, frozen={getattr(_sys, 'frozen', False)}）"
            )
            if _U2_IMPORT_ERROR:
                logger.error(f"uiautomator2 import 阶段错误:\n{_U2_IMPORT_ERROR}")
            else:
                logger.error("uiautomator2 import 异常捕获为空——可能根本没跑到 import 语句")
            return None

        try:
            if device_id is None or device_id == "":
                device = u2.connect()
            else:
                device = u2.connect(device_id)
        except Exception as e:
            logger.error(f"U2 connect error: {e}")
            return None

        # 确保 ATX agent 已部署到手机，否则 dump_hierarchy 等操作会失败
        try:
            device.info  # 快速测试 ATX agent 是否可用
        except Exception:
            logger.info("ATX agent 不可用，尝试自动部署...")
            try:
                device._setup_jar()
                device._setup_ime()
                logger.info("ATX agent 自动部署完成")
            except Exception as e:
                logger.error(f"ATX agent 自动部署失败: {e}")
                return None

        return device

    def dump_hierarchy(self, file_path):
        """
        获取当前屏幕的 xml 布局树并保存到指定路径
        
        Args:
            file_path: 保存 xml 的完整路径
            
        Returns:
            str: 成功时返回 file_path，失败返回 "ERROR"
        """
        if self.device is None:
            logger.error("获取XML失败，未连接U2设备")
            return "ERROR"
            
        try:
            xml = self.device.dump_hierarchy()
            if xml is not None:
                os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(xml)
                return file_path
        except Exception as e:
            logger.error(f"Dump hierarchy failed: {e}")
            
        return "ERROR"

    def click_by_position(self, x, y):
        """
        根据坐标进行点击
        """
        if self.device is None:
            return False
            
        try:
            self.device.click(x, y)
            return True
        except Exception as e:
            logger.error(f"U2 click error: {e}")
            return False

    def type_text(self, input_text, enter=True, position=None):
        """
        利用 U2 键盘输入文本，相比基于ADB广播的方法更加稳定。

        关键顺序（踩过坑）：
          1. set_fastinput_ime(True) 必须在点击聚焦 *之前*；先点再切 IME
             会让新拉起的软键盘继续用原 IME（如搜狗），广播被吞。
          2. 切回原 IME 必须在 press("enter") *之后*；回车前换 IME 会让
             已 commit 的文本被重新解释（搜狗特性），搜索词变 "雷军" → 拼音残留。
          3. 第二次点击 position 已经移除——聚焦已在 send_keys 阶段建立，
             再点一次反而可能让光标离开 EditText。
        """
        text_preview = input_text if len(input_text) <= 32 else input_text[:32] + "…"
        logger.info(
            f"type_text 开始: text={text_preview!r} "
            f"position={position} enter={enter}"
        )

        if self.device is None:
            logger.error("type_text: U2 device is None，放弃输入")
            return False

        try:
            # ── 1. 切到 AdbKeyboard ──
            try:
                current_ime = self.device.current_ime()
                logger.info(f"type_text: 当前 IME={current_ime}")
            except Exception as e:
                current_ime = None
                logger.debug(f"type_text: 读取当前 IME 失败（忽略）: {e}")

            self.device.set_fastinput_ime(True)
            logger.info("type_text: 切换到 AdbKeyboard 完成")
            time.sleep(0.3)

            # ── 2. 点击聚焦 ──
            if position:
                logger.info(f"type_text: 点击聚焦 ({position[0]}, {position[1]})")
                ok = self.click_by_position(position[0], position[1])
                if not ok:
                    logger.warning("type_text: 聚焦点击失败（continue 但可能无焦点）")
                time.sleep(0.5)

            # ── 2.5 读取焦点控件，便于事后排查 ──
            focused_info = ""
            try:
                focused = self.device(focused=True)
                if focused.exists:
                    info = focused.info
                    focused_info = (
                        f"class={info.get('className')} "
                        f"pkg={info.get('packageName')} "
                        f"resource_id={info.get('resourceName')} "
                        f"text={info.get('text')!r}"
                    )
                    logger.info(f"type_text: 当前焦点控件 {focused_info}")
                else:
                    logger.warning("type_text: 找不到任何 focused 控件——send_keys 可能落空")
            except Exception as e:
                logger.debug(f"type_text: 读取焦点控件失败（忽略）: {e}")

            # ── 3. send_keys ──
            t0 = time.time()
            sent = False
            try:
                self.device.send_keys(input_text, clear=True)
                sent = True
            except AdbBroadcastError as e:
                logger.warning(f"type_text: send_keys(clear=True) 广播失败: {e}；改用 clear=False 重试")
                try:
                    self.device.send_keys(input_text, clear=False)
                    sent = True
                except Exception as e2:
                    logger.error(f"type_text: send_keys(clear=False) 也失败: {e2}")
            except Exception as e:
                logger.warning(f"type_text: send_keys(clear=True) 异常: {e}；改用 clear=False 重试")
                try:
                    self.device.send_keys(input_text, clear=False)
                    sent = True
                except Exception as e2:
                    logger.error(f"type_text: send_keys(clear=False) 也失败: {e2}")

            dt_ms = int((time.time() - t0) * 1000)
            logger.info(f"type_text: send_keys 耗时 {dt_ms}ms sent={sent}")

            if not sent:
                # 失败收尾：还原 IME
                try:
                    self.device.set_fastinput_ime(False)
                except Exception:
                    pass
                return False

            # ── 4. 验证文本是否落地 ──
            time.sleep(0.3)
            try:
                focused = self.device(focused=True)
                if focused.exists:
                    after = focused.info.get("text", "")
                    logger.info(f"type_text: 输入后焦点控件 text={after!r}")
                    if not after or input_text not in after:
                        logger.warning(
                            f"type_text: 文本未完整落地（期望包含 {input_text!r}，实际 {after!r}）"
                        )
            except Exception as e:
                logger.debug(f"type_text: 验证文本失败（忽略）: {e}")

            # ── 5. 回车（仍在 AdbKeyboard 下，避免原 IME 重解释已 commit 文本）──
            if enter:
                logger.info("type_text: press enter")
                self.device.press("enter")
                time.sleep(0.3)

            # ── 6. 最后再还原 IME ──
            try:
                self.device.set_fastinput_ime(False)
                logger.info("type_text: 已还原默认 IME")
            except Exception as e:
                logger.debug(f"type_text: 还原 IME 失败（忽略）: {e}")

            logger.info("type_text 完成")
            return True
        except Exception as e:
            logger.error(f"U2 typing error globally: {e}")
            try:
                if self.device:
                    self.device.set_fastinput_ime(False)
            except Exception:
                pass
            return False
