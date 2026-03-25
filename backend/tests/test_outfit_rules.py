"""
Tests for outfit rules module
Tests color matching, style consistency, and category pairing rules
"""

import pytest

from app.schemas.garment import ColorSchema
from app.services.outfit_rules import CategoryRules, ColorRules, StyleRules


class TestColorRules:
    """Test color matching rules"""

    def test_initialization(self):
        """Test ColorRules initialization"""
        rules = ColorRules()
        assert rules is not None

    def test_same_color_harmony(self):
        """Test harmony score for same colors"""
        rules = ColorRules()
        color1 = ColorSchema(name="蓝", hex_code="#0000ff", rgb=(0, 0, 255), hsv=(240, 100, 100))
        color2 = ColorSchema(name="蓝", hex_code="#0000ff", rgb=(0, 0, 255), hsv=(240, 100, 100))

        score, harmony_type = rules.calculate_color_harmony(color1, color2)

        assert score == 1.0
        assert harmony_type == "同色系"

    def test_neutral_color_harmony(self):
        """Test harmony with neutral colors"""
        rules = ColorRules()
        color1 = ColorSchema(name="黑", hex_code="#000000", rgb=(0, 0, 0), hsv=(0, 0, 0))
        color2 = ColorSchema(name="红", hex_code="#ff0000", rgb=(255, 0, 0), hsv=(0, 100, 100))

        score, harmony_type = rules.calculate_color_harmony(color1, color2)

        assert score == 0.9
        assert harmony_type == "中性色搭配"

    def test_complementary_colors(self):
        """Test complementary color harmony"""
        rules = ColorRules()
        color1 = ColorSchema(name="红", hex_code="#ff0000", rgb=(255, 0, 0), hsv=(0, 100, 100))
        color2 = ColorSchema(name="绿", hex_code="#00ff00", rgb=(0, 255, 0), hsv=(120, 100, 100))

        score, harmony_type = rules.calculate_color_harmony(color1, color2)

        assert score == 0.85
        assert harmony_type == "互补色"

    def test_analogous_colors(self):
        """Test analogous color harmony"""
        rules = ColorRules()
        color1 = ColorSchema(name="红", hex_code="#ff0000", rgb=(255, 0, 0), hsv=(0, 100, 100))
        color2 = ColorSchema(name="橙", hex_code="#ffa500", rgb=(255, 165, 0), hsv=(39, 100, 100))

        score, harmony_type = rules.calculate_color_harmony(color1, color2)

        assert score == 0.8
        assert harmony_type == "邻近色"

    def test_same_family_colors(self):
        """Test same family color harmony using HSV"""
        rules = ColorRules()
        # Two shades of blue with similar hue
        color1 = ColorSchema(name="蓝", hex_code="#0000ff", rgb=(0, 0, 255), hsv=(240, 100, 100))
        color2 = ColorSchema(name="深蓝", hex_code="#00008b", rgb=(0, 0, 139), hsv=(240, 100, 55))

        score, harmony_type = rules.calculate_color_harmony(color1, color2)

        # Should be same family due to similar hue
        assert score >= 0.75

    def test_general_color_pairing(self):
        """Test general color pairing (not special harmony)"""
        rules = ColorRules()
        color1 = ColorSchema(name="黄", hex_code="#ffff00", rgb=(255, 255, 0), hsv=(60, 100, 100))
        color2 = ColorSchema(name="粉", hex_code="#ffc0cb", rgb=(255, 192, 203), hsv=(350, 25, 100))

        score, harmony_type = rules.calculate_color_harmony(color1, color2)

        # Should be general pairing
        assert score == 0.5
        assert harmony_type == "一般搭配"

    def test_get_matching_colors(self):
        """Test getting matching colors for a given color"""
        rules = ColorRules()
        color = ColorSchema(name="红", hex_code="#ff0000", rgb=(255, 0, 0), hsv=(0, 100, 100))

        matching = rules.get_matching_colors(color)

        # Should include the color itself
        assert "红" in matching
        # Should include neutral colors
        assert "黑" in matching
        assert "白" in matching
        # Should include complementary colors
        assert "绿" in matching
        # Should include analogous colors
        assert "橙" in matching or "粉" in matching

    def test_all_neutral_colors_match(self):
        """Test that all neutral colors match with each other"""
        rules = ColorRules()
        neutral_colors = ["黑", "白", "灰", "棕", "米", "卡其"]

        for color_name in neutral_colors:
            color = ColorSchema(name=color_name, hex_code="#000000", rgb=(0, 0, 0), hsv=(0, 0, 0))
            matching = rules.get_matching_colors(color)
            # All neutral colors should be in matching list
            for neutral in neutral_colors:
                assert neutral in matching


