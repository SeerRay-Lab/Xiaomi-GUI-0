# -*- coding: utf-8 -*-
"""二维码生成：把 PairingPayload 的 JSON 编码成 QImage 供 QLabel 显示。

依赖 `qrcode` 库（纯 Python，无 C 扩展，MIT）。打包进 PyInstaller 无特殊处理。
"""
from __future__ import annotations

import io
import logging
from typing import Optional

from PySide6.QtGui import QImage

logger = logging.getLogger(__name__)


def build_qr_image(payload_json: str, box_size: int = 8, border: int = 2) -> Optional[QImage]:
    """生成二维码 QImage。

    - box_size: 每个码点的像素大小，调大二维码整体变大。UI 上一般 6~10 合适。
    - border: 四周留白的码点数，< 2 扫码率明显下降，保持默认。
    - 出错（通常是 qrcode 库没装）返回 None，上层给提示让用户 pip install 一下。
    """
    try:
        import qrcode
    except ImportError:
        logger.error("未安装 qrcode 库；pip install qrcode 后重试")
        return None

    qr = qrcode.QRCode(
        version=None,                             # 自动选合适的版本
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload_json)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # PIL.Image → QImage：走 PNG 字节流最省心（不碰 raw bits / stride 坑）
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    qimg = QImage.fromData(buf.getvalue(), "PNG")
    return qimg if not qimg.isNull() else None
