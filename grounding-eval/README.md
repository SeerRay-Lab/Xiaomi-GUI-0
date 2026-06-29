# GUI Grounding Evaluation

Evaluation scripts for GUI grounding models across 5 benchmarks:

- **ScreenSpot** — text/icon grounding on mobile, desktop, web (1,272 samples)
- **ScreenSpot-V2** — updated version with refined annotations (1,272 samples)
- **MMBench-GUI** — multi-platform GUI understanding (3,594 samples)
- **OSWorld-G** — desktop GUI grounding from OSWorld (564 samples)
- **OSWorld-G-Refine** — refined instructions for OSWorld-G (564 samples)

## Requirements

```bash
pip install torch transformers accelerate pillow jinja2 opencv-python imagesize qwen_vl_utils
```

## Quick Start

### Run a single benchmark

```bash
torchrun --standalone --nproc_per_node=8 --master_port=29501 screenspot.py \
    --model-path /path/to/model \
    --batch-size 1 \
    --template ./template/base.jinja \
    --abs_v2 \
    --screenspot-imgs /path/to/screenspot_imgs/ \
    --screenspot-test /path/to/screenspot_annotations/
```

### Run all 5 benchmarks

Set environment variables and run `start.sh`:

```bash
export MODEL_PATH=/path/to/model
export LOG_FILE=./results/eval.log

# ScreenSpot
export SCREENSPOT_IMGS=/path/to/SeeClick/screenspot_imgs/
export SCREENSPOT_TEST=/path/to/SeeClick/

# ScreenSpot-V2
export SCREENSPOT_V2_IMGS=/path/to/ScreenSpot-v2/screenspotv2_image/
export SCREENSPOT_V2_TEST=/path/to/ScreenSpot-v2/

# MMBench-GUI
export MMBENCH_GUI_IMGS=/path/to/MMBench-GUI/offline_images/
export MMBENCH_GUI_TEST=/path/to/MMBench-GUI/

# OSWorld-G / OSWorld-G-Refine
export OSWORLD_G_IMGS=/path/to/OSWorld-G/images/
export OSWORLD_G_TEST=/path/to/OSWorld-G/

bash start.sh
```

## Arguments

| Argument | Description |
|----------|-------------|
| `--model-path` | Path to the HuggingFace model checkpoint |
| `--batch-size` | Inference batch size per GPU (default: 1) |
| `--template` | Path to the Jinja2 prompt template |
| `--screenspot-imgs` | Path to the image directory for the benchmark |
| `--screenspot-test` | Path to the annotation/JSON directory for the benchmark |
| `--abs_v2` | Model outputs coordinates in processor-resized pixel space; rescale back to original image |
| `--abs` | Model outputs absolute pixel coordinates (legacy, for Qwen2.5-VL) |
| `--raw_coords` | Model outputs raw original-image pixel coordinates, no rescaling |

## Dataset Structure

Each benchmark expects a specific directory layout:

```
ScreenSpot/
├── screenspot_imgs/          # --screenspot-imgs
├── screenspot_mobile.json    # --screenspot-test (directory containing these)
├── screenspot_desktop.json
└── screenspot_web.json

ScreenSpot-v2/
├── screenspotv2_image/       # --screenspot-imgs
├── screenspot_mobile_v2.json
├── screenspot_desktop_v2.json
└── screenspot_web_v2.json

MMBench-GUI/
├── offline_images/           # --screenspot-imgs
└── L2_annotations.json       # --screenspot-test

OSWorld-G/
├── images/                   # --screenspot-imgs
├── OSWorld-G.json            # --screenspot-test (used by osworld_g.py)
└── OSWorld-G_refined.json    # (used by osworld_g_refine.py)
```

## Output Format

The model is expected to output bounding box coordinates in one of these formats:
- `<bbox>[x1, y1, x2, y2]</bbox>`
- `` ```json [{"bbox_2d": [x1, y1, x2, y2]}] ``` ``
- `<point>(x, y)</point>`
- `<tool_call>{"position": [rx, ry]}</tool_call>` (normalized 0-1 coordinates)

Accuracy is computed by checking whether the predicted click point (bbox center) falls within the ground-truth bounding box.
