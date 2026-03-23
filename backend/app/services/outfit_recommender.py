"""
Outfit recommendation service
Generates outfit recommendations based on target garment and wardrobe
"""

from typing import List
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.logging import setup_logging
from app.models.garment import Garment
from app.schemas.garment import ColorSchema
from app.services.outfit_rules import CategoryRules, ColorRules, StyleRules

logger = setup_logging()


class OutfitItem(BaseModel):
    """Single item in an outfit"""

    garment_id: UUID = Field(..., description="Garment ID")
    category: str = Field(..., description="Garment category")
    main_color: ColorSchema = Field(..., description="Main color")
    style_tags: List[str] = Field(default_factory=list, description="Style tags")
    image_url: str = Field(..., description="Image URL")
    role: str = Field(..., description="Role in outfit: target/top/bottom/outer/shoes/bag")


class OutfitCard(BaseModel):
    """Complete outfit recommendation card"""

    outfit_id: str = Field(..., description="Unique outfit ID")
    items: List[OutfitItem] = Field(..., description="Garments in outfit")
    occasion: str = Field(..., description="Recommended occasion")
    description: str = Field(..., description="Outfit description")
    color_harmony: str = Field(..., description="Color harmony type")
    color_harmony_score: float = Field(..., ge=0, le=1, description="Color harmony score")
    style_consistency: float = Field(..., ge=0, le=1, description="Style consistency score")
    overall_score: float = Field(..., ge=0, le=1, description="Overall outfit score")

    class Config:
        json_schema_extra = {
            "example": {
                "outfit_id": "outfit_1",
                "items": [
                    {
                        "garment_id": "123e4567-e89b-12d3-a456-426614174000",
                        "category": "上衣",
                        "main_color": {"name": "白", "hex_code": "#ffffff"},
                        "style_tags": ["简约", "通勤"],
                        "image_url": "/uploads/user/shirt.jpg",
                        "role": "target",
                    }
                ],
                "occasion": "商务",
                "description": "白色衬衫搭配黑色西裤，适合正式场合",
                "color_harmony": "中性色搭配",
                "color_harmony_score": 0.9,
                "style_consistency": 0.95,
                "overall_score": 0.92,
            }
        }


