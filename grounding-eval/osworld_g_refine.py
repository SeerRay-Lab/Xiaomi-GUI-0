import re
import os
import json
import math
import torch
import logging
import argparse
from tqdm import tqdm
from PIL import Image
from jinja2 import Template
import torch.distributed as dist
from torch.utils.data import Dataset, DataLoader
from torch.utils.data.sampler import Sampler
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor, AutoModelForImageTextToText
from qwen_vl_utils import process_vision_info
from eval_log import EvalLogger

logging.basicConfig(level=logging.INFO)
MAX_PIXELS = 3_211_264


class NoPaddingDistributedSampler(Sampler):
    def __init__(self, dataset, shuffle=False, seed=0):
        self.dataset = dataset
        self.world_size = dist.get_world_size()
        self.rank = dist.get_rank()
        self.epoch = 0
        self.seed = seed
        self.shuffle = shuffle

        self.total_size = len(dataset)
        self.per_rank_size = math.ceil(self.total_size / self.world_size)
        self.rank_size = min(self.per_rank_size, self.total_size - self.rank * self.per_rank_size)

        self.start_idx = self.rank * self.per_rank_size
        self.end_idx = self.start_idx + self.rank_size

    def __iter__(self):
        if self.shuffle:
            g = torch.Generator()
            g.manual_seed(self.seed + self.epoch)
            indices = torch.randperm(self.total_size, generator=g).tolist()
        else:
            indices = list(range(self.total_size))
        indices = indices[self.start_idx:self.end_idx]
        return iter(indices)

    def __len__(self):
        return self.rank_size

    def set_epoch(self, epoch):
        self.epoch = epoch


class LazySupervisedDataset(Dataset):
    def __init__(self, data_items, processor, imgs_dir, template, system_prompt="You are a GUI Agent."):
        self.data_items = data_items
        self.processor = processor
        self.imgs_dir = imgs_dir
        self.template = template
        self.system_prompt = system_prompt

    def __len__(self):
        return len(self.data_items)

    def __getitem__(self, idx):
        item = self.data_items[idx]
        filename = item["image_path"]
        img_path = os.path.join(self.imgs_dir, filename)

        try:
            image = Image.open(img_path).convert("RGB")
            image_w, image_h = image.size
            instruction = item["instruction"]
            query = self.template.render(instruction=instruction)

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": query},
                ]}
            ]

            # box_coordinates: [x, y, w, h] -> [x1, y1, x2, y2]
            bc = item["box_coordinates"]
            gt_bbox = [bc[0], bc[1], bc[0] + bc[2], bc[1] + bc[3]]

            metadata = {
                "gt_bbox": gt_bbox,
                "img_width": image_w,
                "img_height": image_h,
                "item_id": idx,
                "sample_id": item.get("id", ""),
                "img_filename": filename,
                "img_path": img_path,
                "instruction": instruction,
                "query": query,
                "gui_types": item.get("GUI_types", []),
            }

            if self.processor is None:
                return {
                    "text": "",
                    "images": image,
                    "videos": None,
                    "metadata": metadata
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


def strip_think(text):
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'^.*?</think>', '', text, flags=re.DOTALL)
    return text.strip()


