<p align="center">
  <img src="resources/icon_256.png" width="120" alt="Guiness Logo">
</p>

<h1 align="center">Guiness</h1>

<p align="center">
  <strong>Desktop GUI Agent for Android</strong><br>
  <em>Type a command. Watch the AI operate your phone.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue" alt="Platform">
  <img src="https://img.shields.io/badge/Android-8.0%2B-green" alt="Android">
  <img src="https://img.shields.io/badge/Python-3.9%2B-yellow" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License">
</p>

---

A PySide6 desktop client paired with an Android companion app that turns natural-language instructions into real actions on a physical Android device. An LLM perceives the phone's screen, decides the next action, and the companion app executes it via the Accessibility Service — no ADB, no root, no developer options required in WiFi mode. Every step's screenshot, thought process, and action are streamed live and persisted locally.

---

## Features

- **Native Android control** via Accessibility Service — no ADB, no root, no developer options needed
- **Multiple model adapters** out of the box: Gemini, Claude, GPT, Doubao, AutoGLM, Step-GUI, RealGUI / Mai-UI
- **OpenAI-compatible API** — works with any relay station that exposes `/v1/chat/completions`
- **QR-code pairing** between PC and phone over WiFi (token-based auth, 60-second expiry)
- **USB / ADB fallback** mode for environments without WiFi
- **Live execution stream** — screenshot with annotated tap/swipe position, thought, action JSON per step

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        Guiness Desktop                           │
│                                                                  │
│   User Instruction ──► LLM API ──► Action Decision              │
│         ▲                                    │                   │
│         │              Screenshot             ▼                   │
│         └────────────────────────── Execute on Phone             │
└─────────────────────────────────────────────────────────────────┘
                              │ WiFi / USB
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Guiness Controller (Android)                    │
│                                                                  │
│   Accessibility Service ──► Tap / Swipe / Type / Open            │
│   MediaProjection     ──► Screenshot capture                     │
└─────────────────────────────────────────────────────────────────┘
```

## Requirements

| Component | Requirement |
|-----------|------------|
| PC | Windows 10/11, macOS 11+, or Linux |
| Python | 3.9+ (source builds / dev mode only) |
| Phone | Android 8.0+ (API 26), same LAN as PC for WiFi mode |
| JDK | 17+ (Android APK build only) |
| PyInstaller | For desktop binary packaging only |

## Quick Start — WiFi Mode (Recommended)

### Step 1: Install the Android Companion

1. Transfer `dist/Guiness-Controller.apk` to the phone and install it (allow "Install from unknown sources" if prompted).
2. Open **Guiness Controller** and follow the on-screen prompts:
   - Enable Accessibility: *System Settings → Accessibility → Installed apps → Guiness Controller → Enable*
   - Grant notification permission when prompted
   - Tap **Start Service** inside the app, then grant the screen-capture prompt
3. The app's main screen now displays `http://<phone-ip>:8765` and a 6-digit **Token**. Keep this screen open.

### Step 2: Launch the Desktop App

Run `Guiness.exe` (Windows), `Guiness.app` (macOS), or `./Guiness` (Linux) from the `dist/` directory.

### Step 3: Pair the Devices

1. Click **Settings** (bottom-left gear icon) → **Device** tab.
2. Ensure the connection mode is set to **WiFi**. A QR code appears in the pairing panel.
3. On the phone, tap **Scan** in the Guiness Controller app and aim at the QR code on your PC screen.
4. The endpoint (IP:port) and token fields are filled automatically. Click **Test Connection** — you should see a success message with the phone model and resolution.

> **Manual pairing**: If QR scanning is inconvenient, you can manually type the phone's IP address (with port, e.g. `192.168.1.42:8765`) into the endpoint field and copy the 6-digit token from the phone screen.

### Step 4: Configure the Model

Go to **Settings → Model** and fill in:

