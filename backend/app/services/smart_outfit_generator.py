"""智能穿搭：天气 + 情绪 + 参考图 → 多套衣橱搭配（优先衣橱）。"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx

from app.core.config import settings
from app.core.logging import setup_logging
from app.ml.color_extractor import ColorExtractor
from app.models.garment import Garment
from app.observability.dependency_metrics import (
    classify_external_exception,
    record_dependency_outcome,
)
from app.schemas.garment import ColorSchema
from app.services.garment import get_garments_by_user
from app.services.outfit_recommender_3d import OutfitRecommender3D
from app.services.smart_outfit_rerank import rerank_outfit_cards
from app.services.storage import StorageService
from app.services.user_profile import get_profile_by_user_id

logger = setup_logging()


def _wardrobe_summary(wardrobe: List[Garment]) -> Dict[str, Any]:
    cats: Dict[str, int] = {}
    styles: Dict[str, int] = {}
    for g in wardrobe:
        c = (g.category or "").strip()
        if c:
            cats[c] = cats.get(c, 0) + 1
        for t in g.style_tags or []:
            tt = str(t).strip()
            if tt:
                styles[tt] = styles.get(tt, 0) + 1
    top_categories = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
    top_styles = sorted(styles.items(), key=lambda x: x[1], reverse=True)[:6]
    return {
        "total": len(wardrobe),
        "top_categories": [f"{k}({v})" for k, v in top_categories],
        "top_styles": [f"{k}({v})" for k, v in top_styles],
    }


def _fallback_ai_recommendation(
    *,
    outfit_name: str,
    outfit_style: str,
    score_hint: float,
    weather_note: str,
    mood: str,
    item_names: List[str],
) -> Dict[str, Any]:
    reasons = [
        f"优先使用你的衣橱单品：{('、'.join(item_names[:2]) if item_names else '当前搭配中的现有单品')}，减少重复购置。",
        f"风格聚焦在{outfit_style}，与本套单品标签一致，整体更统一。",
        weather_note or "已按当前天气条件做轻量适配。",
    ]
    if mood.strip():
        reasons[1] = f"结合你当前情绪“{mood[:18]}”微调为{outfit_style}方向，保持穿着舒适感。"
    return {
        "outfit": outfit_name,
        "style": outfit_style,
        "score": round(max(0.0, min(1.0, score_hint)) * 100, 1),
        "reasons": reasons[:3],
    }


def _extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    text = (raw_text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return None
    try:
        parsed = json.loads(text[s : e + 1])
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _extract_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: List[str] = []
        for part in content:
            if isinstance(part, str):
                chunks.append(part)
                continue
            if isinstance(part, dict):
                t = part.get("text")
                if isinstance(t, str) and t.strip():
                    chunks.append(t)
        return "\n".join(chunks)
    return ""


def _coerce_ai_recommendation(
    parsed: Optional[Dict[str, Any]],
    fallback: Dict[str, Any],
) -> Dict[str, Any]:
    if not parsed:
        return fallback
    outfit = str(parsed.get("outfit") or "").strip() or fallback["outfit"]
    style = str(parsed.get("style") or "").strip() or fallback["style"]
    score_raw = parsed.get("score")
    score_val: float
    try:
        score_val = float(score_raw)
    except Exception:
        score_val = float(fallback["score"])
    if score_val <= 1.0:
        score_val *= 100.0
    score_val = round(max(0.0, min(100.0, score_val)), 1)

    reasons_raw = parsed.get("reasons")
    reasons: List[str] = []
    if isinstance(reasons_raw, list):
        for r in reasons_raw:
            t = str(r).strip()
            if t:
                reasons.append(t)
    if not reasons:
        reasons = list(fallback["reasons"])
    while len(reasons) < 3:
        reasons.append(fallback["reasons"][len(reasons) % len(fallback["reasons"])])
    return {
        "outfit": outfit,
        "style": style,
        "score": score_val,
        "reasons": reasons[:3],
    }


async def _generate_ai_recommendation(
    *,
    card_dict: Dict[str, Any],
    weather_note: str,
    mood: str,
    wardrobe_info: Dict[str, Any],
) -> Dict[str, Any]:
    style_tags = card_dict.get("style_tags") or []
    style_name = "、".join([str(x) for x in style_tags[:2]]) or "简约"
    outfit_name = card_dict.get("description") or card_dict.get("scene") or "智能搭配"
    item_names = [
        str((it or {}).get("name") or "").strip() for it in (card_dict.get("items") or [])
    ]
    item_names = [x for x in item_names if x]
    fallback = _fallback_ai_recommendation(
        outfit_name=str(outfit_name),
        outfit_style=style_name,
        score_hint=float(card_dict.get("overall_score") or 0.65),
        weather_note=weather_note,
        mood=mood,
        item_names=item_names,
    )

    if not getattr(settings, "AI_RECOMMENDER_ENABLED", False):
        return fallback

    api_base = str(getattr(settings, "AI_RECOMMENDER_API_BASE_URL", "") or "").strip()
    api_key = str(getattr(settings, "AI_RECOMMENDER_API_KEY", "") or "").strip()
    model = str(getattr(settings, "AI_RECOMMENDER_MODEL", "gpt-4o-mini") or "gpt-4o-mini").strip()
    timeout_ms = int(getattr(settings, "AI_RECOMMENDER_TIMEOUT_MS", 8000) or 8000)
    strict_json = bool(getattr(settings, "AI_RECOMMENDER_STRICT_JSON", True))
    if not api_base or not api_key:
        return fallback

    system_prompt = (
        "你是服装搭配助手。必须只输出一个 JSON 对象，不要 markdown，不要解释。"
        "JSON 必须包含且只包含字段: outfit, style, score, reasons。"
        "其中 score 是 0-100 数值，reasons 是恰好 3 条中文字符串，且必须体现用户衣橱信息。"
    )
    user_payload = {
        "target_schema": {
            "outfit": "string",
            "style": "string",
            "score": "number(0-100)",
            "reasons": ["string", "string", "string"],
        },
        "input": {
            "scene": card_dict.get("scene"),
            "description": card_dict.get("description"),
            "overall_score": card_dict.get("overall_score"),
            "style_tags": style_tags,
            "items": [
                {
                    "name": (it or {}).get("name"),
                    "category": (it or {}).get("category"),
                    "style_tags": (it or {}).get("style_tags") or [],
                }
                for it in (card_dict.get("items") or [])
            ],
            "weather_note": weather_note,
            "mood": mood,
            "wardrobe_summary": wardrobe_info,
        },
    }

    url = f"{api_base.rstrip('/')}/chat/completions"
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
    if strict_json:
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=max(1.0, timeout_ms / 1000.0)) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 400 and strict_json:
                body.pop("response_format", None)
                resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}
            message = (
                ((data.get("choices") or [{}])[0].get("message") or {})
                if isinstance(data, dict)
                else {}
            )
            text = _extract_content_text(message.get("content"))
            parsed = _extract_json_object(text)
            out = _coerce_ai_recommendation(parsed, fallback)
            if parsed and str(parsed.get("outfit") or "").strip():
                record_dependency_outcome("ai", "success")
            else:
                record_dependency_outcome("ai", "degraded")
            return out
    except Exception as e:
        logger.warning("ai recommendation fallback due to error: %s", e)
        record_dependency_outcome("ai", classify_external_exception(e))
        return fallback


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


# Below this share: UI omits color label and shows a photo-first hint (see smart outfit screen).
LOW_MAIN_COLOR_CONFIDENCE = 0.35


def _card_to_response_dict(
    card: Any,
    weather_note: str,
    base_url: str,
) -> Dict[str, Any]:
    d = card.model_dump() if hasattr(card, "model_dump") else dict(card)
    items_out: List[Dict[str, Any]] = []
    for it in d.get("items") or []:
        mc = it.get("main_color") or {}
        cat = (it.get("category") or "单品") or "单品"
        mc_name = str(mc.get("name") or "").strip()
        conf = mc.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf_f = None
        if conf_f is not None and conf_f < LOW_MAIN_COLOR_CONFIDENCE:
            name = cat
            color_hint = "颜色以图片为准"
        else:
            name = f"{cat} · {mc_name}" if mc_name else cat
            color_hint = None
        items_out.append(
            {
                "name": name,
                "category": it.get("category"),
                "image_url": it.get("image_url"),
                "fit_note": it.get("role", ""),
                "style_tags": it.get("style_tags") or [],
                "main_color": mc,
                "color_hint": color_hint,
            }
        )
    preview = ""
    if items_out:
        # Prefer upper-body/major pieces for cover preview;
        # shoes/accessories often miss legacy image links.
        preferred = []
        fallback = []
        low_priority = {"鞋", "鞋子", "配饰", "包", "包包"}
        for it in items_out:
            url = str(it.get("image_url") or "").strip()
            if not url:
                continue
            fallback.append(url)
            cat = str(it.get("category") or "").strip()
            if cat not in low_priority:
                preferred.append(url)
        if preferred:
            preview = preferred[0]
        elif fallback:
            preview = fallback[0]
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
    from app.api.analysis import _coerce_str_list, _recognize_image_bytes_to_clip_dict

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
        raise ValueError("衣橱为空，请先添加衣物后再生成推荐")

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

    cards_dicts = [c.model_dump() for c in cards]
    cards_ranked = rerank_outfit_cards(
        cards_dicts,
        preferred_scene=preferred_scene,
        style_preferences=merged_styles,
        weather_note=weather_note,
        mood=mood,
        top_k=count,
    )

    base = f"http://127.0.0.1:{settings.PORT}"
    outfits_resp: List[Dict[str, Any]] = []
    wardrobe_info = _wardrobe_summary(wardrobe_ordered)
    for c in cards_ranked[:count]:
        card_dict = _card_to_response_dict(c, weather_note, base)
        card_dict["ai_recommendation"] = await _generate_ai_recommendation(
            card_dict=card_dict,
            weather_note=weather_note,
            mood=mood,
            wardrobe_info=wardrobe_info,
        )
        outfits_resp.append(card_dict)

    if not outfits_resp:
        logger.warning(
            "No outfit cards generated from wardrobe (uid=%s, target_category=%s, wardrobe=%s)",
            user_id,
            clip_result.get("category"),
            len(wardrobe_ordered),
        )
        outfits_resp = _fallback_virtual_outfits(
            clip_result=clip_result,
            weather_note=weather_note,
            count=count,
            seed=seed,
        )

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
