# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Guiness

Build:
    pyinstaller build_config.spec
"""

import sys
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# uiautomator2 的子模块（_input / _selector / core / swipe / xpath ...）与它的
# 传递依赖（adbutils、lxml-free 分支下的 logzero、retry、deprecation ...）
# PyInstaller 的静态分析抓不全——只写 hiddenimports=['uiautomator2'] 会让
# 顶层 `import uiautomator2` 在打包环境里抛 ImportError，被 device/automator.py
# 的 except 吞掉，外部看只是 "uiautomator2 package not installed"。
# 用 collect_submodules 递归抓整包。
def _maybe_collect(name: str):
    """本机没装这个包就返回空，避免 spec 自身炸。"""
    try:
        __import__(name)
    except ImportError:
        return []
    return collect_submodules(name)


_u2_submodules = (
    collect_submodules("uiautomator2")
    + collect_submodules("adbutils")
    + collect_submodules("lxml")          # u2 硬依赖 lxml.etree
    + collect_submodules("retry")         # u2 依赖 `from retry import retry`
    + _maybe_collect("deprecation")       # adbutils 可选依赖
)

# uiautomator2 自带 u2.jar + app-uiautomator.apk，首次连接设备时会 push 过去并装
# AdbKeyboard；缺了它们就只剩 u2.connect 能握手，set_fastinput_ime 无效，
# send_keys 的 ADB_KEYBOARD_INPUT_TEXT 广播没人接——表现为 build 后 Type/Search
# 静默失败，而 python main.py 正常（能直接读 site-packages）。
_u2_datas = collect_data_files("uiautomator2", includes=["assets/*", "*.json"])


# ── Bundle Android platform-tools ──
# build.sh 会按目标 OS 把 platform-tools 解压到 vendor/platform-tools/<os>/；
# 打包时全部塞到 bundle 的 "platform-tools/" 子目录下，运行时 _bundled_adb()
# 会去 _MEIPASS / <exe_dir>/platform-tools/ 找 adb。没 vendor 过就跳过
# （用户本机必须已装 ADB 才能跑，和历史行为一致）。
def _collect_platform_tools():
    os_key = os.environ.get("GUINESS_PLATFORM_TOOLS_OS", "")
    if not os_key:
        if sys.platform == "darwin":
            os_key = "darwin"
        elif sys.platform.startswith("win"):
            os_key = "windows"
        else:
            os_key = "linux"

    spec_dir = os.path.dirname(os.path.abspath(SPEC))
    root = os.path.join(spec_dir, "vendor", "platform-tools", os_key)
    if not os.path.isdir(root):
        return []

    items = []
    for dirpath, _dirs, files in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for fn in files:
            src = os.path.join(dirpath, fn)
            if rel_dir == ".":
                dest = "platform-tools"
            else:
                dest = os.path.join("platform-tools", rel_dir)
            items.append((src, dest))
    return items


_platform_tools_datas = _collect_platform_tools()

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('gui/styles/theme.qss', 'gui/styles'),
        ('config.yaml', '.'),
        ('resources/icon_256.png', 'resources'),
        ('resources/app.ico', 'resources'),
        ('apps/data/phone.yaml', 'apps/data'),
        ('apps/data/car.yaml', 'apps/data'),
        ('model/preset_models.yaml', 'model'),
        ('model/adapters/prompts/gemini.txt', 'model/adapters/prompts'),
        ('model/adapters/prompts/claude.txt', 'model/adapters/prompts'),
        ('model/adapters/prompts/gpt.txt', 'model/adapters/prompts'),
        ('model/adapters/prompts/doubao.txt', 'model/adapters/prompts'),
        ('model/adapters/prompts/autoglm.txt', 'model/adapters/prompts'),
        ('model/adapters/prompts/step_gui.txt', 'model/adapters/prompts'),
        ('model/adapters/prompts/realgui.txt', 'model/adapters/prompts'),
    ] + ([('vendor/scrcpy/scrcpy-server.jar', 'scrcpy')] if os.path.isfile('vendor/scrcpy/scrcpy-server.jar') else []
    ) + _u2_datas + _platform_tools_datas,
    hiddenimports=[
        'PySide6.QtWidgets',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'yaml',
        'requests',
        'PIL',
        'uiautomator2',
        'adbutils',
        'websockets',
        'websockets.sync',
        'websockets.sync.client',
        'websockets.client',
        'websockets.protocol',
        # ── gui ──
        'gui',
        'gui.app',
        'gui.chat_manager',
        'gui.cleanup',
        'gui.output_sync',
        'gui.paths',
        'gui.styles',
        'gui.styles.theme',
        'gui.styles.tokens',
        'gui.pages',
        'gui.pages.config_page',
        'gui.pages.config',
        'gui.pages.config.advanced_section',
        'gui.pages.config.model_section',
        'gui.pages.config.task_section',
        'gui.pages.result_page',
        'gui.pages.result',
        'gui.pages.result.detail_section',
        'gui.pages.result.tree_section',
        'gui.widgets',
        'gui.widgets.sidebar',
        'gui.widgets.chat_feed',
        'gui.widgets.step_card',
        'gui.widgets.message_bubble',
        'gui.widgets.input_bar',
        'gui.widgets.model_config_panel',
        'gui.widgets.screenshot_viewer',
        'gui.widgets.settings_dialog',
        'gui.widgets.screen_mirror_dialog',
        'gui.widgets.live_mirror_viewport',
        'gui.widgets.pairing_dialog',
        'gui.widgets.collapsible_section',
        'gui.widgets.log_viewer',
        'gui.widgets.timeline_panel',
        'gui.pairing',
        'gui.pairing.payload',
        'gui.pairing.server',
        'gui.pairing.qrcode',
        'qrcode',
        'qrcode.image.pil',
        'gui.workers',
        'gui.workers.episode_worker',
        'gui.workers.preflight_worker',
        'gui.workers.device_pulse_worker',
        'gui.workers.screen_stream_worker',
        # ── device ──
        'device',
        'device.adb_controller',
        'device.automator',
        'device.backend',
        'device.adb_backend',
        'device.wifi_backend',
        'device.scrcpy_client',
        'device._coord',
        # ── model ──
        'model',
        'model.inference_client',
        'model.response_parser',
        'model.device_info',
        'model.adapters',
        'model.adapters._common',
        'model.adapters.gemini',
        'model.adapters.claude',
        'model.adapters.gpt',
        'model.adapters.doubao',
        'model.adapters.autoglm',
        'model.adapters.step_gui',
        'model.adapters.realgui',
        # ── engine ──
        'runner',
        'runner.episode_runner',
        'action',
        'action.action_space',
        'action.action_executor',
        'apps',
        'apps.registry',
        'core',
        'core.config',
        'core.setup',
        'reporter',
        'reporter.base',
        'reporter.cli_reporter',
        'utils',
        'utils.config_loader',
        'utils.image_utils',
        # ── scrcpy / PyAV (实时镜像) ──
        'av',
        'av.codec',
        'av.video',
        'numpy',
    ] + _u2_submodules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'boto3',
        'botocore',
        's3cmd',
        'flask',
        'flask_cors',
        'flask_socketio',
        'socketio',
        'matplotlib',
        'tkinter',
        'pytest',
        # PyInstaller 不允许同时打包多个 Qt 绑定；本机若装了 PyQt5/PyQt6
        # (例如 qrcode/其他依赖拉进来的) 会和 PySide6 冲突，一律排除
        'PyQt5',
        'PyQt6',
        'PySide2',
        # ── 瘦身：排除不需要的大模块 ──
        'cv2',
        # numpy 不能排除——PyAV (av) 解码 scrcpy H.264 流时需要 to_ndarray()
        # 注意：lxml 不能排除——uiautomator2.__init__ 硬依赖 `from lxml import etree`，
        # 漏了之后打包里 `import uiautomator2` 就 raise ImportError，所有中文 Type/Search
        # 走 ADB fallback 全部废掉（Android 原生 `input text` 不认非 ASCII）。
        'PySide6.QtQuick',
        'PySide6.QtQml',
        'PySide6.QtPdf',
        'PySide6.QtDBus',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.QtMultimedia',
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtPositioning',
        'PySide6.QtRemoteObjects',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtTest',
        'PySide6.QtXml',
    ],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

# ── 打包前过滤：移除不需要的二进制文件 ──
_QT_KEEP = {'QtCore', 'QtGui', 'QtWidgets', 'QtNetwork', 'QtDBus'}
_filtered_binaries = []
for dest, src, typecode in a.binaries:
    skip = False
    # 排除不需要的 Qt framework
    if '/Qt/lib/' in dest or '\\Qt\\lib\\' in dest:
        fname = dest.split('/')[-1].split('\\')[-1]
        framework_name = fname.replace('.framework', '').split('.')[0]
        if framework_name.startswith('Qt') and framework_name not in _QT_KEEP:
            skip = True
    # PIL dylib 全部保留，避免连锁依赖缺失
    # 排除 Qt translations
    if '/translations/' in dest:
        skip = True
    if not skip:
        _filtered_binaries.append((dest, src, typecode))

a.binaries = _filtered_binaries

pyz = PYZ(a.pure, cipher=block_cipher)

if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='Guiness',
        debug=False,
        bootloader_ignore_signals=False,
        strip=True,
        upx=True,
        console=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=True,
        upx=True,
        name='Guiness',
    )
    app = BUNDLE(
        coll,
        name='Guiness.app',
        icon='resources/app.ico',
        bundle_identifier='com.xiaoai.guiness',
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': '1.0.0',
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='Guiness',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        icon='resources/app.ico',
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
