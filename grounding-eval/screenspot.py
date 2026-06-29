import re
import os
import cv2
import json
import math
import torch
import logging
import argparse
import imagesize
from tqdm import tqdm
from PIL import Image
from jinja2 import Template
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import Dataset, DataLoader
from torch.utils.data.sampler import Sampler
from torch.utils.data.distributed import DistributedSampler
from transformers import Qwen2_5_VLForConditionalGeneration, Qwen2VLForConditionalGeneration, AutoProcessor, AutoModelForImageTextToText, AutoModel, AutoModelForCausalLM
from qwen_vl_utils import process_vision_info
from eval_log import EvalLogger

logging.basicConfig(level=logging.INFO)
# Image resize upper bound (pixel area), aligned with training max_pixel_values=3,211,264
# so that eval runs at the same resolution as training. The old `4096*28*28` was the
# Qwen2-VL formula (patch=14, merge=2, factor=28); for Qwen3-VL (patch=16) it no longer
# means "4096 tokens" — hardcode the value to avoid confusion.
MAX_PIXELS = 3_211_264

class NoPaddingDistributedSampler(Sampler):
    """Distributed sampler without padding"""
    def __init__(self, dataset, shuffle=False, seed=0):
        self.dataset = dataset
        self.world_size = dist.get_world_size()  # total processes
        self.rank = dist.get_rank()  # current process rank
        self.epoch = 0
        self.seed = seed
        self.shuffle = shuffle
        
        # Compute samples per process (no padding, last process may have fewer)
        self.total_size = len(dataset)
        self.per_rank_size = math.ceil(self.total_size / self.world_size)
        self.rank_size = min(self.per_rank_size, self.total_size - self.rank * self.per_rank_size)
        
        # Compute sample index range for current process
        self.start_idx = self.rank * self.per_rank_size
        self.end_idx = self.start_idx + self.rank_size

    def __iter__(self):
        if self.shuffle:
            # Shuffle (optional, consistent with original logic)
            g = torch.Generator()
            g.manual_seed(self.seed + self.epoch)
            indices = torch.randperm(self.total_size, generator=g).tolist()
        else:
            # No shuffle, assign in original order
            indices = list(range(self.total_size))
        
        # Slice sample indices for current process (no duplicates, no padding)
        indices = indices[self.start_idx:self.end_idx]
        return iter(indices)

    def __len__(self):
        return self.rank_size

    def set_epoch(self, epoch):
        self.epoch = epoch


class LazySupervisedDataset(Dataset):
    """Lazy-loading dataset that reads images only when accessed"""
    
    def __init__(self, data_items, processor, screenspot_imgs_dir, template):
        self.data_items = data_items
        self.processor = processor
        self.screenspot_imgs_dir = screenspot_imgs_dir
        self.template = template
        
    def __len__(self):
        return len(self.data_items)
    
    def __getitem__(self, idx):
        item = self.data_items[idx]
        filename = item["img_filename"]
        img_path = os.path.join(self.screenspot_imgs_dir, filename)
        
        try:
            image = Image.open(img_path).convert("RGB")
            image_w, image_h = image.size
            instruction = item["instruction"]
            query = self.template.render(instruction=instruction)
            
            messages = [
                {
                    "role": "system",
                    "content": "You are a GUI Agent."
                },
                {"role": "user", "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": query},
                    #{"type": "text", "text": "How many balls are in the image"},
                ]}
            ]
            
            # Prepare GT info (convert to [x1,y1,x2,y2] format)
            gt_bbox = item["bbox"]
            gt_bbox = [gt_bbox[0], gt_bbox[1], gt_bbox[0] + gt_bbox[2], gt_bbox[1] + gt_bbox[3]]
            
            metadata = {
                "gt_bbox": gt_bbox,
                "img_width": image_w,
                "img_height": image_h,
                "data_type": item["data_type"],
                "item_id": idx,
                "img_filename": filename,
                "instruction": instruction,
            }
            
            #text = self.processor.apply_chat_template(
            #    messages, tokenize=False, add_generation_prompt=True
            #)
            text = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            image_inputs, video_inputs = process_vision_info(messages)
            
            return {
                "text": text,
                "images": image_inputs[0] if image_inputs else None,
                "videos": video_inputs[0] if video_inputs else None,
                "metadata": metadata
            }
            
        except Exception as e:
            logging.error(f"Error processing sample {img_path}: {e}")
            return {
                "text": "",
                "images": None,
                "videos": None,
                "metadata": {"error": True, "item_id": idx}
            }