def process_batch_api(api_url, model_name, system_prompt, batch_data):
    from api_inference import call_api_batch
    if batch_data is None:
        return []

    items = [(m["query"], m["img_path"]) for m in batch_data["metadata"]]
    output_texts = call_api_batch(api_url, model_name, system_prompt, items, max_workers=len(items))

    results = []
    for idx, output_text in enumerate(output_texts):
        metadata = batch_data["metadata"][idx]
        output_text = output_text or ""

        raw_point = False
        cleaned_output = strip_think(output_text)
        try:
            tool_call_match = re.search(r'<tool_call>\s*(.*?)\s*</tool_call>', cleaned_output, re.DOTALL)
            if tool_call_match:
                tool_call_json = json.loads(tool_call_match.group(1))
                pos = tool_call_json.get("position", [0, 0])
                img_w = metadata["img_width"]
                img_h = metadata["img_height"]
                px = pos[0] * img_w
                py = pos[1] * img_h
                cleaned_text = json.dumps([{"point_2d": [px, py]}], ensure_ascii=False)
                raw_point = True
            elif "```json" in cleaned_output:
                cleaned_text = re.search(r'```json\n(.*?)\n```', cleaned_output, re.DOTALL).group(1).strip()
            elif 'bbox' in cleaned_output and re.search(r'\[\s*\d+[\s,]+\d+[\s,]+\d+[\s,]+\d+\s*\]', cleaned_output):
                bbox = re.search(r'\[\s*\d+[\s,]+\d+[\s,]+\d+[\s,]+\d+\s*\]', cleaned_output).group(0)
                cleaned_text = f'[{{"bbox_2d": {bbox}}}]'
            elif re.search(r'<point>(.*?)</point>', cleaned_output):
                point = re.search(r'<point>(.*?)</point>', cleaned_output).group(1)
                cleaned_text = f'[{{"point_2d": {point}}}]'
            else:
                cleaned_text = f'[{{"bbox_2d": {cleaned_output}}}]'
        except Exception as e:
            logging.error(e)
            cleaned_text = json.dumps([{"point_2d": [0, 0]}], ensure_ascii=False)

        results.append({
            "output": cleaned_text,
            "raw_output": output_text,
            "raw_point": raw_point,
            "input_width": metadata["img_width"],
            "input_height": metadata["img_height"],
            "metadata": metadata
        })

    return results


def process_batch(model, processor, batch_data, device, is_distributed):
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
            raw_point = False
            try:
                tool_call_match = re.search(r'<tool_call>\s*(.*?)\s*</tool_call>', output_text, re.DOTALL)
                if tool_call_match:
                    tool_call_json = json.loads(tool_call_match.group(1))
                    pos = tool_call_json.get("position", [0, 0])
                    img_w = batch_data["metadata"][idx]["img_width"]
                    img_h = batch_data["metadata"][idx]["img_height"]
                    px = pos[0] * img_w
                    py = pos[1] * img_h
                    cleaned_text = json.dumps([{"point_2d": [px, py]}], ensure_ascii=False)
                    raw_point = True
                elif "```json" in output_text:
                    cleaned_text = re.search(r'```json\n(.*?)\n```', output_text, re.DOTALL).group(1).strip()
                elif 'bbox' in output_text and re.search(r'\[\s*\d+[\s,]+\d+[\s,]+\d+[\s,]+\d+\s*\]', output_text):
                    bbox = re.search(r'\[\s*\d+[\s,]+\d+[\s,]+\d+[\s,]+\d+\s*\]', output_text).group(0)
                    cleaned_text = f'[{{"bbox_2d": {bbox}}}]'
                elif re.search(r'<point>(.*?)</point>', output_text):
                    point = re.search(r'<point>(.*?)</point>', output_text).group(1)
                    cleaned_text = f'[{{"point_2d": {point}}}]'
                else:
                    cleaned_text = f'[{{"bbox_2d": {output_text}}}]'
            except Exception as e:
                logging.error(e)
                print(output_text)
                cleaned_text = json.dumps([{"point_2d": [0, 0]}], ensure_ascii=False)

            if 'image_grid_thw' in inputs:
                _patch_size = int(getattr(processor.image_processor, "patch_size", 16) or 16)
                input_height = inputs['image_grid_thw'][idx][1] * _patch_size
                input_width = inputs['image_grid_thw'][idx][2] * _patch_size
            else:
                input_height = batch_data["metadata"][idx]["img_height"]
                input_width = batch_data["metadata"][idx]["img_width"]

            results.append({
                "output": cleaned_text,
                "raw_output": output_text,
                "raw_point": raw_point,
                "input_width": input_width.item() if isinstance(input_width, torch.Tensor) else input_width,
                "input_height": input_height.item() if isinstance(input_height, torch.Tensor) else input_height,
                "metadata": batch_data["metadata"][idx]
            })

        return results

    except Exception as e:
        logging.error(f"Error during batch processing: {e}")
        return []