class TestStyleRules:
    """Test style consistency rules"""

    def test_initialization(self):
        """Test StyleRules initialization"""
        rules = StyleRules()
        assert rules is not None

    def test_exact_style_match(self):
        """Test perfect style match"""
        rules = StyleRules()
        styles1 = ["通勤", "简约"]
        styles2 = ["通勤", "简约"]

        score = rules.calculate_style_consistency(styles1, styles2)

        assert score == 1.0

    def test_compatible_styles(self):
        """Test compatible styles"""
        rules = StyleRules()
        styles1 = ["通勤"]
        styles2 = ["正式"]

        score = rules.calculate_style_consistency(styles1, styles2)

        # Should be compatible (通勤 and 正式 are compatible)
        assert score > 0.5
        assert score < 1.0

    def test_incompatible_styles(self):
        """Test incompatible styles"""
        rules = StyleRules()
        styles1 = ["运动"]
        styles2 = ["正式"]

        score = rules.calculate_style_consistency(styles1, styles2)

        # Should have low compatibility
        assert score == 0.5  # No compatibility, returns neutral

    def test_empty_styles(self):
        """Test with empty style lists"""
        rules = StyleRules()

        score1 = rules.calculate_style_consistency([], ["通勤"])
        score2 = rules.calculate_style_consistency(["通勤"], [])
        score3 = rules.calculate_style_consistency([], [])

        # All should return neutral score
        assert score1 == 0.5
        assert score2 == 0.5
        assert score3 == 0.5

    def test_multiple_style_matching(self):
        """Test matching with multiple styles"""
        rules = StyleRules()
        styles1 = ["通勤", "简约", "优雅"]
        styles2 = ["正式", "简约"]

        score = rules.calculate_style_consistency(styles1, styles2)

        # Should have high score due to exact match on "简约"
        assert score == 1.0

    def test_get_compatible_styles(self):
        """Test getting compatible styles"""
        rules = StyleRules()
        styles = ["通勤"]

        compatible = rules.get_compatible_styles(styles)

        # Should include original style
        assert "通勤" in compatible
        # Should include compatible styles
        assert "正式" in compatible
        assert "简约" in compatible

    def test_style_compatibility_symmetry(self):
        """Test that style compatibility is symmetric"""
        rules = StyleRules()
        styles1 = ["通勤"]
        styles2 = ["正式"]

        score1 = rules.calculate_style_consistency(styles1, styles2)
        score2 = rules.calculate_style_consistency(styles2, styles1)

        assert score1 == score2

    def test_all_style_combinations(self):
        """Test various style combinations"""
        rules = StyleRules()

        # Test some known compatible pairs
        compatible_pairs = [
            (["通勤"], ["正式"]),
            (["休闲"], ["运动"]),
            (["学院"], ["甜美"]),
            (["简约"], ["优雅"]),
        ]

        for styles1, styles2 in compatible_pairs:
            score = rules.calculate_style_consistency(styles1, styles2)
            assert score > 0.5, f"Expected {styles1} and {styles2} to be compatible"


