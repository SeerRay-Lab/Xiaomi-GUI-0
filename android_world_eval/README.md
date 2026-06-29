# AndroidWorld-CV

A vision-based evaluation framework for GUI agents on Android, built on top of [Google's AndroidWorld](https://github.com/google-research/android_world) benchmark.

This project provides a streamlined pipeline to evaluate any vision-language model (VLM) as a GUI agent on 116 real Android tasks across 20 apps. The agent receives screenshots, reasons about the UI, and outputs structured actions — no accessibility tree or HTML parsing required.

## Key Features

- **Pure vision evaluation** — the agent operates solely from screenshots via an OpenAI-compatible chat completions API
- **116 tasks, 20 apps** — covers contacts, calendar, messaging, browser, file management, settings, and more
- **Any model** — works with any VLM that exposes an OpenAI-compatible endpoint (vLLM, TGI, Ollama, cloud APIs, etc.)
- **Checkpoint & resume** — long benchmark runs can be resumed from where they left off
- **Dynamic task instantiation** — randomized parameters create unique task variations each run

## Architecture

```
run.py                          # Entry point
android_world/
  agents/
    agent_english_final/        # GUI agent: <think> → <action> → <tool_call>
    cv_agent/                   # Shared VLM client, action converter, image utils
  env/                          # Android environment (ADB, gRPC, actuation)
  task_evals/                   # 116 task evaluators with ground-truth checking
```

The agent uses a structured output format:
```xml
<think>[reasoning about the screen]</think>
<action>[natural language description]</action>
<tool_call>{"name": "Tap", "position": [0.5, 0.3], "times": 1}</tool_call>
```

## Installation

### Prerequisites

- Python 3.11+
- Android SDK with an AVD (Pixel 6, API 33 recommended)
- `adb` available in PATH
- `ffmpeg` installed

### Setup

```bash
# 1. Clone and install
git clone <this-repo>
cd android_world_cv
pip install -r requirements.txt
python setup.py install

# 2. Install AndroidEnv dependency
git clone https://github.com/google-deepmind/android_env.git
cd android_env && python setup.py install && cd ..

# 3. Launch Android emulator with gRPC
~/Android/Sdk/emulator/emulator -avd AndroidWorldAvd -no-snapshot -grpc 8554
```

### Environment Variables

```bash
# Required: Your model endpoint (OpenAI-compatible)
export CV_AGENT_MODEL_URL="http://localhost:8000"    # e.g., vLLM server
export CV_AGENT_MODEL_NAME="your-model-name"

# Optional
export CV_AGENT_API_KEY=""              # Bearer token if needed
export CV_AGENT_TEMPERATURE="0.0"      # Sampling temperature
export CV_AGENT_TIMEOUT="120"          # Request timeout (seconds)
export CV_AGENT_MAX_IMAGES="3"         # Max screenshots in context
export CV_AGENT_MAX_TURNS="10"         # Max history turns in context
```

## Evaluation

### First Run (one-time device setup)

The first time you evaluate, pass `--perform_emulator_setup` to install required apps on the emulator:

```bash
python run.py \
  --agent_name=agent_english_final \
  --suite_family=android_world \
  --perform_emulator_setup
```

### Standard Evaluation

```bash
python run.py \
  --agent_name=agent_english_final \
  --suite_family=android_world
```

### Run Specific Tasks

```bash
python run.py \
  --agent_name=agent_english_final \
  --suite_family=android_world \
  --tasks=ContactsAddContact,ClockStopWatchRunning
```

### Resume from Checkpoint

```bash
python run.py \
  --agent_name=agent_english_final \
  --suite_family=android_world \
  --checkpoint_dir=~/android_world/runs/20240101_120000
```

### All Options

| Flag | Default | Description |
|------|---------|-------------|
| `--agent_name` | `m3a_gpt4v` | Agent to evaluate (use `agent_english_final`) |
| `--suite_family` | `android_world` | Task suite (`android_world`, `miniwob`) |
| `--tasks` | all | Comma-separated task names to run |
| `--n_task_combinations` | 1 | Number of random parameter variations per task |
| `--task_random_seed` | 30 | Random seed for task generation |
| `--perform_emulator_setup` | False | Install apps on emulator (first run only) |
| `--checkpoint_dir` | auto | Directory to save/resume checkpoints |
| `--output_path` | `~/android_world/runs` | Output directory for results |
| `--console_port` | 5554 | ADB console port of the emulator |
| `--adb_path` | auto-detect | Path to `adb` binary |

### Results

Results are saved to `~/android_world/runs/<timestamp>/` with per-task success/failure outcomes. Each task is independently scored by ground-truth evaluators (database checks, file verification, UI state validation).

## Docker

A Dockerfile is provided for running the evaluation in a containerized environment with an embedded Android emulator. See `docker_setup/` for the emulator startup scripts.

## Acknowledgments

This project is built on [AndroidWorld](https://github.com/google-research/android_world) by Google Research. If you use the benchmark tasks, please cite:

```bibtex
@misc{rawles2024androidworld,
  title={AndroidWorld: A Dynamic Benchmarking Environment for Autonomous Agents},
  author={Christopher Rawles and Sarah Clinckemaillie and Yifan Chang and Jonathan Waltz and Gabrielle Lau and Marybeth Fair and Alice Li and William Bishop and Wei Li and Folawiyo Campbell-Ajala and Daniel Toyama and Robert Berry and Divya Tyamagundlu and Timothy Lillicrap and Oriana Riva},
  year={2024},
  eprint={2405.14573},
  archivePrefix={arXiv},
  primaryClass={cs.AI},
  url={https://arxiv.org/abs/2405.14573},
}
```

## License

Apache 2.0
