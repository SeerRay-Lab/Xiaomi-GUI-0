# Xiaomi-GUI-0

A monorepo for **RealGUI / Mai-UI**, a family of vision-language GUI agent models for autonomous mobile-phone operation. It bundles a production desktop client that drives real Android devices, plus three complementary evaluation suites and demonstration data.

An LLM perceives the phone screen, decides the next action, and the action is executed on the device — no accessibility tree parsing, no HTML, pure vision.

## Repository Layout

| Directory | What it is |
|-----------|------------|
| [`guiness/`](guiness/) | **Production desktop client.** PySide6 app + Android companion that turns natural-language instructions into real actions on a physical phone (WiFi or USB). Also has a headless batch eval runner. |
| [`android_world_eval/`](android_world_eval/) | **Dynamic emulator benchmark.** Vision-based evaluation on Google's AndroidWorld — 116 tasks across 20 apps, screenshots only. |
| [`grounding-eval/`](grounding-eval/) | **Static grounding benchmark.** Tests whether the model can locate a UI element from an instruction, across 5 datasets (ScreenSpot, ScreenSpot-V2, MMBench-GUI, OSWorld-G, OSWorld-G-Refine). |
| [`RealMobile/`](RealMobile/) | **Real-phone Chinese-app benchmark.** Rule-based (XPath) scoring of recorded agent trajectories on apps like Bilibili, QQ, Douyin, Xiaohongshu, Taobao. |
| [`demo/`](demo/) | **Sample trajectories.** Example agent episodes from AndroidWorld for showcase/documentation. |

## How the Components Relate

```
                    RealGUI / Mai-UI  (GUI Agent Models)
                              │
        ┌──────────────┬──────┴───────┬──────────────────┐
        ▼              ▼              ▼                  ▼
  grounding-eval  android_world_eval  RealMobile      guiness
  (can it locate  (can it complete   (can it complete (run agents on
   UI elements?)   emulator tasks?)   real-phone CN    real devices,
                                      app tasks?)       interactive + batch)
```

- **grounding-eval** — static images, measures the underlying vision model's element-localization accuracy.
- **android_world_eval** — dynamic emulator tasks, measures end-to-end multi-step task completion (English, 116 tasks).
- **RealMobile** — recorded real-device trajectories on Chinese apps, scored by handwritten XPath rules.
- **guiness** — the deployable product that runs the agent on a real phone.
- **demo** — illustrative trajectories, no code.

## Components

### `guiness/` — Desktop GUI Agent
PySide6 desktop client paired with a Kotlin Android companion app. Controls the phone via the Accessibility Service (no ADB / root / developer options needed in WiFi mode), with QR-code pairing and a live execution stream (screenshot + thought + action per step). Ships model adapters for Gemini, Claude, GPT, Doubao, AutoGLM, Step-GUI, and RealGUI / Mai-UI via any OpenAI-compatible endpoint.

- Interactive: `python guiness/main.py`
- Batch eval: `python guiness/run_eval.py`
- Config: `guiness/config.yaml`; build desktop + APK with `guiness/build.sh`
- Requires Python 3.9+, PySide6; Android companion needs JDK 17+ / Gradle.

### `android_world_eval/` — AndroidWorld-CV
Vision-based evaluation on top of Google's AndroidWorld. The agent receives only screenshots and emits structured `<think> → <action> → <tool_call>` output. Supports checkpoint/resume and dynamic task instantiation.

- Entry point: `python android_world_eval/run.py`
- Install: `pip install -e android_world_eval` (compiles protobufs via `setup.py`)
- Requires Python 3.11+, Android SDK + AVD (Pixel 6, API 33), `adb`, `ffmpeg`.
- Point at any VLM via `CV_AGENT_MODEL_URL` / `CV_AGENT_MODEL_NAME`.

### `grounding-eval/` — GUI Grounding Benchmarks
Distributed (torchrun) evaluation of grounding across 5 benchmarks. Accuracy = predicted click point (bbox center) falls inside the ground-truth box.

- Run all: `bash grounding-eval/start.sh`
- Per-benchmark: `screenspot.py`, `screenspot_v2.py`, `mmbench_gui.py`, `osworld_g.py`, `osworld_g_refine.py`
- Requires PyTorch, HuggingFace Transformers (Qwen2.5-VL / Qwen2-VL / Qwen3-VL), accelerate, Pillow, Jinja2, `qwen_vl_utils`.

### `RealMobile/` — Real-Phone Chinese-App Benchmark
Rule-based scoring framework for recorded agent trajectories on real Chinese mobile apps. See [`RealMobile/README.md`](RealMobile/README.md) for full details.

- `rules/` — per-task XPath scoring scripts + `evaluator_xpath.py` engine
- `results/` — aggregated evaluation outputs (JSON / CSV / XLSX)
- `paddle/` — PaddleOCR models used to OCR-augment the UI hierarchy XML
- Trajectory data (~13 GB) is hosted separately on HuggingFace: [`SeerRay-Lab/RealMobile-BMK`](https://huggingface.co/datasets/SeerRay-Lab/RealMobile-BMK)

### `demo/` — Sample Trajectories
Example agent episodes from AndroidWorld (`demo/Android-World/<episode_id>/` with `task.json` + per-step screenshots). Data only, no code.

## Models

All evaluation suites and the client target **RealGUI / Mai-UI**, but work with any model exposing an OpenAI-compatible `/v1/chat/completions` endpoint (Gemini, Claude, GPT, Doubao, AutoGLM, Step-GUI, etc.).

## License

No repository-wide license file. Individual components carry their own terms (`android_world_eval/` is Apache 2.0; `guiness/` is MIT). Check each subdirectory before reuse.
