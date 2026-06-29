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
from transformers import Qwen2_5_VLForConditionalGeneration, Qwen2VLForConditionalGeneration, AutoProcessor, AutoTokenizer,AutoModelForImageTextToText
from qwen_vl_utils import process_vision_info
from eval_log import EvalLogger

# Initialize logging
logging.basicConfig(level=print)
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
        filename = item["image_path"]
        platform = item["platform"]
        grounding_type = item["grounding_type"]
        img_path = os.path.join(self.screenspot_imgs_dir, platform, filename)

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
                ]}
            ]

            # Prepare GT info
            gt_bbox = item["bbox"]

            metadata = {
                "gt_bbox": gt_bbox,
                "img_width": image_w,
                "img_height": image_h,
                "data_type": item["data_type"],
                "platform": platform,
                "grounding_type": grounding_type,
                "item_id": idx,
                # include platform in filename so server can resolve the nested
                # path (image root is the parent of all platform subdirs).
                "img_filename": os.path.join(platform, filename),
                "instruction": instruction,
            }
            
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
    """Process a batch of data, with is_distributed flag for DDP handling"""
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
        
        # Distinguish DDP-wrapped model from raw model
        with torch.no_grad():
                generated_ids = model.generate(** inputs, max_new_tokens=128, use_cache=True)
        
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        
        output_texts = processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        
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
    parser.add_argument('--model-path', type=str, default='')
    parser.add_argument("--screenspot-imgs", type=str, required=True, help="Path to MMBench-GUI images directory")
    parser.add_argument("--screenspot-test", type=str, required=True, help="Path to MMBench-GUI annotation directory")
    parser.add_argument("--template", type=str, required=True)
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size per GPU for inference")
    parser.add_argument("--num-workers", type=int, default=4, help="Number of workers for data loading")
    parser.add_argument("--abs", action="store_true", help="moxing")
    parser.add_argument("--abs_v2", action="store_true", help="Model outputs in processor-resized pixel space")
    parser.add_argument("--raw_coords", action="store_true", help="Model outputs original-image pixel coords normalized to [0,1] by image width/height")
    args = parser.parse_args()


    with open(args.template) as f:
        template = Template(f.read())
    
    # Initialize distributed environment
    is_distributed, rank, world_size = init_distributed()
    device = torch.device(f"cuda:{rank % torch.cuda.device_count()}" if torch.cuda.is_available() else "cpu")
    
    # Only main process (rank=0) prints info
    if rank == 0:
        print(f"Distributed mode: {'enabled' if is_distributed else 'disabled'}, total processes: {world_size}, current rank: {rank}")
        print(f"Using device: {device}")

    # Load model and processor
    if args.abs:
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            args.model_path,
            torch_dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        ).to(device)
    else:
        model = AutoModelForImageTextToText.from_pretrained(
            args.model_path,
            torch_dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
        ).to(device)
    processor = AutoProcessor.from_pretrained(args.model_path, trust_remote_code=True)
    # Qwen3-VL's image_processor reads size["longest_edge"] (default 16.7M);
    # the old max_pixels kwarg has no effect. Override to MAX_PIXELS here to ensure
    # smart_resize actually caps at 3.21M, consistent with training.
    if hasattr(processor, "image_processor") and isinstance(getattr(processor.image_processor, "size", None), dict):
        processor.image_processor.size = {**processor.image_processor.size, "longest_edge": MAX_PIXELS}
    else:
        print("[warn] image_processor.size cannot be overridden, using default upper limit")
    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    tokenizer.padding_side = 'left'

    # Wrap model with DDP if in distributed mode
 #   if is_distributed:
  #      model = DDP(model, device_ids=[device])
    

    # Load data
    dataset = "L2_annotations.json"
    data_path = os.path.join(args.screenspot_test, dataset)
    try:
        with open(data_path, 'r') as f:
            screenspot_data = json.load(f)
    except Exception as e:
        if rank == 0:
            logging.error(f"Error reading {data_path}: {e}")
        return

    # Initialize result statistics structure
    outcome = {
        "os_windows": {
            "basic": {"total": 0, "correct": 0},
            "advanced": {"total": 0, "correct": 0},
        },
        "os_mac": {
            "basic": {"total": 0, "correct": 0},
            "advanced": {"total": 0, "correct": 0},
        },
        "os_linux": {
            "basic": {"total": 0, "correct": 0},
            "advanced": {"total": 0, "correct": 0},
        },
        "os_ios": {
            "basic": {"total": 0, "correct": 0},
            "advanced": {"total": 0, "correct": 0},
        },
        "os_android": {
            "basic": {"total": 0, "correct": 0},
            "advanced": {"total": 0, "correct": 0},
        },
        "os_web": {
            "basic": {"total": 0, "correct": 0},
            "advanced": {"total": 0, "correct": 0},
        },
    }

    # Create dataset and distributed sampler
    dataset = LazySupervisedDataset(screenspot_data, processor, args.screenspot_imgs, template)
    sampler = NoPaddingDistributedSampler(dataset, shuffle=False) if is_distributed else None
    
    dataloader = DataLoader(
        dataset, 
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        collate_fn=collate_fn,
        sampler=sampler,
        pin_memory=True  # Accelerate data transfer to GPU
    )

    # Only main process shows progress bar
    if rank == 0:
        pbar = tqdm(dataloader, desc=f"Processing")
    else:
        pbar = dataloader

    # Store results for each process
    local_results = []
    # Full sample logger (one shard per rank), controlled by LOG_DIR env var
    eval_logger = EvalLogger(os.environ.get("LOG_DIR"), benchmark="mmbench_gui", rank=rank)

    for batch_data in pbar:
        if batch_data is None:
            continue
            
        batch_results = process_batch(model, processor, batch_data, device, is_distributed)
        local_results.extend(batch_results)
        
        # Evaluate each result
        for result in batch_results:
            try:
                content = result["output"]
                metadata = result["metadata"]
                gt_bbox = metadata["gt_bbox"]
                platform = metadata["platform"]
                grounding_type = metadata["grounding_type"]
                
                outcome[platform][grounding_type]["total"] += 1
                
                try:
                    if "bbox_2d" in content:
                        bbox = json.loads(content)[0]["bbox_2d"]
                        x1, y1, x2, y2 = bbox
                        x, y = (x1 + x2) / 2, (y1 + y2) / 2
                    elif "point_2d" in content:
                        x, y = json.loads(content)[0]["point_2d"]
                    
                    if args.raw_coords:
                        # Original-image pixels → normalized [0,1], same space as GT
                        x = x / metadata["img_width"]
                        y = y / metadata["img_height"]
                    elif args.abs_v2:
                        x = x / result["input_width"]
                        y = y / result["input_height"]
                    else:
                        x = x / 1000
                        y = y / 1000
                except Exception as e:
                    if rank == 0:
                        logging.warning(f"Parse error: {e}, content: {content}")
                    x, y = 0, 0
                
                click_point = [x, y]
                is_correct = (gt_bbox[0] <= click_point[0] <= gt_bbox[2]) and (gt_bbox[1] <= click_point[1] <= gt_bbox[3])

                # Log all samples — every sample is written to disk (both correct and incorrect)
                eval_logger.log({
                    "benchmark": "mmbench_gui",
                    "task": platform,
                    "item_id": metadata.get("item_id"),
                    "img_filename": metadata.get("img_filename"),
                    "instruction": metadata.get("instruction"),
                    "grounding_type": grounding_type,
                    "gt_bbox": gt_bbox,
                    "img_width": metadata["img_width"],
                    "img_height": metadata["img_height"],
                    "input_width": result.get("input_width"),
                    "input_height": result.get("input_height"),
                    "raw_output": result.get("raw_output", ""),
                    "cleaned_text": content,
                    "click_point": click_point,
                    "is_correct": bool(is_correct),
                })

                if is_correct:
                    outcome[platform][grounding_type]["correct"] += 1
            except Exception as e:
                if rank == 0:
                    logging.error(f"Error during result evaluation: {e}")
                continue

    # Release model GPU memory to avoid OOM during allgather
    import gc
    del model
    gc.collect()
    torch.cuda.empty_cache()

    # Gather results from all processes to main process
    if is_distributed:
        all_outcomes = [None] * world_size
        dist.all_gather_object(all_outcomes, outcome)
        
        # Main process aggregates results
        if rank == 0:
            final_outcome = outcome.copy()
            # Initialize final_outcome to all zeros
            for platform in final_outcome:
                for gtype in ["basic", "advanced"]:
                    final_outcome[platform][gtype]["total"] = 0
                    final_outcome[platform][gtype]["correct"] = 0
            
            # Aggregate results from all processes
            for proc_outcome in all_outcomes:
                for platform in proc_outcome:
                    for gtype in ["basic", "advanced"]:
                        final_outcome[platform][gtype]["total"] += proc_outcome[platform][gtype]["total"]
                        final_outcome[platform][gtype]["correct"] += proc_outcome[platform][gtype]["correct"]
            outcome = final_outcome
    else:
        final_outcome = outcome

    # Only main process outputs final results
    if rank == 0:
        print("="*100)
        print("Inference Results Summary:")
        
        overall_basic_total = 0
        overall_advanced_total = 0
        overall_basic_correct = 0
        overall_advanced_correct = 0
        
        for task, res in final_outcome.items():
            overall_basic_correct += res["basic"]["correct"]
            overall_advanced_correct += res["advanced"]["correct"]
            overall_basic_total += res["basic"]["total"]
            overall_advanced_total += res["advanced"]["total"]
            
            basic_acc = res["basic"]["correct"] / res["basic"]["total"] if res["basic"]["total"] > 0 else 0
            advanced_acc = res["advanced"]["correct"] / res["advanced"]["total"] if res["advanced"]["total"] > 0 else 0
            total = res["basic"]["total"] + res["advanced"]["total"]
            acc = (res["basic"]["correct"] + res["advanced"]["correct"]) / total if total > 0 else 0
            
            print(f"{'-'*100}")
            print(f'Task {task} Accuracy: {acc:.4f}  ({res["basic"]["correct"] + res["advanced"]["correct"]} / {total})')
            print(f'    Basic Accuracy: {basic_acc:.4f}  ({res["basic"]["correct"]} / {res["basic"]["total"]})')
            print(f'    Advanced Accuracy: {advanced_acc:.4f}  ({res["advanced"]["correct"]} / {res["advanced"]["total"]})')


        total = overall_basic_total + overall_advanced_total
        overall_acc = (overall_basic_correct + overall_advanced_correct) / total if total > 0 else 0
        overall_basic_acc = overall_basic_correct / overall_basic_total if overall_basic_total > 0 else 0
        overall_advanced_acc = overall_advanced_correct / overall_advanced_total if overall_advanced_total > 0 else 0
        
        print(f"{'-'*100}")
        print(f"Overall Correct: {overall_basic_correct + overall_advanced_correct}")
        print(f"Overall Total: {total}")
        print(f"Final Accuracy: {overall_acc:.4f}")
        print(f"Final Basic Accuracy: {overall_basic_acc:.4f} ")
        print(f"Final Advanced Accuracy: {overall_advanced_acc:.4f}")
        

    eval_logger.close()
    if rank == 0 and eval_logger.enabled:
        print(f"\nFull sample logs (one shard per rank) written to: {eval_logger.path}")

    # Clean up distributed environment
    if is_distributed:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
