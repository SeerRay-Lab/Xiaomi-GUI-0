#!/bin/bash

# Start Emulator
#============================================
# ./docker_setup/start_emu_headless.sh && \
# adb root && \
# python3 -m server.android_server

# sleep inf

# export EMULATOR_NAME=BaseAvd
# export CONSOLE_PORT=5554
# export GRPC_PORT=8554
# export EMULATOR_SETUP=true
# export FREEZE_DATETIME=true
export ANDROID_SDK_ROOT="/root/.android"
export PATH="$PATH:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/tools"

bash ./docker_setup/start_emu_headless.sh

OLD_PATH="$PATH"
source /root/miniforge3/etc/profile.d/conda.sh && conda activate android_world
export PATH="$PATH:$OLD_PATH" && \
(
  for i in {1..5}; do
    echo "正在尝试 adb root (第 $i 次)..."
    # 尝试执行 root，如果成功(返回0)则跳出循环
    adb -s emulator-${CONSOLE_PORT} root && echo "Root 指令发送成功，等待设备重连..." && adb -s emulator-${CONSOLE_PORT} wait-for-device && break
    
    echo "Root 失败或连接断开，3秒后重试..."
    sleep 3
  done
) && \
python3 -m android_server
