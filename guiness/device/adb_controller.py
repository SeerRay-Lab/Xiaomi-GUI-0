# -*- coding: utf-8 -*-
"""
ADB 控制器层
提供设备级别的控制，如执行adb命令、获取截图、打开应用等基础操作。
"""
import subprocess
import sys
import re
import time
import base64
import os
import logging
from PIL import Image

from apps.registry import get_package_to_std, get_all_known_packages

logger = logging.getLogger(__name__)

# Windows 上隐藏 subprocess 弹出的 cmd 窗口
_STARTUP_INFO = None
_CREATE_FLAGS = 0
if sys.platform == "win32":
    _STARTUP_INFO = subprocess.STARTUPINFO()
    _STARTUP_INFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _STARTUP_INFO.wShowWindow = 0  # SW_HIDE
    _CREATE_FLAGS = subprocess.CREATE_NO_WINDOW


def _bundled_adb() -> str:
    """在 PyInstaller 打包产物中查找同梱的 adb。
    build_config.spec 会把 vendor/platform-tools/<os>/ 下的文件放到 bundle 的
    platform-tools/ 目录里，运行时 adb 实际位置取决于 bundle 模式：
      - onefile：解压在 sys._MEIPASS/platform-tools/
      - onedir（当前 macOS .app 就是）：在 Contents/Resources/ / Contents/MacOS/
        下各处都可能，取决于 PyInstaller 版本，全部试一遍
    未打包或 vendor 目录不存在时返回空字符串，交给 PATH 兜底。
    """
    exe = "adb.exe" if sys.platform.startswith("win") else "adb"
    roots = []

    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        roots.append(os.path.join(meipass, "platform-tools"))

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        # PyInstaller onedir 常见布局
        roots.append(os.path.join(exe_dir, "platform-tools"))
        roots.append(os.path.join(os.path.dirname(exe_dir), "Frameworks", "platform-tools"))
        roots.append(os.path.join(os.path.dirname(exe_dir), "Resources", "platform-tools"))
        # macOS .app bundle 通常走 Contents/Frameworks，上一行已覆盖

    for root in roots:
        cand = os.path.join(root, exe)
        if os.path.isfile(cand):
            # _MEIPASS 是临时目录，PyInstaller 解压时已设权限；
            # 但一些版本 onedir 模式会丢 x 位，保险起见 chmod 一次。
            if not sys.platform.startswith("win"):
                try:
                    os.chmod(cand, 0o755)
                except OSError:
                    pass
            return cand
    return ""


def _find_adb() -> str:
    """在常见路径中查找 adb 可执行文件，找不到则回退到 'adb'。"""
    # 0. 同梱的 platform-tools 最优先——打包给无 ADB 用户使用时这条是唯一命中
    bundled = _bundled_adb()
    if bundled:
        return bundled

    import shutil
    # 1. 系统 PATH（终端能找到的情况）
    found = shutil.which("adb")
    if found:
        return found
    # 2. 常见安装位置
    candidates = [
        os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
        os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
        "/opt/homebrew/bin/adb",
        "/usr/local/bin/adb",
        "C:\\Users\\{}\\AppData\\Local\\Android\\Sdk\\platform-tools\\adb.exe".format(
            os.environ.get("USERNAME", "")
        ),
    ]
    # ANDROID_HOME / ANDROID_SDK_ROOT
    for env_key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk = os.environ.get(env_key)
        if sdk:
            candidates.insert(0, os.path.join(sdk, "platform-tools", "adb"))
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return "adb"


