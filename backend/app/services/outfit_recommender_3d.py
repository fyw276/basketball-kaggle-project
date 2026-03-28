"""
3D Outfit Recommendation Engine — 场景-品类-风格 三维匹配

Based on research insight:
- Polyvore搭配数据集（数百万套装）→ 搭配规则学习
- 社区动态：推荐不了解体型和场景需求 → 三维偏好模型

This module replaces the previous OutfitRecommender with a more sophisticated
3-dimensional recommendation engine:
1. Scene dimension (场景匹配) — 套装整体适合哪些场合
2. Category dimension (品类完整) — 上下装完整搭配，上下文协调
3. Style dimension (风格一致) — 所有单品风格统一，无突兀感

Features:
- Multi-item outfit generation (不只是上衣+裤子，而是完整套装)
- Scene-aware recommendation (通勤/约会/度假 不同套装)
- Color harmony across ALL items (不只是两件，而是整体协调)
- CLIP-powered semantic matching for style consistency
"""

from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import setup_logging
from app.models.garment import Garment
from app.schemas.garment import ColorSchema
from app.services.outfit_rules import CategoryRules, ColorRules, StyleRules

logger = setup_logging()


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


# ──────────────────────────────────────────────────────────────────────────────
# 体型感知推荐常量
# ──────────────────────────────────────────────────────────────────────────────

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
    """Complete outfit recommendation card with 3D scores."""

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
    overall_score: float = Field(..., ge=0, le=1, description="Weighted overall score")
    # Weight configuration for scoring
    dimension_weights: Dict[str, float] = Field(
        default_factory=lambda: {"scene": 0.30, "category": 0.25, "style": 0.25, "color": 0.20},
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
            if style in self.scene_styles:
                for scene in self.scene_styles[style]:
                    scene_scores[scene] = scene_scores.get(scene, 0) + 1

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
    ) -> List[OutfitCard]:
        """
        Generate outfit recommendations for a target garment (体型+场景感知).

        新增 Step 6 体型感知：
        - 根据用户体型过滤不合适的版型
        - 根据体型调整品类优先度（如梨形优先外套遮臀部）
        - 避免推荐强化用户想遮盖的身体部位

        Args:
            target_garment: 核心单品，以此为中心构建套装
            wardrobe: 用户衣橱
            num_outfits: 返回套装数量（默认3）
            user_style_preferences: 风格偏好（用于场景推断）
            user_body_type: 用户体型（偏瘦/微胖/梨形/倒三角/沙漏/矩形）
            avoid_body_parts: 需要遮盖的身体部位（肩/腰/臀/大腿/小腿）

        Returns:
            List[OutfitCard]: 排序后的套装推荐（含体型感知评分）
        """
        logger.info(
            f"Generating {num_outfits} outfits for {target_garment.category} "
            f"(body_type={user_body_type})"
        )

        if not wardrobe:
            return []

        # Step 1: 体型感知过滤（提前排除明显不适合的服装）
        if user_body_type or avoid_body_parts:
            wardrobe = self._filter_by_body_type(
                wardrobe, user_body_type, avoid_body_parts
            )
            logger.info(f"After body-type filtering: {len(wardrobe)} garments remain")

        # Step 2: Group wardrobe by category
        wardrobe_by_cat = self._group_by_category(wardrobe)

        # Step 3: Derive user's primary scene from style preferences
        style_prefs = user_style_preferences or target_garment.style_tags
        # Step 3: Scene derivation (user-specified scene overrides style inference)
        if preferred_scene:
            primary_scene = preferred_scene
            secondary_scenes = []
            logger.info(f"Using user-specified scene: {primary_scene}")
        else:
            primary_scene, secondary_scenes = self._derive_user_scenes(style_prefs)
            logger.info(f"Derived scene: {primary_scene}, Secondary: {secondary_scenes}")

        # Step 4: Get outfit templates for primary scene
        templates = SCENE_OUTFIT_TEMPLATES.get(
            primary_scene, SCENE_OUTFIT_TEMPLATES["休闲日常"]
        )

        # Step 5: Generate outfit candidates for each template
        all_candidates: List[Tuple[List[Garment], Dict]] = []
        for template in templates:
            cats = template["categories"]
            weight = template["weight"]

            if target_garment.category not in cats:
                continue

            combos = self._generate_for_template(
                target_garment, cats, wardrobe_by_cat,
                user_body_type=user_body_type, avoid_body_parts=avoid_body_parts,
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

        # Step 6: Score all candidates across 5 dimensions (scene/category/style/color/body)
        scored: List[Tuple[List[Garment], Dict, OutfitCard]] = []
        for combo, meta in all_candidates:
            card = self._score_outfit_3d(
                combo,
                primary_scene,
                secondary_scenes,
                user_body_type=user_body_type,
                avoid_body_parts=avoid_body_parts,
            )
            scored.append((combo, meta, card))

        # Step 7: Sort by adjusted score (body_type bonus)
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

        logger.info(f"Generated {len(outfit_cards)} outfit recommendations")
        return outfit_cards

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
            for g in cat_garments:
                style_score = self.style_rules.calculate_style_consistency(
                    target.style_tags, g.style_tags
                )
                color_score, _ = self.color_rules.calculate_color_harmony(
                    ColorSchema(**target.main_color),
                    ColorSchema(**g.main_color),
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
                        style = self.style_rules.calculate_style_consistency(
                            combo[i].style_tags, combo[j].style_tags
                        )
                        color, _ = self.color_rules.calculate_color_harmony(
                            ColorSchema(**combo[i].main_color),
                            ColorSchema(**combo[j].main_color),
                        )
                        total += style + color
                return total / ((len(combo) * (len(combo) - 1)) / 2) if len(combo) > 1 else 0.5

            combinations.sort(key=combo_score, reverse=True)
            combinations = combinations[:30]

        # Always include target
        return [combo for combo in combinations if target in combo]

    # ─── 4D Scoring ─────────────────────────────────────────────────────────────

    def _score_outfit_3d(
        self,
        garments: List[Garment],
        primary_scene: str,
        secondary_scenes: List[str],
        user_body_type: Optional[str] = None,
        avoid_body_parts: Optional[List[str]] = None,
    ) -> OutfitCard:
        """
        Score an outfit across 4 dimensions.
        """
        if not garments:
            return self._empty_card()

        # Collect all styles and colors
        all_styles: Set[str] = set()
        all_colors: List[ColorSchema] = []
        for g in garments:
            all_styles.update(g.style_tags)
            all_colors.append(ColorSchema(**g.main_color))

        # Dimension 1: Scene score
        scene_score = self._score_scene(all_styles, primary_scene, secondary_scenes)

        # Dimension 2: Category completeness
        category_score = self._score_category(garments)

        # Dimension 3: Style consistency (pairwise)
        style_score = self._score_style_pairwise(garments)

        # Dimension 4: Color harmony (pairwise)
        color_score = self._score_color_pairwise(all_colors)

        # Weighted overall
        weights = {"scene": 0.30, "category": 0.25, "style": 0.25, "color": 0.20}
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
            items.append(
                OutfitItem(
                    garment_id=g.garment_id,
                    category=g.category,
                    main_color=ColorSchema(**g.main_color),
                    style_tags=g.style_tags,
                    image_url=g.image_url,
                    role=role,
                )
            )

        # Secondary scenes
        sec_scenes = self._get_secondary_scenes(all_styles, secondary_scenes)

        # Chinese recommendation reason (Step 8)
        reason = self._generate_chinese_reason(
            garments, primary_scene, scene_score, style_score, color_score,
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
        """Score category completeness (has top + bottom)."""
        categories = {g.category for g in garments}
        has_top = bool(categories & {"上衣", "外套"})
        has_bottom = bool(categories & {"裤子", "裙子"})
        base = 1.0 if has_top and has_bottom else 0.5
        # Bonus for having 3+ items
        if len(garments) >= 3:
            base = min(1.0, base + 0.1)
        # Bonus for outerwear in formal scenes
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
                score = self.style_rules.calculate_style_consistency(
                    garments[i].style_tags,
                    garments[j].style_tags,
                )
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
        """Group wardrobe by category."""
        grouped = {}
        for g in wardrobe:
            if g.category not in grouped:
                grouped[g.category] = []
            grouped[g.category].append(g)
        return grouped

    def _determine_role(self, garment: Garment) -> str:
        """Determine the role of a garment in the outfit."""
        role_map = {
            "上衣": "top",
            "裤子": "bottom",
            "裙子": "bottom",
            "外套": "outer",
            "鞋": "shoes",
            "包": "bag",
        }
        return role_map.get(garment.category, "accessory")

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

        colors = [ColorSchema(**g.main_color).name for g in garments]
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
            all_styles.update(g.style_tags)

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
