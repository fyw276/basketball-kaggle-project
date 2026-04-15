"""
本地推理服务：直接调用推理逻辑，不经过 HTTP
这是 mock_finetuned_infer.py 的轻量级版本
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Tuple

# 导入缓存服务
try:
    from .cache_service import cache_recognition_result, get_recognition_result

    HAS_CACHE = True
except ImportError:
    HAS_CACHE = False

# 类别列表
CATEGORIES = ["上衣", "裤子", "裙子", "连衣裙", "外套", "马面裙", "鞋", "包"]

# 特征向量
CATEGORY_FEATURES = {
    "上衣": [0.1] * 32,
    "裤子": [0.2] * 32,
    "裙子": [0.3] * 32,
    "连衣裙": [0.35] * 32,
    "外套": [0.15] * 32,
    "马面裙": [0.32] * 32,
    "鞋": [0.8] * 32,
    "包": [0.7] * 32,
}

# 索引缓存
IMAGE_HASH_TO_CATEGORY: Dict[str, str] = {}
_INDEX_LOADED = False


def _load_index(index_data_path: Path) -> int:
    """从训练数据加载索引"""
    global _INDEX_LOADED, IMAGE_HASH_TO_CATEGORY

    if _INDEX_LOADED:
        return len(IMAGE_HASH_TO_CATEGORY)

    IMAGE_HASH_TO_CATEGORY.clear()
    if not index_data_path.is_file():
        _INDEX_LOADED = True
        return 0

    try:
        raw = json.loads(index_data_path.read_text(encoding="utf-8"))
    except Exception:
        _INDEX_LOADED = True
        return 0

    if not isinstance(raw, list):
        _INDEX_LOADED = True
        return 0

    indexed = 0
    for row in raw:
        if not isinstance(row, dict):
            continue
        image_path = str(row.get("image_path") or "").strip()
        category = str(row.get("category") or "").strip()
        if not image_path or not category:
            continue

        p = Path(image_path)
        if not p.is_absolute():
            # local_inference.py 位于 backend/app/services，parents[2] 即 backend 根目录
            backend_root = Path(__file__).resolve().parents[2]
            p = backend_root / image_path
        if not p.is_file():
            continue

        try:
            digest = hashlib.sha1(p.read_bytes()).hexdigest()
            IMAGE_HASH_TO_CATEGORY[digest] = category
            indexed += 1
        except Exception:
            continue

    _INDEX_LOADED = True
    return indexed


def _infer_category(image_bytes: bytes, hint: str | None, image_path: str = "") -> Tuple[str, bool]:
    """推理衣服类别"""
    if hint and hint in CATEGORIES:
        return hint, False

    # 第一选择：精确字节哈希匹配
    digest = hashlib.sha1(image_bytes).hexdigest()
    exact = IMAGE_HASH_TO_CATEGORY.get(digest)
    if exact:
        return exact, True

    # 第二选择：从文件路径推断
    path_lower = image_path.lower()
    for cat in CATEGORIES:
        if cat in path_lower:
            return cat, False

    # 第三选择：使用本地品类分类器，避免 JPEG/PNG 固定偏置导致“总是上衣”
    try:
        from app.ml.category_classifier import CategoryClassifier

        cls_cat, _ = CategoryClassifier().classify_category(image_bytes)
        normalize_map = {
            "鞋子": "鞋",
            "包包": "包",
            "下装": "裤子",
        }
        cls_cat = normalize_map.get((cls_cat or "").strip(), (cls_cat or "").strip())
        if cls_cat in CATEGORIES:
            return cls_cat, False
    except Exception:
        pass

    # 第四选择：基于字节分布的稳定回退
    category_idx = sum(image_bytes[:4]) % len(CATEGORIES)
    return CATEGORIES[category_idx], False


def infer(
    image_bytes: bytes,
    hint: str = "unknown",
    image_path: str = "",
    return_feature_vector: bool = True,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    推理函数

    Args:
        image_bytes: 图像小节
        hint: 类别提示
        image_path: 图像路径（用于提取类别）
        return_feature_vector: 是否返回特征向量
        use_cache: 是否使用缓存

    Returns:
        推理结果字典
    """
    if len(image_bytes) == 0:
        raise ValueError("Image is empty")

    # 尝试从缓存获取
    if use_cache and HAS_CACHE:
        cached_result = get_recognition_result(image_bytes)
        if cached_result:
            cached_result["_from_cache"] = True
            return cached_result

    # 推理类别
    category, from_index = _infer_category(image_bytes, hint, image_path)
    feature_vector = CATEGORY_FEATURES.get(category, [0.5] * 32)

    # 置信度
    if from_index:
        category_confidence = 0.98
    else:
        category_confidence = 0.75 + (hash(image_bytes) % 20) / 100.0
        category_confidence = min(0.95, max(0.65, category_confidence))

    response = {
        "category": category,
        "category_confidence": category_confidence,
        "style_tags": ["casual"],
        "fit_type": "regular",
        "occasions": ["daily", "work"],
        "_from_cache": False,
    }
    if return_feature_vector:
        response["feature_vector"] = feature_vector

    # 缓存结果
    if HAS_CACHE:
        cache_recognition_result(image_bytes, response)

    return response


# 初始化索引
def init(training_data_path: str = None):
    """初始化推理服务"""
    if training_data_path is None:
        # local_inference.py 位于 backend/app/services，parents[2] 即 backend 目录
        backend_root = Path(__file__).resolve().parents[2]
        training_data_path = backend_root / "training_data.json"
    else:
        training_data_path = Path(training_data_path)

    count = _load_index(training_data_path)
    print(f"[OK] Local inference service initialized: {count} samples indexed")
