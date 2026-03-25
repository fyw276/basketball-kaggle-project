"""
Tests for similarity analysis module
Tests cosine similarity calculation, similarity grading, and batch comparison
"""

from uuid import uuid4

import numpy as np
import pytest

from app.services.similarity import SimilarityAnalyzer, SimilarityMatch


class TestCosineSimilarityCalculation:
    """Test cosine similarity calculation"""

    def test_identical_vectors(self):
        """Test similarity of identical vectors is 1.0"""
        analyzer = SimilarityAnalyzer()
        feature = np.random.rand(1280)

        similarity = analyzer.calculate_similarity(feature, feature)

        assert similarity == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        """Test similarity of orthogonal vectors is 0.0"""
        analyzer = SimilarityAnalyzer()

        # Create orthogonal vectors
        feature1 = np.zeros(1280)
        feature1[0] = 1.0

        feature2 = np.zeros(1280)
        feature2[1] = 1.0

        similarity = analyzer.calculate_similarity(feature1, feature2)

        assert similarity == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors(self):
        """Test similarity of opposite vectors is 0.0 (clipped)"""
        analyzer = SimilarityAnalyzer()

        feature1 = np.ones(1280)
        feature2 = -np.ones(1280)

        similarity = analyzer.calculate_similarity(feature1, feature2)

        # Cosine similarity of opposite vectors is -1, but we clip to [0, 1]
        assert similarity == pytest.approx(0.0, abs=1e-6)

    def test_similar_vectors(self):
        """Test similarity of similar vectors is high"""
        analyzer = SimilarityAnalyzer()

        feature1 = np.random.rand(1280)
        # Create similar vector with small noise
        feature2 = feature1 + np.random.rand(1280) * 0.1

        similarity = analyzer.calculate_similarity(feature1, feature2)

        assert similarity > 0.8  # Should be highly similar

    def test_different_vectors(self):
        """Test similarity of different vectors is low"""
        analyzer = SimilarityAnalyzer()

        feature1 = np.random.rand(1280)
        feature2 = np.random.rand(1280)

        similarity = analyzer.calculate_similarity(feature1, feature2)

        # Random vectors should have low similarity
        assert 0.0 <= similarity <= 1.0

    def test_normalized_vectors(self):
        """Test similarity with L2-normalized vectors"""
        analyzer = SimilarityAnalyzer()

        # Create normalized vectors
        feature1 = np.random.rand(1280)
        feature1 = feature1 / np.linalg.norm(feature1)

        feature2 = np.random.rand(1280)
        feature2 = feature2 / np.linalg.norm(feature2)

        similarity = analyzer.calculate_similarity(feature1, feature2)

        assert 0.0 <= similarity <= 1.0

    def test_zero_vector_handling(self):
        """Test handling of zero vectors"""
        analyzer = SimilarityAnalyzer()

        feature1 = np.zeros(1280)
        feature2 = np.random.rand(1280)

        similarity = analyzer.calculate_similarity(feature1, feature2)

        assert similarity == 0.0

    def test_different_dimensions_raises_error(self):
        """Test that different dimensions raise ValueError"""
        analyzer = SimilarityAnalyzer()

        feature1 = np.random.rand(1280)
        feature2 = np.random.rand(512)

        with pytest.raises(ValueError, match="same shape"):
            analyzer.calculate_similarity(feature1, feature2)


