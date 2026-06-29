#!/bin/bash
NUM_GPUS=8
PORT=29501
BATCH_SIZE=1
TEMPLATE="./evaluation/template/base.jinja"

# Required: set these before running
MODEL_PATH="${MODEL_PATH:?Please set MODEL_PATH}"
LOG_FILE="${LOG_FILE:-./evaluation/results/eval_results.log}"

# Dataset paths (required)
SCREENSPOT_IMGS="${SCREENSPOT_IMGS:?Please set SCREENSPOT_IMGS}"
SCREENSPOT_TEST="${SCREENSPOT_TEST:?Please set SCREENSPOT_TEST}"
SCREENSPOT_V2_IMGS="${SCREENSPOT_V2_IMGS:?Please set SCREENSPOT_V2_IMGS}"
SCREENSPOT_V2_TEST="${SCREENSPOT_V2_TEST:?Please set SCREENSPOT_V2_TEST}"
MMBENCH_GUI_IMGS="${MMBENCH_GUI_IMGS:?Please set MMBENCH_GUI_IMGS}"
MMBENCH_GUI_TEST="${MMBENCH_GUI_TEST:?Please set MMBENCH_GUI_TEST}"
OSWORLD_G_IMGS="${OSWORLD_G_IMGS:?Please set OSWORLD_G_IMGS}"
OSWORLD_G_TEST="${OSWORLD_G_TEST:?Please set OSWORLD_G_TEST}"

export TOKENIZERS_PARALLELISM=false

mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"

run_eval() {
    local name="$1"
    local script="$2"
    local imgs="$3"
    local test="$4"
    echo "==========Evaluation on ${name}=========="
    local tmp_out
    tmp_out=$(mktemp)
    torchrun --standalone --nproc_per_node=$NUM_GPUS --master_port=$PORT "$script" \
        --model-path "$MODEL_PATH" \
        --batch-size $BATCH_SIZE \
        --template "$TEMPLATE" \
        --abs_v2 \
        --screenspot-imgs "$imgs" \
        --screenspot-test "$test" \
        2>&1 | tee "$tmp_out"
    {
        echo "==========Evaluation on ${name}=========="
        tail -n 20 "$tmp_out"
        echo ""
    } >> "$LOG_FILE"
    rm -f "$tmp_out"
}

run_eval "ScreenSpot"       evaluation/screenspot.py       "$SCREENSPOT_IMGS"    "$SCREENSPOT_TEST"
run_eval "ScreenSpot-V2"    evaluation/screenspot_v2.py    "$SCREENSPOT_V2_IMGS" "$SCREENSPOT_V2_TEST"
run_eval "MMBench-GUI"      evaluation/mmbench_gui.py      "$MMBENCH_GUI_IMGS"   "$MMBENCH_GUI_TEST"
run_eval "OSWorld-G"        evaluation/osworld_g.py        "$OSWORLD_G_IMGS"     "$OSWORLD_G_TEST"
run_eval "OSWorld-G-Refine" evaluation/osworld_g_refine.py "$OSWORLD_G_IMGS"     "$OSWORLD_G_TEST"
