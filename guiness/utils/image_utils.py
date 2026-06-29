# -*- coding: utf-8 -*-
"""
图片处理工具
包含图片压缩功能
"""
import os
import logging
import math
from PIL import Image

logger = logging.getLogger(__name__)

# 默认图片压缩参数
IMAGE_FACTOR = 28  
MIN_PIXELS =  52 * 4 * 14 * 14  
MAX_PIXELS = 700 * 4 * 14 * 14  
MAX_RATIO = 200  

def round_by_factor(value: int, factor: int) -> int:
    return round(value / factor) * factor

def floor_by_factor(value: float, factor: int) -> int:
    return int(math.floor(value / factor)) * factor

def ceil_by_factor(value: float, factor: int) -> int:
    return int(math.ceil(value / factor)) * factor

def smart_resize(height: int, width: int, factor: int = IMAGE_FACTOR,
                 min_pixels: int = MIN_PIXELS, max_pixels: int = MAX_PIXELS) -> tuple[int, int]:
    """
    Rescales the image so that the following conditions are met:
    1. Both dimensions (height and width) are divisible by 'factor'.
    2. The total number of pixels is within the range ['min_pixels', 'max_pixels'].
    3. The aspect ratio of the image is maintained as closely as possible.
    """
    if height <= 0 or width <= 0:
        return max(height, factor), max(width, factor)

    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))

    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = floor_by_factor(height / beta, factor)
        w_bar = floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
    
    if max(h_bar, w_bar) / min(h_bar, w_bar) > MAX_RATIO:
        if h_bar > w_bar:
            h_bar = int(w_bar * MAX_RATIO)
        else:
            w_bar = int(h_bar * MAX_RATIO)
        h_bar = floor_by_factor(h_bar, factor)
        w_bar = floor_by_factor(w_bar, factor)
    
    return h_bar, w_bar

def convert_png_to_jpg(source_img, target_img, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS, quality=50):
    try:
        with Image.open(source_img) as img:
            original_width, original_height = img.size
            img = img.convert('RGB')

            compressed_width, compressed_height = original_width, original_height

            if min_pixels > 0 and max_pixels > 0:
                resized_height, resized_width = smart_resize(
                    original_height, original_width,
                    min_pixels=min_pixels, max_pixels=max_pixels
                )
                if resized_width != original_width or resized_height != original_height:
                    img = img.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
                    compressed_width, compressed_height = resized_width, resized_height

            img.save(target_img, "JPEG", optimize=True, quality=quality)
            return True, (compressed_width, compressed_height)
    except Exception:
        logger.exception(f"PNG 转 JPG 失败: {source_img}")
        return False, None

def compress_image(local_path, compress=True, compress_config: dict | None = None):
    """处理本地图片文件，可选压缩 PNG 为 JPG。

    compress_config: 压缩参数 dict（keys: min_pixels/max_pixels/quality）。
    调用方（EpisodeRunner）显式传入；不再回到全局单例。为空时走默认值。
    """
    if not os.path.exists(local_path):
        return local_path, None

    if compress and local_path.lower().endswith('.png'):
        jpg_path = local_path.rsplit('.', 1)[0] + '.jpg'

        cfg = compress_config or {}
        min_p = cfg.get("min_pixels", 52) * 28 * 28
        max_p = cfg.get("max_pixels", 700) * 28 * 28
        quality = cfg.get("quality", 50)

        success, size = convert_png_to_jpg(local_path, jpg_path, min_pixels=min_p, max_pixels=max_p, quality=quality)
        if success and size:
            return jpg_path, size

    try:
        with Image.open(local_path) as img:
            return local_path, img.size
    except Exception:
        return local_path, None
