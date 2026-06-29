#!/usr/bin/env bash
# -------------------------------------------------------
# Guiness 一键打包
#
# 产物：
#   dist/Guiness.app        （macOS；Linux = dist/Guiness，Windows = dist/Guiness.exe）
#   dist/Guiness-Controller.apk   （Android 手机端 APK）
#
# 用法：
#   bash build.sh              一次全部打
#   bash build.sh --no-apk     跳过 Android
#   bash build.sh --no-pc      只打 APK
#   bash build.sh --skip-deps  不自动装 Python 依赖（假设环境已就绪）
# -------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 参数 ──
BUILD_PC=1
BUILD_APK=1
AUTO_INSTALL_DEPS=1
for arg in "$@"; do
    case "$arg" in
        --no-apk)    BUILD_APK=0 ;;
        --no-pc)     BUILD_PC=0 ;;
        --skip-deps) AUTO_INSTALL_DEPS=0 ;;
        -h|--help)
            sed -n '2,15p' "$0"
            exit 0
            ;;
        *) echo "未知参数: $arg"; exit 1 ;;
    esac
done

echo "=== Guiness 打包 ==="

# ── 平台检测 ──
OS="$(uname -s)"
case "$OS" in
    Darwin*)  PLATFORM="macOS"  ; PT_OS="darwin"  ;;
    Linux*)   PLATFORM="Linux"  ; PT_OS="linux"   ;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="Windows" ; PT_OS="windows" ;;
    *)        PLATFORM="Unknown"; PT_OS=""       ;;
esac
echo "当前平台: $PLATFORM"
echo "PC 端: $([ $BUILD_PC -eq 1 ] && echo yes || echo no)  APK: $([ $BUILD_APK -eq 1 ] && echo yes || echo no)"
echo ""

# ───────────────────────────────────────────────
# Vendor Android platform-tools
#
# 工具要发给机器上没装 ADB 的用户，所以把官方 platform-tools 抓下来跟 app 一起打包。
# 这里按打包目标 OS 下载（build.sh 当前运行 OS == 产物 OS，跨编译不走这里）。
# 下载地址：https://dl.google.com/android/repository/platform-tools-latest-<os>.zip
# 只需要 adb + 若干 dylib/dll；zip 里其它小工具（fastboot/dmtracedump 等）一起带着问题不大。
# ───────────────────────────────────────────────
fetch_platform_tools() {
    local os_key="$1"   # darwin | linux | windows
    if [ -z "$os_key" ]; then
        echo "[WARN] 未知平台，跳过 platform-tools 下载（打包后程序将依赖用户本机 adb）"
        return 0
    fi

    local vendor_root="$SCRIPT_DIR/vendor/platform-tools/$os_key"
    local adb_bin
    if [ "$os_key" = "windows" ]; then
        adb_bin="$vendor_root/adb.exe"
    else
        adb_bin="$vendor_root/adb"
    fi

    if [ -f "$adb_bin" ]; then
        echo "[ OK ] 已有 vendor/platform-tools/$os_key"
        return 0
    fi

    mkdir -p "$vendor_root"
    local zip_url="https://dl.google.com/android/repository/platform-tools-latest-${os_key}.zip"
    local tmp_dir
    tmp_dir="$(mktemp -d)"
    local zip_path="$tmp_dir/pt.zip"

    echo "[..] 下载 platform-tools ($os_key): $zip_url"
    if command -v curl >/dev/null 2>&1; then
        if ! curl -fL --retry 3 -o "$zip_path" "$zip_url"; then
            echo "[FAIL] curl 下载失败: $zip_url"
            rm -rf "$tmp_dir"
            return 1
        fi
    elif command -v wget >/dev/null 2>&1; then
        if ! wget -q -O "$zip_path" "$zip_url"; then
            echo "[FAIL] wget 下载失败: $zip_url"
            rm -rf "$tmp_dir"
            return 1
        fi
    else
        echo "[FAIL] 需要 curl 或 wget 才能下载 platform-tools"
        rm -rf "$tmp_dir"
        return 1
    fi

    if ! command -v unzip >/dev/null 2>&1; then
        echo "[FAIL] 需要 unzip 才能解压 platform-tools"
        rm -rf "$tmp_dir"
        return 1
    fi
    unzip -q -o "$zip_path" -d "$tmp_dir"

    # 官方 zip 解压后是 platform-tools/<files>
    if [ ! -d "$tmp_dir/platform-tools" ]; then
        echo "[FAIL] 解压后未找到 platform-tools 目录"
        rm -rf "$tmp_dir"
        return 1
    fi

    # 搬运到 vendor_root（已 mkdir，上面可能留了空目录）
    rm -rf "$vendor_root"
    mv "$tmp_dir/platform-tools" "$vendor_root"
    rm -rf "$tmp_dir"

    if [ "$os_key" != "windows" ]; then
        chmod +x "$vendor_root/adb" 2>/dev/null || true
    fi
    echo "[ OK ] vendor/platform-tools/$os_key 就绪"
    return 0
}

