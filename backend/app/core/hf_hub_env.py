"""
在加载 transformers / huggingface_hub 模型之前设置环境变量。

默认 huggingface_hub 连接超时约 10s，国内访问 huggingface.co 易失败；
可配合 HF_ENDPOINT 镜像或拉长超时。
"""

from __future__ import annotations

import os
from typing import Any


def sync_hf_env_from_settings(settings: Any) -> None:
    """
    将 Pydantic Settings 中的 HF 字段同步到 os.environ。
    huggingface_hub 只读环境变量，不把 .env 里未声明的键注入进程，故需在启动时显式写入。
    """
    pairs = [
        ("HF_ENDPOINT", getattr(settings, "HF_ENDPOINT", None)),
        ("HF_HOME", getattr(settings, "HF_HOME", None)),
        ("HF_TOKEN", getattr(settings, "HF_TOKEN", None)),
        ("TRANSFORMERS_CACHE", getattr(settings, "TRANSFORMERS_CACHE", None)),
        ("HF_HUB_DOWNLOAD_TIMEOUT", getattr(settings, "HF_HUB_DOWNLOAD_TIMEOUT", None)),
    ]
    for key, val in pairs:
        if val is None:
            continue
        s = str(val).strip()
        if s:
            os.environ[key] = s


def apply_hf_hub_env_defaults() -> None:
    """幂等：仅对未设置的环境变量写入默认值。"""
    # 单次下载/连接超时（秒），官方默认偏短，易在国内网络下失败
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
    # huggingface_hub 对 `HEAD` / etag 的超时（默认约 10s，常导致国内网络反复重试）
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "120")
    # 默认关闭遥测，减少离线/受限网络下的不确定性
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