def list_all_devices(adb_path=None):
    """
    列出当前连接的所有 adb 设备序列号
    """
    if adb_path is None:
        adb_path = _find_adb()
    try:
        result = subprocess.run(
            [adb_path, "devices"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            startupinfo=_STARTUP_INFO, creationflags=_CREATE_FLAGS,
        )
        device_list = []
        if result.returncode == 0:
            devices = result.stdout.strip().split("\n")[1:]
            for d in devices:
                if d.strip():
                    device_list.append(d.split()[0])
        return device_list
    except Exception as e:
        logger.error(f"List devices error: {e}")
        return []


class ADBController:
    """
    Android 设备基础操作控制器。
    封装了通过 ADB 执行的屏幕控制、应用管理、状态获取等底层方法。
    """
    def __init__(self, serial=None, adb_path=None, task_type="phone"):
        self.serial = serial
        self.adb_path = adb_path or _find_adb()
        self.task_type = task_type
        
        self.adb_cmd = [self.adb_path]
        if self.serial:
            self.adb_cmd.extend(['-s', self.serial])
            
        self.width = 0
        self.height = 0
        self._get_device_size()
        
    def run_shell(self, cmd_parts, timeout=None):
        """执行 adb shell 命令"""
        full_cmd = self.adb_cmd + ['shell'] + cmd_parts
        try:
            return subprocess.run(
                full_cmd, capture_output=True, text=True, timeout=timeout,
                startupinfo=_STARTUP_INFO, creationflags=_CREATE_FLAGS,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"ADB shell timeout: {' '.join(cmd_parts)}")
            return subprocess.CompletedProcess(args=full_cmd, returncode=-1, stdout="", stderr="Timeout")
        except Exception as e:
            logger.error(f"ADB shell error: {e}")
            return subprocess.CompletedProcess(args=full_cmd, returncode=-1, stdout="", stderr=str(e))

    def _get_device_size(self):
        """获取并缓存设备分辨率"""
        try:
            res = self.run_shell(['wm', 'size'])
            if res.stdout:
                parts = res.stdout.strip().split(": ")
                if len(parts) > 1:
                    size_str = parts[-1]
                    self.width, self.height = map(int, size_str.split("x"))
                    logger.info(f"设备分配率: {self.width}x{self.height}")
        except Exception as e:
            logger.warning(f"[{self.serial}] 获取设备尺寸失败: {e}")
            
    def modify_coordinate(self, x, y):
        """
        坐标转换，支持归一化坐标 [0,1] 或 百分比坐标，返回实际像素值。
        """
        if isinstance(x, list):
            y = x[1]
            x = x[0]

        x, y = float(x), float(y)

        if self.width == 0 or self.height == 0:
            self._get_device_size()
            if self.width == 0 or self.height == 0:
                logger.warning("设备尺寸为 0，坐标转换可能不准确")
                return int(x), int(y)

        if 0 <= x <= 1.02:
            x = self.width * x
        elif 1.02 < x <= 1000 and self.width > 1000:
            x = self.width * (x / 1000.0)

        if 0 <= y <= 1.02:
            y = self.height * y
        elif 1.02 < y <= 1000 and self.height > 1000:
            y = self.height * (y / 1000.0)

        x = max(0, min(int(x), max(self.width - 1, 0)))
        y = max(0, min(int(y), max(self.height - 1, 0)))
        return x, y

    def get_android_version(self):
        res = self.run_shell(['getprop', 'ro.build.version.release'])
        return res.stdout.strip() if res else "Unknown"

    def get_android_device_name(self):
        res = self.run_shell(['settings', 'get', 'global', 'device_name'])
        return res.stdout.strip() if res else "Unknown"

    def _get_top_package_name(self):
        """准确获取栈顶的应用包名"""
        try:
            # Plan A: mCurrentFocus
            res = self.run_shell(['dumpsys', 'window'], timeout=2)
            if res.stdout:
                for line in res.stdout.split('\n'):
                    if 'mCurrentFocus' in line and "phud" not in line:
                        match = re.search(r'([a-zA-Z0-9_.]+)/([a-zA-Z0-9_.]+)', line)
                        if match:
                            return match.group(1)
        except Exception:
            pass

        try:
            # Plan B: mFocusedApp
            res = self.run_shell(['dumpsys', 'activity'], timeout=2)
            if res.stdout:
                for line in res.stdout.split('\n'):
                    if 'mFocusedApp' in line:
                        match = re.search(r"u0\s+([a-zA-Z0-9_.]+)", line)
                        if match:
                            return match.group(1)
        except Exception:
            pass

        return None

    def get_foreground_info(self):
        """一次 ADB 调用同时获取前台应用标准名称和包名，避免重复 dumpsys。"""
        pkg_name = self._get_top_package_name()
        if pkg_name:
            try:
                pkg_to_std = get_package_to_std(self.task_type)
                app_name = pkg_to_std.get(pkg_name, pkg_name)
            except Exception:
                app_name = pkg_name
            return app_name, pkg_name
        return "未知应用", None

    def get_foreground_app(self):
        """获取前台应用的标准名称（如 '微信'，'抖音'）"""
        app_name, _ = self.get_foreground_info()
        return app_name

    def get_foreground_package(self):
        return self._get_top_package_name()

    def force_stop_app(self, package_name):
        try:
            result = self.run_shell(['am', 'force-stop', package_name])
            if result.returncode == 0:
                logger.info(f"已强制停止应用: {package_name}")
                return True
        except Exception as e:
            logger.error(f"强制停止应用异常: {e}")
        return False

    def force_stop_all_known_apps(self):
        try:
            target_packages = get_all_known_packages(self.task_type)
            whitelist = ["com.miui.home", "com.huawei.android.launcher", "com.android.systemui", 
                         "com.android.settings", "com.android.camera"] 
                         
            final_targets = [pkg.split('/')[0] for pkg in target_packages if pkg.split('/')[0] not in whitelist]
            final_targets = list(set(final_targets))

            for pkg in final_targets:
                self.run_shell(['am', 'force-stop', pkg])
            
            # 回到桌面
            self.run_shell(['input', 'keyevent', '3'])
            return True
        except Exception as e:
            logger.error(f"[ADB] 暴力清理后台失败: {e}", exc_info=True)
            return False

    @staticmethod
    def _is_valid_png(path: str) -> bool:
        """检查文件是否以 PNG magic bytes 开头。"""
        try:
            with open(path, "rb") as f:
                return f.read(8) == b'\x89PNG\r\n\x1a\n'
        except OSError:
            return False

    def get_screenshot(self, local_save_path):
        """
        截取屏幕并保存到本地。
        支持重试机制和 adb exec-out 快速拉取。
        """
        if self.width == 0:
            self._get_device_size()

        os.makedirs(os.path.dirname(os.path.abspath(local_save_path)), exist_ok=True)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = subprocess.run(
                    self.adb_cmd + ['exec-out', 'screencap', '-p'],
                    capture_output=True, timeout=10,
                    startupinfo=_STARTUP_INFO, creationflags=_CREATE_FLAGS,
                )
                stdout = result.stdout
                # adb 可能在 stdout 前混入文本警告（如 "[Warning] Multiple displays"），
                # 需要定位真正的 PNG 数据起始位置。
                png_magic = b'\x89PNG\r\n\x1a\n'
                png_offset = stdout.find(png_magic)
                if png_offset > 0:
                    logger.debug(f"[{self.serial}] 截图数据前有 {png_offset} 字节非 PNG 前缀，已跳过")
                    stdout = stdout[png_offset:]

                if stdout and stdout[:8] == png_magic:
                    with open(local_save_path, "wb") as f:
                        f.write(stdout)
                    return local_save_path
                else:
                    logger.warning(f"[{self.serial}] 截图非有效PNG, 重试 {attempt+1}/{max_retries}")
            except Exception as e:
                logger.warning(f"[{self.serial}] 截图异常: {e}, 重试 {attempt+1}")
            time.sleep(1)

        # Fallback 到 screencap + pull
        try:
            logger.info("尝试回退到 screencap + pull")
            remote_path = "/sdcard/temp_screen_fallback.png"
            self.run_shell(['rm', remote_path])
            self.run_shell(['screencap', '-p', remote_path])
            subprocess.run(
                self.adb_cmd + ['pull', remote_path, local_save_path],
                capture_output=True,
                startupinfo=_STARTUP_INFO, creationflags=_CREATE_FLAGS,
            )
            self.run_shell(['rm', remote_path])

            if os.path.exists(local_save_path) and self._is_valid_png(local_save_path):
                return local_save_path
            elif os.path.exists(local_save_path):
                logger.warning("Fallback 截图文件非有效 PNG")
        except Exception as e:
            logger.error(f"Fallback 截图模式失败: {e}")

        logger.error("所有截图手段失效，构建纯黑图。")
        try:
            w = self.width if self.width > 0 else 1080
            h = self.height if self.height > 0 else 1920
            img = Image.new('RGB', (w, h), color='black')
            img.save(local_save_path)
        except Exception:
            pass
        return local_save_path

    # ==================== 动作底层执行 ====================
    
    def tap_point(self, x, y):
        x, y = self.modify_coordinate(x, y)
        self.run_shell(['input', 'tap', str(int(x)), str(int(y))])

    def long_press(self, x, y, duration_ms=2000):
        x, y = self.modify_coordinate(x, y)
        self.run_shell(['input', 'touchscreen', 'swipe', str(x), str(y), str(x), str(y), str(duration_ms)])

    def swipe(self, x1, y1, x2, y2, duration=400):
        x1, y1 = self.modify_coordinate(x1, y1)
        x2, y2 = self.modify_coordinate(x2, y2)
        self.run_shell(['input', 'swipe', str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(duration)])

    def input_text(self, text, by_broadcast=True):
        if not text:
            return
            
        if by_broadcast:
            # 检查是否有 adbkeyboard，这个输入方式需要特定的输入法
            res = self.run_shell(['pm', 'list', 'packages', 'com.android.adbkeyboard'])
            if res and res.stdout and 'com.android.adbkeyboard' in res.stdout:
                b64_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")
                self.run_shell(['am', 'broadcast', '-a', 'ADB_INPUT_B64', '--es', 'msg', b64_text])
                return
                
        # 原生 input text fallback
        safe_text = text.replace(' ', '%s').replace("'", "")
        self.run_shell(['input', 'text', safe_text])

    def press_key(self, key_code):
        if isinstance(key_code, str):
            # 如 KEYCODE_BACK, KEYCODE_ENTER, \
            self.run_shell(['input', 'keyevent', key_code])
        else:
            self.run_shell(['input', 'keyevent', str(key_code)])
            
    def open_app_by_package(self, package):
        """启动应用，按可靠性依次尝试多种方式"""
        # 方法1: am start with package (最通用，Android 7+ 都支持)
        r = self.run_shell([
            'am', 'start',
            '-a', 'android.intent.action.MAIN',
            '-c', 'android.intent.category.LAUNCHER',
            '-p', package,
        ])
        if r.returncode == 0 and 'Error' not in (r.stdout or '') and 'Error' not in (r.stderr or ''):
            logger.info(f"am start 启动成功: {package}")
            return

        # 方法2: monkey (某些设备上 am start -p 不行但 monkey 可以)
        r = self.run_shell(['monkey', '-p', package, '-c', 'android.intent.category.LAUNCHER', '1'])
        if r.returncode == 0 and 'No activities found' not in (r.stdout or ''):
            logger.info(f"monkey 启动成功: {package}")
            return

        # 方法3: 解析具体 activity 再 am start -n
        result = self.run_shell([
            'cmd', 'package', 'resolve-activity', '--brief',
            '-a', 'android.intent.action.MAIN',
            '-c', 'android.intent.category.LAUNCHER',
            package,
        ])
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().splitlines()
            component = lines[-1].strip() if lines else ""
            if '/' in component:
                r = self.run_shell(['am', 'start', '-n', component])
                if r.returncode == 0:
                    logger.info(f"am start -n 启动成功: {component}")
                    return

        logger.error(f"所有方式均无法启动 {package}")
        
    def open_mini_program(self, uri):
        """通过 deeplink/URI 启动小程序"""
        self.run_shell(['am', 'start', '-a', 'android.intent.action.VIEW', '-d', uri])