def collate_fn(batch):
    """Custom collate function that filters out errored samples"""
    valid_batch = [item for item in batch if item["images"] is not None]
    if not valid_batch:
        return None
    
    texts = [item["text"] for item in valid_batch]
    images = [item["images"] for item in valid_batch]
    videos = [item["videos"] for item in valid_batch if item["videos"] is not None]
    metadata = [item["metadata"] for item in valid_batch]
    
    return {
        "texts": texts,
        "images": images,
        "videos": videos if videos else None,
        "metadata": metadata
    }

def process_batch(model, processor, batch_data, device, is_distributed):
    """Process a batch of data, adapted for DDP model"""
    if batch_data is None:
        return []
    
    try:
        inputs = processor(
            text=batch_data["texts"],
            images=batch_data["images"],
            videos=batch_data["videos"],
            padding=True,
            return_tensors="pt"
        )
        inputs = inputs.to(device)
        
        with torch.no_grad():
                generated_ids = model.generate(**inputs, max_new_tokens=1280, use_cache=True)
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        
        output_texts = processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        print(output_texts)

        results = []
        for idx, output_text in enumerate(output_texts):
            try:
                if "```json" in output_text:
                    cleaned_text = re.search(r'```json\n(.*?)\n```', output_text, re.DOTALL).group(1).strip()
                elif re.search(r'<bbox>(.*?)</bbox>', output_text):
                    bbox = re.search(r'<bbox>(.*?)</bbox>', output_text).group(1)
                    cleaned_text = f"[{{\"bbox_2d\": {bbox}}}]"
                elif re.search(r'<point>(.*?)</point>', output_text):
                    point = re.search(r'<point>(.*?)</point>', output_text).group(1)
                    cleaned_text = cleaned_text = f"[{{\"point_2d\": {point}}}]"
                else:
                    cleaned_text = f"[{{\"bbox_2d\": {output_text}}}]"
            except Exception as e:
                logging.error(e)
                print(output_text)
                cleaned_text = json.dumps([{"point_2d": [0, 0]}], ensure_ascii=False)
            
            if 'image_grid_thw' in inputs:
                # patch_size: 14 for Qwen2-VL, 16 for Qwen3-VL. Read from
                # processor so the coord-translation (--abs_v2) is correct
                # regardless of the model family.
                _patch_size = int(getattr(processor.image_processor, "patch_size", 16) or 16)
                input_height = inputs['image_grid_thw'][idx][1] * _patch_size
                input_width = inputs['image_grid_thw'][idx][2] * _patch_size
            else:
                input_height = batch_data["metadata"][idx]["img_height"]
                input_width = batch_data["metadata"][idx]["img_width"]
            
            results.append({
                "output": cleaned_text,
                "raw_output": output_text,
                "input_width": input_width.item() if isinstance(input_width, torch.Tensor) else input_width,
                "input_height": input_height.item() if isinstance(input_height, torch.Tensor) else input_height,
                "metadata": batch_data["metadata"][idx]
            })
        
        return results
    
    except Exception as e:
        logging.error(f"Error during batch processing: {e}")
        return []

