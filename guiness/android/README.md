# Guiness Controller (Android)

自研 WiFi 模式设备端。PC 通过 HTTP 与本 APP 通信，APP 内用
**AccessibilityService** 注入手势、**MediaProjection** 截图；无需 ADB、无需开启
开发者选项、无需 root。

## 目录结构

```
android/
  settings.gradle.kts  build.gradle.kts  gradle/libs.versions.toml
  app/src/main/
    AndroidManifest.xml
    res/xml/accessibility_service_config.xml
    java/com/guiness/controller/
      GuinessApp.kt               # Application 单例，持有 capture/input/server
      MainActivity.kt             # 启动 UI，拉起 MediaProjection 授权
      ui/{AppRoot,StatusScreen,LogScreen}.kt
      service/ControlForegroundService.kt     # 前台服务（Android 10+ 合规）
      service/ControlAccessibilityService.kt  # 无障碍服务（手势 + 文本输入）
      capture/ScreenCaptureManager.kt         # VirtualDisplay + JPEG 编码
      input/InputDispatcher.kt                # 串行手势注入
      server/{HttpServer,Routes,AuthPlugin,Protocol,ControlSession}.kt
      util/{AppLog,NetworkUtils,TokenStore}.kt
```

## 构建

### 本地命令行

```bash
cd android
./gradlew :app:assembleDebug       # debug APK
# 或
./gradlew :app:assembleRelease     # release APK（未签名，仅自用）
```

产物位于 `app/build/outputs/apk/debug/app-debug.apk`。

### Android Studio

直接用 Hedgehog (AGP 8.2) 及以上打开 `android/` 目录。

依赖版本（`gradle/libs.versions.toml` 已锁）：
- AGP 8.2.2 / Kotlin 2.0.0 / compose-compiler 2.0.0
- compileSdk 34 / minSdk 26 / targetSdk 34
- Ktor 2.3.10（CIO engine）
- androidx.security:security-crypto 1.1.0-alpha06（EncryptedSharedPreferences）

## 安装与授权

1. 把 `app-debug.apk` 传到手机安装（开"安装未知来源应用"即可，一般 OEM 设置里就能开）。
2. 打开 **Guiness 控制器**，首次进入会提示：
   - 开启无障碍：`系统设置 → 无障碍 → 已安装的应用 → Guiness 控制器 → 开启`（不同 OEM 入口略有差别）。
   - 授权通知：首次运行会弹 POST_NOTIFICATIONS，允许即可（拒绝也能跑，只是看不到通知）。
3. 回到 APP，点 **启动服务**。
4. 系统弹出"录屏授权"对话框，勾 **不再询问**（若有）后允许。
5. 顶部卡片显示 `http://192.168.x.y:8765` 即就绪。

Token 在 **Token** 卡片里，右侧有 **重置 Token** 按钮可手动刷新。

### 省电 / 保活

- 不同 OEM（MIUI/Coloros/OneUI）要把本 APP 加入"电池优化白名单"、"允许后台活动"。
- 无障碍服务被系统重置时，APP 会在接到请求时返回 503；重新打开无障碍即可恢复。

## PC 侧接入（Stage 2 CLI 手测）

在 `config.yaml` 里改：

```yaml
device:
  mode: wifi
  wifi_endpoint: http://192.168.x.y:8765     # 手机屏上显示那串
  token: <手机屏上显示的 Token>
  device_type: phone
```

跑一个任务：

```bash
python run_eval.py --config config.yaml --task-type phone ...
```

## 手动烟测

> 下面的 `TOKEN` 全部从 APP 屏幕上复制。

```bash
ENDPOINT=http://192.168.x.y:8765
TOKEN=<your-token>

# 1. 存活
curl -s "$ENDPOINT/ping" -H "X-Guiness-Token: $TOKEN"
# {"ok":true,"version":"1",...}

# 2. 设备信息
curl -s "$ENDPOINT/device_info" -H "X-Guiness-Token: $TOKEN" | jq .
# {"model":"...","width":1080,"height":2400,...}

# 3. 截图
curl -s "$ENDPOINT/screenshot?q=60" -H "X-Guiness-Token: $TOKEN" -o /tmp/s.jpg
open /tmp/s.jpg

# 4. 点击（像素或 [0,1] 归一化皆可，APP 会自动识别）
curl -s -X POST "$ENDPOINT/tap" \
  -H "X-Guiness-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"x":0.5, "y":0.5}'

# 5. Home
curl -s -X POST "$ENDPOINT/home" -H "X-Guiness-Token: $TOKEN"

# 6. 输入文本
curl -s -X POST "$ENDPOINT/input_text" \
  -H "X-Guiness-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"hello", "clear":false, "enter":false}'
```

错 token：

```bash
curl -i "$ENDPOINT/ping" -H "X-Guiness-Token: bad"
# HTTP/1.1 401 ...
```

## Stage 2 验收清单

- [ ] 手机安装 APK，授权无障碍 + 录屏 → 屏上显示 IP:Port + Token。
- [ ] `curl /ping` / `/device_info` 均 200。
- [ ] PC `config.yaml` 切 `mode: wifi`，CLI 跑 "打开设置 → 搜 wifi → 输入 hello"。
- [ ] 错 token → 401。
- [ ] 无障碍被重置 → 动作接口返回 503，`{"code":"accessibility_disabled"}`。

## 已知限制（Stage 2）

- 仅支持 Android 8.0+（minSdk=26）。
- 无 TLS：仅限同一可信 WiFi；公共网络禁用。
- 不支持 `open / open_deeplink / force_stop*` — 这些会在 Stage 3 补齐，当前会 404。
- 不支持流式截图 — Stage 4 补 WebSocket。
