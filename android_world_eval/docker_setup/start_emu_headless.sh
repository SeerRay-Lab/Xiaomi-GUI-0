#!/bin/bash


# Credits to https://github.com/amrsa1/Android-Emulator-image

# export ANDROID_EMULATOR_USE_IPV6_LOCALHOST=0

BL='\033[0;34m'
G='\033[0;32m'
RED='\033[0;31m'
YE='\033[1;33m'
NC='\033[0m' # No Color
emulator_name=${EMULATOR_NAME}

function check_hardware_acceleration() {
    if [[ "$HW_ACCEL_OVERRIDE" != "" ]]; then
        hw_accel_flag="$HW_ACCEL_OVERRIDE"
    else
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS-specific hardware acceleration check
            HW_ACCEL_SUPPORT=$(sysctl -a | grep -E -c '(vmx|svm)')
        else
            # generic Linux hardware acceleration check
            HW_ACCEL_SUPPORT=$(grep -E -c '(vmx|svm)' /proc/cpuinfo)
        fi

        if [[ $HW_ACCEL_SUPPORT == 0 ]]; then
            hw_accel_flag="-accel off"
            echo "Warning: no accelerator found. This Docker image is experimental and has only been tested on linux devices with KVM enabled."
        else
            hw_accel_flag="-accel on"
        fi
    fi

    echo "$hw_accel_flag"
}


# hw_accel_flag=$(check_hardware_acceleration)

function launch_emulator () {
  adb devices | grep emulator-${CONSOLE_PORT} | cut -f1 | xargs -I {} adb -s "{}" emu kill
  # Clean up stale lock files from previous unclean shutdown (e.g. os._exit)
  # This prevents "Running multiple emulators with the same AVD" error on restart
  sleep 2

  # 强力清理残留(新增)
  pkill -9 -f "qemu-system.*${CONSOLE_PORT}" 2>/dev/null || true
  pkill -9 -f "emulator.*-port ${CONSOLE_PORT}" 2>/dev/null || true
  pkill -9 -f crashpad_handler 2>/dev/null || true
  sleep 1

  avd_dir="${HOME}/.android/avd/${emulator_name}.avd"
  if [ -d "$avd_dir" ]; then
    rm -f "$avd_dir"/*.lock
    echo "Cleaned up stale lock files in $avd_dir"
  fi
  # options="@${emulator_name} -no-window -no-snapshot -noaudio -no-boot-anim -memory 2048 ${hw_accel_flag} -camera-back none  -grpc 8554"

  # 资源配置（可通过环境变量覆盖，便于容器启动脚本调整）
  EMU_CORES=${EMU_CORES:-4}
  EMU_MEMORY=${EMU_MEMORY:-6144}
  EMU_GPU=${EMU_GPU:-"swiftshader_indirect"}

  options="@${emulator_name}  -port ${CONSOLE_PORT} -grpc ${GRPC_PORT} -cores ${EMU_CORES} -memory ${EMU_MEMORY} -no-snapshot -no-boot-anim -no-window -no-audio -skip-adb-auth -gpu ${EMU_GPU}"
  cmd="emulator $options"
  echo $cmd
  nohup emulator $options&

  if [ $? -ne 0 ]; then
    echo "Error launching emulator"
    return 1
  fi
}


function check_emulator_status () {
  printf "${G}==> ${BL}Checking emulator booting up status 🧐${NC}\n"
  start_time=$(date +%s)
  spinner=( "⠹" "⠺" "⠼" "⠶" "⠦" "⠧" "⠇" "⠏" )
  i=0
  # Get the timeout value from the environment variable or use the default value of 300 seconds (5 minutes)
  timeout=${EMULATOR_TIMEOUT:-300}

  while true; do
    result=$(adb -s emulator-${CONSOLE_PORT} shell getprop sys.boot_completed 2>&1)

    if [ "$result" == "1" ]; then
      printf "\e[K${G}==> \u2713 Emulator is ready : '$result'           ${NC}\n"
      adb devices -l
      adb -s emulator-${CONSOLE_PORT} shell input keyevent 82
      return 0  # Return a 0 to indicate emulator has booted successfully
    elif [ "$result" == "" ]; then
      printf "${YE}==> Emulator is partially Booted! 😕 ${spinner[$i]} ${NC}\r"
    else
      printf "${RED}==> $result, please wait ${spinner[$i]} ${NC}\r"
      i=$(( (i+1) % 8 ))
    fi

    current_time=$(date +%s)
    elapsed_time=$((current_time - start_time))
    if [ $elapsed_time -gt $timeout ]; then
      printf "${RED}==> Timeout after ${timeout} seconds elapsed 🕛.. ${NC}\n"
      return 1 # Return a 1 to indicate failure if exceeded timeout
    fi
    sleep 4
  done
};


function disable_animation() {
  adb  -s emulator-${CONSOLE_PORT} shell "settings put global window_animation_scale 0.0"
  adb  -s emulator-${CONSOLE_PORT} shell "settings put global transition_animation_scale 0.0"
  adb  -s emulator-${CONSOLE_PORT} shell "settings put global animator_duration_scale 0.0"
};

function hidden_policy() {
  adb  -s emulator-${CONSOLE_PORT} shell "settings put global hidden_api_policy_pre_p_apps 1;settings put global hidden_api_policy_p_apps 1;settings put global hidden_api_policy 1"
};

launch_emulator
sleep 2

if check_emulator_status; then
  # Only run the below if the emulator is actually ready
  # sleep 1
  # disable_animation
  # sleep 1
  # hidden_policy
  # sleep 1
  sleep 3
else
  echo "Emulator failed to start properly, exiting..."
  exit 1
fi