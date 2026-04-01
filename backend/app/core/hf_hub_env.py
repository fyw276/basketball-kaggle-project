"""
在加载 transformers / huggingface_hub 模型之前设置环境变量。

默认 huggingface_hub 连接超时约 10s，国内访问 huggingface.co 易失败；
可配合 HF_ENDPOINT 镜像或拉长超时。
"""

import os


def apply_hf_hub_env_defaults() -> None:
    """幂等：仅对未设置的环境变量写入默认值。"""
    # 单次下载/连接超时（秒），官方默认偏短，易在国内网络下失败
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
    # huggingface_hub 对 `HEAD` / etag 的超时（默认约 10s，常导致国内网络反复重试）
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "120")
    # 默认关闭遥测，减少离线/受限网络下的不确定性
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
