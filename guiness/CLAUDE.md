# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Guiness is a desktop GUI-agent that drives real Android phones from a PC: user types a natural-language instruction, a VLM loops `screenshot → think → action` on the device until `Complete / Fail / max_steps`. Two entry points share the same engine:

- `main.py` — PySide6 desktop app (product entry). One conversation = one task.
- `run_eval.py` — JSONL batch CLI for regression/eval runs.

`ARCHITECTURE.md` has the detailed design notes (read it before non-trivial changes). `android/README.md` covers the companion Android APK ("Guiness Controller") used by WiFi mode.

## Commands

```bash
# Run from source (dev)
pip install -r requirements.txt
python main.py                           # GUI
python run_eval.py --config config.yaml  # CLI batch eval (reads task.task_file)
python run_eval.py --dry-run             # validate config + imports without running

# Package
bash build.sh                  # PC bundle (PyInstaller) + Android APK
bash build.sh --no-apk         # PC only
bash build.sh --no-pc          # APK only
bash build.sh --skip-deps      # skip pip install

# Android (companion APK, see android/README.md)
cd android && ./gradlew :app:assembleDebug
```

No test suite or linter is wired up. Validate changes by running `python main.py` (GUI) or `python run_eval.py --dry-run` (CLI imports/config sanity). For end-to-end: a real Android device + WiFi mode APK or USB ADB.

## Architecture (what to know before touching it)

Layers — lower does not depend on higher:

```
entry         main.py (GUI) │ run_eval.py (CLI)
factory       core/setup.py            build_components / build_runner / resolve_device_id
engine        runner/episode_runner.py EpisodeRunner
              reporter/                Reporter protocol (CLI colored output / GUI null)
capabilities  device/ action/ model/ apps/
infra         core/config.py  gui/paths.py  utils/
```

### Components (`core/setup.py`)

`build_components(device_id, device_type, model_config, mode, token, on_progress)` returns:

```python
@dataclass
class Components:
    backend: DeviceBackend     # usb → AdbBackend, wifi → WifiBackend
    inference: InferenceClient
    executor: ActionExecutor
```

> Note: `ARCHITECTURE.md` still describes an older `Components(adb, automator, inference, executor)` shape. The current code uses a single `backend` abstraction — trust the code.

`build_runner(components, config, output_dir, date_str, stop_check, on_step_complete, reporter)` wires those into an `EpisodeRunner`.

### DeviceBackend protocol (`device/backend.py`)

Upper layers (`ActionExecutor`, `EpisodeRunner`) depend on this Protocol only, never on `AdbBackend` / `WifiBackend` directly. Unsupported extensions raise `CapabilityUnsupported` so callers can degrade.

- **USB mode** → `device/adb_backend.py` (ADB + uiautomator2).
- **WiFi mode** → `device/wifi_backend.py` talks HTTP + WebSocket to the Android companion APK (`android/`), which uses AccessibilityService + MediaProjection on the phone. No ADB, no dev-options, no root.

### Episode lifecycle (`runner/episode_runner.py`)

`EpisodeRunner.run(task)` is three phases:

| Phase | Work |
| --- | --- |
| `_prepare_episode` | Fill metadata, create `output_dir/<date>/<app>/<episode_id>/`, init history |
| `_run_step` × N | screenshot → XML dump → compress → `inference.predict` → `normalize_action` → `executor.execute` → append `step_record` → `reporter.on_step_complete` + external callback |
| `_finalize_episode` | Deep-copy episode, strip `screenshot_time` (reporter-only field, does not hit disk), write `task.json`, clean tmp, issue `back_times` back presses |

Termination: `stop_check()` is True, `action.func ∈ {Complete, End, Speak, Fail}`, or `step >= max_steps`.

### Reporter (`reporter/base.py`)

```python
class Reporter(Protocol):
    def on_episode_start(self, task: dict) -> None: ...
    def on_step_complete(self, step_record: dict) -> None: ...
    def on_episode_finish(self, result: dict) -> None: ...
```

Engine never prints. CLI uses `reporter/cli_reporter.py` (ANSI). GUI uses `NullReporter()` and renders via a separate `on_step_complete` callback → Qt signal → `ChatFeed`.

### Config (`core/config.py`, schema in `config.yaml`)

Top-level keys: `device`, `operation`, `compress`, `model`, `task`. See `config.yaml` for the authoritative schema. `model.source` is `mify | custom` (each has its own prompt file — see below).

**Convention**: library code does not call `get_*_config()`. Entry points read the config once and pass sub-dicts explicitly (`compress` → `compress_image()`, `model` → `InferenceClient`). `get_config()` is for outermost entry only.

### Model inference (`model/`)

- `inference_client.py` branches on `source`:
  - `mify` → mify gateway + token auth, reads `model/prompts/mify.txt`
  - `custom` → any OpenAI-compatible endpoint, reads `model/prompts/custom.txt`
