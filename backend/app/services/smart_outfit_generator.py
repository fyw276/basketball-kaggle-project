"""智能穿搭：天气 + 情绪 + 参考图 → 多套衣橱搭配（优先衣橱）。"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx

from app.api.analysis import _coerce_str_list, _recognize_image_bytes_to_clip_dict
from app.core.config import settings
from app.core.logging import setup_logging
from app.ml.color_extractor import ColorExtractor
from app.models.garment import Garment
from app.schemas.garment import ColorSchema
from app.services.garment import get_garments_by_user
from app.services.outfit_recommender_3d import OutfitRecommender3D
from app.services.storage import StorageService
from app.services.user_profile import get_profile_by_user_id

logger = setup_logging()


def normalize_mood_input(mood: Optional[str]) -> str:
    """
    规范化情绪文案：去控制字符与空字节、折叠空白、限制长度，避免 JSON/日志与下游异常。
    """
    if mood is None:
        return ""
    s = str(mood).replace("\x00", "")
    out: List[str] = []
    for ch in s:
        o = ord(ch)
        if o in (9, 10, 13):
            out.append(" ")
        elif o < 32:
            continue
        else:
            out.append(ch)
    s = "".join(out)
    s = " ".join(s.split())
    if len(s) > 500:
        s = s[:500]
    return s.strip()


def _scene_from_weather(weather_cn: str, temperature: float) -> str:
    """将天气映射到推荐引擎场景键。"""
    w = (weather_cn or "").strip()
    if "雨" in w or "雷" in w:
        return "通勤上班"
    if "雪" in w:
        return "商务正式"
    if temperature >= 28:
        return "度假旅行"
    if temperature <= 8:
        return "商务正式"
    if "晴" in w or "多云" in w:
        return "休闲日常"
    return "休闲日常"


def _rotate_scene(base_scene: str, regeneration_index: int) -> str:
    """重新生成时轮换场景，避免结果完全重复。"""
    from app.services.outfit_recommender_3d import SCENE_OUTFIT_TEMPLATES

    keys = list(SCENE_OUTFIT_TEMPLATES.keys())
    if base_scene in keys:
        i = keys.index(base_scene)
    else:
        i = 0
    return keys[(i + int(regeneration_index)) % len(keys)]


def _mood_extra_styles(mood: str) -> List[str]:
    """从自由文本情绪中提取风格偏好提示。"""
    m = (mood or "").strip()
    if not m:
        return []
    tags: List[str] = []
    pairs = [
        (("治愈", "温柔", "安静", "平静"), ["简约", "优雅"]),
        (("开心", "元气", "活力"), ["甜酷", "运动", "街头"]),
        (("酷", "冷淡", "冷"), ["街头", "朋克", "简约"]),
        (("正式", "通勤", "上班"), ["通勤", "正式"]),
        (("约会", "甜"), ["甜美", "优雅"]),
        (
            (
                "难受",
                "委屈",
                "低落",
                "丧",
                "烦",
                "累",
                "焦虑",
                "压力",
                "难过",
                "伤心",
                "郁闷",
                "被骂",
                "崩溃",
                "绝望",
                "孤独",
                "emo",
            ),
            ["简约", "温柔", "优雅", "舒适"],
        ),
        (("生气", "愤怒", "火大", "暴躁"), ["简约", "街头", "休闲"]),
    ]
    for keys, styles in pairs:
        if any(k in m for k in keys):
            tags.extend(styles)
    return list(dict.fromkeys(tags))[:8]


def _weather_advice(weather_cn: str, temperature: float, mood: str) -> str:
    parts = [f"当前约 {temperature:.0f}°C，{weather_cn}"]
    if "雨" in weather_cn or "雷" in weather_cn:
        parts.append("注意防雨防滑，鞋包宜选易打理材质。")
    elif "雪" in weather_cn:
        parts.append("注意保暖防滑。")
    elif temperature >= 28:
        parts.append("天气炎热，宜轻薄透气、浅色单品。")
    elif temperature <= 10:
        parts.append("气温较低，可叠穿外套并注意头部保暖。")
    if mood.strip():
        parts.append("已结合你描述的心情倾向微调风格。")
    return "；".join(parts)


def _is_safe_image_url_for_user(user_id: str, image_url: str) -> bool:
    uid = str(user_id)
    u = (image_url or "").strip().replace("\\", "/")
    if not u:
        return False
    if u.startswith("http://") or u.startswith("https://"):
        return f"/uploads/{uid}/" in u
    return uid in u and "/uploads/" in u


async def load_image_bytes(image_url: str) -> bytes:
    """
    加载参考图字节。若 image_url 为本服务上的 /uploads/ 绝对地址，**直接从磁盘读取**，
    避免 httpx 回环请求本机（与当前请求同进程时易 502/死锁）。
    """
    u = image_url.strip()
    if u.startswith("http://") or u.startswith("https://"):
        parsed = urlparse(u)
        path_part = (parsed.path or "").replace("\\", "/")
        low = path_part.lower()
        if "/uploads/" in low:
            idx = low.find("/uploads/")
            tail = path_part[idx + len("/uploads/") :].lstrip("/")
            if tail:
                full = Path(settings.UPLOAD_DIR) / tail
                if full.is_file():
                    return full.read_bytes()
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(u)
            r.raise_for_status()
            return r.content
    path = u.replace("\\", "/")
    if "/uploads/" in path.lower():
        idx = path.lower().find("/uploads/")
        tail = path[idx + len("/uploads/") :]
        full = Path(settings.UPLOAD_DIR) / tail
    else:
        full = Path(settings.UPLOAD_DIR) / path.lstrip("/")
    if not full.is_file():
        raise FileNotFoundError(f"image not found: {full}")
    return full.read_bytes()


def _shuffle_wardrobe(wardrobe: List[Garment], seed: int) -> List[Garment]:
    w = list(wardrobe)
    rng = random.Random(seed)
    rng.shuffle(w)
    return w


def _card_to_response_dict(
    card: Any,
    weather_note: str,
    base_url: str,
) -> Dict[str, Any]:
    d = card.model_dump()
    items_out: List[Dict[str, Any]] = []
    for it in d.get("items") or []:
        mc = it.get("main_color") or {}
        name = f"{it.get('category', '单品')} · {mc.get('name', '')}"
        items_out.append(
            {
                "name": name,
                "category": it.get("category"),
                "image_url": it.get("image_url"),
                "fit_note": it.get("role", ""),
                "style_tags": it.get("style_tags") or [],
            }
        )
    preview = ""
    if items_out:
        preview = items_out[0].get("image_url") or ""
    d["preview_image_url"] = preview
    d["effect_image_url"] = preview
    d["items"] = items_out
    d["style_tags"] = list(
        dict.fromkeys([t for it in items_out for t in (it.get("style_tags") or [])])
    )[:12]
    d["weather_fit_note"] = weather_note
    d["adapter_note"] = weather_note
    return d


def _fallback_virtual_outfits(
    clip_result: Dict[str, Any],
    weather_note: str,
    count: int,
    seed: int,
) -> List[Dict[str, Any]]:
    """衣橱为空时：基于参考图品类与风格生成文字型搭配方案。"""
    cat = clip_result.get("category", "上衣")
    styles = clip_result.get("style_tags") or ["休闲"]
    rng = random.Random(seed)
    variants = [
        f"以参考「{cat}」为主角，配简约下装与同色系鞋包，整体延续{styles[0]}风格。",
        f"在同色系基础上加入一件外套或配饰层次，突出{cat}的质感，适合当前天气出行。",
        f"尝试{styles[0] if styles else '休闲'}与中性色下装组合，鞋履选舒适款式以应对气温变化。",
    ]
    out: List[Dict[str, Any]] = []
    for i in range(count):
        desc = variants[(i + rng.randint(0, 99)) % len(variants)]
        out.append(
            {
                "outfit_id": f"virtual_{i}_{seed}",
                "scene": "休闲日常",
                "secondary_scenes": [],
                "description": desc,
                "reason": "衣橱暂无单品，以下为基于参考图的款式方向建议；可购入或添加类似单品后再生成完整搭配。",
                "scene_score": 0.5,
                "category_score": 0.4,
                "style_score": 0.5,
                "color_score": 0.5,
                "gender_compatibility": None,
                "overall_score": 0.45,
                "items": [],
                "preview_image_url": "",
                "effect_image_url": "",
                "style_tags": styles[:5],
                "weather_fit_note": weather_note,
                "adapter_note": weather_note,
            }
        )
    return out


async def generate_smart_outfits(
    *,
    db: Any,
    user_id: str,
    image_url: str,
    city: str,
    weather: str,
    temperature: float,
    mood: str,
    count: int,
    regeneration_index: int,
    gender_expression: Optional[float],
) -> Dict[str, Any]:
    """
    生成智能穿搭结果字典：outfits, city, weather, temperature, mood, weather_fallback 等。
    """
    mood = normalize_mood_input(mood)

    if not _is_safe_image_url_for_user(user_id, image_url):
        raise ValueError("无效的图片地址，请使用本账号上传的参考图")

    image_bytes = await load_image_bytes(image_url)
    clip_result = _recognize_image_bytes_to_clip_dict(image_bytes)

    user_profile = get_profile_by_user_id(db, UUID(str(user_id)))
    user_style_prefs = _coerce_str_list(user_profile.style_preference if user_profile else [])
    user_body_type = user_profile.body_type if user_profile else None
    avoid_body_parts = _coerce_str_list(user_profile.avoid_body_parts if user_profile else [])
    user_gender = getattr(user_profile, "gender", None) if user_profile else None
    profile_ge = getattr(user_profile, "gender_expression", None) if user_profile else None
    explore_cross = getattr(user_profile, "explore_cross_gender", False) if user_profile else False

    mood_styles = _mood_extra_styles(mood)
    merged_styles = list(dict.fromkeys(user_style_prefs + mood_styles))[:20]

    base_scene = _scene_from_weather(weather, float(temperature))
    preferred_scene = _rotate_scene(base_scene, regeneration_index)
    weather_note = _weather_advice(weather, float(temperature), mood)

    wardrobe = get_garments_by_user(db, UUID(str(user_id)), limit=500)
    seed = hash(image_url) % (2**31) + int(regeneration_index) * 1009
    wardrobe_ordered = _shuffle_wardrobe(wardrobe, seed)

    color_extractor = ColorExtractor(n_colors=3)
    colors = color_extractor.extract_colors(image_bytes)
    main_color = (
        colors[0]
        if colors
        else ColorSchema(name="灰", rgb=(128, 128, 128), hsv=(0.0, 0.0, 50.0), hex_code="#808080")
    )
    secondary_colors = colors[1:] if len(colors) > 1 else []

    clip_features = clip_result["feature_vector"]
    fdim = len(clip_features)
    if fdim == 768:
        feature_vector = clip_features + [0.0] * 512
    elif fdim == 512:
        feature_vector = clip_features + [0.0] * 768
    else:
        feature_vector = clip_features[:1280] + [0.0] * max(0, 1280 - len(clip_features))

    target = Garment(
        garment_id=uuid4(),
        user_id=UUID(str(user_id)),
        category=clip_result["category"],
        main_color=main_color.model_dump(),
        secondary_colors=[c.model_dump() for c in secondary_colors],
        style_tags=clip_result["style_tags"],
        fit_type=clip_result.get("fit_type"),
        image_path="",
        image_url=image_url,
        feature_vector=feature_vector,
    )

    is_female = user_gender == "女"
    if gender_expression is not None:
        final_ge = gender_expression if is_female else None
    else:
        final_ge = profile_ge if is_female else None

    recommender = OutfitRecommender3D()
    if not wardrobe_ordered:
        virtual = _fallback_virtual_outfits(clip_result, weather_note, count, seed)
        return {
            "outfits": virtual,
            "city": city,
            "weather": weather,
            "temperature": temperature,
            "mood": mood,
            "weather_fallback": False,
            "message": "衣橱为空，已返回款式方向建议",
        }

    cards = recommender.recommend_outfits(
        target_garment=target,
        wardrobe=wardrobe_ordered,
        num_outfits=count,
        user_style_preferences=merged_styles,
        user_body_type=user_body_type,
        avoid_body_parts=avoid_body_parts,
        preferred_scene=preferred_scene,
        user_gender=user_gender,
        user_gender_expression=final_ge,
        explore_cross_gender=explore_cross,
    )

    base = f"http://127.0.0.1:{settings.PORT}"
    outfits_resp: List[Dict[str, Any]] = []
    for c in cards[:count]:
        outfits_resp.append(_card_to_response_dict(c, weather_note, base))

    return {
        "outfits": outfits_resp,
        "city": city,
        "weather": weather,
        "temperature": temperature,
        "mood": mood,
        "weather_fallback": False,
        "message": "ok",
    }


async def upload_reference_image(
    user_id: str,
    image_bytes: bytes,
    original_name: str,
) -> str:
    """保存参考图并返回可访问的 image_url（相对 /uploads）。"""
    storage = StorageService()
    _, url = storage.save_image_bytes(image_bytes, str(user_id), original_name=original_name)
    return url
