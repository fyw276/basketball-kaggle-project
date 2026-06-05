"""
Outfit recommendation rules engine
Includes color matching, style consistency, and category pairing rules
"""

from typing import List, Set, Tuple

from app.core.logging import setup_logging
from app.schemas.garment import ColorSchema

logger = setup_logging()


class ColorRules:
    """
    Color matching rules for outfit recommendations

    Implements three main color harmony principles:
    1. Monochromatic (同色系): Same color family
    2. Analogous (邻近色): Adjacent colors on color wheel
    3. Complementary (互补色): Opposite colors on color wheel
    """

    # Color wheel mapping (HSV hue values) — extended
    COLOR_WHEEL = {
        "红": (0, 15),
        "粉": (330, 360),
        "橙": (15, 45),
        "黄": (45, 75),
        "绿": (75, 165),
        "青": (165, 195),
        "蓝": (195, 255),
        "紫": (255, 285),
        "紫红": (285, 330),
        # Extended warm/cool groups
        "酒红": (0, 15),
        "粉红": (330, 360),
        "橙红": (10, 25),
        "青绿": (165, 195),
        "蓝绿": (165, 195),
        "藏青": (220, 260),
        "墨绿": (90, 160),
    }

    # Neutral colors (work with everything) — extended
    NEUTRAL_COLORS = {
        "黑",
        "白",
        "灰",
        "深灰",
        "棕",
        "米",
        "卡其",
        "金",
        "银",
        "暗红",
        "浅红",
    }

    # Canonical colour name → list of names to treat as the same base
    # for harmony rules (so "粉红" matches rules for "粉", etc.)
    _COLOR_ALIAS = {
        "粉红": "粉",
        "浅红": "红",
        "暗红": "红",
        "酒红": "红",
        "橙红": "橙",
        "青绿": "青",
        "蓝绿": "青",
        "墨绿": "绿",
        "藏青": "蓝",
        "紫红": "紫",
        "亮": "灰",
        "浅": "灰",
        "暗": "灰",
    }

    def _canonical(self, name: str) -> str:
        """Reduce extended colour names to their harmony-rule base."""
        stripped = name.strip()
        # Try direct alias
        if stripped in self._COLOR_ALIAS:
            return self._COLOR_ALIAS[stripped]
        # Try prefix match (e.g. "亮蓝" → "蓝")
        for alias, base in self._COLOR_ALIAS.items():
            if alias in stripped:
                return base
        return stripped

    # Color harmony rules (use canonical base names internally)
    COMPLEMENTARY_PAIRS = {
        "红": ["绿", "青绿", "蓝绿"],
        "橙": ["蓝", "藏青"],
        "黄": ["紫", "紫红"],
        "绿": ["红", "粉", "粉红"],
        "青": ["橙红", "红"],
        "蓝": ["橙", "黄", "橙红"],
        "紫": ["黄", "青绿"],
        "粉": ["绿", "墨绿"],
    }

    ANALOGOUS_COLORS = {
        "红": ["橙", "粉", "紫", "橙红"],
        "橙": ["红", "黄", "橙红"],
        "黄": ["橙", "绿", "青绿"],
        "绿": ["黄", "青", "蓝"],
        "青": ["绿", "蓝", "蓝绿"],
        "蓝": ["青", "紫", "绿", "藏青"],
        "紫": ["蓝", "红", "粉", "紫红"],
        "粉": ["红", "紫", "粉红"],
    }

    def __init__(self):
        """Initialize color rules"""
        logger.info("ColorRules initialized")

    def calculate_color_harmony(
        self, color1: ColorSchema, color2: ColorSchema
    ) -> Tuple[float, str]:
        """
        Calculate color harmony score between two colors.
        Extended to support free-form colour names via canonical alias mapping.

        Args:
            color1: First color
            color2: Second color

        Returns:
            Tuple[float, str]: (harmony_score [0, 1], harmony_type)
        """
        name1 = self._canonical(color1.name)
        name2 = self._canonical(color2.name)

        # Also keep original names for neutral / same-colour fast paths
        orig1, orig2 = color1.name, color2.name

        # Same colour — perfect harmony
        if orig1 == orig2 or name1 == name2:
            return 1.0, "同色系"

        # Any name containing a neutral keyword → treat as neutral
        neutral_keywords = {"黑", "白", "灰", "深灰", "亮灰", "棕", "米", "卡其", "银", "金"}
        is_neutral = any(k in orig1 for k in neutral_keywords) or any(
            k in orig2 for k in neutral_keywords
        )
        if is_neutral:
            return 0.9, "中性色搭配"

        # Check complementary colours (canonical names)
        if self._is_complementary(name1, name2):
            return 0.85, "互补色"

        # Check analogous colours (canonical names)
        if self._is_analogous(name1, name2):
            return 0.8, "邻近色"

        # Check if colours are in same HSV family (fallback)
        if self._is_same_family(color1, color2):
            return 0.75, "同色系"

        # Default — acceptable but not ideal
        return 0.5, "一般搭配"

    def _is_complementary(self, color1: str, color2: str) -> bool:
        """Check if two colors are complementary"""
        return color2 in self.COMPLEMENTARY_PAIRS.get(
            color1, []
        ) or color1 in self.COMPLEMENTARY_PAIRS.get(color2, [])

    def _is_analogous(self, color1: str, color2: str) -> bool:
        """Check if two colors are analogous"""
        return color2 in self.ANALOGOUS_COLORS.get(
            color1, []
        ) or color1 in self.ANALOGOUS_COLORS.get(color2, [])

    def _is_same_family(self, color1: ColorSchema, color2: ColorSchema) -> bool:
        """Check if two colors are in the same family using HSV"""
        # Extract hue values
        hue1 = color1.hsv[0]
        hue2 = color2.hsv[0]

        # Calculate hue difference (considering circular nature)
        hue_diff = abs(hue1 - hue2)
        if hue_diff > 180:
            hue_diff = 360 - hue_diff

        # Same family if hue difference < 30 degrees
        return hue_diff < 30

    def get_matching_colors(self, color: ColorSchema) -> List[str]:
        """
        Get list of colors that match well with given color

        Args:
            color: Target color

        Returns:
            List[str]: List of matching color names
        """
        color_name = color.name

        matching = set()

        # Add same color
        matching.add(color_name)

        # Add neutral colors (always match)
        matching.update(self.NEUTRAL_COLORS)

        # Add complementary colors
        matching.update(self.COMPLEMENTARY_PAIRS.get(color_name, []))

        # Add analogous colors
        matching.update(self.ANALOGOUS_COLORS.get(color_name, []))

        return list(matching)