def init_distributed():
    """Initialize distributed environment"""
    if not dist.is_available():
        return False, 0, 0
    
    # Get distributed info from environment variables
    rank = int(os.environ.get('RANK', 0))
    world_size = int(os.environ.get('WORLD_SIZE', 1))
    
    if world_size <= 1:
        return False, rank, world_size
        
    # Initialize process group
    dist.init_process_group(
        backend='nccl',  # Use NCCL backend for GPU
        rank=rank,
        world_size=world_size
    )
    
    # Set GPU for current process
    torch.cuda.set_device(rank % torch.cuda.device_count())
    
    return True, rank, world_size

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-path', type=str, required=True, help='Model path')
    parser.add_argument("--screenspot-imgs", type=str, required=True, help="Path to ScreenSpot images directory")
    parser.add_argument("--screenspot-test", type=str, required=True, help="Path to ScreenSpot annotation directory")
    parser.add_argument("--task", type=str, default="all", help="Task type: mobile/desktop/web/all")
    parser.add_argument("--template", type=str, required=True)
    parser.add_argument("--batch-size", type=int, default=4, help="Batch size per GPU")
    parser.add_argument("--num-workers", type=int, default=4, help="Number of data loading workers")
    parser.add_argument("--abs", action="store_true", help="moxing")
    parser.add_argument("--abs_v2", action="store_true", help="Model outputs in processor-resized pixel space; rescale to original image")
    parser.add_argument("--raw_coords", action="store_true", help="Model outputs raw original-image pixel coordinates, no rescaling")
    parser.add_argument('--local-rank', type=int, default=-1, help='Local GPU rank')
    parser.add_argument('--world-size', type=int, default=None, help='Total number of GPUs')
    parser.add_argument('--dist-url', type=str, default='env://', help='Distributed init URL')
    args = parser.parse_args()


    with open(args.template) as f:
        template = Template(f.read())

    # Set device and process rank
    is_distributed, rank, world_size = init_distributed()
    device = torch.device(f"cuda:{rank % torch.cuda.device_count()}" if torch.cuda.is_available() else "cpu")

    # Only main process prints info
    if rank == 0:
        print(f"Distributed mode: {'enabled' if is_distributed else 'disabled'}")
        print(f"Using device: {device}")

    # Load model and processor
    if args.abs:
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            args.model_path,
            torch_dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        ).to(device)
    else:
        #model = Qwen2VLForConditionalGeneration.from_pretrained(
        model = AutoModelForImageTextToText.from_pretrained(
            args.model_path,
            torch_dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
            trust_remote_code=True
        ).to(device)
    processor = AutoProcessor.from_pretrained(args.model_path, trust_remote_code=True)
    # Qwen3-VL's image_processor reads size["longest_edge"] (default 16.7M);
    # the old max_pixels kwarg has no effect. Override to MAX_PIXELS here to ensure
    # smart_resize actually caps at 3.21M, consistent with training.
    if hasattr(processor, "image_processor") and isinstance(getattr(processor.image_processor, "size", None), dict):
        processor.image_processor.size = {**processor.image_processor.size, "longest_edge": MAX_PIXELS}
    else:
        print("[warn] image_processor.size cannot be overridden, using default upper limit")

    # Diagnostic: log processor resize key params for cross-branch comparison
    if rank == 0:
        _ip = getattr(processor, "image_processor", None)
        _proc_info = {
            "branch": "main",
            "model_path": args.model_path,
            "processor_class": type(_ip).__name__ if _ip is not None else None,
            "patch_size": getattr(_ip, "patch_size", None),
            "merge_size": getattr(_ip, "merge_size", None),
            "size": dict(getattr(_ip, "size", {}) or {}) if _ip is not None else None,
            "max_pixels": getattr(_ip, "max_pixels", None),
            "min_pixels": getattr(_ip, "min_pixels", None),
            "MAX_PIXELS_target": MAX_PIXELS,
        }
        print(f"[processor-info] {json.dumps(_proc_info, ensure_ascii=False)}")
        _ld = os.environ.get("LOG_DIR")
        if _ld:
            os.makedirs(_ld, exist_ok=True)
            with open(os.path.join(_ld, "processor_info.json"), "w", encoding="utf-8") as _f:
                json.dump(_proc_info, _f, ensure_ascii=False, indent=2)

    # Wrap as DDP model
 #   if is_distributed:
  #      model = DDP(model, device_ids=[device])
    model.eval()  # Inference mode

    # Initialize result statistics structure
    outcome = {
        "mobile": {
            "text": {"total": 0, "correct": 0},
            "icon": {"total": 0, "correct": 0},
        },
        "desktop": {
            "text": {"total": 0, "correct": 0},
            "icon": {"total": 0, "correct": 0},
        },
        "web": {
            "text": {"total": 0, "correct": 0},
            "icon": {"total": 0, "correct": 0},
        }
    }

    # Determine task list
    tasks = ["mobile", "desktop", "web"] if args.task == "all" else [args.task]

    # Global error records (accumulated across tasks), appended in task loop
    wrong_records_all = []
    # Full sample logger (one shard per rank), controlled by LOG_DIR env var
    eval_logger = EvalLogger(os.environ.get("LOG_DIR"), benchmark="screenspot", rank=rank)

    for task in tasks:
        # Load task data
        dataset = f"screenspot_{task}.json"
        data_path = os.path.join(args.screenspot_test, dataset)
        try:
            with open(data_path, 'r') as f:
                screenspot_data = json.load(f)
            if rank == 0:
                print(f"Loaded {task} dataset, {len(screenspot_data)} samples")
        except Exception as e:
            if rank == 0:
                logging.error(f"Failed to read {data_path}: {e}")
            continue  # Skip task if data loading failed

        # Create dataset and distributed sampler
        dataset = LazySupervisedDataset(screenspot_data, processor, args.screenspot_imgs, template)
        sampler = NoPaddingDistributedSampler(dataset, shuffle=False) if is_distributed else None
        
        dataloader = DataLoader(
            dataset, 
            batch_size=args.batch_size,
            shuffle=(sampler is None),
            num_workers=args.num_workers,
            collate_fn=collate_fn,
            sampler=sampler,
            pin_memory=True,
            drop_last=False  # Do not drop the last incomplete batch
        )

        # Initialize task statistics (local per-process counts)
        task_stats = {
            "text_correct": 0,
            "text_total": 0,
            "icon_correct": 0,
            "icon_total": 0
        }

        # Error sample details (collected per rank into wrong_records_all). Categories:
        #   parse_failed    - JSON parsing completely failed (regex/json.loads threw exception)
        #   format_unknown  - JSON parsed but neither bbox_2d nor point_2d found
        #   out_of_image    - Coordinates fall outside image bounds
        #   missed_gt       - Coordinates within image but outside GT bbox

        # Progress bar shown on main process only
        if rank == 0:
            pbar = tqdm(dataloader, desc=f"Processing {task}")
        else:
            pbar = dataloader

        # Start inference
        for batch_data in pbar:
            if batch_data is None:
                continue
                
            batch_results = process_batch(model, processor, batch_data, device, is_distributed)
            
            # Evaluate each result
            for result in batch_results:
                try:
                    content = result["output"]
                    metadata = result["metadata"]
                    gt_bbox = metadata["gt_bbox"]
                    data_type = metadata["data_type"]
                    err_category = None  # None means not yet classified as error

                    # Parse predicted coordinates
                    try:
                        parsed = json.loads(content)
                        if "bbox_2d" in parsed[0]:
                            bbox = parsed[0]["bbox_2d"]
                            x1, y1, x2, y2 = bbox
                            x, y = (x1 + x2) / 2, (y1 + y2) / 2
                        elif "point_2d" in parsed[0]:
                            x, y = parsed[0]["point_2d"]
                        else:
                            x, y = 0, 0  # Default coordinates for format error
                            err_category = "format_unknown"

                        # Coordinate conversion
                        if args.raw_coords:
                            # Model output is already in original-image pixels, use directly
                            x, y = round(x), round(y)
                        elif args.abs_v2:
                            # processor-resized pixels → original-image pixels
                            x = round(x * metadata["img_width"] / result["input_width"])
                            y = round(y * metadata["img_height"] / result["input_height"])
                        else:
                            # 0-1000 normalized → original-image pixels
                            x = round(x /1000 * metadata["img_width"])
                            y = round(y /1000 * metadata["img_height"])
                    except Exception as e:
                        if rank == 0:
                            logging.warning(f"Parse error: {e}, content: {content}")
                        x, y = 0, 0
                        err_category = "parse_failed"

                    # Check if prediction hits GT box
                    click_point = [x, y]
                    is_correct = (gt_bbox[0] <= click_point[0] <= gt_bbox[2]) and (gt_bbox[1] <= click_point[1] <= gt_bbox[3])

                    # Log all samples — write every sample to disk (both correct and incorrect)
                    eval_logger.log({
                        "benchmark": "screenspot",
                        "task": task,
                        "item_id": metadata.get("item_id"),
                        "img_filename": metadata.get("img_filename"),
                        "instruction": metadata.get("instruction"),
                        "data_type": data_type,
                        "data_source": metadata.get("data_source"),
                        "gt_bbox": gt_bbox,
                        "img_width": metadata["img_width"],
                        "img_height": metadata["img_height"],
                        "input_width": result.get("input_width"),
                        "input_height": result.get("input_height"),
                        "raw_output": result.get("raw_output", ""),
                        "cleaned_text": content,
                        "click_point": click_point,
                        "is_correct": bool(is_correct),
                        "category": err_category,
                    })

                    # Update statistics
                    if data_type == 'text':
                        task_stats["text_total"] += 1
                        if is_correct:
                            task_stats["text_correct"] += 1
                    else:  # icon
                        task_stats["icon_total"] += 1
                        if is_correct:
                            task_stats["icon_correct"] += 1

                    # Error archiving: if already classified as parse_failed / format_unknown, record directly;
                    # otherwise check if point falls outside image -> out_of_image; inside image but outside GT -> missed_gt.
                    if not is_correct:
                        if err_category is None:
                            img_w, img_h = metadata["img_width"], metadata["img_height"]
                            if x < 0 or x >= img_w or y < 0 or y >= img_h:
                                err_category = "out_of_image"
                            else:
                                err_category = "missed_gt"
                        wrong_records_all.append({
                            "task": task,
                            "item_id": metadata.get("item_id"),
                            "img_filename": metadata.get("img_filename", ""),
                            "instruction": metadata.get("instruction", ""),
                            "data_type": data_type,
                            "gt_bbox": gt_bbox,
                            "img_width": metadata["img_width"],
                            "img_height": metadata["img_height"],
                            "input_width": result.get("input_width"),
                            "input_height": result.get("input_height"),
                            "raw_output": result.get("raw_output", ""),
                            "cleaned_text": content,
                            "click_point": [x, y],
                            "category": err_category,
                        })

                except Exception as e:
                    if rank == 0:
                        logging.error(f"Error during result evaluation: {e}")
                    continue

        # Distributed aggregation of statistics
        if is_distributed:
            # Gather statistics from all processes
            all_stats = [None] * world_size
            dist.all_gather_object(all_stats, task_stats)
            
            # Main process aggregates results
            if rank == 0:
                total_text_correct = 0
                total_text_total = 0
                total_icon_correct = 0
                total_icon_total = 0
                
                for stats in all_stats:
                    total_text_correct += stats["text_correct"]
                    total_text_total += stats["text_total"]
                    total_icon_correct += stats["icon_correct"]
                    total_icon_total += stats["icon_total"]
                
                # Update global results
                outcome[task]["text"]["correct"] = total_text_correct
                outcome[task]["text"]["total"] = total_text_total
                outcome[task]["icon"]["correct"] = total_icon_correct
                outcome[task]["icon"]["total"] = total_icon_total
        else:
            # Non-distributed: use local statistics directly
            outcome[task]["text"]["correct"] = task_stats["text_correct"]
            outcome[task]["text"]["total"] = task_stats["text_total"]
            outcome[task]["icon"]["correct"] = task_stats["icon_correct"]
            outcome[task]["icon"]["total"] = task_stats["icon_total"]


    # Only main process outputs final results
    if rank == 0:
        print("="*100)
        print("Inference Results Summary:")

        overall_text_total = 0
        overall_icon_total = 0
        overall_text_correct = 0
        overall_icon_correct = 0

        for task in tasks:
            res = outcome[task]
            overall_text_correct += res["text"]["correct"]
            overall_icon_correct += res["icon"]["correct"]
            overall_text_total += res["text"]["total"]
            overall_icon_total += res["icon"]["total"]
            
            text_acc = res["text"]["correct"] / res["text"]["total"] if res["text"]["total"] > 0 else 0
            icon_acc = res["icon"]["correct"] / res["icon"]["total"] if res["icon"]["total"] > 0 else 0
            total = res["text"]["total"] + res["icon"]["total"]
            acc = (res["text"]["correct"] + res["icon"]["correct"]) / total if total > 0 else 0
            
            print(f"{'-'*100}")
            print(f'Task {task} Accuracy: {acc:.4f}  ({res["text"]["correct"] + res["icon"]["correct"]} / {total})')
            print(f'    text Accuracy: {text_acc:.4f}  ({res["text"]["correct"]} / {res["text"]["total"]})')
            print(f'    icon Accuracy: {icon_acc:.4f}  ({res["icon"]["correct"]} / {res["icon"]["total"]})')


        total = overall_text_total + overall_icon_total
        overall_acc = (overall_text_correct + overall_icon_correct) / total if total > 0 else 0
        overall_text_acc = overall_text_correct / overall_text_total if overall_text_total > 0 else 0
        overall_icon_acc = overall_icon_correct / overall_icon_total if overall_icon_total > 0 else 0
        
        print(f"{'-'*100}")
        print(f"Overall Correct: {overall_text_correct + overall_icon_correct}")
        print(f"Overall Total: {total}")
        print(f"Final Accuracy: {overall_acc:.4f}")
        print(f"Final text Accuracy: {overall_text_acc:.4f} ")
        print(f"Final icon Accuracy: {overall_icon_acc:.4f}")


    # ===== Error analysis: aggregate error samples across ranks, stats by category + examples + dump =====
    if is_distributed:
        all_wrong = [None] * world_size
        dist.all_gather_object(all_wrong, wrong_records_all)
    else:
        all_wrong = [wrong_records_all]

    if rank == 0:
        merged_wrong = [r for sub in all_wrong for r in (sub or [])]
        from collections import Counter, defaultdict
        cat_counts = Counter(r["category"] for r in merged_wrong)

        print("\n" + "="*100)
        print("Error Diagnosis")
        print("="*100)
        print(f"Total errors: {len(merged_wrong)}")
        print(f"{'-'*100}")
        print("Distribution by error type:")
        for cat in ("parse_failed", "format_unknown", "out_of_image", "missed_gt"):
            cnt = cat_counts.get(cat, 0)
            pct = cnt / len(merged_wrong) * 100 if merged_wrong else 0
            print(f"  {cat:<16s}: {cnt:>6d}  ({pct:5.2f}%)")

        # Pick 1 sample per category as example
        by_cat = defaultdict(list)
        for r in merged_wrong:
            by_cat[r["category"]].append(r)

        print(f"\n{'-'*100}")
        print("Error examples (1 per category):")
        for cat in ("parse_failed", "format_unknown", "out_of_image", "missed_gt"):
            samples = by_cat.get(cat, [])
            if not samples:
                continue
            ex = samples[0]
            raw = ex.get("raw_output", "")
            if len(raw) > 300:
                raw = raw[:300] + "...[truncated]"
            print(f"\n[{cat}] task={ex['task']} data_type={ex['data_type']}")
            print(f"  img_filename: {ex['img_filename']}")
            print(f"  instruction : {ex['instruction']}")
            print(f"  gt_bbox     : {ex['gt_bbox']}")
            print(f"  img_size    : {ex['img_width']}x{ex['img_height']}  (processor-input: {ex['input_width']}x{ex['input_height']})")
            print(f"  click_point : {ex['click_point']}")
            print(f"  cleaned_text: {ex['cleaned_text']}")
            print(f"  raw_output  : {raw!r}")

        # Write full error records to JSONL for later inspection. Prefer LOG_DIR;
        # fall back to current working directory if LOG_DIR is not set.
        _log_dir = os.environ.get("LOG_DIR") or os.getcwd()
        err_dump_path = os.environ.get(
            "ERROR_DUMP_PATH",
            os.path.join(_log_dir, "screenspot_errors.jsonl"),
        )
        try:
            os.makedirs(os.path.dirname(err_dump_path) or ".", exist_ok=True)
            with open(err_dump_path, "w") as f:
                for r in merged_wrong:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"\nFull error records written to: {err_dump_path}")
        except Exception as e:
            logging.error(f"Failed to write error file: {e}")

    # Close full sample logger
    eval_logger.close()
    if rank == 0 and eval_logger.enabled:
        d = eval_logger.path.parent
        print(f"\nFull sample logs (one shard per rank) written to: {d}")
        print(f"  Merge command: cat {d}/screenspot.rank*.jsonl > {d}/screenspot.jsonl")

    # Clean up distributed environment
    if is_distributed:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
