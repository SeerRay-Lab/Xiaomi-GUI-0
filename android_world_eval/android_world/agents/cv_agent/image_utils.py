import base64
import io
import math
import os
import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

IMAGE_FACTOR = 28
MIN_PIXELS = 52 * 4 * 14 * 14
MAX_PIXELS = int(os.environ.get("CV_AGENT_MAX_PIXELS", 700 * 4 * 14 * 14))
MAX_RATIO = 200
JPEG_QUALITY = int(os.environ.get("CV_AGENT_JPEG_QUALITY", 50))


def _round_by_factor(value: int, factor: int) -> int:
    return round(value / factor) * factor


def _floor_by_factor(value: float, factor: int) -> int:
    return int(math.floor(value / factor)) * factor


def _ceil_by_factor(value: float, factor: int) -> int:
    return int(math.ceil(value / factor)) * factor


def smart_resize(
    height: int,
    width: int,
    factor: int = IMAGE_FACTOR,
    min_pixels: int = MIN_PIXELS,
    max_pixels: int = MAX_PIXELS,
) -> tuple[int, int]:
    h_bar = max(factor, _round_by_factor(height, factor))
    w_bar = max(factor, _round_by_factor(width, factor))

    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = _floor_by_factor(height / beta, factor)
        w_bar = _floor_by_factor(width / beta, factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = _ceil_by_factor(height * beta, factor)
        w_bar = _ceil_by_factor(width * beta, factor)

    if max(h_bar, w_bar) / min(h_bar, w_bar) > MAX_RATIO:
        if h_bar > w_bar:
            h_bar = int(w_bar * MAX_RATIO)
        else:
            w_bar = int(h_bar * MAX_RATIO)
        h_bar = _floor_by_factor(h_bar, factor)
        w_bar = _floor_by_factor(w_bar, factor)

    return h_bar, w_bar


def encode_screenshot(
    pixels: np.ndarray,
    max_pixels: int = MAX_PIXELS,
    quality: int = JPEG_QUALITY,
) -> str:
    img = Image.fromarray(pixels)
    img = img.convert("RGB")
    w, h = img.size

    new_h, new_w = smart_resize(h, w, max_pixels=max_pixels)
    if new_w != w or new_h != h:
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", optimize=True, quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")