class StyleRules:
    """
    Style consistency rules for outfit recommendations

    Ensures that garments in an outfit have compatible style tags
    """

    # Style compatibility matrix
    # Each style maps to compatible styles
    STYLE_COMPATIBILITY = {
        "通勤": ["正式", "简约", "优雅", "学院"],
        "休闲": ["运动", "街头", "简约", "学院"],
        "正式": ["通勤", "优雅", "简约"],
        "运动": ["休闲", "街头", "简约"],
        "街头": ["休闲", "运动", "朋克"],
        "学院": ["通勤", "休闲", "简约", "甜美"],
        "甜美": ["学院", "优雅", "度假"],
        "简约": ["通勤", "休闲", "正式", "学院", "优雅"],
        "复古": ["优雅", "民族"],
        "朋克": ["街头"],
        "民族": ["复古", "度假"],
        "优雅": ["正式", "通勤", "简约", "甜美", "复古"],
        "度假": ["休闲", "甜美", "民族"],
    }

    def __init__(self):
        """Initialize style rules"""
        logger.info("StyleRules initialized")

    def calculate_style_consistency(self, styles1: List[str], styles2: List[str]) -> float:
        """
        Calculate style consistency score between two garments

        Args:
            styles1: Style tags of first garment
            styles2: Style tags of second garment

        Returns:
            float: Consistency score [0, 1]
        """
        if not styles1 or not styles2:
            return 0.5  # Neutral if no style tags

        # Check for exact matches
        common_styles = set(styles1) & set(styles2)
        if common_styles:
            return 1.0  # Perfect match

        # Check for compatible styles
        compatible_count = 0
        total_checks = 0

        for style1 in styles1:
            for style2 in styles2:
                total_checks += 1
                if self._is_compatible(style1, style2):
                    compatible_count += 1

        if total_checks == 0:
            return 0.5

        # Calculate compatibility ratio
        compatibility_ratio = compatible_count / total_checks

        # Scale to [0.5, 0.9] range (never 0 or 1 for different styles)
        return 0.5 + (compatibility_ratio * 0.4)

    def _is_compatible(self, style1: str, style2: str) -> bool:
        """Check if two styles are compatible"""
        return style2 in self.STYLE_COMPATIBILITY.get(
            style1, []
        ) or style1 in self.STYLE_COMPATIBILITY.get(style2, [])

    def get_compatible_styles(self, styles: List[str]) -> Set[str]:
        """
        Get set of styles compatible with given styles

        Args:
            styles: List of style tags

        Returns:
            Set[str]: Set of compatible style tags
        """
        compatible = set(styles)  # Include original styles

        for style in styles:
            compatible.update(self.STYLE_COMPATIBILITY.get(style, []))

        return compatible


