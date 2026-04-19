"""
在加载 transformers / huggingface_hub 模型之前设置环境变量。

默认 huggingface_hub 连接超时约 10s，国内访问 huggingface.co 易失败；
可配合 HF_ENDPOINT 镜像或拉长超时。
"""

from __future__ import annotations

import importlib.util
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _disable_hf_transfer_if_package_missing() -> None:
    """
    huggingface_hub: HF_HUB_ENABLE_HF_TRANSFER=1 requires the optional `hf_transfer`
    package. If the env is set (often globally on Windows) but the package is
    absent, any from_pretrained (including cache hits) fails immediately.
    """
    flag = (os.environ.get("HF_HUB_ENABLE_HF_TRANSFER") or "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return
    if importlib.util.find_spec("hf_transfer") is not None:
        return
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    logger.info(
        "HF_HUB_ENABLE_HF_TRANSFER was set but hf_transfer is not installed; "
        "disabled fast transfer. Install with: pip install hf_transfer"
    )


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
    _disable_hf_transfer_if_package_missing()
    # 单次下载/连接超时（秒），官方默认偏短，易在国内网络下失败
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
    # huggingface_hub 对 `HEAD` / etag 的超时（默认约 10s，常导致国内网络反复重试）
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "120")
    # 默认关闭遥测，减少离线/受限网络下的不确定性
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
