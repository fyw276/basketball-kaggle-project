"""
Similarity analysis service
Calculates similarity between garments using cosine similarity
"""

from typing import List, Tuple
from uuid import UUID

import numpy as np
from pydantic import BaseModel, Field

from app.core.logging import setup_logging

logger = setup_logging()


class SimilarityMatch(BaseModel):
    """Similarity match result"""

    garment_id: UUID = Field(..., description="Garment ID")
    similarity_score: float = Field(..., ge=0, le=1, description="Similarity score [0, 1]")
    similarity_level: str = Field(..., description="Similarity level: 高相似度/中度相似度/低相似度")

    class Config:
        json_schema_extra = {
            "example": {
                "garment_id": "123e4567-e89b-12d3-a456-426614174000",
                "similarity_score": 0.85,
                "similarity_level": "高相似度",
            }
        }


class SimilarityAnalyzer:
    """
    Similarity analyzer for garment comparison

    Uses cosine similarity to compare feature vectors and identify
    similar garments in the wardrobe.
    """

    def __init__(
        self,
        high_threshold: float = 0.86,
        medium_threshold: float = 0.65,
        calibration_offset: float = 0.08,
        calibration_power: float = 1.1,
    ):
        """
        Initialize similarity analyzer

        Args:
            high_threshold: Threshold for high similarity (default: 0.8)
            medium_threshold: Threshold for medium similarity (default: 0.5)
        """
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.calibration_offset = max(0.0, min(0.4, calibration_offset))
        self.calibration_power = max(1.0, min(1.6, calibration_power))

        logger.info(
            f"SimilarityAnalyzer initialized with thresholds: "
            f"high={high_threshold}, medium={medium_threshold}"
        )

    def calculate_similarity(self, feature1: np.ndarray, feature2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two feature vectors

        Cosine similarity formula:
        similarity = (A · B) / (||A|| * ||B||)

        Args:
            feature1: First feature vector (1280-dim)
            feature2: Second feature vector (1280-dim)

        Returns:
            float: Cosine similarity score [0, 1]

        Raises:
            ValueError: If feature vectors have different dimensions
        """
        # Validate input
        if feature1.shape != feature2.shape:
            raise ValueError(
                f"Feature vectors must have same shape. "
                f"Got {feature1.shape} and {feature2.shape}"
            )

        # Ensure vectors are 1D
        feature1 = feature1.flatten()
        feature2 = feature2.flatten()

        # Calculate cosine similarity
        # Using numpy's dot product and norm functions
        dot_product = np.dot(feature1, feature2)
        norm1 = np.linalg.norm(feature1)
        norm2 = np.linalg.norm(feature2)

        # Avoid division by zero
        if norm1 == 0 or norm2 == 0:
            logger.warning("One or both feature vectors have zero norm")
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # Clip to [0, 1] range (cosine similarity can be [-1, 1])
        # but for normalized feature vectors, it should be [0, 1]
        similarity = np.clip(similarity, 0.0, 1.0)

        # Calibrate raw cosine scores to suppress optimistic high-similarity
        # labels when visual overlap is weak.
        if self.calibration_offset > 0:
            similarity = max(0.0, float(similarity) - self.calibration_offset)
            similarity = similarity / (1.0 - self.calibration_offset)
        if self.calibration_power > 1.0:
            similarity = float(similarity) ** self.calibration_power
        similarity = np.clip(similarity, 0.0, 1.0)

        logger.debug(f"Calculated similarity: {similarity:.4f}")

        return float(similarity)

    def classify_similarity_level(self, similarity_score: float) -> str:
        """
        Classify similarity score into levels

        Args:
            similarity_score: Similarity score [0, 1]

        Returns:
            str: Similarity level (高相似度/中度相似度/低相似度)
        """
        if similarity_score >= self.high_threshold:
            return "高相似度"
        elif similarity_score >= self.medium_threshold:
            return "中度相似度"
        else:
            return "低相似度"

    def find_similar_garments(
        self,
        target_feature: np.ndarray,
        wardrobe_features: List[Tuple[UUID, np.ndarray]],
        min_threshold: float = 0.0,
        top_k: int = None,
    ) -> List[SimilarityMatch]:
        """
        Find similar garments in wardrobe

        Args:
            target_feature: Target garment feature vector
            wardrobe_features: List of (garment_id, feature_vector) tuples
            min_threshold: Minimum similarity threshold (default: 0.0)
            top_k: Return top K similar garments (default: None, return all)

        Returns:
            List[SimilarityMatch]: List of similarity matches, sorted by score (descending)
        """
        if not wardrobe_features:
            logger.info("Wardrobe is empty, no similar garments found")
            return []

        logger.info(f"Finding similar garments in wardrobe of {len(wardrobe_features)} items")

        matches = []

        for garment_id, feature in wardrobe_features:
            try:
                # Calculate similarity
                similarity_score = self.calculate_similarity(target_feature, feature)

                # Filter by threshold
                if similarity_score >= min_threshold:
                    similarity_level = self.classify_similarity_level(similarity_score)

                    match = SimilarityMatch(
                        garment_id=garment_id,
                        similarity_score=similarity_score,
                        similarity_level=similarity_level,
                    )
                    matches.append(match)

            except Exception as e:
                logger.error(f"Failed to calculate similarity for garment {garment_id}: {e}")
                continue

        # Sort by similarity score (descending)
        matches.sort(key=lambda x: x.similarity_score, reverse=True)

        # Return top K if specified
        if top_k is not None:
            matches = matches[:top_k]

        logger.info(f"Found {len(matches)} similar garments " f"(threshold: {min_threshold:.2f})")

        return matches

    def batch_calculate_similarity(
        self,
        target_feature: np.ndarray,
        features: List[np.ndarray],
    ) -> np.ndarray:
        """
        Calculate similarity between target and multiple features (optimized)

        Args:
            target_feature: Target feature vector (1280-dim)
            features: List of feature vectors

        Returns:
            np.ndarray: Array of similarity scores
        """
        if not features:
            return np.array([])

        # Stack features into matrix
        features_matrix = np.stack(features)

        # Normalize target feature
        target_norm = target_feature / np.linalg.norm(target_feature)

        # Normalize all features
        features_norms = features_matrix / np.linalg.norm(features_matrix, axis=1, keepdims=True)

        # Calculate dot products (cosine similarity for normalized vectors)
        similarities = np.dot(features_norms, target_norm)

        # Clip to [0, 1]
        similarities = np.clip(similarities, 0.0, 1.0)

        # Apply the same calibration used by calculate_similarity so batch
        # results stay numerically consistent with individual comparisons.
        if self.calibration_offset > 0:
            similarities = np.maximum(0.0, similarities - self.calibration_offset)
            similarities = similarities / (1.0 - self.calibration_offset)
        if self.calibration_power > 1.0:
            similarities = np.power(similarities, self.calibration_power)
        similarities = np.clip(similarities, 0.0, 1.0)

        return similarities

    def average_similarity_scores(self, scores: List[float]) -> float:
        """Average bounded similarity scores, returning 0 for empty input."""
        if not scores:
            return 0.0
        clipped = [max(0.0, min(1.0, float(score))) for score in scores]
        return sum(clipped) / len(clipped)

    def has_duplicate_warning(self, matches: List[SimilarityMatch]) -> bool:
        """
        Check if there are high similarity matches (duplicate warning)

        Args:
            matches: List of similarity matches

        Returns:
            bool: True if any match has high similarity
        """
        return any(match.similarity_score >= self.high_threshold for match in matches)

    def get_recommendation_message(
        self, matches: List[SimilarityMatch], budget_range: str = None
    ) -> str:
        """
        Generate recommendation message based on similarity matches

        Args:
            matches: List of similarity matches
            budget_range: User's budget range (optional)

        Returns:
            str: Recommendation message
        """
        if not matches:
            return "您的衣橱中没有相似单品，可以考虑购买。"

        # Check for high similarity
        high_similarity_count = sum(1 for m in matches if m.similarity_score >= self.high_threshold)

        if high_similarity_count > 0:
            message = f"您的衣橱中已有 {high_similarity_count} 件高度相似的单品，建议谨慎购买。"

            if budget_range and budget_range in ["低", "中等"]:
                message += "考虑到您的预算，建议优先搭配现有单品。"

            return message

        # Check for medium similarity
        medium_similarity_count = sum(
            1 for m in matches if self.medium_threshold <= m.similarity_score < self.high_threshold
        )

        if medium_similarity_count > 0:
            return (
                f"您的衣橱中有 {medium_similarity_count} 件中度相似的单品，"
                "可以考虑是否需要增加新款式。"
            )

        return "这件单品与您现有衣橱风格不同，可以丰富您的搭配选择。"