class CategoryRules:
    """
    Category pairing rules for outfit recommendations

    Defines which garment categories can be paired together
    """

    # Valid outfit combinations
    # Each category maps to compatible categories for pairing
    CATEGORY_COMBINATIONS = {
        "上衣": {
            "required": ["裤子", "裙子"],  # Must have bottom
            "optional": ["外套", "鞋", "包"],  # Can add these
        },
        "裤子": {
            "required": ["上衣"],  # Must have top
            "optional": ["外套", "鞋", "包"],
        },
        "裙子": {
            "required": ["上衣"],  # Must have top
            "optional": ["外套", "鞋", "包"],
        },
        "外套": {
            "required": ["上衣", "裤子", "裙子"],  # Must have top and bottom
            "optional": ["鞋", "包"],
        },
        "鞋": {
            "required": [],  # Shoes are always optional
            "optional": ["上衣", "裤子", "裙子", "外套", "包"],
        },
        "包": {
            "required": [],  # Bags are always optional
            "optional": ["上衣", "裤子", "裙子", "外套", "鞋"],
        },
    }

    # Outfit templates (category combinations)
    OUTFIT_TEMPLATES = [
        ["上衣", "裤子"],
        ["上衣", "裙子"],
        ["上衣", "裤子", "鞋"],
        ["上衣", "裙子", "鞋"],
        ["上衣", "裤子", "外套"],
        ["上衣", "裙子", "外套"],
        ["上衣", "裤子", "外套", "鞋"],
        ["上衣", "裙子", "外套", "鞋"],
        ["上衣", "裤子", "鞋", "包"],
        ["上衣", "裙子", "鞋", "包"],
    ]

    def __init__(self):
        """Initialize category rules"""
        logger.info("CategoryRules initialized")

    def get_required_categories(self, target_category: str) -> List[str]:
        """
        Get required categories to pair with target category

        Args:
            target_category: Target garment category

        Returns:
            List[str]: List of required categories
        """
        rules = self.CATEGORY_COMBINATIONS.get(target_category, {})
        return rules.get("required", [])

    def get_optional_categories(self, target_category: str) -> List[str]:
        """
        Get optional categories that can be added

        Args:
            target_category: Target garment category

        Returns:
            List[str]: List of optional categories
        """
        rules = self.CATEGORY_COMBINATIONS.get(target_category, {})
        return rules.get("optional", [])

    def is_valid_outfit(self, categories: List[str]) -> bool:
        """
        Check if category combination forms a valid outfit

        Args:
            categories: List of garment categories

        Returns:
            bool: True if valid outfit
        """
        category_set = set(categories)

        # Check against templates
        for template in self.OUTFIT_TEMPLATES:
            if category_set == set(template):
                return True

        # Check basic rules
        # Must have at least top and bottom (or dress equivalent)
        has_top = "上衣" in category_set or "外套" in category_set
        has_bottom = "裤子" in category_set or "裙子" in category_set

        return has_top and has_bottom

    def get_outfit_templates_for_category(self, target_category: str) -> List[List[str]]:
        """
        Get outfit templates that include the target category

        Args:
            target_category: Target garment category

        Returns:
            List[List[str]]: List of outfit templates
        """
        return [template for template in self.OUTFIT_TEMPLATES if target_category in template]

    def get_complementary_categories(
        self, target_category: str, existing_categories: List[str] = None
    ) -> List[str]:
        """
        Get categories needed to complete an outfit

        Args:
            target_category: Target garment category
            existing_categories: Already selected categories

        Returns:
            List[str]: List of complementary categories
        """
        if existing_categories is None:
            existing_categories = []

        existing_set = set(existing_categories + [target_category])

        # Find the simplest valid template
        for template in self.OUTFIT_TEMPLATES:
            template_set = set(template)
            if target_category in template_set:
                # Check what's missing
                missing = template_set - existing_set
                if missing:
                    return list(missing)

        return []
