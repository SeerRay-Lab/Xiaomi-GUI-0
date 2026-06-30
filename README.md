<div align="center">

<img src="https://raw.githubusercontent.com/SeerRay-Lab/Xiaomi-GUI-0/gh-pages/assets/logo/xiaomi_logo.png" width="92" alt="Xiaomi-GUI-0"/>

# Xiaomi-GUI-0

### A Native End-to-End Multimodal GUI Agent for Real Mobile Environments

*Training and evaluating a GUI agent inside a **real-device closed loop** — closing the gap between benchmark scores and real-world usability.*

<p>
  <a href="https://seerray-lab.github.io/Xiaomi-GUI-0/"><img src="https://img.shields.io/badge/🌐_Project_Page-Xiaomi--GUI--0-ff6700?style=for-the-badge" alt="Project Page"/></a>
  <a href="https://huggingface.co/SeerRay-Lab"><img src="https://img.shields.io/badge/🤗_HuggingFace-SeerRay--Lab-FFD21E?style=for-the-badge" alt="HuggingFace"/></a>
  <a href="https://github.com/SeerRay-Lab/Xiaomi-GUI-0"><img src="https://img.shields.io/badge/GitHub-Code-181717?style=for-the-badge&logo=github" alt="GitHub"/></a>
</p>

<p>
  <img src="https://img.shields.io/badge/Backbone-Qwen3--VL--30B--A3B-blue" alt="Backbone"/>
  <img src="https://img.shields.io/badge/RealMobile-72.0%25-success" alt="RealMobile"/>
  <img src="https://img.shields.io/badge/AndroidWorld-78.9%25-success" alt="AndroidWorld"/>
  <img src="https://img.shields.io/badge/Benchmark-100_tasks_·_14_apps-orange" alt="Benchmark"/>
</p>

📱 **Real-device-dominant** &nbsp;·&nbsp; 🔁 **Error-driven data flywheel** &nbsp;·&nbsp; 🎯 **SFT → Step RL → Agentic RL** &nbsp;·&nbsp; 🧪 **RealMobile benchmark**

</div>

***

## 🚨 News

