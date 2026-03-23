"""
Test script for color suitability scoring functionality.

This script demonstrates the color scoring feature by testing various
color and skin tone combinations.
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.schemas.garment import ColorSchema
from app.services.suitability_scorer import SuitabilityScorer


def main():
    """Test color scoring with various combinations"""
    scorer = SuitabilityScorer()

    print("=" * 80)
    print("颜色适合度评分测试")
    print("=" * 80)
    print()

    # Test cases: (color_name, rgb, skin_tone)
    test_cases = [
        ("蓝色", (0, 100, 200), "冷白", "高分预期"),
        ("黄色", (255, 255, 0), "冷白", "低分预期"),
        ("绿色", (0, 150, 50), "冷白", "中分预期"),
        ("蓝色", (0, 100, 200), "黄皮", "高分预期"),
        ("橙色", (255, 165, 0), "黄皮", "低分预期"),
        ("白色", (255, 255, 255), "小麦", "高分预期"),
        ("黄色", (255, 255, 0), "小麦", "低分预期"),
        ("白色", (255, 255, 255), "深色", "高分预期"),
        ("黑色", (0, 0, 0), "深色", "低分预期"),
    ]

    for color_name, rgb, skin_tone, expected in test_cases:
        # Create color schema
        color = ColorSchema(
            name=color_name,
            rgb=rgb,
            hsv=(0, 0, 0),  # Simplified for demo
            hex_code=f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}",
        )

        # Calculate score
        score, explanation = scorer._color_score(color, [], skin_tone)

        # Display result
        print(f"测试: {color_name} + {skin_tone} ({expected})")
        print(f"  评分: {score}/100")
        print(f"  说明: {explanation}")
        print()

    # Test with secondary colors
    print("-" * 80)
    print("测试辅助色影响")
    print("-" * 80)
    print()

    main_color = ColorSchema(name="绿色", rgb=(0, 150, 50), hsv=(140, 100, 59), hex_code="#009632")
    secondary_colors = [
        ColorSchema(name="蓝色", rgb=(0, 100, 200), hsv=(210, 100, 78), hex_code="#0064c8"),
        ColorSchema(name="紫色", rgb=(128, 0, 128), hsv=(300, 100, 50), hex_code="#800080"),
    ]

    score_without = scorer._color_score(main_color, [], "冷白")[0]
    score_with, explanation_with = scorer._color_score(main_color, secondary_colors, "冷白")

    print("主色: 绿色 (冷白肤色)")
    print(f"  仅主色评分: {score_without}/100")
    print(f"  含辅助色评分: {score_with}/100")
    print(f"  说明: {explanation_with}")
    print()

    print("=" * 80)
    print("测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    main()
