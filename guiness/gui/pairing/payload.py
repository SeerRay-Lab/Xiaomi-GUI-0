# -*- coding: utf-8 -*-
"""配对协议的数据结构。

二维码载荷和手机回拨结果都是 dataclass，独立一份避免上层代码到处拼 dict。
"""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Optional

PAYLOAD_VERSION = 1
DEFAULT_EXPIRE_SECONDS = 60
TOKEN_DIGITS = 6  # 保持和 Android TokenStore 一致：6 位十进制数字


def _random_token(digits: int = TOKEN_DIGITS) -> str:
    """生成 6 位数字 token。用 secrets 保证不可预测，和 Android 的 SecureRandom 对齐。"""
    return "".join(str(secrets.randbelow(10)) for _ in range(digits))


@dataclass
class PairingPayload:
    """PC 生成、写进二维码的载荷。"""
    pc_ip: str
    pc_port: int
    token: str
    pc_name: str
    exp: int  # unix 秒；手机在此时间之后扫到应拒绝

    def to_json(self) -> str:
        return json.dumps(
            {
                "v": PAYLOAD_VERSION,
                "pcIp": self.pc_ip,
                "pcPort": self.pc_port,
                "token": self.token,
                "pcName": self.pc_name,
                "exp": self.exp,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @classmethod
    def create(cls, pc_ip: str, pc_port: int, pc_name: str,
               token: Optional[str] = None,
               expire_seconds: int = DEFAULT_EXPIRE_SECONDS) -> "PairingPayload":
        return cls(
            pc_ip=pc_ip,
            pc_port=pc_port,
            token=token or _random_token(),
            pc_name=pc_name,
            exp=int(time.time()) + expire_seconds,
        )


@dataclass
class PairResult:
    """手机回拨 POST /pair 的结果。"""
    phone_ip: str
    phone_port: int
    phone_token: str
    phone_name: str

    def endpoint(self) -> str:
        """拼装现成的 WifiBackend endpoint 字符串。"""
        return f"{self.phone_ip}:{self.phone_port}"

    def to_dict(self) -> dict:
        return asdict(self)
