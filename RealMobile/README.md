# GUI Agent Benchmark (guiagentbmk)

A benchmark and scoring framework for **evaluating mobile GUI agents**.

Agents (such as `GuiClaw`, built on top of large models like Claude) operate Chinese-language apps (Bilibili, QQ, Douyin, RED/Xiaohongshu, Weibo, Taobao, QQ Music, Ctrip, AMap, etc.) on real Android phones to complete natural-language tasks. This repository records the agent's execution **trajectories** (screenshots + UI hierarchy XML + OCR + actions), scores each trajectory with **hand-written rule scripts**, and aggregates the results into success rates.

## Directory Structure

```
guiagentbmk/
├── rules/                       # Scoring scripts (core)
│   ├── evaluator_xpath.py       # Evaluation engine: XML parsing + XPath matching
│   ├── 1.py ... 143.py          # Each file = scoring rules for one evaluation task
│   └── __pycache__/
├── BMK/                         # Trajectory data (multiple test runs)
│   ├── first/  second/  third/  fourth/   # Trajectory folders per batch
│   └── 2026-04-29/              # Human-annotated data organized by app (Bilibili, QQ, Douyin…)
├── paddle/                      # PaddleOCR models (used when generating _ocr.xml)
│   ├── det/ rec/ cls/ doc_ori/  # Detection / recognition / orientation classification / document orientation models
├── results/                     # Evaluation outputs (JSON / CSV / XLSX)
├── query_comparison_report.json # Cross-reference report: task queries ↔ model trajectories
└── README.md
```

## Core Concepts

### Trajectory
Each trajectory is a folder (e.g. `BMK/first/67037d53/`) representing the complete process of an agent executing one task:

| File | Meaning |
|------|---------|
| `task.json` | Task metadata + every step's action (query, app, phone model, tap coordinates, thought, etc.) |
| `N.xml` | The Android UI hierarchy tree at step N (`uiautomator dump`) |
| `N_ocr.xml` | XML enhanced by PaddleOCR with an `ocr_texts` attribute (preferred during scoring) |
| `N.png` / `N.jpg` | Screenshot at step N |
| `N.json` | Action metadata at step N |
| `N_error.txt` | Error log for that step (if any) |

### Scoring Rules (rules/N.py)
Each `rules/N.py` corresponds to one evaluation task and includes:
- `QUERY` — the task instruction, e.g. `"Turn off Bilibili background playback"`
- `TASK_ID` — the task number
- `STEPRULES` — human-readable step-by-step scoring criteria
- `evaluate_rule_X()` — per-step scoring function that matches UI elements + tap coordinates via XPath
- `evaluate_trajectory(path)` — entry function that returns the score dictionary for a trajectory

Scoring is **cumulative across steps**: multi-step tasks award scores progressively at 0.33 / 0.66 / 1.0, with `total_score` ranging from 0.0 to 1.0.

### Evaluation Engine (evaluator_xpath.py)
- Parses Android UI XML into a list of elements, supporting attributes such as `text`, `ocr_texts`, `bounds`, `checked`, etc.
- Provides XPath-like matching and an extended custom function `bbox_contains_point(@bounds, $point)` — which checks whether the agent's tap coordinate falls within the target element's bounding box
- The core function `evaluate_action_xml(xml, xpath, action_dict)` returns whether there is a match

## Usage

### Dependencies
```bash
pip install lxml
# The OCR preprocessing step also requires PaddleOCR (models are included in the paddle/ directory)
```
Everything else uses the Python standard library (`json`, `os`, `re`, etc.).

### Evaluating a Single Task
Each rule script hard-codes several batches of trajectory paths in its `__main__` block, so you can run it directly:
```bash
cd /mnt/vlm-ks3/wuqinzhuo/guiagentbmk
python rules/1.py
```
This outputs the task's score JSON across the trajectories.

### Calling from Code
```python
import sys
sys.path.append("rules")
import importlib
mod = importlib.import_module("1")          # load rules/1.py

result = mod.evaluate_trajectory("BMK/first/67037d53")
# {
#   "query": "Turn off Bilibili background playback",
#   "id": 1,
#   "total_score": 1.0,
#   "details": [{"rule": ..., "score": 0.33, "satisfied": true, "evidence": "At step 9..."}, ...]
# }
```

### Viewing Aggregated Results
The `evaluation_results_<timestamp>.json` files under `results/` are the aggregated outputs of batch evaluation, structured as:
```json
{
  "summary": {
    "total_tasks": 108,
    "total_paths": 433,
    "total_success": 393,
    "total_success_rate": 0.9076,
    "overall_avg_score": 0.9295
  },
  "results": [
    {
      "id": 1,
      "query": "Turn off Bilibili background playback",
      "scores_list": [1.0, 1.0, ...],
      "success_rate": 1.0,
      "path_results": [ { "path": "...", "score": 1.0, "details": [...] } ]
    }
  ]
}
```
The same data is also available in `.csv` / `.xlsx` versions for convenient viewing in a spreadsheet.

## Workflow Overview

```
Agent runs a task on the phone
        ↓
Collect trajectory (screenshots + uiautomator XML + action coordinates)  →  BMK/<batch>/<episode_id>/
        ↓
Enhance XML with PaddleOCR (generate _ocr.xml)                           ←  paddle/
        ↓
rules/N.py scores step by step using XPath rules (evaluator_xpath.py)
        ↓
Aggregate scores and success rates                                      →  results/
```

## Notes
- Example phone models seen in the data: Redmi 12 5G / Xiaomi 14 Pro Ti, Android 13/15.
- The `task` field is labeled `GuiClaw`; some entries are "GuiClaw human-annotated" golden trajectories.
- `query_comparison_report.json` records the mapping between 108 queries and their corresponding model (e.g. `claude-opus-4-7`) trajectories, used for cross-model/version comparison.
- The benchmark currently contains **108 evaluation tasks and 433 trajectories**, with an overall success rate of about **90.8%**.
