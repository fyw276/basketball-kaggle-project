"""
Enhanced Suitability Scoring Engine — 场景-体型-风格 三维偏好模型

Based on research insight: 小红书/知乎用户痛点 —
推荐不了解体型和场景需求 → "场景-体型-风格"三维偏好模型可解决此痛点

This module replaces the previous SuitabilityScorer with a more sophisticated
3-dimensional model that considers:
1. Scene compatibility (场景匹配) — 通勤/约会/运动/度假 etc.
2. Body type fit (体型适配) — 上窄下宽/苹果型/梨形 etc.
3. Style consistency (风格一致) — 个人风格偏好 vs 服装风格

Each dimension contributes to a final suitability score with interpretable explanations.
"""

from typing import Dict, List, Optional, Tuple

from app.schemas.garment import ColorSchema
from app.schemas.user_profile import UserProfileResponse

# ──────────────────────────────────────────────────────────────────────────────
# Dimension 1: Scene Compatibility Rules (场景匹配)
# ──────────────────────────────────────────────────────────────────────────────
# Maps style tags → suitable scenes
STYLE_TO_SCENES: Dict[str, List[str]] = {
    "通勤": ["通勤上班", "商务正式", "校园"],
    "正式": ["商务正式", "正式宴会", "通勤上班"],
    "学院": ["校园", "通勤上班", "约会"],
    "甜美": ["约会", "聚会", "度假旅行"],
    "甜酷": ["约会", "街头潮流", "聚会"],
    "简约": ["通勤上班", "休闲日常", "校园", "约会"],
    "街头": ["街头潮流", "休闲日常", "聚会"],
    "复古": ["约会", "聚会", "街头潮流"],
    "运动": ["运动健身", "休闲日常"],
    "休闲": ["休闲日常", "校园", "约会"],
    "度假": ["度假旅行", "休闲日常", "约会"],
    "国风": ["正式宴会", "约会", "聚会", "度假旅行"],
    "新中式": ["正式宴会", "约会", "聚会", "商务正式"],
    "朋克": ["街头潮流", "聚会"],
    "民族": ["度假旅行", "聚会", "街头潮流"],
    "优雅": ["约会", "正式宴会", "商务正式", "聚会"],
}

# Maps user scene preferences → expected styles
SCENE_PREFERENCE_STYLES: Dict[str, List[str]] = {
    "通勤上班": ["通勤", "简约", "学院", "正式", "优雅"],
    "商务正式": ["正式", "通勤", "优雅"],
    "约会": ["甜美", "甜酷", "优雅", "复古", "简约"],
    "休闲日常": ["休闲", "简约", "街头", "运动"],
    "运动健身": ["运动"],
    "校园": ["学院", "简约", "休闲"],
    "聚会": ["甜酷", "甜美", "优雅", "复古", "街头", "朋克"],
    "度假旅行": ["度假", "民族", "甜美", "休闲"],
    "街头潮流": ["街头", "朋克", "复古"],
    "正式宴会": ["正式", "优雅"],
}

