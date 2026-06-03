"""
3D Outfit Recommendation Engine — 场景-品类-风格 三维匹配 + 无性别推荐系统（修正版）

修正规则：
- 女性用户（gender == "女"）：全量召回（男装+女装+中性）
  - 应用 gender_compatibility 评分：1 - |gender_expression - neutral_score|
- 男性用户（gender == "男"）：默认仅召回 gender_label in [male, neutral]
  - explore_cross_gender=True 时：小比例混入 neutral_score>0.7 的女款
  - 不应用 gender_compatibility，简化公式：final_score = w1*scene + w2*category + w3*style + w4*color

This module provides gender-inclusive outfit recommendations:
1. Scene dimension (场景匹配) — 套装整体适合哪些场合
2. Category dimension (品类完整) — 上下装完整搭配，上下文协调
3. Style dimension (风格一致) — 所有单品风格统一，无突兀感
4. Gender dimension (女性专用) — 仅女性用户应用 gender_compatibility 评分
"""

from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import setup_logging
from app.models.garment import Garment
from app.schemas.garment import ColorSchema
from app.services.garment_taxonomy import (
    CATEGORY_BAG,
    CATEGORY_PANTS,
    CATEGORY_SHOES,
    CATEGORY_SKIRT,
    CATEGORY_TOP,
    normalize_category,
    validate_outfit_slots,
)
from app.services.outfit_rules import CategoryRules, ColorRules, StyleRules

if TYPE_CHECKING:
    from app.services.feedback_prefs import FeedbackRerankContext

logger = setup_logging()


def _public_image_url_for_garment(g: Garment) -> str:
    """
    Prefer persisted image_url; if missing, derive /uploads/... URL from image_path.
    (Older rows may have empty image_url.)
    """
    uid = str(getattr(g, "user_id", "") or "")
    u = (getattr(g, "image_url", None) or "").strip()
    u_norm = u.replace("\\", "/") if u else ""
    u_low = u_norm.lower()
    if u_norm:
        # Canonicalize any persisted path/URL that points under uploads.
        idx_u = u_low.find("/uploads/")
        if idx_u >= 0:
            tail_u = u_norm[idx_u + len("/uploads/") :].lstrip("/")
            if tail_u:
                return f"/uploads/{tail_u}"
        if u_low.startswith("uploads/"):
            return f"/{u_norm.lstrip('/')}"
        # Non-upload absolute URLs may become stale after migration; try image_path fallback below.
        if u_low.startswith("http://") or u_low.startswith("https://"):
            pass
        else:
            return u_norm
    p = (getattr(g, "image_path", None) or "").strip()
    if not p:
        return u_norm if u_norm else ""
    p_norm = p.replace("\\", "/")
    low = p_norm.lower()
    idx = low.find("/uploads/")
    if idx >= 0:
        tail = p_norm[idx + len("/uploads/") :]
        return f"/uploads/{tail}"
    if low.startswith("uploads/"):
        return f"/{p_norm.lstrip('/')}"
    name = Path(p_norm).name
    if uid and name:
        return f"/uploads/{uid}/{name}"
    return u_norm if u_norm else ""


# ──────────────────────────────────────────────────────────────────────────────
# Scene Templates (基于 Polyvore + 社区痛点分析)
# ──────────────────────────────────────────────────────────────────────────────
# Complete outfit templates by scene and season
SCENE_OUTFIT_TEMPLATES: Dict[str, List[Dict]] = {
    "通勤上班": [
        {"categories": ["上衣", "裤子"], "weight": 0.4},
        {"categories": ["上衣", "裤子", "外套"], "weight": 0.3},
        {"categories": ["上衣", "裙子", "外套"], "weight": 0.2},
        {"categories": ["上衣", "裙子"], "weight": 0.1},
    ],
    "商务正式": [
        {"categories": ["上衣", "裤子", "外套"], "weight": 0.5},
        {"categories": ["上衣", "裙子", "外套"], "weight": 0.3},
        {"categories": ["上衣", "裤子"], "weight": 0.2},
    ],
    "约会": [
        {"categories": ["上衣", "裙子"], "weight": 0.35},
        {"categories": ["上衣", "裤子"], "weight": 0.30},
        {"categories": ["上衣", "裤子", "外套"], "weight": 0.20},
        {"categories": ["上衣", "裙子", "外套"], "weight": 0.15},
    ],
    "休闲日常": [
        {"categories": ["上衣", "裤子"], "weight": 0.40},
        {"categories": ["上衣", "裙子"], "weight": 0.25},
        {"categories": ["上衣", "裤子", "鞋"], "weight": 0.25},
        {"categories": ["上衣", "裙子", "鞋"], "weight": 0.10},
    ],
    "校园": [
        {"categories": ["上衣", "裤子"], "weight": 0.40},
        {"categories": ["上衣", "裙子"], "weight": 0.25},
        {"categories": ["上衣", "裤子", "外套"], "weight": 0.20},
        {"categories": ["上衣", "裙子", "外套"], "weight": 0.15},
    ],
    "运动健身": [
        {"categories": ["上衣", "裤子"], "weight": 0.6},
        {"categories": ["上衣"], "weight": 0.4},
    ],
    "度假旅行": [
        {"categories": ["上衣", "裙子"], "weight": 0.35},
        {"categories": ["上衣", "裤子"], "weight": 0.30},
        {"categories": ["上衣", "裙子", "外套"], "weight": 0.20},
        {"categories": ["上衣", "裤子", "外套"], "weight": 0.15},
    ],
    "聚会": [
        {"categories": ["上衣", "裤子"], "weight": 0.30},
        {"categories": ["上衣", "裙子"], "weight": 0.35},
        {"categories": ["上衣", "裤子", "外套"], "weight": 0.20},
        {"categories": ["上衣", "裙子", "外套"], "weight": 0.15},
    ],
    "街头潮流": [
        {"categories": ["上衣", "裤子"], "weight": 0.45},
        {"categories": ["上衣", "裤子", "外套"], "weight": 0.35},
        {"categories": ["上衣", "裙子"], "weight": 0.20},
    ],
    "正式宴会": [
        {"categories": ["上衣", "裤子", "外套"], "weight": 0.40},
        {"categories": ["上衣", "裙子", "外套"], "weight": 0.40},
        {"categories": ["上衣", "裤子"], "weight": 0.20},
    ],
}