class TestCategoryRules:
    """Test category pairing rules"""

    def test_initialization(self):
        """Test CategoryRules initialization"""
        rules = CategoryRules()
        assert rules is not None

    def test_get_required_categories_for_top(self):
        """Test required categories for top"""
        rules = CategoryRules()

        required = rules.get_required_categories("上衣")

        assert "裤子" in required or "裙子" in required
        assert len(required) > 0

    def test_get_required_categories_for_bottom(self):
        """Test required categories for bottom"""
        rules = CategoryRules()

        required_pants = rules.get_required_categories("裤子")
        required_skirt = rules.get_required_categories("裙子")

        assert "上衣" in required_pants
        assert "上衣" in required_skirt

    def test_get_optional_categories(self):
        """Test optional categories"""
        rules = CategoryRules()

        optional = rules.get_optional_categories("上衣")

        # Should include accessories
        assert "外套" in optional or "鞋" in optional or "包" in optional

    def test_valid_outfit_basic(self):
        """Test basic valid outfit (top + bottom)"""
        rules = CategoryRules()

        assert rules.is_valid_outfit(["上衣", "裤子"]) is True
        assert rules.is_valid_outfit(["上衣", "裙子"]) is True

    def test_valid_outfit_with_accessories(self):
        """Test valid outfit with accessories"""
        rules = CategoryRules()

        assert rules.is_valid_outfit(["上衣", "裤子", "鞋"]) is True
        assert rules.is_valid_outfit(["上衣", "裙子", "外套"]) is True
        assert rules.is_valid_outfit(["上衣", "裤子", "鞋", "包"]) is True

    def test_invalid_outfit_missing_bottom(self):
        """Test invalid outfit missing bottom"""
        rules = CategoryRules()

        assert rules.is_valid_outfit(["上衣"]) is False
        assert rules.is_valid_outfit(["上衣", "鞋"]) is False

    def test_invalid_outfit_missing_top(self):
        """Test invalid outfit missing top"""
        rules = CategoryRules()

        assert rules.is_valid_outfit(["裤子"]) is False
        assert rules.is_valid_outfit(["裙子", "鞋"]) is False

    def test_invalid_outfit_only_accessories(self):
        """Test invalid outfit with only accessories"""
        rules = CategoryRules()

        assert rules.is_valid_outfit(["鞋"]) is False
        assert rules.is_valid_outfit(["包"]) is False
        assert rules.is_valid_outfit(["鞋", "包"]) is False

    def test_get_outfit_templates_for_category(self):
        """Test getting outfit templates for a category"""
        rules = CategoryRules()

        templates = rules.get_outfit_templates_for_category("上衣")

        # Should return templates containing "上衣"
        assert len(templates) > 0
        for template in templates:
            assert "上衣" in template

    def test_get_complementary_categories(self):
        """Test getting complementary categories"""
        rules = CategoryRules()

        # For top, need bottom
        complementary = rules.get_complementary_categories("上衣")
        assert "裤子" in complementary or "裙子" in complementary

        # For bottom, need top
        complementary = rules.get_complementary_categories("裤子")
        assert "上衣" in complementary

    def test_get_complementary_with_existing(self):
        """Test getting complementary categories with existing items"""
        rules = CategoryRules()

        # Already have top and bottom, might suggest accessories
        complementary = rules.get_complementary_categories("上衣", ["裤子"])

        # Should return empty or accessories since outfit is already valid
        # (depends on implementation - might return empty for complete outfit)
        assert isinstance(complementary, list)

    def test_all_outfit_templates_valid(self):
        """Test that all predefined templates are valid"""
        rules = CategoryRules()

        for template in rules.OUTFIT_TEMPLATES:
            assert rules.is_valid_outfit(template) is True

    def test_outfit_with_outer_layer(self):
        """Test outfit with outer layer"""
        rules = CategoryRules()

        # Outer layer needs both top and bottom
        assert rules.is_valid_outfit(["外套", "上衣", "裤子"]) is True
        assert rules.is_valid_outfit(["外套"]) is False

    def test_category_combinations_coverage(self):
        """Test that all categories have rules defined"""
        rules = CategoryRules()

        categories = ["上衣", "裤子", "裙子", "外套", "鞋", "包"]

        for category in categories:
            assert category in rules.CATEGORY_COMBINATIONS
            rules_for_cat = rules.CATEGORY_COMBINATIONS[category]
            assert "required" in rules_for_cat
            assert "optional" in rules_for_cat