if [ $BUILD_PC -eq 1 ] && [ -n "$PT_OS" ]; then
    echo "--- Android platform-tools vendor ---"
    if ! fetch_platform_tools "$PT_OS"; then
        echo "[WARN] platform-tools 未 vendor 成功，打包后程序将依赖用户本机 adb"
    fi
    export GUINESS_PLATFORM_TOOLS_OS="$PT_OS"
    echo ""
fi

# ───────────────────────────────────────────────
# 环境检查
# ───────────────────────────────────────────────
ERRORS=0

check_python() {
    if ! command -v python3 &>/dev/null; then
        echo "[FAIL] 未找到 python3（Guiness 要求 Python 3.9+）"
        ERRORS=$((ERRORS + 1))
        return
    fi
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
    PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
        echo "[FAIL] Python 版本 $PY_VERSION 过低，需要 >= 3.9"
        ERRORS=$((ERRORS + 1))
    else
        echo "[ OK ] Python $PY_VERSION"
    fi
}

check_java() {
    if ! command -v java &>/dev/null; then
        echo "[FAIL] 未找到 java（APK 构建需要 JDK 17+；或 export JAVA_HOME 指向 JDK）"
        ERRORS=$((ERRORS + 1))
        return
    fi
    # 用 -version 输出的第一行判大版本；OpenJDK 会输出 "openjdk version \"17.0.x\""
    JV=$(java -version 2>&1 | head -n1)
    echo "[ OK ] $JV"
}

install_python_deps() {
    echo "---- 安装 / 升级 Python 依赖 ----"
    python3 -m pip install --upgrade pip setuptools wheel
    # requirements.txt 包含运行时依赖；pyinstaller 只在打包阶段用
    python3 -m pip install -r requirements.txt
    python3 -m pip install "pyinstaller>=6.0"
    echo "---- Python 依赖就绪 ----"
}

check_python_packages() {
    # import_name:pip_name；两端同名时只写一半
    local packages=(
        "PySide6:PySide6"
        "yaml:PyYAML"
        "requests:requests"
        "PIL:Pillow"
        "uiautomator2:uiautomator2"
        "websockets:websockets"
    )
    local missing=0
    for spec in "${packages[@]}"; do
        local import_name="${spec%%:*}"
        local pip_name="${spec##*:}"
        if python3 -c "import $import_name" 2>/dev/null; then
            echo "[ OK ] $pip_name"
        else
            echo "[MISS] $pip_name"
            missing=$((missing + 1))
        fi
    done
    # pyinstaller 是可执行 + 模块；两者都要有
    if ! python3 -c "import PyInstaller" 2>/dev/null; then
        echo "[MISS] pyinstaller"
        missing=$((missing + 1))
    else
        PI_VER=$(python3 -c "import PyInstaller; print(PyInstaller.__version__)" 2>/dev/null || echo unknown)
        echo "[ OK ] pyinstaller $PI_VER"
    fi
    return $missing
}

check_files() {
    local required=(
        "main.py"
        "build_config.spec"
        "config.yaml"
        "gui/styles/theme.qss"
    )
    if [ $BUILD_APK -eq 1 ]; then
        required+=("android/gradlew" "android/app/build.gradle.kts")
    fi
    for f in "${required[@]}"; do
        if [ -f "$SCRIPT_DIR/$f" ] || [ -d "$SCRIPT_DIR/$f" ]; then
            echo "[ OK ] $f"
        else
            echo "[FAIL] 缺少文件: $f"
            ERRORS=$((ERRORS + 1))
        fi
    done
}

echo "--- 环境检查 ---"
check_python
if [ $BUILD_APK -eq 1 ]; then
    check_java
fi
check_files
echo ""

# ── Python 依赖：先检查，不行就装 ──
if [ $BUILD_PC -eq 1 ]; then
    echo "--- Python 依赖检查 ---"
    set +e
    check_python_packages
    dep_missing=$?
    set -e
    if [ $dep_missing -gt 0 ]; then
        if [ $AUTO_INSTALL_DEPS -eq 1 ]; then
            install_python_deps
            # 装完再核一次
            set +e
            check_python_packages
            dep_missing=$?
            set -e
            if [ $dep_missing -gt 0 ]; then
                echo "[FAIL] 自动安装后仍缺 $dep_missing 个包，请手动排查"
                ERRORS=$((ERRORS + 1))
            fi
        else
            echo "[FAIL] 缺 $dep_missing 个 Python 包（--skip-deps 已开，不自动装）"
            ERRORS=$((ERRORS + 1))
        fi
    fi
    echo ""