- **2026-06** — 🌐 Project page is live: **[seerray-lab.github.io/Xiaomi-GUI-0](https://seerray-lab.github.io/Xiaomi-GUI-0/)**
- **2026-06** — 📊 Released the **RealMobile** benchmark — 100 real-device tasks across 14 live Chinese apps, scored by fine-grained sub-goals.
- **2026-06** — 🤗 Models and evaluation suites available under **[SeerRay-Lab](https://huggingface.co/SeerRay-Lab)** on HuggingFace.

***

## ✨ What Is Xiaomi-GUI-0?

GUI agents complete user tasks end-to-end in real applications through interface-level actions — tapping, swiping, text entry, and page navigation. Yet existing mobile agents are trained and measured largely on **offline trajectories, simulated environments, and static benchmarks**, which differ sharply from real apps in layout, interaction logic, and the distribution of abnormal states.

On real devices, factors such as account states, permission dialogs, payment authentication, and risk-control mechanisms continually reshape the state distribution encountered during execution — opening a persistent gap between high benchmark scores and real-world usability. To close this gap, **Xiaomi-GUI-0** is a native end-to-end multimodal GUI agent for real mobile environments, trained and evaluated within a **real-device closed loop**:

- **📱 Real-device-dominant hybrid infrastructure** — hundreds of physical phones and tablets as the primary execution substrate, with sandboxes for scalable, reproducible collection, so data collection, training, rollout, and evaluation share a real deployment distribution.
- **🔁 Error-driven data flywheel** — failure trajectories from real rollouts are turned into corrected actions, reflective explanations, and recovery demonstrations — direct supervision for abnormal-state recognition and self-recovery.
- **🎯 Progressive three-stage training** — SFT → step-level RL → agentic RL incrementally builds basic interface operation, long-horizon planning, and error recovery.
- **🧪 RealMobile benchmark** — 100 tasks across 14 live apps, scored by fine-grained sub-goals on physical devices, with 57% spanning multiple applications.

***

## 📊 Results Snapshot

**Navigation** — task completion on the real-device **RealMobile** benchmark and on **AndroidWorld**. Success = fraction of fully completed tasks; Progress = mean fraction of completed sub-goals. Reported as mean@4 over four runs.

| Model | RealMobile&nbsp;Success | RealMobile&nbsp;Progress | AndroidWorld |
|---|:---:|:---:|:---:|
| *Proprietary* | | | |
| Gemini 3.1 Pro | 85.0% | 89.6% | — |
| Seed 2.0 Pro | 80.0% | 88.1% | — |
| Claude Opus 4.7 | 60.0% | 74.8% | — |
| Gemini 3.1 Flash | 58.0% | 72.4% | — |
| UI-TARS-2 | — | — | 73.3% |
| *Open-source* | | | |
| MAI-UI-8B | 33.0% | 50.8% | 70.7% |
| GUI-Owl-1.5-32B-Thinking | 31.0% | 51.7% | 69.8% |
| UI-Venus-1.5-30B-A3B | 21.0% | 44.6% | 77.6% |
| Step-GUI-8B | 15.0% | 32.8% | 67.7% |
| **🔶 Xiaomi-GUI-0-30B-A3B** | **72.0%** | **85.8%** | **78.9%** |

> **Takeaway.** Xiaomi-GUI-0 substantially outperforms locally deployable open-source models on the real-device benchmark and **achieves the best AndroidWorld result among evaluated models**, while approaching frontier proprietary systems despite their larger scale — evidence that a real-device closed loop narrows the gap between benchmark scores and real-world deployability.

**GUI Grounding** — competitive on English/desktop-dominated public benchmarks despite being optimized for real-world Chinese mobile & cockpit apps.

| ScreenSpot-V2 | MMBench-GUI-L2 | OSWorld-G | OSWorld-G-Refine |
|:---:|:---:|:---:|:---:|
| 94.7% | 82.7% | 58.7% | 64.2% |

***

## 🛠️ Method

### Real-Device-Dominant Hybrid Infrastructure

Physical devices serve as the primary execution environment with sandboxes as auxiliary support, organized into a resource layer, a scheduling layer, and an execution & collection layer. A **Device-Pull** scheduler lets idle devices request tasks matching their current readiness.

<div align="center">
  <img src="https://raw.githubusercontent.com/SeerRay-Lab/Xiaomi-GUI-0/gh-pages/assets/figs/infra.png" width="90%" alt="Hybrid infrastructure"/>
</div>

### Multi-Source Training Data

Three progressive data tiers span the supervision needed for real mobile scenarios: **high-frequency task data** for head functions, **high-generalization data** for long-tail intents via function trees and behavior buckets, and **agent-capability enhancement data** with a five-field structured chain-of-thought schema.

<div align="center">
  <img src="https://raw.githubusercontent.com/SeerRay-Lab/Xiaomi-GUI-0/gh-pages/assets/figs/data.png" width="90%" alt="High-generalization data pipeline"/>
  <img src="https://raw.githubusercontent.com/SeerRay-Lab/Xiaomi-GUI-0/gh-pages/assets/figs/query.png" width="90%" alt="Query synthesis pipeline"/>
</div>

### Error-Driven Data Flywheel

Rather than scaling data volume, the flywheel is organized around the error distribution exposed during real rollouts. A teacher model scores each step; sustained below-threshold scores trigger a bounded takeover that produces a deviation–diagnosis–recovery segment.

<div align="center">
  <img src="https://raw.githubusercontent.com/SeerRay-Lab/Xiaomi-GUI-0/gh-pages/assets/figs/flywheel.png" width="90%" alt="Teacher scoring and takeover"/>
</div>

***

## 🧪 The RealMobile Benchmark

RealMobile is built from real user traffic, hand-rewritten for reproducible evaluation, and executed on **physical devices against live applications**. It runs entirely on real devices, scores each task through **fine-grained sub-goals** with partial credit, and most tasks span **multiple applications**.

| Domain | Tasks | Avg. Apps | Multi-App |
|---|:---:|:---:|:---:|
| Foundation | 10 | 1.30 | 10% |
| Safety & Reflection | 16 | 1.31 | 31% |
| Memory & Knowledge | 33 | 1.73 | 58% |
| Complex Reasoning & Planning | 41 | 2.49 | 78% |
| **Overall** | **100** | **1.93** | **57%** |

<div align="center">
  <img src="https://raw.githubusercontent.com/SeerRay-Lab/Xiaomi-GUI-0/gh-pages/assets/figs/app_freq_pie.png" width="44%" alt="Application frequency"/>
  <img src="https://raw.githubusercontent.com/SeerRay-Lab/Xiaomi-GUI-0/gh-pages/assets/figs/multiapp_bar.png" width="40%" alt="Applications per task"/>
</div>

> Trajectory data (~13 GB) is hosted on HuggingFace: [`SeerRay-Lab/RealMobile-BMK`](https://huggingface.co/datasets/SeerRay-Lab/RealMobile-BMK)

***

## 🗂️ Repository Layout

| Directory | What it is |
|-----------|------------|
| [`guiness/`](guiness/) | **Production desktop client.** PySide6 app + Android companion that turns natural-language instructions into real actions on a physical phone (WiFi or USB). Also has a headless batch eval runner. |
| [`android_world_eval/`](android_world_eval/) | **Dynamic emulator benchmark.** Vision-based evaluation on Google's AndroidWorld — 116 tasks across 20 apps, screenshots only. |
| [`grounding-eval/`](grounding-eval/) | **Static grounding benchmark.** Tests whether the model can locate a UI element from an instruction, across 5 datasets (ScreenSpot, ScreenSpot-V2, MMBench-GUI, OSWorld-G, OSWorld-G-Refine). |
| [`RealMobile/`](RealMobile/) | **Real-phone Chinese-app benchmark.** Rule-based (XPath) scoring of recorded agent trajectories on apps like Bilibili, QQ, Douyin, Xiaohongshu, Taobao. |
| [`demo/`](demo/) | **Sample trajectories.** Example agent episodes from AndroidWorld for showcase/documentation. |

### How the Components Relate

```
                    Xiaomi-GUI-0  (GUI Agent Model)
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

***

## 🧩 Components

### `guiness/` — Desktop GUI Agent
PySide6 desktop client paired with a Kotlin Android companion app. Controls the phone via the Accessibility Service (no ADB / root / developer options needed in WiFi mode), with QR-code pairing and a live execution stream (screenshot + thought + action per step). Ships model adapters for Gemini, Claude, GPT, Doubao, AutoGLM, Step-GUI, and Xiaomi-GUI-0 via any OpenAI-compatible endpoint.

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

***

## 📚 Citation

If you find this work useful, please cite:

```bibtex
@techreport{xiaomigui0_2026,
  title        = {Xiaomi-GUI-0 Technical Report},
  author       = {Mimir Team},
  institution  = {Xiaomi},
  year         = {2026},
  url          = {https://github.com/SeerRay-Lab/Xiaomi-GUI-0}
}
```

***

## 📄 License

No repository-wide license file. Individual components carry their own terms (`android_world_eval/` is Apache 2.0; `guiness/` is MIT). Check each subdirectory before reuse.

<div align="center">
<sub>Visit the <a href="https://seerray-lab.github.io/Xiaomi-GUI-0/">project page</a> for demos, full results, and updates.</sub>
</div>
