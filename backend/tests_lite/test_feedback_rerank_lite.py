"""Lite tests for feedback boost math (no DB)."""

from unittest.mock import MagicMock

from app.services.feedback_prefs import FeedbackRerankContext
from app.services.outfit_recommender_3d import OutfitRecommender3D


def test_feedback_boost_respects_cap():
    eng = OutfitRecommender3D()
    g1 = MagicMock()
    g1.garment_id = "u1"
    g1.style_tags = ["休闲", "简约"]
    g2 = MagicMock()
    g2.garment_id = "u2"
    g2.style_tags = ["休闲"]
    ctx = FeedbackRerankContext(
        liked_garment_ids={"u1", "u2"},
        style_tag_boost={"休闲": 0.05, "简约": 0.02},
    )
    b = eng._feedback_boost_for_combo([g1, g2], ctx)
    assert b <= 0.08
    assert b > 0