class OutfitRecommender:
    """
    Outfit recommendation engine

    Generates outfit recommendations by:
    1. Identifying required garment categories
    2. Finding matching garments from wardrobe
    3. Scoring combinations based on color and style
    4. Generating outfit cards with descriptions
    """

    # Occasion mapping based on style tags
    OCCASION_MAPPING = {
        "正式": "正式场合",
        "通勤": "商务",
        "休闲": "休闲",
        "运动": "运动健身",
        "街头": "街头潮流",
        "学院": "校园",
        "甜美": "约会",
        "优雅": "聚会",
        "度假": "度假旅行",
    }

    def __init__(
        self,
        color_rules: ColorRules = None,
        style_rules: StyleRules = None,
        category_rules: CategoryRules = None,
    ):
        """
        Initialize outfit recommender

        Args:
            color_rules: Color matching rules (creates new if None)
            style_rules: Style consistency rules (creates new if None)
            category_rules: Category pairing rules (creates new if None)
        """
        self.color_rules = color_rules or ColorRules()
        self.style_rules = style_rules or StyleRules()
        self.category_rules = category_rules or CategoryRules()

        logger.info("OutfitRecommender initialized")

    def recommend_outfits(
        self,
        target_garment: Garment,
        wardrobe: List[Garment],
        num_outfits: int = 3,
    ) -> List[OutfitCard]:
        """
        Generate outfit recommendations

        Args:
            target_garment: Target garment to build outfits around
            wardrobe: User's wardrobe garments
            num_outfits: Number of outfits to generate (default: 3)

        Returns:
            List[OutfitCard]: List of outfit recommendations
        """
        logger.info(
            f"Generating {num_outfits} outfit recommendations for " f"{target_garment.category}"
        )

        # Get required categories for target
        required_categories = self.category_rules.get_required_categories(target_garment.category)

        if not required_categories:
            logger.warning(
                f"No required categories for {target_garment.category}, "
                "returning empty recommendations"
            )
            return []

        # Check if wardrobe has any garments in required categories
        wardrobe_by_category = self._group_by_category(wardrobe)
        has_required = any(
            cat in wardrobe_by_category and len(wardrobe_by_category[cat]) > 0
            for cat in required_categories
        )

        if not has_required:
            logger.warning(
                f"Wardrobe does not have garments in required categories: {required_categories}"
            )
            return []

        # Generate outfit combinations
        outfit_combinations = self._generate_combinations(
            target_garment, required_categories, wardrobe_by_category
        )

        # Score and rank combinations
        scored_outfits = []
        for combination in outfit_combinations:
            score_info = self._score_outfit(combination)
            scored_outfits.append((combination, score_info))

        # Sort by overall score (descending)
        scored_outfits.sort(key=lambda x: x[1]["overall_score"], reverse=True)

        # Generate outfit cards for top N
        outfit_cards = []
        for idx, (combination, score_info) in enumerate(scored_outfits[:num_outfits]):
            card = self._create_outfit_card(
                outfit_id=f"outfit_{idx + 1}",
                garments=combination,
                target_garment=target_garment,
                score_info=score_info,
            )
            outfit_cards.append(card)

        logger.info(f"Generated {len(outfit_cards)} outfit recommendations")

        return outfit_cards

    def _group_by_category(self, wardrobe: List[Garment]) -> dict[str, List[Garment]]:
        """Group wardrobe garments by category"""
        grouped = {}
        for garment in wardrobe:
            category = garment.category
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(garment)
        return grouped

    def _generate_combinations(
        self,
        target_garment: Garment,
        required_categories: List[str],
        wardrobe_by_category: dict[str, List[Garment]],
    ) -> List[List[Garment]]:
        """
        Generate all valid outfit combinations

        Args:
            target_garment: Target garment
            required_categories: Required categories to pair with
            wardrobe_by_category: Wardrobe grouped by category

        Returns:
            List[List[Garment]]: List of garment combinations
        """
        combinations = []

        # For simplicity, we'll generate combinations for the first required category
        # In a full implementation, this would handle multiple required categories
        if not required_categories:
            return [[target_garment]]

        primary_category = required_categories[0]
        primary_garments = wardrobe_by_category.get(primary_category, [])

        if not primary_garments:
            logger.warning(f"No garments found in category: {primary_category}")
            return [[target_garment]]

        # Create combinations with each garment from primary category
        for garment in primary_garments[:10]:  # Limit to top 10 to avoid explosion
            combination = [target_garment, garment]

            # Optionally add shoes if available
            if "鞋" in wardrobe_by_category and len(wardrobe_by_category["鞋"]) > 0:
                # Add first matching shoe
                for shoe in wardrobe_by_category["鞋"][:3]:
                    combo_with_shoes = combination + [shoe]
                    combinations.append(combo_with_shoes)

            # Also add combination without shoes
            combinations.append(combination)

        return combinations

    def _score_outfit(self, garments: List[Garment]) -> dict:
        """
        Score an outfit combination

        Args:
            garments: List of garments in outfit

        Returns:
            dict: Score information
        """
        if len(garments) < 2:
            return {
                "color_harmony_score": 0.5,
                "color_harmony_type": "未知",
                "style_consistency": 0.5,
                "overall_score": 0.5,
            }

        # Calculate color harmony (average pairwise scores)
        color_scores = []
        color_types = []

        for i in range(len(garments) - 1):
            color1 = ColorSchema(**garments[i].main_color)
            color2 = ColorSchema(**garments[i + 1].main_color)
            score, harmony_type = self.color_rules.calculate_color_harmony(color1, color2)
            color_scores.append(score)
            color_types.append(harmony_type)

        avg_color_score = sum(color_scores) / len(color_scores) if color_scores else 0.5
        primary_harmony_type = color_types[0] if color_types else "一般搭配"

        # Calculate style consistency (average pairwise scores)
        style_scores = []

        for i in range(len(garments) - 1):
            styles1 = garments[i].style_tags
            styles2 = garments[i + 1].style_tags
            score = self.style_rules.calculate_style_consistency(styles1, styles2)
            style_scores.append(score)

        avg_style_score = sum(style_scores) / len(style_scores) if style_scores else 0.5

        # Calculate overall score (weighted average)
        overall_score = (avg_color_score * 0.5) + (avg_style_score * 0.5)

        return {
            "color_harmony_score": avg_color_score,
            "color_harmony_type": primary_harmony_type,
            "style_consistency": avg_style_score,
            "overall_score": overall_score,
        }

    def _create_outfit_card(
        self,
        outfit_id: str,
        garments: List[Garment],
        target_garment: Garment,
        score_info: dict,
    ) -> OutfitCard:
        """
        Create outfit card from garments and scores

        Args:
            outfit_id: Unique outfit ID
            garments: List of garments in outfit
            target_garment: Target garment
            score_info: Scoring information

        Returns:
            OutfitCard: Complete outfit card
        """
        # Create outfit items
        items = []
        for garment in garments:
            role = self._determine_role(garment, target_garment)
            item = OutfitItem(
                garment_id=garment.garment_id,
                category=garment.category,
                main_color=ColorSchema(**garment.main_color),
                style_tags=garment.style_tags,
                image_url=garment.image_url,
                role=role,
            )
            items.append(item)

        # Determine occasion
        occasion = self._determine_occasion(garments)

        # Generate description
        description = self._generate_description(garments, score_info)

        return OutfitCard(
            outfit_id=outfit_id,
            items=items,
            occasion=occasion,
            description=description,
            color_harmony=score_info["color_harmony_type"],
            color_harmony_score=score_info["color_harmony_score"],
            style_consistency=score_info["style_consistency"],
            overall_score=score_info["overall_score"],
        )

    def _determine_role(self, garment: Garment, target_garment: Garment) -> str:
        """Determine garment role in outfit"""
        if garment.garment_id == target_garment.garment_id:
            return "target"

        category_role_map = {
            "上衣": "top",
            "裤子": "bottom",
            "裙子": "bottom",
            "外套": "outer",
            "鞋": "shoes",
            "包": "bag",
        }

        return category_role_map.get(garment.category, "accessory")

    def _determine_occasion(self, garments: List[Garment]) -> str:
        """Determine recommended occasion based on style tags"""
        # Collect all style tags
        all_styles = []
        for garment in garments:
            all_styles.extend(garment.style_tags)

        if not all_styles:
            return "日常"

        # Count style occurrences
        style_counts = {}
        for style in all_styles:
            style_counts[style] = style_counts.get(style, 0) + 1

        # Find most common style
        most_common_style = max(style_counts, key=style_counts.get)

        # Map to occasion
        return self.OCCASION_MAPPING.get(most_common_style, "日常")

    def _generate_description(self, garments: List[Garment], score_info: dict) -> str:
        """Generate outfit description"""
        if len(garments) < 2:
            return "单品展示"

        # Get color names
        colors = [ColorSchema(**g.main_color).name for g in garments]
        categories = [g.category for g in garments]

        # Build description
        parts = []

        # Describe items
        for i, (color, category) in enumerate(zip(colors, categories)):
            if i == 0:
                parts.append(f"{color}色{category}")
            else:
                parts.append(f"{color}色{category}")

        items_desc = "搭配".join(parts)

        # Add harmony description
        harmony_desc = score_info["color_harmony_type"]

        # Add occasion
        occasion = self._determine_occasion(garments)

        description = f"{items_desc}，{harmony_desc}，适合{occasion}"

        return description