def normalize_category_for_outfit_templates(raw: Optional[str]) -> str:
    return normalize_category(raw, default=CATEGORY_TOP)


def _normalize_garment_category_in_place(garment: Garment) -> None:
    raw = (getattr(garment, "category", "") or "").strip()
    normalized = normalize_category(raw, default=CATEGORY_TOP)
    if normalized == raw:
        return
    garment.category = normalized
    tags = getattr(garment, "style_tags", None) or []
    if not isinstance(tags, list):
        tags = []
    if raw and raw not in tags:
        garment.style_tags = [raw] + list(tags)


BODY_TYPE_IDEAL_FITS: Dict[str, List[str]] = {
    "偏瘦": ["宽松", "oversized", "标准"],
    "倒三角": ["宽松", "oversized"],
    "梨形": ["宽松", "oversized", "标准"],
    "矩形": ["修身", "标准", "宽松"],
    "沙漏": ["修身", "标准"],
    "微胖": ["宽松", "oversized", "标准"],
}

BODY_TYPE_CATEGORY_SCORES: Dict[str, Dict[str, float]] = {
    "梨形": {"上衣": 0.8, "外套": 0.9, "裤子": 0.5, "裙子": 0.7},
    "倒三角": {"上衣": 0.6, "外套": 0.6, "裤子": 0.9, "裙子": 0.8},
    "偏瘦": {"上衣": 0.8, "外套": 0.9, "裤子": 0.7, "裙子": 0.8},
    "微胖": {"上衣": 0.6, "外套": 0.8, "裤子": 0.6, "裙子": 0.7},
    "矩形": {"上衣": 0.8, "外套": 0.7, "裤子": 0.8, "裙子": 0.8},
    "沙漏": {"上衣": 0.9, "外套": 0.7, "裤子": 0.8, "裙子": 0.9},
}


# ──────────────────────────────────────────────────────────────────────────────
# 无性别推荐系统常量（修正版）
# ──────────────────────────────────────────────────────────────────────────────

# 男性用户跨性别探索配置
CROSS_GENDER_CONFIG = {
    # 当 explore_cross_gender=True 时，允许混入的女款比例
    "max_female_ratio": 0.15,  # 最多 15% 的女款
    # 仅混入高中性化的女款
    "min_neutral_score": 0.7,  # neutral_score >= 0.7 才混入
}


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ──────────────────────────────────────────────────────────────────────────────


class OutfitItem(BaseModel):
    """Single item in an outfit recommendation."""

    garment_id: UUID
    category: str
    main_color: ColorSchema
    style_tags: List[str]
    image_url: str
    role: str  # target / top / bottom / outer / shoes / bag


class OutfitCard(BaseModel):
    """Complete outfit recommendation card with 3D scores + gender-inclusive scoring."""

    outfit_id: str
    scene: str = Field(..., description="Primary occasion for this outfit")
    secondary_scenes: List[str] = Field(
        default_factory=list, description="Other suitable occasions"
    )
    items: List[OutfitItem]
    description: str = Field(..., description="Natural language outfit summary")
    reason: str = Field(
        default="",
        description="Chinese recommendation reason (body/scene/style analysis)",
    )
    # 3D scores
    scene_score: float = Field(..., ge=0, le=1, description="Scene compatibility")
    category_score: float = Field(..., ge=0, le=1, description="Category completeness")
    style_score: float = Field(..., ge=0, le=1, description="Style consistency across all items")
    color_score: float = Field(..., ge=0, le=1, description="Color harmony across all items")
    # 无性别推荐系统新增评分（仅对女性生效）
    gender_compatibility: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Gender expression compatibility (仅对女性生效, None=男性用户不使用)",
    )
    overall_score: float = Field(..., ge=0, le=1, description="Weighted overall score")
    # Weight configuration for scoring
    dimension_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "scene": 0.28,
            "category": 0.22,
            "style": 0.22,
            "color": 0.18,
            "gender": 0.10,
        },
        description="Weights for each dimension",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "outfit_id": "outfit_1",
                "scene": "通勤上班",
                "secondary_scenes": ["商务正式", "正式宴会"],
                "items": [],
                "description": "简约通勤穿搭，深灰上衣 + 黑色裤子 + 深灰外套，干练利落",
                "reason": "深色系单品视觉显瘦，适合需要遮盖臀部的身形；简约干练风格完美契合通勤场景；色彩高度统一，商务感强",
                "scene_score": 0.92,
                "category_score": 1.0,
                "style_score": 0.88,
                "color_score": 0.90,
                "gender_compatibility": 0.85,
                "overall_score": 0.90,
            }
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3D Outfit Recommender
# ──────────────────────────────────────────────────────────────────────────────