# Scene importance weight per user (computed from style_preference → dominant scenes)
SCENE_SCORE_RULES: Dict[str, Dict[str, int]] = {
    # 冷白肤色 — 推荐蓝色/紫色/粉色/灰色/黑色
    "冷白": {
        "高分": ["蓝色", "紫色", "粉色", "灰色", "黑色"],
        "中分": ["绿色", "白色", "红色"],
        "低分": ["橙色", "黄色", "棕色"],
    },
    # 黄皮 — 推荐蓝色/绿色/白色/灰色
    "黄皮": {
        "高分": ["蓝色", "绿色", "白色", "灰色"],
        "中分": ["紫色", "粉色", "黑色"],
        "低分": ["黄色", "橙色", "棕色"],
    },
    # 小麦肤色 — 推荐白色/蓝色/绿色/红色
    "小麦": {
        "高分": ["白色", "蓝色", "绿色", "红色"],
        "中分": ["黑色", "灰色", "紫色"],
        "低分": ["黄色", "棕色"],
    },
    # 深色肤色 — 推荐白色/红色/蓝色/黄色
    "深色": {
        "高分": ["白色", "红色", "蓝色", "黄色"],
        "中分": ["绿色", "紫色", "粉色"],
        "低分": ["黑色", "棕色", "灰色"],
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Dimension 2: Body Type Fit Rules (体型适配)
# ──────────────────────────────────────────────────────────────────────────────
BODY_TYPE_FIT_RULES: Dict[str, Dict[str, int]] = {
    "偏瘦": {
        "修身": 85,
        "标准": 90,
        "宽松": 70,
        "oversized": 60,
    },
    "微胖": {
        "修身": 50,
        "标准": 75,
        "宽松": 90,
        "oversized": 85,
    },
    "梨形": {
        "修身": 60,
        "标准": 80,
        "宽松": 85,
        "oversized": 75,
        # 梨形下身偏胖：下装宽松，上装可修身
        "上衣服饰": {"修身": 80, "标准": 75, "宽松": 65, "oversized": 55},
        "下衣服饰": {"修身": 50, "标准": 70, "宽松": 90, "oversized": 85},
    },
    "倒三角": {
        "修身": 65,
        "标准": 80,
        "宽松": 90,
        "oversized": 85,
        # 倒三角上身宽：上装宽松遮肩，下装可修身
        "上衣服饰": {"修身": 40, "标准": 60, "宽松": 90, "oversized": 95},
        "下衣服饰": {"修身": 85, "标准": 80, "宽松": 70, "oversized": 60},
    },
    "沙漏": {
        "修身": 90,
        "标准": 85,
        "宽松": 70,
        "oversized": 60,
    },
    "矩形": {
        "修身": 75,
        "标准": 85,
        "宽松": 80,
        "oversized": 70,
    },
}

# Fit type emphasis on body parts
FIT_TYPE_EMPHASIS: Dict[str, List[str]] = {
    "修身": ["肩", "腰", "臀", "大腿"],
    "标准": ["肩"],
    "宽松": [],
    "oversized": [],
}

# Category-aware body emphasis (which body parts does each category affect most)
CATEGORY_BODY_PARTS: Dict[str, List[str]] = {
    "上衣": ["肩", "腰", "手臂", "胸部"],
    "裤子": ["腰", "臀", "大腿", "小腿"],
    "裙子": ["腰", "臀", "大腿"],
    "外套": ["肩", "腰", "手臂"],
    "鞋": ["小腿"],
    "包": [],  # 包不直接影响体型
}

# ──────────────────────────────────────────────────────────────────────────────
# Dimension 3: Style Preference Matching (风格一致)
# ──────────────────────────────────────────────────────────────────────────────
STYLE_PREFERENCE_RULES: Dict[str, List[str]] = {
    "通勤": ["通勤", "简约", "正式", "优雅"],
    "学院": ["学院", "简约", "休闲", "甜美"],
    "甜酷": ["甜美", "街头", "休闲"],
    "简约": ["简约", "通勤", "优雅", "正式"],
    "街头": ["街头", "休闲", "运动", "朋克"],
    "复古": ["复古", "优雅", "民族"],
    "运动": ["运动", "休闲", "街头"],
    "正式": ["正式", "通勤", "优雅", "简约"],
    "休闲": ["休闲", "简约", "运动", "街头"],
    "甜美": ["甜美", "学院", "优雅"],
    "优雅": ["优雅", "正式", "简约", "通勤"],
    "朋克": ["朋克", "街头", "复古"],
    "民族": ["民族", "复古", "优雅"],
    "度假": ["度假", "休闲", "甜美", "民族"],
    "国风": ["民族", "复古", "优雅", "正式"],
    "新中式": ["民族", "复古", "优雅", "正式", "简约"],
}


# ──────────────────────────────────────────────────────────────────────────────
# Occasion Mapping (for recommendation)
# ──────────────────────────────────────────────────────────────────────────────
OCCASION_MAPPING: Dict[str, List[str]] = {
    "正式": ["商务正式", "正式宴会"],
    "通勤": ["通勤上班", "商务正式"],
    "休闲": ["休闲日常", "校园"],
    "运动": ["运动健身"],
    "街头": ["街头潮流", "聚会"],
    "学院": ["校园", "通勤上班"],
    "甜美": ["约会", "聚会"],
    "优雅": ["正式宴会", "约会", "聚会"],
    "复古": ["约会", "聚会"],
    "甜酷": ["街头潮流", "约会", "聚会"],
    "简约": ["通勤上班", "休闲日常", "校园", "约会"],
    "朋克": ["街头潮流", "聚会"],
    "民族": ["度假旅行", "聚会"],
    "度假": ["度假旅行", "休闲日常"],
    "国风": ["正式宴会", "约会", "聚会"],
    "新中式": ["正式宴会", "约会", "聚会", "商务正式"],
}


# ──────────────────────────────────────────────────────────────────────────────
# 3-Dimensional Suitability Scorer
# ──────────────────────────────────────────────────────────────────────────────


class SuitabilityScorer3D:
    """
    场景-体型-风格 三维适合度评分引擎

    Computes suitability scores across three independent dimensions,
    then synthesizes a final weighted score with detailed explanations.

    Weights (可调参数):
    - scene_score:    25% — 场景匹配度
    - body_score:     35% — 体型适配度
    - style_score:    40% — 风格一致度

    Color compatibility is still computed but as a sub-weight within scene_score.
    """

    DEFAULT_WEIGHTS = {
        "scene": 0.25,
        "body": 0.35,
        "style": 0.40,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize the 3D scorer.

        Args:
            weights: Optional weight override for {scene, body, style}.
                     Must sum to 1.0 if provided.
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        # Validate weights sum to 1
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            # Normalize
            self.weights = {k: v / total for k, v in self.weights.items()}

    # ─── Scene name normalization (frontend → scorer internal names) ─────
    SCENE_NORMALIZE: Dict[str, List[str]] = {
        "日常通勤": ["通勤上班", "商务正式"],
        "正式场合": ["商务正式", "正式宴会"],
        "休闲娱乐": ["休闲日常", "聚会"],
        "约会聚会": ["约会", "聚会"],
        "运动健身": ["运动健身"],
        "旅行出游": ["度假旅行"],
    }

    # ─── Dimension 1: Scene Score ──────────────────────────────────────────

    def _compute_scene_score(
        self,
        style_tags: List[str],
        user_profile: UserProfileResponse,
        selected_scene: Optional[str] = None,
    ) -> Tuple[int, str]:
        """
        Compute scene compatibility score.
        - Maps garment styles → suitable scenes
        - Maps user style_preference → dominant user scenes
        - Computes overlap as scene compatibility
        - If selected_scene is provided, boosts/penalizes based on garment-scene fit
        """
        # Derive user-preferred scenes from their style preferences
        # SCENE_PREFERENCE_STYLES keys are scene names, values are style lists.
        # Reverse-map: for each scene, check if user prefers any of its styles.
        user_scenes: Dict[str, int] = {}
        user_prefs_set = set(user_profile.style_preference)
        for scene, styles in SCENE_PREFERENCE_STYLES.items():
            matched = sum(1 for s in styles if s in user_prefs_set)
            if matched:
                user_scenes[scene] = matched

        # Debug: trace scene computation
        print(
            f"[Scorer] style_preference={list(user_profile.style_preference)}, "
            f"user_scenes={user_scenes}, "
            f"style_tags={style_tags}, "
            f"selected_scene={selected_scene!r}"
        )

        if not user_scenes:
            return 70, "无法判断场景适合度（用户画像缺少场景偏好）"

        # Derive garment-compatible scenes
        garment_scenes: Dict[str, int] = {}
        for style_tag in style_tags:
            for scene in STYLE_TO_SCENES.get(style_tag, []):
                garment_scenes[scene] = garment_scenes.get(scene, 0) + 1

        print(f"[Scorer] garment_scenes={garment_scenes}")

        if not garment_scenes:
            return 70, "无法判断场景适合度（服装缺少风格标签）"

        # Compute scene overlap
        common_scenes = set(user_scenes.keys()) & set(garment_scenes.keys())

        if not common_scenes:
            # Check compatibility via 1-hop (user scene → compatible styles → garment scene)
            expanded_common = self._expand_scene_compatibility(user_scenes, garment_scenes)
            if expanded_common:
                score = 60
                score, scene_fit_note = self._adjust_for_selected_scene(
                    score, selected_scene, style_tags, garment_scenes
                )
                return (
                    score,
                    f"服装适合{expanded_common}等场合，与您的偏好场景有所不同{scene_fit_note}",
                )
            score = 50
            score, scene_fit_note = self._adjust_for_selected_scene(
                score, selected_scene, style_tags, garment_scenes
            )
            return score, f"服装场景与您的偏好场景差异较大，建议根据场合选择{scene_fit_note}"

        # Score based on overlap ratio and weight of common scenes
        # Weight each common scene by how strongly user prefers it
        user_total = sum(user_scenes.values())
        overlap_weight = sum(user_scenes[s] for s in common_scenes) / user_total

        # Bonus: if top user scene is matched
        top_user_scene = max(user_scenes, key=user_scenes.get)
        top_match_bonus = 5 if top_user_scene in common_scenes else 0

        raw_score = int(60 + overlap_weight * 30 + top_match_bonus)
        score = min(100, raw_score)

        # ── Selected scene adjustment ──
        score, scene_fit_note = self._adjust_for_selected_scene(
            score, selected_scene, style_tags, garment_scenes
        )

        # Build explanation
        common_list = "、".join(
            sorted(common_scenes, key=lambda s: user_scenes[s], reverse=True)[:3]
        )
        explanation = (
            f"服装适合{common_list}等场合，与您的风格偏好高度匹配{scene_fit_note}"
            if score >= 80
            else (
                f"服装适合{common_list}等场合，与您的偏好较为匹配{scene_fit_note}"
                if score >= 60
                else f"服装适合{common_list}等场合，与您的偏好有所差异{scene_fit_note}"
            )
        )

        return score, explanation

    def _adjust_for_selected_scene(
        self,
        score: int,
        selected_scene: Optional[str],
        style_tags: List[str],
        garment_scenes: Dict[str, int],
    ) -> Tuple[int, str]:
        if not selected_scene:
            return score, ""

        normalized = self.SCENE_NORMALIZE.get(selected_scene, [selected_scene])
        garment_scene_set = set(garment_scenes.keys())
        scene_match = bool(set(normalized) & garment_scene_set)
        matched_ranks = []
        for style_tag in style_tags:
            ranked_scenes = STYLE_TO_SCENES.get(style_tag, [])
            for normalized_scene in normalized:
                if normalized_scene in ranked_scenes:
                    matched_ranks.append(ranked_scenes.index(normalized_scene))

        print(
            f"[Scorer] scene_adjust: selected={selected_scene!r}, "
            f"normalized={normalized}, "
            f"garment_scenes={garment_scene_set}, "
            f"match={scene_match}, "
            f"score_before={score}"
        )

        if scene_match:
            best_rank = min(matched_ranks) if matched_ranks else 2
            boost = 12 if best_rank == 0 else (8 if best_rank == 1 else 5)
            score = min(100, score + boost)
            scene_fit_note = f"，且非常适合「{selected_scene}」场景"
        else:
            score = max(30, score - 18)
            scene_fit_note = f"，但不太适合「{selected_scene}」场景"

        print(f"[Scorer] scene_adjust result: score_after={score}")
        return score, scene_fit_note

    def _expand_scene_compatibility(
        self,
        user_scenes: Dict[str, int],
        garment_scenes: Dict[str, int],
    ) -> str:
        """Check 1-hop scene compatibility via shared styles."""
        # Get styles that serve user's top scenes
        user_styles = set()
        for scene in user_scenes:
            for style in SCENE_PREFERENCE_STYLES.get(scene, []):
                user_styles.add(style)

        # Get scenes that garment styles serve
        garment_scene_set = set()
        for style in set(STYLE_TO_SCENES.keys()):
            for scene in STYLE_TO_SCENES.get(style, []):
                if style in user_styles:
                    garment_scene_set.add(scene)

        expanded = garment_scene_set & set(user_scenes.keys())
        if expanded:
            return "、".join(sorted(expanded, key=lambda s: user_scenes[s], reverse=True)[:2])
        return ""

    # ─── Dimension 2: Body Score ─────────────────────────────────────────────

    def _compute_body_score(
        self,
        fit_type: Optional[str],
        category: str,
        body_type: str,
        avoid_body_parts: List[str],
        selected_scene: Optional[str] = None,
    ) -> Tuple[int, str]:
        """
        Compute body-type fit score.
        - Uses category-aware rules (upper vs lower garment)
        - Penalizes fit types that emphasize avoided body parts
        """
        if not fit_type:
            # No fit info — conservative default
            return 70, "无法从图片判断版型，建议参考尺码信息"

        if body_type not in BODY_TYPE_FIT_RULES:
            return 70, "无法判断体型适合度"

        body_rules = BODY_TYPE_FIT_RULES[body_type]

        # Determine which rules to use (category-specific for 梨形/倒三角)
        if category in ("裤子", "裙子") and "下衣服饰" in body_rules:
            rules = body_rules["下衣服饰"]
        elif category in ("上衣", "外套") and "上衣服饰" in body_rules:
            rules = body_rules["上衣服饰"]
        else:
            rules = body_rules

        base_score = rules.get(fit_type, 70)

        # Check avoid parts
        affected_parts = CATEGORY_BODY_PARTS.get(category, [])
        conflicting_parts = [p for p in avoid_body_parts if p in affected_parts]

        if conflicting_parts:
            penalty = min(len(conflicting_parts) * 15, 30)
            final_score = max(base_score - penalty, 30)
            parts_str = "、".join(conflicting_parts)
            explanation = f"{fit_type}版型可能强化{parts_str}，建议选择更宽松或不同剪裁的款式"
        else:
            final_score = base_score
            explanation = (
                f"{fit_type}版型与您的{body_type}体型搭配度较高"
                if final_score >= 80
                else (
                    f"{fit_type}版型与您的{body_type}体型搭配度一般"
                    if final_score >= 60
                    else f"{fit_type}版型可能不太适合{body_type}体型"
                )
            )

        scene_note = self._body_scene_note(selected_scene, fit_type, category)
        if scene_note:
            explanation += scene_note

        return final_score, explanation

    def _body_scene_note(
        self,
        selected_scene: Optional[str],
        fit_type: Optional[str],
        category: str,
    ) -> str:
        if not selected_scene or not fit_type:
            return ""

        if selected_scene == "正式场合":
            if fit_type in ("修身", "标准"):
                return "；正式场合更看重利落线条，这个版型能保持轮廓整洁"
            return "；正式场合通常需要更利落的轮廓，过于宽松会削弱精致感"
        if selected_scene == "日常通勤":
            return "；日常通勤需要兼顾活动量和整洁度，版型稳定性会影响全天穿着状态"
        if selected_scene == "休闲娱乐":
            return "；休闲娱乐场景更重视舒适和松弛感，体型修饰不必过度强调"
        if selected_scene == "约会聚会":
            return "；约会聚会会更关注整体比例和上镜效果，剪裁轮廓会被放大感知"
        if selected_scene == "运动健身":
            if category in ("鞋", "裤子", "上衣"):
                return "；运动健身更需要活动余量，版型是否限制动作会影响适配度"
            return "；运动健身场景对功能性要求更高，配饰类单品对体型影响较弱"
        if selected_scene == "旅行出游":
            return "；旅行出游更看重长时间穿着舒适度，宽容的版型会更友好"
        return ""

    # ─── Dimension 3: Style Score ─────────────────────────────────────────

    def _compute_style_score(
        self,
        garment_styles: List[str],
        user_style_preferences: List[str],
        selected_scene: Optional[str] = None,
    ) -> Tuple[int, str]:
        """
        Compute style consistency score.
        - Exact match: 100 per tag
        - Compatible match: 80 per tag
        - No match: 50 per tag
        """
        if not garment_styles or not user_style_preferences:
            return 70, "无法判断风格适合度"

        perfect_matches = 0
        compatible_matches = 0
        total_tags = len(garment_styles)

        for garment_style in garment_styles:
            if garment_style in user_style_preferences:
                perfect_matches += 1
            elif garment_style in self._get_compatible_user_styles(
                garment_style, user_style_preferences
            ):
                compatible_matches += 1

        if perfect_matches + compatible_matches == 0:
            scene_note = self._style_scene_note(selected_scene, garment_styles)
            return 50, f"服装风格与您的偏好差异较大，建议选择更符合个人风格的款式{scene_note}"

        total_score = (perfect_matches * 100 + compatible_matches * 80) / total_tags
        score = int(total_score)

        garment_str = "、".join(garment_styles[:3])
        pref_str = "、".join(user_style_preferences[:3])

        if score >= 90:
            explanation = f"{garment_str}风格与您的{pref_str}偏好完全契合"
        elif score >= 75:
            explanation = f"{garment_str}风格与您的{pref_str}偏好较为匹配"
        else:
            explanation = f"{garment_str}风格与您的{pref_str}偏好有一定差异"

        scene_note = self._style_scene_note(selected_scene, garment_styles)
        if scene_note:
            explanation += scene_note

        return score, explanation

    def _style_scene_note(
        self,
        selected_scene: Optional[str],
        garment_styles: List[str],
    ) -> str:
        if not selected_scene or not garment_styles:
            return ""
        normalized = self.SCENE_NORMALIZE.get(selected_scene, [selected_scene])
        matching_styles = []
        for style in garment_styles:
            if set(STYLE_TO_SCENES.get(style, [])) & set(normalized):
                matching_styles.append(style)
        if matching_styles:
            matched_style_text = "、".join(matching_styles[:2])
            return f"；同时也呼应「{selected_scene}」对{matched_style_text}风格的需求"
        return f"；但与「{selected_scene}」的典型风格要求不完全一致"

    def _get_compatible_user_styles(self, garment_style: str, user_prefs: List[str]) -> List[str]:
        """Get all styles compatible with user's preferences."""
        compatible = set()
        for pref in user_prefs:
            compatible.update(STYLE_PREFERENCE_RULES.get(pref, [pref]))
        return list(compatible)

    # ─── Color Score (sub-component, used in scene dimension context) ───────

    def _compute_color_score(
        self,
        garment_color: ColorSchema,
        secondary_colors: List[ColorSchema],
        skin_tone: str,
    ) -> Tuple[int, str]:
        """Compute color compatibility with skin tone."""
        if skin_tone not in SCENE_SCORE_RULES:
            return 70, "无法判断颜色适合度"

        rules = SCENE_SCORE_RULES[skin_tone]
        color_name = garment_color.name

        if color_name in rules["高分"]:
            main_score = 90
            explanation = f"{color_name}与您的{skin_tone}肤色搭配度很高，能提亮肤色"
        elif color_name in rules["中分"]:
            main_score = 70
            explanation = f"{color_name}与您的{skin_tone}肤色搭配度适中"
        elif color_name in rules["低分"]:
            main_score = 50
            explanation = f"{color_name}可能不太适合{skin_tone}肤色，建议选择其他颜色"
        else:
            main_score = 70
            explanation = f"{color_name}与您的{skin_tone}肤色搭配度适中"

        # Secondary color adjustment
        if secondary_colors:
            sec_scores = []
            for sec in secondary_colors:
                if sec.name in rules["高分"]:
                    sec_scores.append(90)
                elif sec.name in rules["中分"]:
                    sec_scores.append(70)
                elif sec.name in rules["低分"]:
                    sec_scores.append(50)
                else:
                    sec_scores.append(70)
            final_score = int(main_score * 0.8 + (sum(sec_scores) / len(sec_scores)) * 0.2)
            if final_score > main_score:
                explanation += "，辅助色搭配也较为协调"
        else:
            final_score = main_score

        return final_score, explanation

    # ─── Scene Score (dimension 1, wrapper with color sub-component) ────────

    def compute_scene_score_with_color(
        self,
        style_tags: List[str],
        garment_color: ColorSchema,
        secondary_colors: List[ColorSchema],
        skin_tone: str,
        user_profile: UserProfileResponse,
        selected_scene: Optional[str] = None,
    ) -> Tuple[int, str]:
        """
        Full scene dimension score = scene compatibility (70%) + color compatibility (30%).
        Color sub-score acts as a bonus/penalty within the scene dimension.
        """
        scene_score, scene_exp = self._compute_scene_score(
            style_tags, user_profile, selected_scene=selected_scene
        )
        color_score, color_exp = self._compute_color_score(
            garment_color, secondary_colors, skin_tone
        )

        # Weighted combination: 70% scene match + 30% color match
        combined = int(scene_score * 0.7 + color_score * 0.3)

        # Craft explanation based on which part drove the score
        if color_score < 60:
            explanation = scene_exp + "，" + color_exp
        else:
            explanation = scene_exp + "，色彩搭配也协调。"

        return combined, explanation

    # ─── Main API ────────────────────────────────────────────────────────────

    def calculate_score(
        self,
        garment_color: ColorSchema,
        secondary_colors: List[ColorSchema],
        garment_fit: Optional[str],
        garment_styles: List[str],
        garment_category: str,
        user_profile: UserProfileResponse,
        selected_scene: Optional[str] = None,
    ) -> dict:
        """
        Compute full 3D suitability score.

        Args:
            garment_color: Main color of the garment
            secondary_colors: Secondary colors
            garment_fit: Fit type (修身/宽松/标准/oversized) or None
            garment_styles: Style tags
            garment_category: Garment category
            user_profile: User profile with preferences

        Returns:
            Dict with all scores and explanations
        """
        # Dimension 1: Scene (with color sub-component)
        scene_score, scene_explanation = self.compute_scene_score_with_color(
            garment_styles,
            garment_color,
            secondary_colors,
            user_profile.skin_tone,
            user_profile,
            selected_scene=selected_scene,
        )

        # Dimension 2: Body type fit
        body_score, body_explanation = self._compute_body_score(
            garment_fit,
            garment_category,
            user_profile.body_type,
            user_profile.avoid_body_parts,
            selected_scene=selected_scene,
        )

        # Dimension 3: Style consistency
        style_score, style_explanation = self._compute_style_score(
            garment_styles,
            user_profile.style_preference,
            selected_scene=selected_scene,
        )

        # Color sub-score (also returned separately for UI)
        color_score, color_explanation = self._compute_color_score(
            garment_color,
            secondary_colors,
            user_profile.skin_tone,
        )

        # Weighted overall score
        overall = int(
            scene_score * self.weights["scene"]
            + body_score * self.weights["body"]
            + style_score * self.weights["style"]
        )

        # Recommended occasions
        recommended_occasions = self._recommend_occasions(garment_styles, overall)

        # Suggestions
        suggestions = self._generate_suggestions(
            scene_score,
            scene_explanation,
            body_score,
            body_explanation,
            style_score,
            style_explanation,
            color_score,
            color_explanation,
            overall,
        )

        from app.schemas.suitability import SuitabilityResult

        return SuitabilityResult(
            scene_score=scene_score,
            body_score=body_score,
            suitability_score=overall,
            color_score=color_score,
            fit_score=body_score,  # "fit" dimension = body score
            style_score=style_score,
            explanation={
                "scene": scene_explanation,
                "body": body_explanation,
                "style": style_explanation,
            },
            recommended_occasions=recommended_occasions,
            suggestions=suggestions,
        )

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _recommend_occasions(
        self,
        garment_styles: List[str],
        overall_score: int,
    ) -> List[str]:
        """Recommend suitable occasions based on style tags."""
        if overall_score < 50:
            return []

        occasions: set = set()
        for style in garment_styles:
            occasions.update(OCCASION_MAPPING.get(style, []))

        if overall_score >= 80 and not occasions:
            occasions.add("休闲日常")
        elif overall_score >= 70 and not occasions:
            occasions.add("日常")

        return sorted(list(occasions))[:5]

    def _generate_suggestions(
        self,
        scene_score: int,
        scene_exp: str,
        body_score: int,
        body_exp: str,
        style_score: int,
        style_exp: str,
        color_score: int,
        color_exp: str,
        overall: int,
    ) -> List[str]:
        """Generate actionable suggestions based on low-scoring dimensions."""
        suggestions = []

        if overall >= 85:
            return suggestions  # No suggestions needed

        if scene_score < 65:
            if "差异" in scene_exp or overall < 70:
                suggestions.append("建议根据您的主要场景（通勤/约会/运动等）选择更合适的款式")

        if body_score < 65:
            if "强化" in body_exp:
                suggestions.append("建议选择宽松或落肩款式，避免强化身体线条")
            else:
                suggestions.append("建议根据体型选择更合适的版型")

        if style_score < 65:
            if "差异" in style_exp:
                suggestions.append("建议选择更符合个人风格偏好的款式")

        if color_score < 65:
            if "不太适合" in color_exp or "建议选择其他颜色" in color_exp:
                suggestions.append("建议选择更适合您肤色的颜色，如蓝色、绿色或白色系")

        if overall < 60 and not suggestions:
            suggestions.append("建议综合考虑场合、体型和风格，选择整体更协调的服饰")

        return suggestions[:3]  # Max 3 suggestions