fi

# ── main.py 语法自检 ──
if [ $BUILD_PC -eq 1 ] && [ -f "$SCRIPT_DIR/main.py" ]; then
    if python3 -c "import py_compile; py_compile.compile('main.py', doraise=True)" 2>/dev/null; then
        echo "[ OK ] main.py 语法正确"
    else
        echo "[FAIL] main.py 存在语法错误"
        ERRORS=$((ERRORS + 1))
    fi
fi

if [ "$ERRORS" -gt 0 ]; then
    echo ""
    echo "=== 环境检查失败：$ERRORS 个问题 ==="
    exit 1
fi

echo ""
echo "=== 环境检查通过 ==="
echo ""

# ── 清理旧产物 ──
echo "清理旧的构建产物..."
rm -rf build/ dist/
mkdir -p dist/

# ───────────────────────────────────────────────
# Android APK
# ───────────────────────────────────────────────
if [ $BUILD_APK -eq 1 ]; then
    echo ""
    echo "=== 构建 Android APK ==="
    pushd "$SCRIPT_DIR/android" >/dev/null
    # assembleDebug 够用且不需要签名；要 release 就改 assembleRelease + 在
    # app/build.gradle.kts 里配 signingConfigs
    ./gradlew :app:assembleDebug
    popd >/dev/null

    APK_SRC="$SCRIPT_DIR/android/app/build/outputs/apk/debug/app-debug.apk"
    if [ ! -f "$APK_SRC" ]; then
        echo "[FAIL] 未找到 APK 产物: $APK_SRC"
        exit 1
    fi
    cp "$APK_SRC" "$SCRIPT_DIR/dist/Guiness-Controller.apk"
    echo "[ OK ] APK 输出: dist/Guiness-Controller.apk"
fi

# ───────────────────────────────────────────────
# PC 端（PyInstaller）
# ───────────────────────────────────────────────
if [ $BUILD_PC -eq 1 ]; then
    echo ""
    echo "=== 构建 PC 端 ==="
    # 注意：PyInstaller 会把 dist/ 当输出根目录，所以前面的 rm -rf 后面的
    # cp APK 顺序不能乱——APK 必须在 pyinstaller 之后再拷回来
    pyinstaller build_config.spec --noconfirm

    # 把 APK 塞进 PC 产物里，方便分发时一起带走
    if [ $BUILD_APK -eq 1 ] && [ -f "$SCRIPT_DIR/dist/Guiness-Controller.apk" ]; then
        echo "重新放置 APK（pyinstaller 会清理 dist/，需要再拷一次）"
        cp "$SCRIPT_DIR/android/app/build/outputs/apk/debug/app-debug.apk" \
            "$SCRIPT_DIR/dist/Guiness-Controller.apk"
    fi

    # ───────────────────────────────────────
    # macOS：深度重签 + ditto 打包
    # PyInstaller 默认的 ad-hoc 签名不覆盖所有内嵌 Qt framework，
    # 同时 Finder 右键压缩会破坏 bundle 符号链接 → 对方 Mac 报"已损坏"。
    # 这里统一用 codesign --deep 覆盖所有二进制，再用 ditto 打可分发 zip。
    # ───────────────────────────────────────
    if [ "$PLATFORM" = "macOS" ] && [ -d "$SCRIPT_DIR/dist/Guiness.app" ]; then
        APP_PATH="$SCRIPT_DIR/dist/Guiness.app"
        echo ""
        echo "--- macOS 深度重签 (ad-hoc) ---"

        # 1) 清理悬空符号链接
        #    build_config.spec 过滤掉部分 Qt framework 的二进制后，
        #    框架目录里指向那些二进制的符号链接就成了死链接，
        #    codesign --verify 碰到会直接报错，Gatekeeper 会判为已损坏。
        DANGLING_COUNT=0
        while IFS= read -r -d '' link; do
            DANGLING_COUNT=$((DANGLING_COUNT + 1))
            rm -f "$link"
        done < <(find "$APP_PATH" -type l ! -exec test -e {} \; -print0 2>/dev/null)
        if [ "$DANGLING_COUNT" -gt 0 ]; then
            echo "[ OK ] 清理 $DANGLING_COUNT 个悬空符号链接"
        fi

        # 2) 连带清理空的 framework 壳（没有二进制的 .framework 目录）
        EMPTY_FW_COUNT=0
        while IFS= read -r -d '' fw; do
            name=$(basename "$fw" .framework)
            if [ ! -f "$fw/$name" ] && [ ! -f "$fw/Versions/A/$name" ] && [ ! -f "$fw/Versions/Current/$name" ]; then
                EMPTY_FW_COUNT=$((EMPTY_FW_COUNT + 1))
                rm -rf "$fw"
            fi
        done < <(find "$APP_PATH" -type d -name "*.framework" -print0 2>/dev/null)
        if [ "$EMPTY_FW_COUNT" -gt 0 ]; then
            echo "[ OK ] 清理 $EMPTY_FW_COUNT 个空的 framework 目录"
        fi

        # 3) 清掉 PyInstaller/Finder 写入的冗余扩展属性，避免干扰签名哈希
        xattr -cr "$APP_PATH" 2>/dev/null || true

        # 4) 深度签名：--deep 递归签所有 Qt framework / dylib
        #    不加 --options runtime：未公证的 ad-hoc 启用 hardened runtime
        #    会因缺失 Python 所需的 allow-jit / allow-unsigned-executable-memory 权益而拒绝启动
        if codesign --force --deep --sign - "$APP_PATH" 2>/tmp/guiness-codesign.log; then
            echo "[ OK ] 深度重签完成"
        else
            echo "[FAIL] codesign 失败："
            sed 's/^/  /' /tmp/guiness-codesign.log | head -20
            exit 1
        fi

        # 5) 校验签名完整性
        if codesign --verify --deep --strict --verbose=2 "$APP_PATH" >/tmp/guiness-verify.log 2>&1; then
            echo "[ OK ] codesign --verify 通过"
        else
            echo "[WARN] codesign --verify 报告如下，分发前请排查："
            sed 's/^/  /' /tmp/guiness-verify.log | head -20
        fi

        # 6) 用 Apple 官方 ditto 打包：保留符号链接/扩展属性/签名元数据
        #    不要用 Finder 右键压缩 或 zip 命令，都会毁 bundle。
        echo "--- 打包可分发 zip (ditto) ---"
        ZIP_OUT="$SCRIPT_DIR/dist/Guiness.app.zip"
        rm -f "$ZIP_OUT"
        ( cd "$SCRIPT_DIR/dist" && \
          ditto -c -k --sequesterRsrc --keepParent Guiness.app Guiness.app.zip )
        if [ -f "$ZIP_OUT" ]; then
            ZIP_SIZE=$(du -sh "$ZIP_OUT" | cut -f1)
            echo "[ OK ] 分发 zip: dist/Guiness.app.zip [$ZIP_SIZE]"
        else
            echo "[FAIL] ditto 未生成 zip"
            exit 1
        fi
    fi
