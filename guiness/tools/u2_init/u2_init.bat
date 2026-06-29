@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Guiness - U2 Init Tool

echo ============================================================
echo           Guiness U2 Init Tool
echo ============================================================
echo.
echo  This tool installs uiautomator2 ATX Agent on your phone.
echo  Make sure:
echo    1. Phone is connected via USB
echo    2. USB debugging is enabled
echo    3. You have authorized this PC on the phone
echo.
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "ADB="

:: Find adb - check same directory first
if exist "%SCRIPT_DIR%adb.exe" (
    set "ADB=%SCRIPT_DIR%adb.exe"
    echo [OK] Found adb in script directory
    goto :found_adb
)

:: Check common platform-tools location
if exist "C:\platform-tools-latest-windows\platform-tools\adb.exe" (
    set "ADB=C:\platform-tools-latest-windows\platform-tools\adb.exe"
    echo [OK] Found adb in C:\platform-tools-latest-windows\platform-tools\
    goto :found_adb
)

:: Check Guiness vendor directory
if exist "%SCRIPT_DIR%..\..\vendor\platform-tools\win\adb.exe" (
    set "ADB=%SCRIPT_DIR%..\..\vendor\platform-tools\win\adb.exe"
    echo [OK] Found adb in vendor directory
    goto :found_adb
)

:: Check system PATH
where adb.exe >nul 2>&1
if !errorlevel! equ 0 (
    set "ADB=adb.exe"
    echo [OK] Found adb in system PATH
    goto :found_adb
)

echo [ERROR] adb.exe not found!
echo         Please put adb.exe in the same folder as this script,
echo         or install platform-tools to C:\platform-tools-latest-windows\platform-tools\
echo.
pause
exit /b 1

:found_adb
echo.

:: Check device connection
echo [Step 1/4] Checking device connection...
"!ADB!" devices > "%TEMP%\u2_init_devices.txt" 2>&1
findstr /r "device$" "%TEMP%\u2_init_devices.txt" >nul
if !errorlevel! neq 0 (
    echo [ERROR] No Android device detected!
    echo         Please check USB connection and debugging authorization.
    echo.
    type "%TEMP%\u2_init_devices.txt"
    echo.
    pause
    exit /b 1
)

for /f "tokens=1" %%i in ('findstr /r "device$" "%TEMP%\u2_init_devices.txt"') do (
    echo         Connected device: %%i
)
echo.

:: Push u2.jar
echo [Step 2/4] Pushing u2.jar to phone...
if not exist "%SCRIPT_DIR%u2.jar" (
    echo [ERROR] u2.jar not found in script directory!
    pause
    exit /b 1
)
"!ADB!" push "%SCRIPT_DIR%u2.jar" /data/local/tmp/u2.jar
:: Verify file exists on device (adb push may return error even on success)
"!ADB!" shell ls /data/local/tmp/u2.jar >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Failed to push u2.jar!
    pause
    exit /b 1
)
echo         u2.jar pushed successfully
echo.

:: Install AdbKeyboard APK
echo [Step 3/4] Installing AdbKeyboard...
if not exist "%SCRIPT_DIR%app-uiautomator.apk" (
    echo [ERROR] app-uiautomator.apk not found in script directory!
    pause
    exit /b 1
)
"!ADB!" install -r "%SCRIPT_DIR%app-uiautomator.apk"
if !errorlevel! neq 0 (
    echo [WARN] Install failed, trying uninstall first...
    "!ADB!" uninstall com.github.uiautomator >nul 2>&1
    "!ADB!" install "%SCRIPT_DIR%app-uiautomator.apk"
    if !errorlevel! neq 0 (
        echo [ERROR] AdbKeyboard install failed!
        pause
        exit /b 1
    )
)
echo         AdbKeyboard installed successfully
echo.

:: Enable AdbKeyboard IME
echo [Step 4/4] Enabling AdbKeyboard IME...
"!ADB!" shell ime enable com.github.uiautomator/.AdbKeyboard >nul 2>&1
echo         AdbKeyboard enabled
echo.

echo ============================================================
echo  Done! You can now use Guiness normally.
echo ============================================================
echo.
pause
