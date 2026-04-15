"""Category-aware similarity matching utilities.

Provides functions for normalizing clothing categories and determining
search scope based on category compatibility.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SimilarityDecision:
    """Decision on which category group to search for similarity."""

    group: str
    """Category group ('上衣', '下装', '外套', '连衣裙', etc.)"""

    confidence: float
    """Confidence of the category decision (0-1)"""


# Category grouping for similarity matching
SIMILARITY_GROUPS = {
    "上衣": ["T恤", "衬衫", "毛衣", "卫衣"],
    "下装": ["牛仔裤", "休闲裤", "短裤", "紧身裤"],
    "外套": ["夹克", "西装", "风衣", "羽绒服"],
    "连衣裙": ["连衣裙", "短裙"],
    "其他": ["鞋", "帽子", "围巾", "包"],
}

# Reverse mapping: category -> group
CATEGORY_TO_GROUP = {}
for group, categories in SIMILARITY_GROUPS.items():
    for cat in categories:
        CATEGORY_TO_GROUP[cat] = group


def normalize_similarity_category(category: Optional[str]) -> str:
    """Normalize a clothing category to its group for similarity matching.

    Args:
        category: Raw clothing category (e.g., "T恤", "上衣")

    Returns:
        Normalized category group (e.g., "上衣") or "其他" if unknown
    """
    if not category:
        return "其他"

    cat_normalized = str(category).strip()

    # Direct mapping first
    if cat_normalized in CATEGORY_TO_GROUP:
        return CATEGORY_TO_GROUP[cat_normalized]

    # If already a group, return as-is
    if cat_normalized in SIMILARITY_GROUPS:
        return cat_normalized

    # Default
    return "其他"


def is_similarity_category_compatible(group1: str, group2: str) -> bool:
    """Check if two category groups are compatible for similarity matching.

    Args:
        group1: First category group
        group2: Second category group

    Returns:
        True if compatible for similarity search
    """
    # Same group is always compatible
    if group1 == group2:
        return True

    # Define compatible pairs for cross-group matching
    compatible_pairs = {
        ("上衣", "外套"),
        ("下装", "其他"),  # Can match pants with shoes/accessories
    }

    # Check both directions
    if (group1, group2) in compatible_pairs or (group2, group1) in compatible_pairs:
        return True

    return False


def detect_similarity_category(
    image_bytes: Optional[bytes] = None,
    clip_category: Optional[str] = None,
    clip_confidence: float = 0.0,
) -> SimilarityDecision:
    """Detect the category group for similarity search.

    Args:
        image_bytes: Optional raw image data (for future vision-based refinement)
        clip_category: Category detected by CLIP model
        clip_confidence: Confidence score from CLIP (0-1)

    Returns:
        SimilarityDecision with group and confidence
    """
    # Normalize the CLIP category to a group
    group = normalize_similarity_category(clip_category)

    # Use CLIP confidence as decision confidence
    confidence = max(0.0, min(1.0, clip_confidence))

    return SimilarityDecision(group=group, confidence=confidence)