class OutfitRecommender3D:
    """
    3D Outfit Recommendation Engine — 场景-品类-风格 三维匹配

    Pipeline:
    1. Scene dimension: 从用户画像推断主场景，匹配场景模板
    2. Category dimension: 根据模板生成品类组合，确保套装完整
    3. Style dimension: CLIP-powered 风格一致性打分
    4. Color dimension: 整体色彩和谐打分

    Advantage over previous OutfitRecommender:
    - Scene-aware: 不只是"上下搭配"，而是"适合某场景的完整套装"
    - Full outfits: 考虑外套、鞋、包，而非仅上下装
    - Better scoring: 四维分别打分，解释性更强
    """

    def __init__(
        self,
        color_rules: ColorRules = None,
        style_rules: StyleRules = None,
        category_rules: CategoryRules = None,
    ):
        self.color_rules = color_rules or ColorRules()
        self.style_rules = style_rules or StyleRules()
        self.category_rules = category_rules or CategoryRules()

        # Scene-to-style mapping (which styles fit each scene)
        self.scene_styles = self._build_scene_style_map()
        logger.info("OutfitRecommender3D initialized")

    def _build_scene_style_map(self) -> Dict[str, List[str]]:
        """Build a scene → dominant styles mapping."""
        SCENE_STYLE_MAP = {
            "通勤上班": ["通勤", "简约", "学院", "正式", "优雅"],
            "商务正式": ["正式", "通勤", "优雅"],
            "约会": ["甜美", "甜酷", "优雅", "复古", "简约"],
            "休闲日常": ["休闲", "简约", "街头", "运动"],
            "校园": ["学院", "简约", "休闲"],
            "运动健身": ["运动"],
            "度假旅行": ["度假", "民族", "甜美", "休闲"],
            "聚会": ["甜酷", "甜美", "优雅", "复古", "街头", "朋克"],
            "街头潮流": ["街头", "朋克", "复古"],
            "正式宴会": ["正式", "优雅"],
        }
        return SCENE_STYLE_MAP

    def _derive_user_scenes(self, style_preferences: List[str]) -> Tuple[str, List[str]]:
        """
        Derive user's primary and secondary scenes from style preferences.
        Returns (primary_scene, [secondary_scenes]).
        """
        scene_scores: Dict[str, int] = {}
        for style in style_preferences:
            for scene, scene_style_list in self.scene_styles.items():
                if style in scene_style_list:
                    # Prefer more specific scenes over broad umbrella scenes.
                    # For example, "运动" should map to "运动健身" instead of
                    # defaulting to a generic "休闲日常" tie.
                    specificity_weight = 1.0 / max(len(scene_style_list), 1)
                    scene_scores[scene] = scene_scores.get(scene, 0.0) + specificity_weight

        if not scene_scores:
            return "休闲日常", []

        sorted_scenes = sorted(scene_scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_scenes[0][0]
        secondary = [s for s, _ in sorted_scenes[1:4]]
        return primary, secondary

    # ─── Main recommendation API ──────────────────────────────────────────────

    def recommend_outfits(
        self,
        target_garment: Garment,
        wardrobe: List[Garment],
        num_outfits: int = 3,
        user_style_preferences: Optional[List[str]] = None,
        user_body_type: Optional[str] = None,
        avoid_body_parts: Optional[List[str]] = None,
        preferred_scene: Optional[str] = None,
        # 无性别推荐系统参数（修正版）
        user_gender: Optional[str] = None,  # "男" / "女" / None
        user_gender_expression: Optional[float] = None,  # 仅对女性生效
        explore_cross_gender: bool = False,  # 仅对男性生效
        feedback_rerank: Optional["FeedbackRerankContext"] = None,
        fixed_reference_category: Optional[str] = None,
    ) -> List[OutfitCard]:
        """
        Generate outfit recommendations for a target garment (体型+场景感知 + 无性别推荐)

        无性别推荐系统（修正版）：
        - 女性用户（gender == "女"）：全量召回，应用 gender_compatibility 评分
        - 男性用户（gender == "男"）：默认仅召回 [male, neutral]，不应用 gender_compatibility
        - 男性用户（explore_cross_gender=True）：小比例混入 neutral_score>0.7 的女款

        排序公式：
        - 女性：final_score = w1*scene + w2*category + w3*style + w4*color + w5*(1-|gender_expression-neutral_score|)  # noqa: E501
        - 男性：final_score = w1*scene + w2*category + w3*style + w4*color
        """
        logger.info(
            f"Generating {num_outfits} outfits for {target_garment.category} "
            f"(gender={user_gender}, gender_expression={user_gender_expression}, "
            f"explore_cross_gender={explore_cross_gender})"
        )

        if not wardrobe:
            return []

        _normalize_garment_category_in_place(target_garment)
        for garment in wardrobe:
            _normalize_garment_category_in_place(garment)

        raw_target_cat = (getattr(target_garment, "category", None) or "").strip()
        slot_cat = normalize_category_for_outfit_templates(target_garment.category)
        if slot_cat != raw_target_cat:
            logger.info(
                "Normalized target category for outfit templates: %r -> %r",
                raw_target_cat,
                slot_cat,
            )
            target_garment.category = slot_cat
            tags = getattr(target_garment, "style_tags", None) or []
            if not isinstance(tags, list):
                tags = []
            if raw_target_cat and raw_target_cat not in tags:
                target_garment.style_tags = [raw_target_cat] + list(tags)
        fixed_slot_cat = normalize_category_for_outfit_templates(
            fixed_reference_category or target_garment.category
        )

        # Step 0: 无性别推荐系统 - 性别区分召回（修正版）
        filtered_wardrobe = self._filter_by_gender(
            wardrobe,
            user_gender=user_gender,
            explore_cross_gender=explore_cross_gender,
        )
        logger.info(
            f"After gender filtering: {len(filtered_wardrobe)}/{len(wardrobe)} garments remain"
        )

        # Step 1: 体型感知过滤
        if user_body_type or avoid_body_parts:
            filtered_wardrobe = self._filter_by_body_type(
                filtered_wardrobe, user_body_type, avoid_body_parts
            )
            logger.info(f"After body-type filtering: {len(filtered_wardrobe)} garments remain")

        # Step 2: Group wardrobe by category
        wardrobe_by_cat = self._group_by_category(filtered_wardrobe)

        # Step 3: Derive user's primary scene from style preferences
        raw_tags = getattr(target_garment, "style_tags", None) or []
        if not isinstance(raw_tags, list):
            raw_tags = []
        style_prefs = user_style_preferences or raw_tags
        if not isinstance(style_prefs, list):
            style_prefs = []
        if preferred_scene:
            primary_scene = preferred_scene
            secondary_scenes = []
            logger.info(f"Using user-specified scene: {primary_scene}")
        else:
            primary_scene, secondary_scenes = self._derive_user_scenes(style_prefs)
            logger.info(f"Derived scene: {primary_scene}, Secondary: {secondary_scenes}")

        # Step 4: Get outfit templates for primary scene
        templates = SCENE_OUTFIT_TEMPLATES.get(primary_scene, SCENE_OUTFIT_TEMPLATES["休闲日常"])

        # Step 5: Generate outfit candidates for each template
        all_candidates: List[Tuple[List[Garment], Dict]] = []
        for template in templates:
            cats = template["categories"]
            weight = template["weight"]

            if not self._template_can_anchor_reference(cats, fixed_slot_cat):
                continue
            if self._template_conflicts_with_fixed_reference(cats, fixed_slot_cat):
                continue

            combos = self._generate_for_template(
                target_garment,
                cats,
                wardrobe_by_cat,
                user_body_type=user_body_type,
                avoid_body_parts=avoid_body_parts,
            )
            for combo in combos:
                all_candidates.append(
                    (
                        combo,
                        {
                            "scene": primary_scene,
                            "template_weight": weight,
                        },
                    )
                )

        # Step 6: Score all candidates across 4-5 dimensions
        # - 女性：5维 (scene/category/style/color/gender_compatibility)
        # - 男性：4维 (scene/category/style/color)
        is_female = user_gender == "女"
        scored: List[Tuple[List[Garment], Dict, OutfitCard]] = []
        for combo, meta in all_candidates:
            card = self._score_outfit_3d(
                combo,
                primary_scene,
                secondary_scenes,
                user_body_type=user_body_type,
                avoid_body_parts=avoid_body_parts,
                # 无性别推荐系统（修正版）
                user_gender_expression=user_gender_expression if is_female else None,
            )
            scored.append((combo, meta, card))

        if feedback_rerank is not None:
            from app.services.feedback_prefs import FeedbackRerankContext

            if not isinstance(feedback_rerank, FeedbackRerankContext):
                raise TypeError("feedback_rerank must be FeedbackRerankContext")
            scored = self._apply_feedback_rerank(scored, feedback_rerank)

        # Step 7: Sort by adjusted score
        scored.sort(
            key=lambda x: (
                x[2].overall_score * (0.7 + 0.3 * x[1]["template_weight"]),
                x[2].scene_score,
            ),
            reverse=True,
        )

        # Step 8: Build final outfit cards
        outfit_cards = []
        for idx, (combo, meta, card) in enumerate(scored[:num_outfits]):
            card.outfit_id = f"outfit_{idx + 1}"
            outfit_cards.append(card)

        logger.info(
            f"Generated {len(outfit_cards)} outfit recommendations "
            f"(gender={user_gender}, female_compatible={is_female})"
        )
        return outfit_cards

    def _apply_feedback_rerank(
        self,
        scored: List[Tuple[List[Garment], Dict, OutfitCard]],
        ctx: "FeedbackRerankContext",
    ) -> List[Tuple[List[Garment], Dict, OutfitCard]]:
        """根据历史点赞/采纳单品与风格，微调 overall_score 后重排。"""
        if not ctx.liked_garment_ids and not ctx.style_tag_boost:
            return scored
        out: List[Tuple[List[Garment], Dict, OutfitCard]] = []
        for combo, meta, card in scored:
            delta = self._feedback_boost_for_combo(combo, ctx)
            new_card = card.model_copy(
                update={"overall_score": min(1.0, card.overall_score + delta)}
            )
            out.append((combo, meta, new_card))
        return out

    @staticmethod
    def _feedback_boost_for_combo(
        combo: List[Garment],
        ctx: "FeedbackRerankContext",
    ) -> float:
        boost = 0.0
        for g in combo:
            if str(g.garment_id) in ctx.liked_garment_ids:
                boost += 0.015
            for t in g.style_tags or []:
                boost += ctx.style_tag_boost.get(str(t), 0.0)
        return min(0.08, boost)

    def _filter_by_gender(
        self,
        wardrobe: List[Garment],
        user_gender: Optional[str],
        explore_cross_gender: bool = False,
    ) -> List[Garment]:
        """
        无性别推荐系统 - 性别区分召回（修正版）

        规则：
        - 女性用户（gender == "女"）：全量召回（男装+女装+中性）
        - 男性用户（gender == "男"）：默认仅召回 [male, neutral]
        - 男性用户（explore_cross_gender=True）：小比例混入 neutral_score>0.7 的女款
        """
        if user_gender is None:
            # 未设置性别，全量召回
            return wardrobe

        if user_gender == "女":
            # 女性用户：全量召回
            return wardrobe

        if user_gender == "男":
            # 男性用户：仅召回 [male, neutral]
            if not explore_cross_gender:
                return [
                    g for g in wardrobe if self._get_garment_gender_label(g) in ["male", "neutral"]
                ]

            # explore_cross_gender=True：小比例混入高中性化的女款
            male_neutral_items = [
                g for g in wardrobe if self._get_garment_gender_label(g) in ["male", "neutral"]
            ]
            female_items = [
                g
                for g in wardrobe
                if self._get_garment_gender_label(g) == "female"
                and getattr(g, "neutral_score", 0) >= CROSS_GENDER_CONFIG["min_neutral_score"]
            ]

            # 计算可混入的女款数量
            max_female_count = int(
                len(male_neutral_items)
                * CROSS_GENDER_CONFIG["max_female_ratio"]
                / (1 - CROSS_GENDER_CONFIG["max_female_ratio"])
            )
            female_items_to_include = female_items[:max_female_count]

            logger.info(
                f"Cross-gender exploration: including {len(female_items_to_include)} "
                f"female items (neutral_score >= {CROSS_GENDER_CONFIG['min_neutral_score']})"
            )
            return male_neutral_items + female_items_to_include

        # 其他性别：全量召回
        return wardrobe

    def _get_garment_gender_label(self, garment: Garment) -> str:
        """获取服装的性别标签"""
        return getattr(garment, "gender_label", "neutral")

    def _filter_by_body_type(
        self,
        wardrobe: List[Garment],
        body_type: Optional[str],
        avoid_parts: Optional[List[str]],
    ) -> List[Garment]:
        """
        体型感知过滤：排除版型/品类不适合的服装

        Rules:
        - 偏瘦：过滤掉紧身款（强化瘦弱感）
        - 微胖：过滤掉修身/紧身（强化肉感）
        - 梨形：下身降低权重（宽松更佳）
        - 避免部位：对应品类降低权重
        """
        if not body_type and not avoid_parts:
            return wardrobe

        ideal_fits = BODY_TYPE_IDEAL_FITS.get(body_type, [])
        ideal_set = set(ideal_fits)
        bad_fits = {"修身"} - ideal_set

        filtered = []
        for g in wardrobe:
            # Skip if garment has a bad fit type for this body
            if g.fit_type in bad_fits:
                logger.debug(f"Filter out {g.garment_id} (fit={g.fit_type}, body={body_type})")
                continue
            filtered.append(g)

        return filtered

    # ─── Template-based generation ─────────────────────────────────────────────

    def _generate_for_template(
        self,
        target: Garment,
        categories: List[str],
        wardrobe_by_cat: Dict[str, List[Garment]],
        user_body_type: Optional[str] = None,
        avoid_body_parts: Optional[List[str]] = None,
    ) -> List[List[Garment]]:
        """Generate outfit combinations for a given category template."""
        combinations = []
        remaining_cats = [c for c in categories if c != target.category]

        if not remaining_cats:
            return [[target]]

        # Simple combination: pick best-matching item from each required category
        for cat in remaining_cats:
            cat_garments = wardrobe_by_cat.get(cat, [])
            if not cat_garments:
                continue

            # Score each garment for compatibility with target
            scored = []
            tt = getattr(target, "style_tags", None) or []
            tm = getattr(target, "main_color", None) or {}
            if not isinstance(tt, list):
                tt = []
            for g in cat_garments:
                gt = getattr(g, "style_tags", None) or []
                if not isinstance(gt, list):
                    gt = []
                gm = getattr(g, "main_color", None) or {}
                style_score = self.style_rules.calculate_style_consistency(tt, gt)
                color_score, _ = self.color_rules.calculate_color_harmony(
                    (
                        ColorSchema(**tm)
                        if isinstance(tm, dict)
                        else ColorSchema(
                            name="灰", rgb=(128, 128, 128), hsv=(0.0, 0.0, 50.0), hex_code="#808080"
                        )
                    ),
                    (
                        ColorSchema(**gm)
                        if isinstance(gm, dict)
                        else ColorSchema(
                            name="灰", rgb=(128, 128, 128), hsv=(0.0, 0.0, 50.0), hex_code="#808080"
                        )
                    ),
                )
                combo_score = style_score * 0.5 + color_score * 0.5
                scored.append((combo_score, g))

            # Sort by score, take top N
            scored.sort(key=lambda x: x[0], reverse=True)
            top_items = [g for _, g in scored[:5]]  # Top 5 candidates per category

            # Generate combinations
            if not combinations:
                combinations = [[target, item] for item in top_items]
            else:
                new_combos = []
                for combo in combinations:
                    for item in top_items:
                        if item not in combo:
                            new_combos.append(combo + [item])
                combinations = new_combos

        # Limit combinations to avoid explosion
        if len(combinations) > 30:
            # Sort by internal score and take top 30
            def combo_score(combo):
                total = 0.0
                for i in range(len(combo) - 1):
                    for j in range(i + 1, len(combo)):
                        ti = getattr(combo[i], "style_tags", None) or []
                        tj = getattr(combo[j], "style_tags", None) or []
                        if not isinstance(ti, list):
                            ti = []
                        if not isinstance(tj, list):
                            tj = []
                        style = self.style_rules.calculate_style_consistency(ti, tj)
                        mi = getattr(combo[i], "main_color", None) or {}
                        mj = getattr(combo[j], "main_color", None) or {}
                        default_c = {
                            "name": "灰",
                            "rgb": (128, 128, 128),
                            "hsv": (0.0, 0.0, 50.0),
                            "hex_code": "#808080",
                        }
                        color, _ = self.color_rules.calculate_color_harmony(
                            ColorSchema(**mi) if isinstance(mi, dict) else ColorSchema(**default_c),
                            ColorSchema(**mj) if isinstance(mj, dict) else ColorSchema(**default_c),
                        )
                        total += style + color
                return total / ((len(combo) * (len(combo) - 1)) / 2) if len(combo) > 1 else 0.5

            combinations.sort(key=combo_score, reverse=True)
            combinations = combinations[:30]

        # Always include target
        return [
            combo
            for combo in combinations
            if target in combo and not self._has_conflicting_bottoms(combo)
        ]

    @staticmethod
    def _template_can_anchor_reference(
        categories: List[str],
        fixed_reference_category: str,
    ) -> bool:
        cats = {normalize_category(c, default="") for c in categories}
        fixed = normalize_category(fixed_reference_category, default="")
        has_body = CATEGORY_TOP in cats and bool(cats & {CATEGORY_PANTS, CATEGORY_SKIRT})
        if fixed in {CATEGORY_SHOES, CATEGORY_BAG}:
            return has_body
        return fixed in cats

    @staticmethod
    def _template_conflicts_with_fixed_reference(
        categories: List[str],
        fixed_reference_category: str,
    ) -> bool:
        cats = {normalize_category(c, default="") for c in categories}
        fixed = normalize_category(fixed_reference_category, default="")
        if not validate_outfit_slots(cats):
            return True
        if fixed == CATEGORY_PANTS and CATEGORY_SKIRT in cats:
            return True
        if fixed == CATEGORY_SKIRT and CATEGORY_PANTS in cats:
            return True
        return False

    @staticmethod
    def _has_conflicting_bottoms(garments: List[Garment]) -> bool:
        return not validate_outfit_slots(getattr(g, "category", None) for g in garments)

    def _score_outfit_3d(
        self,
        garments: List[Garment],
        primary_scene: str,
        secondary_scenes: List[str],
        user_body_type: Optional[str] = None,
        avoid_body_parts: Optional[List[str]] = None,
        # 无性别推荐系统参数（修正版）
        # 仅对女性生效，None = 男性用户，不应用此评分
        user_gender_expression: Optional[float] = None,
    ) -> OutfitCard:
        """
        Score an outfit across 4-5 dimensions（修正版）

        - 女性用户（user_gender_expression != None）：5维评分（含 gender_compatibility）
        - 男性用户（user_gender_expression == None）：4维评分（不含 gender_compatibility）
        """
        if not garments:
            return self._empty_card()

        # Collect all styles and colors
        all_styles: Set[str] = set()
        all_colors: List[ColorSchema] = []
        for g in garments:
            tags = getattr(g, "style_tags", None) or []
            if isinstance(tags, list):
                all_styles.update(tags)
            mc = getattr(g, "main_color", None) or {}
            if isinstance(mc, dict):
                all_colors.append(ColorSchema(**mc))

        # Dimension 1: Scene score
        scene_score = self._score_scene(all_styles, primary_scene, secondary_scenes)

        # Dimension 2: Category completeness
        category_score = self._score_category(garments)

        # Dimension 3: Style consistency (pairwise)
        style_score = self._score_style_pairwise(garments)

        # Dimension 4: Color harmony (pairwise)
        color_score = self._score_color_pairwise(all_colors)

        # Dimension 5: 无性别推荐系统 - Gender compatibility（仅对女性生效）
        if user_gender_expression is not None:
            # 女性用户：计算性别兼容性
            # Some historical garment rows may have neutral_score=None; treat as neutral (1.0)
            # rather than crashing the whole recommendation flow.
            total_neutral = 0.0
            for g in garments:
                v = getattr(g, "neutral_score", 1.0)
                if v is None:
                    v = 1.0
                total_neutral += float(v)
            avg_neutral = total_neutral / len(garments) if garments else 0.5
            # 性别兼容性：用户性别表达与商品中性化程度的匹配度
            gender_compatibility = 1.0 - abs(user_gender_expression - avg_neutral)

            # 女性用户：5维评分
            weights = {
                "scene": 0.28,
                "category": 0.22,
                "style": 0.22,
                "color": 0.18,
                "gender": 0.10,
            }
            overall = (
                scene_score * weights["scene"]
                + category_score * weights["category"]
                + style_score * weights["style"]
                + color_score * weights["color"]
                + gender_compatibility * weights["gender"]
            )
        else:
            # 男性用户：4维评分（不应用性别兼容性）
            gender_compatibility = None  # 不计入评分
            weights = {
                "scene": 0.30,
                "category": 0.25,
                "style": 0.25,
                "color": 0.20,
            }
            overall = (
                scene_score * weights["scene"]
                + category_score * weights["category"]
                + style_score * weights["style"]
                + color_score * weights["color"]
            )

        # Description
        description = self._generate_description(garments, all_styles, primary_scene)

        # Role assignment
        items = []
        for g in garments:
            role = self._determine_role(g)
            st = getattr(g, "style_tags", None) or []
            if not isinstance(st, list):
                st = []
            mc = getattr(g, "main_color", None) or {}
            items.append(
                OutfitItem(
                    garment_id=g.garment_id,
                    category=g.category,
                    main_color=(
                        ColorSchema(**mc)
                        if isinstance(mc, dict)
                        else ColorSchema(
                            name="灰", rgb=(128, 128, 128), hsv=(0.0, 0.0, 50.0), hex_code="#808080"
                        )
                    ),
                    style_tags=st,
                    image_url=_public_image_url_for_garment(g),
                    role=role,
                )
            )

        # Secondary scenes
        sec_scenes = self._get_secondary_scenes(all_styles, secondary_scenes)

        # Chinese recommendation reason (Step 8)
        reason = self._generate_chinese_reason(
            garments,
            primary_scene,
            scene_score,
            style_score,
            color_score,
        )

        return OutfitCard(
            outfit_id="",
            scene=primary_scene,
            secondary_scenes=sec_scenes,
            items=items,
            description=description,
            reason=reason,
            scene_score=round(scene_score, 3),
            category_score=round(category_score, 3),
            style_score=round(style_score, 3),
            color_score=round(color_score, 3),
            gender_compatibility=(
                round(gender_compatibility, 3) if gender_compatibility is not None else None
            ),
            overall_score=round(overall, 3),
        )

    def _score_scene(
        self,
        all_styles: Set[str],
        primary_scene: str,
        secondary_scenes: List[str],
    ) -> float:
        """Score scene compatibility."""
        if not all_styles:
            return 0.5

        scene_styles = self.scene_styles.get(primary_scene, [])
        primary_match = len(all_styles & set(scene_styles)) / len(all_styles) if all_styles else 0

        # Secondary scene bonus
        secondary_bonus = 0.0
        if secondary_scenes:
            total_secondary_match = 0.0
            for scene in secondary_scenes:
                scene_styles_s = self.scene_styles.get(scene, [])
                total_secondary_match += len(all_styles & set(scene_styles_s)) / len(all_styles)
            secondary_bonus = (total_secondary_match / len(secondary_scenes)) * 0.15

        return min(1.0, primary_match + secondary_bonus)

    def _score_category(self, garments: List[Garment]) -> float:
        categories = {
            normalize_category(getattr(g, "category", None), default="") for g in garments
        }
        has_top = bool(categories & {"上衣", "外套"})
        has_bottom = bool(categories & {"裤子", "裙子"})
        base = 1.0 if has_top and has_bottom else 0.5
        if len(garments) >= 3:
            base = min(1.0, base + 0.1)
        if "外套" in categories:
            base = min(1.0, base + 0.1)
        return base

    def _score_style_pairwise(self, garments: List[Garment]) -> float:
        """Score style consistency (average pairwise)."""
        if len(garments) < 2:
            return 0.8

        scores = []
        for i in range(len(garments)):
            for j in range(i + 1, len(garments)):
                ti = getattr(garments[i], "style_tags", None) or []
                tj = getattr(garments[j], "style_tags", None) or []
                if not isinstance(ti, list):
                    ti = []
                if not isinstance(tj, list):
                    tj = []
                score = self.style_rules.calculate_style_consistency(ti, tj)
                scores.append(score)

        return sum(scores) / len(scores) if scores else 0.5

    def _score_color_pairwise(self, colors: List[ColorSchema]) -> float:
        """Score color harmony (average pairwise)."""
        if len(colors) < 2:
            return 0.9

        scores = []
        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                score, _ = self.color_rules.calculate_color_harmony(colors[i], colors[j])
                scores.append(score)

        return sum(scores) / len(scores) if scores else 0.5

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _group_by_category(self, wardrobe: List[Garment]) -> Dict[str, List[Garment]]:
        grouped: Dict[str, List[Garment]] = {}
        for g in wardrobe:
            category = normalize_category(getattr(g, "category", None), default=CATEGORY_TOP)
            g.category = category
            grouped.setdefault(category, []).append(g)
        return grouped

    def _determine_role(self, garment: Garment) -> str:
        role_map = {
            "上衣": "top",
            "裤子": "bottom",
            "裙子": "bottom",
            "外套": "outer",
            "鞋": "shoes",
            "包": "bag",
        }
        category = normalize_category(getattr(garment, "category", None), default="")
        return role_map.get(category, "accessory")

    def _get_secondary_scenes(
        self,
        all_styles: Set[str],
        user_secondary: List[str],
    ) -> List[str]:
        """Determine secondary suitable scenes."""
        scored: List[Tuple[str, int]] = []
        for scene, scene_style_list in self.scene_styles.items():
            match_count = len(all_styles & set(scene_style_list))
            if match_count > 0:
                scored.append((scene, match_count))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:3]]

    def _generate_description(
        self,
        garments: List[Garment],
        all_styles: Set[str],
        primary_scene: str,
    ) -> str:
        """Generate natural language outfit description."""
        if not garments:
            return "单品展示"

        colors = []
        for g in garments:
            mc = getattr(g, "main_color", None) or {}
            if isinstance(mc, dict):
                colors.append(ColorSchema(**mc).name)
            else:
                colors.append("单品")
        categories = [g.category for g in garments]

        # Build item description
        items_desc = " + ".join([f"{c}{cat}" for c, cat in zip(colors, categories)])

        # Style summary
        top_styles = sorted(all_styles, key=lambda s: 1)[:2]
        style_str = "、".join(top_styles) if top_styles else "简约"

        # Scene description
        scene_desc_map = {
            "通勤上班": "通勤干练",
            "商务正式": "商务正式",
            "约会": "优雅约会",
            "休闲日常": "休闲舒适",
            "校园": "学院青春",
            "运动健身": "运动活力",
            "度假旅行": "度假风情",
            "聚会": "聚会时尚",
            "街头潮流": "街头潮流",
            "正式宴会": "正式典雅",
        }
        scene_desc = scene_desc_map.get(primary_scene, primary_scene)

        return f"{style_str}穿搭，{items_desc}，{scene_desc}"

    def _empty_card(self) -> OutfitCard:
        """Return an empty outfit card."""
        return OutfitCard(
            outfit_id="",
            scene="无",
            secondary_scenes=[],
            items=[],
            description="单品展示",
            reason="",
            scene_score=0.0,
            category_score=0.0,
            style_score=0.0,
            color_score=0.0,
            gender_compatibility=None,  # 男性用户不显示此字段
            overall_score=0.0,
        )

    # ─── Chinese Localization (Step 8) ────────────────────────────────────────

    def _generate_chinese_reason(
        self,
        garments: List[Garment],
        scene: str,
        scene_score: float,
        style_score: float,
        color_score: float,
    ) -> str:
        """
        生成中文推荐理由，帮助用户理解决策逻辑

        格式：「[场景] + [搭配亮点] + [推荐要点]」
        """
        reasons: List[str] = []

        # 场景适配说明
        scene_tips = {
            "通勤上班": "干练利落，适合职场环境",
            "商务正式": "沉稳大气，彰显专业气质",
            "约会": "优雅得体，展现个人魅力",
            "休闲日常": "舒适自在，适合日常生活",
            "校园": "青春活力，学院风格十足",
            "运动健身": "运动便捷，舒适合身",
            "度假旅行": "轻松休闲，度假感满满",
            "聚会": "时尚吸睛，聚会焦点",
            "街头潮流": "个性张扬，街头风格",
            "正式宴会": "典雅端庄，宴会首选",
        }
        scene_tip = scene_tips.get(scene, "")
        if scene_tip:
            reasons.append(scene_tip)

        # 色彩搭配亮点
        if color_score >= 0.85:
            reasons.append("色彩高度统一，视觉协调")
        elif color_score >= 0.70:
            reasons.append("色彩搭配得当，整体和谐")

        # 风格一致性亮点
        if style_score >= 0.85:
            reasons.append("风格高度一致，无违和感")
        elif style_score >= 0.70:
            reasons.append("风格统一，搭配协调")

        # 品类完整性
        categories = {g.category for g in garments}
        if len(garments) >= 3 and len(categories) >= 3:
            reasons.append("上下装搭配完整，层次丰富")

        # 特色风格检测
        all_styles: Set[str] = set()
        for g in garments:
            tg = getattr(g, "style_tags", None) or []
            if isinstance(tg, list):
                all_styles.update(tg)

        style_highlights = {
            "简约": "简约风格，大方得体",
            "复古": "复古韵味，独特品味",
            "甜美": "甜美可人，温柔气质",
            "街头": "街头时尚，个性十足",
            "运动": "运动休闲，活力满满",
            "通勤": "通勤实用，职场必备",
            "正式": "正式得体，商务首选",
            "休闲": "休闲舒适，轻松自在",
            "国风": "国风雅韵，文化气息",
            "汉服": "汉服之美，传统韵味",
            "马面裙": "马面裙搭配，端庄典雅",
            "新中式": "新中式风格，古典时尚",
        }
        for style, highlight in style_highlights.items():
            if style in all_styles and len(reasons) < 3:
                reasons.insert(0, highlight)
                break

        return "；".join(reasons) if reasons else f"适合{scene}场合的穿搭搭配"