def init_distributed():
    if not dist.is_available():
        return False, 0, 0

    rank = int(os.environ.get('RANK', 0))
    world_size = int(os.environ.get('WORLD_SIZE', 1))

    if world_size <= 1:
        return False, rank, world_size

    dist.init_process_group(backend='nccl', rank=rank, world_size=world_size)
    torch.cuda.set_device(rank % torch.cuda.device_count())

    return True, rank, world_size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-path', type=str, default='')
    parser.add_argument('--api-url', type=str, default=None, help='Remote vLLM API URL')
    parser.add_argument('--model-name', type=str, default='UIAgent', help='Model name for API calls')
    parser.add_argument("--screenspot-imgs", type=str, required=True, help="Path to OSWorld-G images directory")
    parser.add_argument("--screenspot-test", type=str, required=True, help="Path to OSWorld-G annotation directory")
    parser.add_argument("--template", type=str, required=True)
    parser.add_argument("--system-prompt", type=str, default=None, help="Path to system prompt file")
    parser.add_argument("--batch-size", type=int, default=4, help="Batch size per GPU")
    parser.add_argument("--num-workers", type=int, default=4, help="Number of data loading workers")
    parser.add_argument("--abs", action="store_true")
    parser.add_argument("--abs_v2", action="store_true", help="Model outputs in processor-resized pixel space; rescale to original image")
    parser.add_argument("--raw_coords", action="store_true", help="Model outputs raw original-image pixel coordinates, no rescaling")
    parser.add_argument('--local-rank', type=int, default=-1)
    args = parser.parse_args()

    with open(args.template) as f:
        template = Template(f.read())

    system_prompt = "You are a GUI Agent."
    if args.system_prompt:
        with open(args.system_prompt) as f:
            system_prompt = f.read().strip()

    if args.api_url:
        is_distributed, rank, world_size = False, 0, 1
        device = None
        model = None
        processor = None
    else:
        is_distributed, rank, world_size = init_distributed()
        device = torch.device(f"cuda:{rank % torch.cuda.device_count()}" if torch.cuda.is_available() else "cpu")

    if rank == 0:
        if args.api_url:
            print(f"API inference mode: {args.api_url}")
        else:
            print(f"Distributed mode: {'enabled' if is_distributed else 'disabled'}, total processes: {world_size}")
            print(f"Using device: {device}")

    if not args.api_url:
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
                trust_remote_code=True
            ).to(device)

        processor = AutoProcessor.from_pretrained(args.model_path, trust_remote_code=True)
        if hasattr(processor, "image_processor") and isinstance(getattr(processor.image_processor, "size", None), dict):
            processor.image_processor.size = {**processor.image_processor.size, "longest_edge": MAX_PIXELS}

        model.eval()

    # Load data - use refined version
    data_path = os.path.join(args.screenspot_test, "OSWorld-G_refined.json")
    try:
        with open(data_path, 'r') as f:
            all_data = json.load(f)
        if rank == 0:
            print(f"Loaded OSWorld-G-Refine dataset, {len(all_data)} samples")
    except Exception as e:
        if rank == 0:
            logging.error(f"Failed to read {data_path}: {e}")
        return

    dataset = LazySupervisedDataset(all_data, processor, args.screenspot_imgs, template, system_prompt)
    sampler = NoPaddingDistributedSampler(dataset, shuffle=False) if is_distributed else None

    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        collate_fn=collate_fn,
        sampler=sampler,
        pin_memory=True,
        drop_last=False
    )

    total_correct = 0
    total_count = 0

    if rank == 0:
        pbar = tqdm(dataloader, desc="Processing OSWorld-G-Refine")
    else:
        pbar = dataloader

    eval_logger = EvalLogger(os.environ.get("LOG_DIR"), benchmark="osworld_g_refine", rank=rank)

    for batch_data in pbar:
        if batch_data is None:
            continue

        if args.api_url:
            batch_results = process_batch_api(args.api_url, args.model_name, system_prompt, batch_data)
        else:
            batch_results = process_batch(model, processor, batch_data, device, is_distributed)

        for result in batch_results:
            try:
                content = result["output"]
                metadata = result["metadata"]
                gt_bbox = metadata["gt_bbox"]

                try:
                    parsed = json.loads(content)
                    if "bbox_2d" in parsed[0]:
                        bbox = parsed[0]["bbox_2d"]
                        x1, y1, x2, y2 = bbox
                        x, y = (x1 + x2) / 2, (y1 + y2) / 2
                    elif "point_2d" in parsed[0]:
                        x, y = parsed[0]["point_2d"]
                    else:
                        x, y = 0, 0

                    if result.get("raw_point"):
                        x, y = round(x), round(y)
                    elif args.raw_coords:
                        x, y = round(x), round(y)
                    elif args.abs_v2:
                        x = round(x * metadata["img_width"] / result["input_width"])
                        y = round(y * metadata["img_height"] / result["input_height"])
                    else:
                        x = round(x / 1000 * metadata["img_width"])
                        y = round(y / 1000 * metadata["img_height"])
                except Exception as e:
                    raw_text = result.get("raw_output", content)
                    coord_match = re.search(r'\[\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)[\s,]+(\d+)\s*\]', raw_text)
                    if coord_match:
                        x1, y1, x2, y2 = int(coord_match.group(1)), int(coord_match.group(2)), int(coord_match.group(3)), int(coord_match.group(4))
                        x, y = (x1 + x2) / 2, (y1 + y2) / 2
                        if result.get("raw_point"):
                            x, y = round(x), round(y)
                        elif args.raw_coords:
                            x, y = round(x), round(y)
                        elif args.abs_v2:
                            x = round(x * metadata["img_width"] / result["input_width"])
                            y = round(y * metadata["img_height"] / result["input_height"])
                        else:
                            x = round(x / 1000 * metadata["img_width"])
                            y = round(y / 1000 * metadata["img_height"])
                    else:
                        if rank == 0:
                            logging.warning(f"Parse error: {e}, content: {content}")
                        x, y = 0, 0

                click_point = [x, y]
                is_correct = (gt_bbox[0] <= click_point[0] <= gt_bbox[2]) and (gt_bbox[1] <= click_point[1] <= gt_bbox[3])

                eval_logger.log({
                    "benchmark": "osworld_g_refine",
                    "item_id": metadata.get("item_id"),
                    "sample_id": metadata.get("sample_id"),
                    "img_filename": metadata.get("img_filename"),
                    "instruction": metadata.get("instruction"),
                    "gui_types": metadata.get("gui_types"),
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

                total_count += 1
                if is_correct:
                    total_correct += 1

            except Exception as e:
                if rank == 0:
                    logging.error(f"Error during result evaluation: {e}")
                continue

    # Release model GPU memory to avoid OOM during allgather
    import gc
    if not args.api_url:
        del model
        gc.collect()
        torch.cuda.empty_cache()

    # Distributed aggregation
    if is_distributed:
        all_stats = [None] * world_size
        dist.all_gather_object(all_stats, {"correct": total_correct, "total": total_count})
        if rank == 0:
            total_correct = sum(s["correct"] for s in all_stats)
            total_count = sum(s["total"] for s in all_stats)

    if rank == 0:
        print("=" * 100)
        print("OSWorld-G-Refine Inference Results Summary:")
        print(f"{'-' * 100}")
        acc = total_correct / total_count if total_count > 0 else 0
        print(f"Overall Correct: {total_correct}")
        print(f"Overall Total: {total_count}")
        print(f"Final Accuracy: {acc:.4f}")

    eval_logger.close()
    if rank == 0 and eval_logger.enabled:
        d = eval_logger.path.parent
        print(f"\nFull sample logs written to: {d}")
        print(f"  Merge command: cat {d}/osworld_g_refine.rank*.jsonl > {d}/osworld_g_refine.jsonl")

    if is_distributed:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
