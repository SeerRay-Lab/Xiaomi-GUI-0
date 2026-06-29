# -*- coding: utf-8 -*-
"""扫码配对模块：PC 显示二维码，手机扫码后回拨 PC 建立连接。

公开 API：
    PairingServer    - PC 本地回拨 HTTP 服务（端口 9876，占用则回退）
    PairingPayload   - 二维码载荷（dataclass，序列化为 JSON）
    build_qr_image   - 生成二维码 QImage，用于 QLabel 显示

两端字段约定（JSON，camelCase 与 Android 侧 Protocol.kt 保持一致）：
    二维码 → 手机：
        {
            "v": 1,
            "pcIp": "192.168.1.23",
            "pcPort": 9876,
            "token": "301295",
            "pcName": "MacBook-Pro",
            "exp": 1714200000   # unix 秒，默认 60s 后过期
        }
    手机回拨 POST /pair：
        {
            "v": 1,
            "phoneIp": "192.168.1.88",
            "phonePort": 8765,
            "phoneToken": "889021",
            "phoneName": "Mi 14",
            "token": "301295"   # 回显二维码里的 PC 端 token，校验后才放行
        }
"""
from gui.pairing.payload import PairingPayload, PairResult
from gui.pairing.server import PairingServer
from gui.pairing.qrcode import build_qr_image

__all__ = ["PairingPayload", "PairResult", "PairingServer", "build_qr_image"]
