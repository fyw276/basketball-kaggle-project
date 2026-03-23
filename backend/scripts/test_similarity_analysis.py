"""
Test similarity analysis module

This script tests:
1. Cosine similarity calculation
2. Similarity level classification
3. Finding similar garments
4. Batch similarity calculation
5. Duplicate warning detection
6. Recommendation message generation
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from uuid import uuid4

import numpy as np

from app.core.logging import setup_logging
from app.services.similarity import SimilarityAnalyzer, SimilarityMatch

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


def test_cosine_similarity():
    """Test cosine similarity calculation"""
    print_section("1. Testing Cosine Similarity Calculation")

    try:
        analyzer = SimilarityAnalyzer()
        print("   ✓ SimilarityAnalyzer initialized")

        # Test case 1: Identical vectors
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([1.0, 0.0, 0.0])
        similarity = analyzer.calculate_similarity(vec1, vec2)
        print(f"   ✓ Identical vectors: {similarity:.4f} (expected: 1.0000)")
        assert abs(similarity - 1.0) < 0.001

        # Test case 2: Orthogonal vectors
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([0.0, 1.0, 0.0])
        similarity = analyzer.calculate_similarity(vec1, vec2)
        print(f"   ✓ Orthogonal vectors: {similarity:.4f} (expected: 0.0000)")
        assert abs(similarity - 0.0) < 0.001

        # Test case 3: Similar vectors
        vec1 = np.array([1.0, 1.0, 0.0])
        vec2 = np.array([1.0, 0.9, 0.1])
        similarity = analyzer.calculate_similarity(vec1, vec2)
        print(f"   ✓ Similar vectors: {similarity:.4f} (expected: ~0.99)")
        assert 0.95 < similarity < 1.0

        # Test case 4: High-dimensional vectors (1280-dim)
        vec1 = np.random.rand(1280)
        vec2 = vec1 + np.random.rand(1280) * 0.1  # Slightly different
        similarity = analyzer.calculate_similarity(vec1, vec2)
        print(f"   ✓ High-dim vectors: {similarity:.4f}")
        assert 0.0 <= similarity <= 1.0

        print("   ✓ All cosine similarity tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_similarity_classification():
    """Test similarity level classification"""
    print_section("2. Testing Similarity Level Classification")

    try:
        analyzer = SimilarityAnalyzer(high_threshold=0.8, medium_threshold=0.5)
        print("   ✓ SimilarityAnalyzer initialized")

        # Test high similarity
        level = analyzer.classify_similarity_level(0.85)
        print(f"   ✓ Score 0.85 → {level} (expected: 高相似度)")
        assert level == "高相似度"

        # Test medium similarity
        level = analyzer.classify_similarity_level(0.65)
        print(f"   ✓ Score 0.65 → {level} (expected: 中度相似度)")
        assert level == "中度相似度"

        # Test low similarity
        level = analyzer.classify_similarity_level(0.35)
        print(f"   ✓ Score 0.35 → {level} (expected: 低相似度)")
        assert level == "低相似度"

        # Test boundary cases
        level = analyzer.classify_similarity_level(0.8)
        print(f"   ✓ Score 0.80 → {level} (boundary: 高相似度)")
        assert level == "高相似度"

        level = analyzer.classify_similarity_level(0.5)
        print(f"   ✓ Score 0.50 → {level} (boundary: 中度相似度)")
        assert level == "中度相似度"

        print("   ✓ All classification tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_find_similar_garments():
    """Test finding similar garments"""
    print_section("3. Testing Find Similar Garments")

    try:
        analyzer = SimilarityAnalyzer()
        print("   ✓ SimilarityAnalyzer initialized")

        # Create target feature
        target_feature = np.random.rand(1280)

        # Create wardrobe features
        wardrobe_features = []
        for i in range(10):
            garment_id = uuid4()
            # Create features with varying similarity
            if i < 2:
                # High similarity
                feature = target_feature + np.random.rand(1280) * 0.1
            elif i < 5:
                # Medium similarity
                feature = target_feature + np.random.rand(1280) * 0.5
            else:
                # Low similarity
                feature = np.random.rand(1280)

            wardrobe_features.append((garment_id, feature))

        print(f"   ✓ Created wardrobe with {len(wardrobe_features)} garments")

        # Find similar garments
        matches = analyzer.find_similar_garments(
            target_feature=target_feature,
            wardrobe_features=wardrobe_features,
            min_threshold=0.3,
        )

        print(f"   ✓ Found {len(matches)} similar garments (threshold: 0.3)")

        # Verify matches are sorted by score
        for i in range(len(matches) - 1):
            assert matches[i].similarity_score >= matches[i + 1].similarity_score

        print("   ✓ Matches are sorted by similarity score")

        # Test top_k parameter
        top_3_matches = analyzer.find_similar_garments(
            target_feature=target_feature,
            wardrobe_features=wardrobe_features,
            min_threshold=0.0,
            top_k=3,
        )

        assert len(top_3_matches) == 3
        print("   ✓ Top-K filtering works (top_k=3)")

        # Test empty wardrobe
        empty_matches = analyzer.find_similar_garments(
            target_feature=target_feature, wardrobe_features=[], min_threshold=0.0
        )

        assert len(empty_matches) == 0
        print("   ✓ Empty wardrobe handled correctly")

        print("   ✓ All find similar garments tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_batch_calculation():
    """Test batch similarity calculation"""
    print_section("4. Testing Batch Similarity Calculation")

    try:
        analyzer = SimilarityAnalyzer()
        print("   ✓ SimilarityAnalyzer initialized")

        # Create target and features
        target_feature = np.random.rand(1280)
        features = [np.random.rand(1280) for _ in range(100)]

        print("   ✓ Created 100 feature vectors")

        # Batch calculation
        import time

        start_time = time.time()
        similarities = analyzer.batch_calculate_similarity(target_feature, features)
        elapsed = time.time() - start_time

        print(f"   ✓ Batch calculation completed in {elapsed:.4f}s")
        print(f"     - Calculated {len(similarities)} similarities")
        print(f"     - Average: {np.mean(similarities):.4f}")
        print(f"     - Min: {np.min(similarities):.4f}")
        print(f"     - Max: {np.max(similarities):.4f}")

        # Verify all scores are in [0, 1]
        assert np.all(similarities >= 0.0) and np.all(similarities <= 1.0)
        print("   ✓ All scores in valid range [0, 1]")

        # Test empty list
        empty_similarities = analyzer.batch_calculate_similarity(target_feature, [])
        assert len(empty_similarities) == 0
        print("   ✓ Empty list handled correctly")

        print("   ✓ All batch calculation tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_duplicate_warning():
    """Test duplicate warning detection"""
    print_section("5. Testing Duplicate Warning Detection")

    try:
        analyzer = SimilarityAnalyzer(high_threshold=0.8)
        print("   ✓ SimilarityAnalyzer initialized")

        # Test with high similarity matches
        high_matches = [
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.85, similarity_level="高相似度"),
            SimilarityMatch(
                garment_id=uuid4(), similarity_score=0.65, similarity_level="中度相似度"
            ),
        ]

        has_duplicate = analyzer.has_duplicate_warning(high_matches)
        print(f"   ✓ High similarity matches → has_duplicate={has_duplicate} (expected: True)")
        assert has_duplicate is True

        # Test with no high similarity
        low_matches = [
            SimilarityMatch(
                garment_id=uuid4(), similarity_score=0.65, similarity_level="中度相似度"
            ),
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.45, similarity_level="低相似度"),
        ]

        has_duplicate = analyzer.has_duplicate_warning(low_matches)
        print(f"   ✓ No high similarity → has_duplicate={has_duplicate} (expected: False)")
        assert has_duplicate is False

        # Test empty matches
        has_duplicate = analyzer.has_duplicate_warning([])
        print(f"   ✓ Empty matches → has_duplicate={has_duplicate} (expected: False)")
        assert has_duplicate is False

        print("   ✓ All duplicate warning tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_recommendation_message():
    """Test recommendation message generation"""
    print_section("6. Testing Recommendation Message Generation")

    try:
        analyzer = SimilarityAnalyzer(high_threshold=0.8, medium_threshold=0.5)
        print("   ✓ SimilarityAnalyzer initialized")

        # Test with high similarity
        high_matches = [
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.85, similarity_level="高相似度"),
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.82, similarity_level="高相似度"),
        ]

        message = analyzer.get_recommendation_message(high_matches, budget_range="中等")
        print(f"   ✓ High similarity message: {message}")
        assert "高度相似" in message or "谨慎购买" in message

        # Test with medium similarity
        medium_matches = [
            SimilarityMatch(
                garment_id=uuid4(), similarity_score=0.65, similarity_level="中度相似度"
            ),
        ]

        message = analyzer.get_recommendation_message(medium_matches)
        print(f"   ✓ Medium similarity message: {message}")
        assert "中度相似" in message

        # Test with no matches
        message = analyzer.get_recommendation_message([])
        print(f"   ✓ No matches message: {message}")
        assert "没有相似单品" in message or "可以考虑购买" in message

        print("   ✓ All recommendation message tests passed")
        return True

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print_header("SIMILARITY ANALYSIS MODULE TEST")

    results = {
        "Cosine Similarity": test_cosine_similarity(),
        "Similarity Classification": test_similarity_classification(),
        "Find Similar Garments": test_find_similar_garments(),
        "Batch Calculation": test_batch_calculation(),
        "Duplicate Warning": test_duplicate_warning(),
        "Recommendation Message": test_recommendation_message(),
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
        print("\nSimilarity Analysis Module Status: READY")
        print("\nNext Steps:")
        print("  1. Test API endpoint with HTTP requests")
        print("  2. Implement outfit recommendation (Task 15-16)")
        print("  3. Implement suitability scoring (Task 18)")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        print("\nPlease review the failed tests and fix issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