class TestRulesIntegration:
    """Test integration between different rule types"""

    def test_complete_outfit_evaluation(self):
        """Test evaluating a complete outfit with all rules"""
        color_rules = ColorRules()
        style_rules = StyleRules()
        category_rules = CategoryRules()

        # Define a complete outfit
        categories = ["上衣", "裤子", "鞋"]
        colors = [
            ColorSchema(name="白", hex_code="#ffffff", rgb=(255, 255, 255), hsv=(0, 0, 100)),
            ColorSchema(name="黑", hex_code="#000000", rgb=(0, 0, 0), hsv=(0, 0, 0)),
            ColorSchema(name="棕", hex_code="#8b4513", rgb=(139, 69, 19), hsv=(25, 86, 55)),
        ]
        styles = [["简约", "通勤"], ["正式"], ["休闲"]]

        # Check category validity
        assert category_rules.is_valid_outfit(categories) is True

        # Check color harmony
        color_score1, _ = color_rules.calculate_color_harmony(colors[0], colors[1])
        color_score2, _ = color_rules.calculate_color_harmony(colors[1], colors[2])
        assert color_score1 > 0.5  # White and black are neutral
        assert color_score2 > 0.5  # Black and brown work together

        # Check style consistency
        style_score1 = style_rules.calculate_style_consistency(styles[0], styles[1])
        style_score2 = style_rules.calculate_style_consistency(styles[1], styles[2])
        assert style_score1 > 0.5  # 简约/通勤 compatible with 正式
        # style_score2 might be lower (正式 and 休闲 less compatible)

    def test_rules_work_together(self):
        """Test that all rule types can be used together"""
        color_rules = ColorRules()
        style_rules = StyleRules()
        category_rules = CategoryRules()

        # All should be initialized
        assert color_rules is not None
        assert style_rules is not None
        assert category_rules is not None

        # All should have their methods available
        assert hasattr(color_rules, "calculate_color_harmony")
        assert hasattr(style_rules, "calculate_style_consistency")
        assert hasattr(category_rules, "is_valid_outfit")


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_color_rules_with_unknown_colors(self):
        """Test color rules with colors not in predefined lists"""
        rules = ColorRules()
        color1 = ColorSchema(name="未知色", hex_code="#123456", rgb=(18, 52, 86), hsv=(210, 79, 34))
        color2 = ColorSchema(
            name="另一个未知色", hex_code="#654321", rgb=(101, 67, 33), hsv=(30, 67, 40)
        )

        score, harmony_type = rules.calculate_color_harmony(color1, color2)

        # Should still return a valid score
        assert 0.0 <= score <= 1.0
        assert isinstance(harmony_type, str)

    def test_style_rules_with_unknown_styles(self):
        """Test style rules with unknown style tags"""
        rules = StyleRules()
        styles1 = ["未知风格"]
        styles2 = ["另一个未知风格"]

        score = rules.calculate_style_consistency(styles1, styles2)

        # Should return neutral score
        assert score == 0.5

    def test_category_rules_with_unknown_category(self):
        """Test category rules with unknown category"""
        rules = CategoryRules()

        required = rules.get_required_categories("未知品类")
        optional = rules.get_optional_categories("未知品类")

        # Should return empty lists
        assert required == []
        assert optional == []

    def test_very_long_style_lists(self):
        """Test with very long style lists"""
        rules = StyleRules()
        styles1 = ["通勤", "简约", "优雅", "正式", "学院"] * 10
        styles2 = ["休闲", "运动", "街头"] * 10

        score = rules.calculate_style_consistency(styles1, styles2)

        # Should still return valid score
        assert 0.0 <= score <= 1.0

    def test_outfit_with_duplicate_categories(self):
        """Test outfit with duplicate categories"""
        rules = CategoryRules()

        # Multiple tops or bottoms
        result = rules.is_valid_outfit(["上衣", "上衣", "裤子"])

        # Behavior depends on implementation
        # Should either handle gracefully or return False
        assert isinstance(result, bool)