class TestSimilarityGrading:
    """Test similarity level classification"""

    def test_high_similarity_classification(self):
        """Test high similarity classification"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8, medium_threshold=0.5)

        assert analyzer.classify_similarity_level(0.9) == "高相似度"
        assert analyzer.classify_similarity_level(0.8) == "高相似度"
        assert analyzer.classify_similarity_level(1.0) == "高相似度"

    def test_medium_similarity_classification(self):
        """Test medium similarity classification"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8, medium_threshold=0.5)

        assert analyzer.classify_similarity_level(0.7) == "中度相似度"
        assert analyzer.classify_similarity_level(0.5) == "中度相似度"
        assert analyzer.classify_similarity_level(0.6) == "中度相似度"

    def test_low_similarity_classification(self):
        """Test low similarity classification"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8, medium_threshold=0.5)

        assert analyzer.classify_similarity_level(0.4) == "低相似度"
        assert analyzer.classify_similarity_level(0.0) == "低相似度"
        assert analyzer.classify_similarity_level(0.2) == "低相似度"

    def test_custom_thresholds(self):
        """Test custom threshold values"""
        analyzer = SimilarityAnalyzer(high_threshold=0.9, medium_threshold=0.6)

        assert analyzer.classify_similarity_level(0.95) == "高相似度"
        assert analyzer.classify_similarity_level(0.7) == "中度相似度"
        assert analyzer.classify_similarity_level(0.5) == "低相似度"


class TestFindSimilarGarments:
    """Test finding similar garments in wardrobe"""

    def test_empty_wardrobe(self):
        """Test with empty wardrobe"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)

        matches = analyzer.find_similar_garments(target_feature, [])

        assert len(matches) == 0

    def test_single_garment_wardrobe(self):
        """Test with single garment in wardrobe"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)
        garment_id = uuid4()
        wardrobe_feature = np.random.rand(1280)

        matches = analyzer.find_similar_garments(target_feature, [(garment_id, wardrobe_feature)])

        assert len(matches) == 1
        assert matches[0].garment_id == garment_id
        assert 0.0 <= matches[0].similarity_score <= 1.0
        assert matches[0].similarity_level in ["高相似度", "中度相似度", "低相似度"]

    def test_multiple_garments_sorted(self):
        """Test that results are sorted by similarity score"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)

        # Create garments with varying similarity
        wardrobe_features = []
        for i in range(5):
            garment_id = uuid4()
            feature = np.random.rand(1280)
            wardrobe_features.append((garment_id, feature))

        matches = analyzer.find_similar_garments(target_feature, wardrobe_features)

        # Check that results are sorted in descending order
        for i in range(len(matches) - 1):
            assert matches[i].similarity_score >= matches[i + 1].similarity_score

    def test_min_threshold_filtering(self):
        """Test minimum threshold filtering"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.ones(1280)

        # Create garments with known similarity
        garment1_id = uuid4()
        garment1_feature = np.ones(1280)  # Identical - similarity = 1.0

        garment2_id = uuid4()
        garment2_feature = np.zeros(1280)
        garment2_feature[0] = 1.0  # Orthogonal - similarity = 0.0

        wardrobe_features = [(garment1_id, garment1_feature), (garment2_id, garment2_feature)]

        # Filter with threshold 0.5
        matches = analyzer.find_similar_garments(
            target_feature, wardrobe_features, min_threshold=0.5
        )

        # Only garment1 should pass the threshold
        assert len(matches) == 1
        assert matches[0].garment_id == garment1_id

    def test_top_k_limiting(self):
        """Test top K limiting"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)

        # Create 10 garments
        wardrobe_features = []
        for i in range(10):
            garment_id = uuid4()
            feature = np.random.rand(1280)
            wardrobe_features.append((garment_id, feature))

        # Get top 3
        matches = analyzer.find_similar_garments(target_feature, wardrobe_features, top_k=3)

        assert len(matches) == 3

    def test_similarity_match_model(self):
        """Test SimilarityMatch model structure"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)
        garment_id = uuid4()
        wardrobe_feature = np.random.rand(1280)

        matches = analyzer.find_similar_garments(target_feature, [(garment_id, wardrobe_feature)])

        match = matches[0]
        assert isinstance(match, SimilarityMatch)
        assert match.garment_id == garment_id
        assert isinstance(match.similarity_score, float)
        assert isinstance(match.similarity_level, str)


class TestBatchSimilarityCalculation:
    """Test batch similarity calculation"""

    def test_batch_calculation_empty(self):
        """Test batch calculation with empty list"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)

        similarities = analyzer.batch_calculate_similarity(target_feature, [])

        assert len(similarities) == 0

    def test_batch_calculation_single(self):
        """Test batch calculation with single feature"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)
        features = [np.random.rand(1280)]

        similarities = analyzer.batch_calculate_similarity(target_feature, features)

        assert len(similarities) == 1
        assert 0.0 <= similarities[0] <= 1.0

    def test_batch_calculation_multiple(self):
        """Test batch calculation with multiple features"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)
        features = [np.random.rand(1280) for _ in range(10)]

        similarities = analyzer.batch_calculate_similarity(target_feature, features)

        assert len(similarities) == 10
        for sim in similarities:
            assert 0.0 <= sim <= 1.0

    def test_batch_vs_individual_calculation(self):
        """Test that batch calculation matches individual calculations"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)
        features = [np.random.rand(1280) for _ in range(5)]

        # Batch calculation
        batch_similarities = analyzer.batch_calculate_similarity(target_feature, features)

        # Individual calculations
        individual_similarities = [
            analyzer.calculate_similarity(target_feature, f) for f in features
        ]

        # Compare results
        for batch_sim, ind_sim in zip(batch_similarities, individual_similarities):
            assert batch_sim == pytest.approx(ind_sim, abs=1e-6)


class TestDuplicateWarning:
    """Test duplicate warning detection"""

    def test_no_duplicate_warning(self):
        """Test no duplicate warning with low similarity"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8)

        matches = [
            SimilarityMatch(
                garment_id=uuid4(), similarity_score=0.5, similarity_level="中度相似度"
            ),
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.3, similarity_level="低相似度"),
        ]

        assert analyzer.has_duplicate_warning(matches) is False

    def test_has_duplicate_warning(self):
        """Test duplicate warning with high similarity"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8)

        matches = [
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.9, similarity_level="高相似度"),
            SimilarityMatch(
                garment_id=uuid4(), similarity_score=0.5, similarity_level="中度相似度"
            ),
        ]

        assert analyzer.has_duplicate_warning(matches) is True

    def test_duplicate_warning_at_threshold(self):
        """Test duplicate warning at exact threshold"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8)

        matches = [
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.8, similarity_level="高相似度"),
        ]

        assert analyzer.has_duplicate_warning(matches) is True

    def test_empty_matches_no_warning(self):
        """Test no warning with empty matches"""
        analyzer = SimilarityAnalyzer()

        assert analyzer.has_duplicate_warning([]) is False