fi

# ───────────────────────────────────────────────
# 总结
# ───────────────────────────────────────────────
echo ""
echo "=== 打包完成 ==="
if [ $BUILD_PC -eq 1 ]; then
    case "$PLATFORM" in
        macOS)
            echo "PC 产物:"
            echo "  dist/Guiness.app          本机直接双击运行"
            echo "  dist/Guiness.app.zip      ★ 给别人用的就发这个（ditto 打包，保留签名）"
            echo ""
            echo "【分发须知】切勿再用 Finder 右键压缩或 zip 命令重打包——会破坏符号链接，对方必然报「已损坏」。"
            echo ""
            echo "【对方收到后】双击 zip 解压出 Guiness.app，然后任选一种方式首次打开："
            echo "  方式 A（推荐）：在 Finder 中 右键 Guiness.app → 打开 → 弹窗里再点 \"任然打开\""
            echo "  方式 B（命令行）：xattr -cr /path/to/Guiness.app && open /path/to/Guiness.app"
            echo ""
            echo "首次放行后，之后双击即可正常启动。若仍报「已损坏」，八成是"
            echo "中途被微信/QQ 二次压缩过——让对方直接从原始 zip 解压。"
            ;;
        Linux)
            echo "PC 产物: dist/Guiness"
            echo "运行:    ./dist/Guiness"
            echo ""
            echo "【目标机器依赖】Qt 需要 libxcb-cursor0、libfontconfig1 等；"
            echo "Ubuntu 22.04+ 若启动失败请 apt install libxcb-cursor0 libxkbcommon-x11-0"
            ;;
        Windows)
            echo "PC 产物: dist\\Guiness.exe"
            echo "运行:    双击 dist\\Guiness.exe"
            ;;
        *)
            echo "PC 产物: dist/"
            ;;
    esac
fi
if [ $BUILD_APK -eq 1 ]; then
    echo ""
    echo "APK 产物: dist/Guiness-Controller.apk"
    echo "安装:     adb install -r dist/Guiness-Controller.apk"
fi
