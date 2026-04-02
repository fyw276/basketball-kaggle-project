"""
整套穿搭图拆分规划：在裁切条带基础上用 CLIP（失败则 MobileNet）标注连衣裙 / 上下装 / 鞋 / 包，减少遗漏与误分。
"""

from __future__ import annotations

import io
from typing import Dict, List, Tuple

from PIL import Image

from app.core.logging import setup_logging
from app.schemas.garment import VALID_CATEGORIES

logger = setup_logging()

# (品类, 归一化裁切框 (l,t,r,b), 置信度)
SplitPlanItem = Tuple[str, Tuple[float, float, float, float], float]


def _coerce_category(raw: str, fallback: str) -> str:
    c = (raw or "").strip()
    if c in VALID_CATEGORIES:
        return c
    aliases = {"包包": "包", "手提包": "包", "背包": "包"}
    if c in aliases and aliases[c] in VALID_CATEGORIES:
        return aliases[c]
    return fallback if fallback in VALID_CATEGORIES else "上衣"


def _recognize_full(image_bytes: bytes) -> Tuple[str, Dict[str, float]]:
    try:
        from app.ml.clip_recognizer import get_clip_recognizer

        r = get_clip_recognizer().recognize(image_bytes)
        scores = r.get("category_scores") or {}
        return str(r.get("category", "上衣")), {k: float(v) for k, v in scores.items()}
    except Exception as e:
        logger.warning(f"CLIP full-image recognition failed, fallback ImageRecognizer: {e}")
        from app.ml.image_recognizer import ImageRecognizer

        ir = ImageRecognizer().recognize(image_bytes)
        return ir.category, {ir.category: float(ir.category_confidence)}


def _recognize_crop(image_bytes: bytes) -> Tuple[str, Dict[str, float]]:
    try:
        from app.ml.clip_recognizer import get_clip_recognizer

        r = get_clip_recognizer().recognize(image_bytes)
        scores = r.get("category_scores") or {}
        return str(r.get("category", "上衣")), {k: float(v) for k, v in scores.items()}
    except Exception as e:
        logger.warning(f"CLIP crop recognition failed, fallback ImageRecognizer: {e}")
        from app.ml.image_recognizer import ImageRecognizer

        ir = ImageRecognizer().recognize(image_bytes)
        return ir.category, {ir.category: float(ir.category_confidence)}


def _crop_to_bytes(img: Image.Image, box: Tuple[float, float, float, float]) -> bytes:
    w, h = img.size
    l, t, r, b = box
    x0, y0 = int(l * w), int(t * h)
    x1, y1 = int(r * w), int(b * h)
    x0, x1 = max(0, x0), min(w, max(x0 + 1, x1))
    y0, y1 = max(0, y0), min(h, max(y0 + 1, y1))
    cropped = img.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _is_bag_likely(scores: Dict[str, float]) -> bool:
    sb = scores.get("包", 0.0)
    if sb < 0.11:
        return False
    others = max(
        scores.get("上衣", 0.0),
        scores.get("裤子", 0.0),
        scores.get("裙子", 0.0),
        scores.get("连衣裙", 0.0),
        scores.get("外套", 0.0),
        scores.get("鞋", 0.0),
    )
    return sb >= others - 0.02


def _dress_mode_from_scores(is_fullbody: bool, primary: str, scores: Dict[str, float]) -> bool:
    if not is_fullbody:
        return False
    s_dress = scores.get("连衣裙", 0.0) + 0.04 * scores.get("裙子", 0.0)
    s_split = max(scores.get("上衣", 0.0), scores.get("裤子", 0.0))
    if primary in ("上衣", "裤子") and s_split > s_dress + 0.06:
        return False
    if s_dress >= 0.14 and s_dress + 0.02 >= s_split:
        return True
    if primary in ("连衣裙", "裙子"):
        return True
    return False


def _append_side_bags(img: Image.Image, items: List[SplitPlanItem]) -> None:
    """左右窄条检测手持包/挎包。"""
    narrow = [
        (0.0, 0.12, 0.28, 0.78),
        (0.72, 0.12, 1.0, 0.78),
    ]
    for box in narrow:
        b = _crop_to_bytes(img, box)
        _, sc = _recognize_crop(b)
        if _is_bag_likely(sc):
            conf = min(0.88, float(sc.get("包", 0.55)))
            items.append(("包", box, conf))


def plan_outfit_split(img: Image.Image, image_bytes: bytes) -> List[SplitPlanItem]:
    """
    返回 [(品类, 归一化裁切框, 置信度), ...]，顺序即拆分列表下标。
    """
    w, h = img.size
    if w < 2 or h < 2:
        return []

    aspect = h / max(w, 1)
    is_fullbody = aspect > 1.08

    primary, scores = _recognize_full(image_bytes)
    logger.info(f"outfit_split: primary={primary} fullbody={is_fullbody}")

    items: List[SplitPlanItem] = []

    if _dress_mode_from_scores(is_fullbody, primary, scores):
        box_dress = (0.04, 0.06, 0.96, 0.79)
        box_shoe = (0.05, 0.72, 0.95, 0.995)
        b_d = _crop_to_bytes(img, box_dress)
        _, sc_d = _recognize_crop(b_d)
        if sc_d.get("裙子", 0) > sc_d.get("连衣裙", 0) + 0.06:
            final_d = "裙子"
        else:
            final_d = "连衣裙"
        final_d = _coerce_category(final_d, "连衣裙")
        conf_d = min(0.92, float(max(scores.get("连衣裙", 0), scores.get("裙子", 0), 0.72)))
        items.append((final_d, box_dress, conf_d))

        b_s = _crop_to_bytes(img, box_shoe)
        cat_s, sc_s = _recognize_crop(b_s)
        final_s = _coerce_category(cat_s, "鞋")
        if final_s == "包":
            final_s = "鞋"
        conf_s = min(0.88, float(max(sc_s.get(final_s, 0.55), 0.6)))
        items.append((final_s, box_shoe, conf_s))

        _append_side_bags(img, items)
    else:
        bands = [
            ((0.0, 0.0, 1.0, 0.44), "上衣"),
            ((0.0, 0.36, 1.0, 0.76), "裤子"),
            ((0.0, 0.66, 1.0, 1.0), "鞋"),
        ]
        for box, default in bands:
            b = _crop_to_bytes(img, box)
            cat, sc = _recognize_crop(b)
            raw = cat
            if default == "裤子":
                if sc.get("连衣裙", 0) > sc.get("裤子", 0) + 0.03:
                    raw = "连衣裙"
                elif sc.get("裙子", 0) > sc.get("裤子", 0) + 0.03:
                    raw = "裙子"
            final = _coerce_category(raw, default)
            if default == "裤子" and final == "上衣":
                final = "裤子"
            if default == "鞋" and final not in ("鞋", "包"):
                final = "鞋"
            conf = min(0.9, float(max(sc.get(final, 0.5), 0.55)))
            items.append((final, box, conf))

        _append_side_bags(img, items)

    return items


def plan_outfit_split_safe(img: Image.Image, image_bytes: bytes) -> List[SplitPlanItem]:
    fallback = [
        ("上衣", (0.0, 0.0, 1.0, 0.42), 0.5),
        ("裤子", (0.0, 0.38, 1.0, 0.74), 0.5),
        ("鞋", (0.0, 0.68, 1.0, 1.0), 0.5),
    ]
    try:
        p = plan_outfit_split(img, image_bytes)
        return p if p else fallback
    except Exception as e:
        logger.exception(f"plan_outfit_split failed, fallback: {e}")
        return fallback