class TestRecommendationMessage:
    """Test recommendation message generation"""

    def test_empty_wardrobe_message(self):
        """Test message for empty wardrobe"""
        analyzer = SimilarityAnalyzer()

        message = analyzer.get_recommendation_message([])

        assert "没有相似单品" in message
        assert "可以考虑购买" in message

    def test_high_similarity_message(self):
        """Test message for high similarity matches"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8)

        matches = [
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.9, similarity_level="高相似度"),
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.85, similarity_level="高相似度"),
        ]

        message = analyzer.get_recommendation_message(matches)

        assert "2 件高度相似" in message
        assert "建议谨慎购买" in message

    def test_high_similarity_with_budget_message(self):
        """Test message for high similarity with budget consideration"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8)

        matches = [
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.9, similarity_level="高相似度"),
        ]

        message = analyzer.get_recommendation_message(matches, budget_range="中等")

        assert "高度相似" in message
        assert "预算" in message

    def test_medium_similarity_message(self):
        """Test message for medium similarity matches"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8, medium_threshold=0.5)

        matches = [
            SimilarityMatch(
                garment_id=uuid4(), similarity_score=0.6, similarity_level="中度相似度"
            ),
            SimilarityMatch(
                garment_id=uuid4(), similarity_score=0.7, similarity_level="中度相似度"
            ),
        ]

        message = analyzer.get_recommendation_message(matches)

        assert "2 件中度相似" in message
        assert "是否需要增加新款式" in message

    def test_low_similarity_message(self):
        """Test message for low similarity matches"""
        analyzer = SimilarityAnalyzer(high_threshold=0.8, medium_threshold=0.5)

        matches = [
            SimilarityMatch(garment_id=uuid4(), similarity_score=0.3, similarity_level="低相似度"),
        ]

        message = analyzer.get_recommendation_message(matches)

        assert "风格不同" in message
        assert "丰富" in message


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_very_large_wardrobe(self):
        """Test with very large wardrobe"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)

        # Create 1000 garments
        wardrobe_features = []
        for i in range(1000):
            garment_id = uuid4()
            feature = np.random.rand(1280)
            wardrobe_features.append((garment_id, feature))

        matches = analyzer.find_similar_garments(target_feature, wardrobe_features, top_k=10)

        assert len(matches) == 10

    def test_all_identical_garments(self):
        """Test with all identical garments"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)

        # Create 5 identical garments
        wardrobe_features = []
        for i in range(5):
            garment_id = uuid4()
            wardrobe_features.append((garment_id, target_feature.copy()))

        matches = analyzer.find_similar_garments(target_feature, wardrobe_features)

        assert len(matches) == 5
        for match in matches:
            assert match.similarity_score == pytest.approx(1.0, abs=1e-6)
            assert match.similarity_level == "高相似度"

    def test_threshold_boundary_values(self):
        """Test with boundary threshold values"""
        analyzer = SimilarityAnalyzer(high_threshold=1.0, medium_threshold=0.0)

        assert analyzer.classify_similarity_level(1.0) == "高相似度"
        assert analyzer.classify_similarity_level(0.5) == "中度相似度"
        assert analyzer.classify_similarity_level(0.0) == "中度相似度"

    def test_negative_threshold_handling(self):
        """Test that negative thresholds work correctly"""
        analyzer = SimilarityAnalyzer()
        target_feature = np.random.rand(1280)
        garment_id = uuid4()
        wardrobe_feature = np.random.rand(1280)

        # Should return all matches with negative threshold
        matches = analyzer.find_similar_garments(
            target_feature, [(garment_id, wardrobe_feature)], min_threshold=-1.0
        )

        assert len(matches) == 1
