"""
整套穿搭拆分「保存到衣橱」专用：不依赖 CLIP / Hugging Face，避免首次下载阻塞请求导致前端超时。

特征向量由裁剪图下采样像素构造并 L2 归一化，维度与衣橱其它接口一致（1280），
相似度检索精度弱于 CLIP，但保证离线、弱网环境下可稳定入库。
"""

from __future__ import annotations

import io
from typing import List

import numpy as np
from PIL import Image


def local_split_feature_vector(crop_bytes: bytes, dim: int = 1280) -> List[float]:
    """从裁剪字节生成固定维度向量，无外部模型下载。"""
    img = (
        Image.open(io.BytesIO(crop_bytes)).convert("RGB").resize((56, 56), Image.Resampling.LANCZOS)
    )
    arr = np.asarray(img, dtype=np.float32).ravel()
    if arr.size >= dim:
        v = arr[:dim].copy()
    else:
        v = np.zeros(dim, dtype=np.float32)
        v[: arr.size] = arr
    n = float(np.linalg.norm(v))
    if n > 1e-12:
        v = v / n
    else:
        # 纯色块等极端情况，给随机单位向量避免全零
        rng = np.random.default_rng(abs(hash(crop_bytes[:2048])) % (2**32))
        v = rng.standard_normal(dim, dtype=np.float32)
        v = v / np.linalg.norm(v)
    return v.tolist()
