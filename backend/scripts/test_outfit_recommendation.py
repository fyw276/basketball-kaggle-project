"""
Test outfit recommendation module

This script tests:
1. Color matching rules
2. Style consistency rules
3. Category pairing rules
4. Outfit generation
5. Outfit scoring
6. Complete recommendation flow
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from uuid import uuid4

from app.core.logging import setup_logging
from app.models.garment import Garment
from app.schemas.garment import ColorSchema
from app.services.outfit_recommender import OutfitRecommender
from app.services.outfit_rules import CategoryRules, ColorRules, StyleRules

logger = setup_logging()


def print_header(title):
    """Print formatted header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_section(title):
    """Print formatted section"""
    print(f"\n{title}")
    print("-" * 80)


def test_color_rules():
    """Test color matching rules"""
    print_section("1. Testing Color Matching Rules")

    try:
        rules = ColorRules()
        print("   ✓ ColorRules initialized")

        # Test same color
        color1 = ColorSchema(name="蓝", rgb=(0, 100, 200), hsv=(210, 100, 78), hex_code="#0064c8")
        color2 = ColorSchema(name="蓝", rgb=(0, 100, 200), hsv=(210, 100, 78), hex_code="#0064c8")
        score, harmony_type = rules.calculate_color_harmony(color1, color2)
        print(f"   ✓ Same color: {score:.2f} ({harmony_type})")
        assert score == 1.0 and harmony_type == "同色系"

        # Test neutral color
        color1 = ColorSchema(name="白", rgb=(255, 255, 255), hsv=(0, 0, 100), hex_code="#ffffff")
        color2 = ColorSchema(name="蓝", rgb=(0, 100, 200), hsv=(210, 100, 78), hex_code="#0064c8")
        score, harmony_type = rules.calculate_color_harmony(color1, color2)
        print(f"   ✓ Neutral + color: {score:.2f} ({harmony_type})")
        assert score == 0.9 and harmony_type == "中性色搭配"

        # Test complementary colors
        color1 = ColorSchema(name="红", rgb=(200, 0, 0), hsv=(0, 100, 78), hex_code="#c80000")
        color2 = ColorSchema(name="绿", rgb=(0, 200, 0), hsv=(120, 100, 78), hex_code="#00c800")
        score, harmony_type = rules.calculate_color_harmony(color1, color2)
        print(f"   ✓ Complementary: {score:.2f} ({harmony_type})")
        assert score == 0.85 and harmony_type == "互补色"

        # Test analogous colors
        color1 = ColorSchema(name="红", rgb=(200, 0, 0), hsv=(0, 100, 78), hex_code="#c80000")
        color2 = ColorSchema(name="橙", rgb=(200, 100, 0), hsv=(30, 100, 78), hex_code="#c86400")
        score, harmony_type = rules.calculate_color_harmony(color1, color2)
        print(f"   ✓ Analogous: {score:.2f} ({harmony_type})")
        assert score == 0.8 and harmony_type == "邻近色"

        print("   ✓ All color rule tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_style_rules():
    """Test style consistency rules"""
    print_section("2. Testing Style Consistency Rules")

    try:
        rules = StyleRules()
        print("   ✓ StyleRules initialized")

        # Test exact match
        styles1 = ["通勤", "简约"]
        styles2 = ["通勤", "简约"]
        score = rules.calculate_style_consistency(styles1, styles2)
        print(f"   ✓ Exact match: {score:.2f}")
        assert score == 1.0

        # Test compatible styles
        styles1 = ["通勤"]
        styles2 = ["正式"]
        score = rules.calculate_style_consistency(styles1, styles2)
        print(f"   ✓ Compatible styles: {score:.2f}")
        assert 0.5 < score < 1.0

        # Test incompatible styles
        styles1 = ["运动"]
        styles2 = ["正式"]
        score = rules.calculate_style_consistency(styles1, styles2)
        print(f"   ✓ Incompatible styles: {score:.2f}")
        assert score <= 0.6

        # Test empty styles
        styles1 = []
        styles2 = ["通勤"]
        score = rules.calculate_style_consistency(styles1, styles2)
        print(f"   ✓ Empty styles: {score:.2f}")
        assert score == 0.5

        print("   ✓ All style rule tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_category_rules():
    """Test category pairing rules"""
    print_section("3. Testing Category Pairing Rules")

    try:
        rules = CategoryRules()
        print("   ✓ CategoryRules initialized")

        # Test required categories
        required = rules.get_required_categories("上衣")
        print(f"   ✓ Required for 上衣: {required}")
        assert "裤子" in required or "裙子" in required

        # Test valid outfit
        is_valid = rules.is_valid_outfit(["上衣", "裤子"])
        print(f"   ✓ Valid outfit [上衣, 裤子]: {is_valid}")
        assert is_valid is True

        # Test invalid outfit
        is_valid = rules.is_valid_outfit(["上衣"])
        print(f"   ✓ Invalid outfit [上衣]: {is_valid}")
        assert is_valid is False

        # Test outfit templates
        templates = rules.get_outfit_templates_for_category("上衣")
        print(f"   ✓ Templates for 上衣: {len(templates)} templates")
        assert len(templates) > 0

        print("   ✓ All category rule tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_outfit_recommender():
    """Test outfit recommender"""
    print_section("4. Testing Outfit Recommender")

    try:
        recommender = OutfitRecommender()
        print("   ✓ OutfitRecommender initialized")

        # Create target garment (上衣)
        target = Garment(
            garment_id=uuid4(),
            user_id=uuid4(),
            category="上衣",
            main_color={
                "name": "白",
                "rgb": (255, 255, 255),
                "hsv": (0, 0, 100),
                "hex_code": "#ffffff",
            },
            secondary_colors=[],
            style_tags=["通勤", "简约"],
            fit_type="标准",
            image_path="/path/to/image.jpg",
            image_url="/uploads/image.jpg",
            feature_vector=[0.1] * 1280,
        )
        print("   ✓ Target garment created (白色上衣)")

        # Create wardrobe
        wardrobe = []

        # Add pants
        for i in range(3):
            color_name = ["黑", "蓝", "灰"][i]
            color_rgb = [(0, 0, 0), (0, 100, 200), (128, 128, 128)][i]
            color_hex = ["#000000", "#0064c8", "#808080"][i]

            pants = Garment(
                garment_id=uuid4(),
                user_id=uuid4(),
                category="裤子",
                main_color={
                    "name": color_name,
                    "rgb": color_rgb,
                    "hsv": (0, 0, 0),
                    "hex_code": color_hex,
                },
                secondary_colors=[],
                style_tags=["通勤", "简约"],
                fit_type="标准",
                image_path=f"/path/to/pants{i}.jpg",
                image_url=f"/uploads/pants{i}.jpg",
                feature_vector=[0.1] * 1280,
            )
            wardrobe.append(pants)

        # Add shoes
        shoes = Garment(
            garment_id=uuid4(),
            user_id=uuid4(),
            category="鞋",
            main_color={"name": "黑", "rgb": (0, 0, 0), "hsv": (0, 0, 0), "hex_code": "#000000"},
            secondary_colors=[],
            style_tags=["通勤"],
            fit_type=None,
            image_path="/path/to/shoes.jpg",
            image_url="/uploads/shoes.jpg",
            feature_vector=[0.1] * 1280,
        )
        wardrobe.append(shoes)

        print(f"   ✓ Wardrobe created ({len(wardrobe)} items)")

        # Generate recommendations
        outfits = recommender.recommend_outfits(
            target_garment=target, wardrobe=wardrobe, num_outfits=3
        )

        print(f"   ✓ Generated {len(outfits)} outfit recommendations")

        # Validate outfits
        for idx, outfit in enumerate(outfits):
            print(f"\n   Outfit {idx + 1}:")
            print(f"     - Items: {len(outfit.items)}")
            print(f"     - Occasion: {outfit.occasion}")
            print(
                f"     - Color harmony: {outfit.color_harmony} ({outfit.color_harmony_score:.2f})"
            )
            print(f"     - Style consistency: {outfit.style_consistency:.2f}")
            print(f"     - Overall score: {outfit.overall_score:.2f}")
            print(f"     - Description: {outfit.description}")

            # Validate
            assert len(outfit.items) >= 2
            assert 0 <= outfit.color_harmony_score <= 1
            assert 0 <= outfit.style_consistency <= 1
            assert 0 <= outfit.overall_score <= 1

        print("\n   ✓ All outfit recommender tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_empty_wardrobe():
    """Test with empty wardrobe"""
    print_section("5. Testing Empty Wardrobe Handling")

    try:
        recommender = OutfitRecommender()
        print("   ✓ OutfitRecommender initialized")

        # Create target garment
        target = Garment(
            garment_id=uuid4(),
            user_id=uuid4(),
            category="上衣",
            main_color={
                "name": "白",
                "rgb": (255, 255, 255),
                "hsv": (0, 0, 100),
                "hex_code": "#ffffff",
            },
            secondary_colors=[],
            style_tags=["通勤"],
            fit_type="标准",
            image_path="/path/to/image.jpg",
            image_url="/uploads/image.jpg",
            feature_vector=[0.1] * 1280,
        )

        # Empty wardrobe
        wardrobe = []

        # Generate recommendations
        outfits = recommender.recommend_outfits(
            target_garment=target, wardrobe=wardrobe, num_outfits=3
        )

        print(f"   ✓ Empty wardrobe handled: {len(outfits)} outfits")
        assert len(outfits) == 0

        print("   ✓ Empty wardrobe test passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print_header("OUTFIT RECOMMENDATION MODULE TEST")

    results = {
        "Color Rules": test_color_rules(),
        "Style Rules": test_style_rules(),
        "Category Rules": test_category_rules(),
        "Outfit Recommender": test_outfit_recommender(),
        "Empty Wardrobe": test_empty_wardrobe(),
    }

    # Summary
    print_header("TEST SUMMARY")
    print()
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name:.<50} {status}")

    total = len(results)
    passed = sum(results.values())
    print()
    print(f"  Total: {passed}/{total} tests passed")
    print("=" * 80)

    if all(results.values()):
        print("\n✓ ALL TESTS PASSED")
        print("\nOutfit Recommendation Module Status: READY")
        print("\nNext Steps:")
        print("  1. Test API endpoint with HTTP requests")
        print("  2. Implement suitability scoring (Task 18)")
        print("  3. Core business logic verification (Task 17)")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        print("\nPlease review the failed tests and fix issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