| Field | Description |
|-------|-------------|
| **Model name** | Pick a preset from the dropdown (supports type-to-filter) or enter a custom model ID. See [Supported Models](#supported-models) for the full list. |
| **Model name override** | *(Optional)* Only fill this if your relay station's actual model ID differs from the preset. For example, you select `vertex_ai/gemini-3.1-pro` but the upstream expects `gemini-3.1-pro-preview`. The adapter (system prompt + parser) is still selected by the preset; only the `model` field in the API payload changes. |
| **API URL** | Base URL of your inference endpoint, e.g. `http://model.mify.ai.srv` or `https://api.openai.com`. Guiness automatically appends `/v1/chat/completions` if the URL doesn't already end with it. |
| **API key** | Bearer token for authentication. Leave empty for unauthenticated endpoints. |

Click **Save**, then type a command in the chat input bar (e.g. *"Open Settings and turn WiFi on"*) and hit **Send**.

Each step's screenshot, thought process, and action appear in real-time in the chat stream. Click **Stop** at any time to interrupt execution.

## Alternative: USB Mode (ADB)

If you cannot use WiFi or prefer not to install the companion APK:

1. Connect the phone to the PC with a **data-capable** USB cable.
2. On the phone: enable *Developer Options → USB Debugging* and authorize the RSA fingerprint prompt.
3. In **Settings → Device**, switch mode to **USB (ADB)**. The device dropdown auto-refreshes every second.
4. Select your device and proceed — no APK needed, but developer options must stay enabled.

Bundled platform-tools are included under `vendor/platform-tools/<os>/`, so no separate ADB installation is required.

## Building from Source

### One-Shot Build Script

```bash
bash build.sh
```

This builds both the **desktop app** and the **Android APK**. Outputs go to `dist/`:

| Platform | Desktop | Android |
|----------|---------|---------|
| macOS | `dist/Guiness.app` (+ `.app.zip`, ad-hoc codesigned) | `dist/Guiness-Controller.apk` |
| Linux | `dist/Guiness` | `dist/Guiness-Controller.apk` |
| Windows | `dist\Guiness.exe` | `dist\Guiness-Controller.apk` |

**Flags:**
- `--no-apk` — skip the Android APK build
- `--no-pc` — skip the desktop build
- `--skip-deps` — skip Python dependency installation (assumes already installed)

### Manual Desktop Build

```bash
pip install -r requirements.txt
pyinstaller build_config.spec --noconfirm
```

The spec's entry point is `main.py`; the output binary is named `Guiness`. It bundles PySide6, `uiautomator2`, `websockets`, `qrcode`, along with data files (stylesheets, config template, model presets, adapter prompts, icons, vendored platform-tools).

### Manual APK Build

```bash
cd android
./gradlew :app:assembleDebug
```

Produces `app/build/outputs/apk/debug/app-debug.apk`. See [`android/README.md`](android/README.md) for details on the companion app's permissions and architecture.

### Running from Source (No Packaging)

```bash
pip install -r requirements.txt
python main.py
```

This launches the GUI directly from the source tree. Config is read from `./config.yaml` in the repo root. The phone-side APK is still required for WiFi mode.

## Supported Models

The following model presets are available out of the box (defined in `model/preset_models.yaml`):

| Model ID | Adapter | Display Name |
|----------|---------|--------------|
| `vertex_ai/gemini-3.1-pro` | gemini | Gemini 3.1 Pro |
| `gemini-3.1-pro-preview-ai-train` | gemini | Gemini 3.1 Pro Preview AI Train |
| `vertex_ai/gemini-3.1-flash` | gemini | Gemini 3.1 Flash |
| `vertex_ai/gemini-3.5-flash` | gemini | Gemini 3.5 Flash |
| `claude-opus-4-7` | claude | Claude Opus 4.7 |
| `claude-opus-4-6` | claude | Claude Opus 4.6 |
| `gpt-5.5` | gpt | GPT 5.5 |
| `gpt-5.4` | gpt | GPT 5.4 |
| `doubao-seed-2-0-pro` | doubao | Doubao Seed 2.0 Pro |
| `doubao-seed-1-8` | doubao | Doubao Seed 1.8 |
| `autoglm-phone` | autoglm | AutoGLM-9B |
| `GELab-Zero-4B-preview` | step_gui | Step-GUI (GELab-Zero-4B) |
| `mai-ui` | realgui | Mai-UI |
| `RealGUI` | realgui | RealGUI |

**Adding a custom model**: Edit `model/preset_models.yaml` and add an entry pointing `adapter:` at one of the existing families (`gemini`, `claude`, `gpt`, `doubao`, `autoglm`, `step_gui`, `realgui`). The adapter determines the system prompt, message assembly format, and response parser used.

**Important**: The adapter is selected based on the **Model name** (preset ID), not the **Model name override**. The override only changes the `model` field in the API request payload.

## Configuration

Settings are persisted to a per-user YAML file:

| OS | Config Path |
|----|-------------|
| Windows | `%APPDATA%\Guiness\config.yaml` |
| macOS | `~/Library/Application Support/Guiness/config.yaml` |
| Linux | `$XDG_CONFIG_HOME/Guiness/config.yaml` (default: `~/.config/Guiness/config.yaml`) |

Application logs are written to `~/Guiness/data/logs/app.log` (packaged build) or `./data/logs/app.log` (dev mode).

When running from source (`python main.py`), the repo's own `config.yaml` is used directly instead of the per-user path.

## Troubleshooting

| Symptom | Solution |
|---------|----------|
| API returns 401 Unauthorized | Check that the **API key** field contains a valid bearer token |
| API returns 400 "model not found" | Fill the **Model name override** field with the relay station's actual model ID |
| WiFi test connection fails | Ensure phone and PC are on the same LAN; confirm the companion app's service is started; verify the token matches |
| WiFi works initially, then returns 503 | The Accessibility Service was killed by the phone's battery optimizer — re-enable it in System Settings and add Guiness Controller to the battery whitelist |
| USB device not listed | Use a data-capable cable; re-authorize the USB debugging prompt on the phone |
| Screenshot is all black | Phone is locked — unlock and retry |
| QR pairing fails | Token expires after 60 seconds — click **Regenerate** in the Settings panel to get a fresh QR |
| Model timeout | Check network connectivity and API endpoint availability |

## Project Layout

```
guiness/
├── main.py                 PySide6 GUI entry point
├── gui/                    Desktop UI (app window, widgets, pages, styles, workers, pairing)
├── device/                 Phone backends (WiFi HTTP, ADB/uiautomator2, coordinators)
├── model/                  Inference client, adapters, preset config, response parser
├── core/                   Config loading, component factory
├── android/                Kotlin Android companion app (Guiness Controller)
├── apps/                   Foreground app registry (phone.yaml, car.yaml)
├── action/                 Action space definition and executor
├── runner/                 Episode runner (step loop orchestration)
├── reporter/               Execution reporters (CLI)
├── resources/              App icons
├── tools/                  Utilities (uiautomator2 init scripts)
├── utils/                  Shared helpers (config loader, image utils)
├── build_config.spec       PyInstaller spec
├── build.sh                One-shot build script
└── requirements.txt        Python runtime dependencies
```

## Further Reading

- [Architecture Deep-Dive](ARCHITECTURE.md) — internal design, data flow, adapter system
- [Android Companion App](android/README.md) — Kotlin app architecture, permissions, build instructions