- **`mify.txt` and `custom.txt` are intentionally duplicated.** Do not merge them into a parameterized template even if they currently look similar — they evolve independently and merging causes "one-change-two-places" bugs. See the comment in `model/prompts/__init__.py`.
- `preset_models.yaml` — mify model catalogue (drives UI dropdown).
- `response_parser.py` — parses `<think>`/`<thought>` + `<answer>` JSON from model output.
- `device_info.py` — `device_type` → system-prompt device info string.

### Actions (`action/`)

`action_space.py::ACTION_REGISTRY` defines legal `func` + required fields. `action_executor.py::_handlers` routes each `func` to backend calls. Swipe direction uses the table-driven `_SWIPE_DIRECTIONS`.

### Apps registry (`apps/registry.py`)

Loads `apps/data/phone.yaml` / `car.yaml` (alias → package name). Used by `Open` action and injected into the system prompt. **Adding a new app = edit yaml only**, no code change.

### GUI (`gui/`)

- `app.py` — `QMainWindow`, owns `ChatManager` + `EpisodeWorker`.
- `chat_manager.py` — `Conversation` dataclass, thread-safe dict under `threading.Lock`, history persistence.
- `paths.py` — single source of truth for paths: `project_root / resource_path / data_dir / config_file_path`.
- `workers/episode_worker.py` — `QThread` that drives `build_components` / `build_runner` and turns runner callbacks into Qt signals.
- `pages/config/` and `pages/result/` use a **module-function** style: `build_xxx(page)` + `on_yyy(page, ...)` attach widgets to `ConfigPage` / `ResultPage`. They are NOT `QWidget` subclasses. Keep this style for new sections — splitting files without moving state/re-wiring signals is the whole point.

#### Threading (GUI)

- Main thread: UI + `ChatManager`.
- One `EpisodeWorker(QThread)` per running Episode.
- Runner's `stop_check` binds to `conv.is_stop_requested`; stop button calls `ChatManager.stop` → `Conversation.request_stop()` → `threading.Event.set()`.
- Do **not** read `Conversation._stop_event` / `_stop_flag` externally. Use `request_stop()` / `is_stop_requested()`.

### Data products

```
data/
  output/<date>/<app>/<episode_id>/
    task.json                 # query / app / phone / eval_score / data[]
    1.png 1.xml 2.png 2.xml … # per-step screenshot + uiautomator hierarchy
  history/
    conversations.json        # GUI conversation history (metadata + steps, no screenshots)
```

`task.json.data[i]` has `step`, `foreground_app`, `thought`, `action` (raw), `action_normalized` (with absolute coords), `raw_model_output`, optional `error`. **Field names are locked during refactor** — changing them requires touching write (`runner/episode_runner.py::_run_step`), GUI read (`gui/widgets/step_card.py`), and GUI display (`gui/pages/result/detail_section.py`), or historical records misalign.

### Packaging

`build_config.spec` + `build.sh` run PyInstaller:

- `datas=` must include `config.yaml`, `apps/data/*.yaml`, `model/prompts/*.txt`, `model/preset_models.yaml`, `gui/styles/theme.qss`, `resources/`.
- `hiddenimports=` covers dynamically imported modules: `apps.registry`, `core.config`, `core.setup`, `model.prompts`, `model.response_parser`, `model.device_info`, `reporter.*`.
- Runtime: `gui/paths.py::data_dir()` checks `sys.frozen` — frozen writes to `~/Guiness/data/`, dev writes to repo-local `data/`.
- `build.sh` also vendors Android `platform-tools` (adb) into `vendor/platform-tools/<os>/` so end-users without ADB still work.

## Common pitfalls when editing

- **New action func**: update all three of `action/action_space.py::ACTION_REGISTRY`, `action/action_executor.py::_handlers`, and (if terminal) `runner/episode_runner.py::_TERMINAL_FUNCS`. Names must match exactly — past bug: Tap vs. Click split.
- **New `device_type`**: update `config.yaml` dropdown, `apps/data/` (new yaml if needed), `model/device_info.py` mapping, and `AdbBackend` / `WifiBackend` branches for `task_type`.
- **Editing prompts**: change `mify.txt` or `custom.txt` directly. Do not extract a shared template.
- **Changing `task.json` shape**: update write side (`runner/episode_runner.py`), GUI read (`gui/widgets/step_card.py`), GUI display (`gui/pages/result/detail_section.py`) together.
- **New GUI section**: use the module-function style in `pages/config/` / `pages/result/`. Only introduce `QWidget` subclasses in `gui/widgets/` for genuinely reusable controls.
- **New backend capability**: extend `DeviceBackend` protocol in `device/backend.py`; raise `CapabilityUnsupported` in backends that can't implement it yet so callers can degrade.
