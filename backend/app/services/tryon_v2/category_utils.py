"""Shared garment category helpers for try-on v2 (lower/upper/skirt routing)."""

from __future__ import annotations

LOWER_KEYWORDS = (
    "bottom",
    "lower",
    "pants",
    "jeans",
    "trousers",
    "shorts",
    "下装",
    "裤子",
    "长裤",
    "短裤",
    "牛仔裤",
    "裤装",
    "裤",
    "牛仔",
)

SKIRT_KEYWORDS = (
    "skirt",
    "dress",
    "overall",
    "裙",
    "连衣裙",
    "裙装",
    "半身裙",
)

TOP_KEYWORDS = (
    "top",
    "upper",
    "shirt",
    "tshirt",
    "t-shirt",
    "hoodie",
    "sweater",
    "jacket",
    "coat",
    "上装",
    "上衣",
    "外套",
    "t恤",
    "毛衣",
    "卫衣",
)

# Modes that should not be the default path for pants / lower garments.
_LOW_QUALITY_MODES_FOR_LOWER = frozenset(
    {
        "stable_fast",
        "paste",
        "blend",
        "strict",
        "balanced",
    }
)


def normalize_category(garment_category: str | None) -> str:
    return (garment_category or "").strip().lower()


def is_lower_garment_category(garment_category: str | None) -> bool:
    """Return True when category refers to pants / bottoms / lower garments."""
    cat = normalize_category(garment_category)
    if not cat:
        return False
    # Exact CatVTON types first.
    if cat in {"lower", "bottom", "pants", "jeans", "trousers", "shorts"}:
        return True
    return any(k in cat for k in LOWER_KEYWORDS)


def is_skirt_garment_category(garment_category: str | None) -> bool:
    cat = normalize_category(garment_category)
    if not cat:
        return False
    if cat in {"skirt", "dress", "overall"}:
        return True
    return any(k in cat for k in SKIRT_KEYWORDS)


def map_to_catvton_cloth_type(garment_category: str | None) -> str:
    """Map API garment_category to CatVTON cloth_type: upper | lower | overall."""
    cat = normalize_category(garment_category)
    if is_lower_garment_category(cat):
        return "lower"
    if is_skirt_garment_category(cat):
        return "overall"
    return "upper"


def prefer_high_quality_mode_for_lower(
    garment_category: str | None,
    mode: str,
    *,
    preferred: str = "detail_fidelity",
) -> str:
    """Force pants/lower away from warp-only / low-quality modes.

    Prefer detail_fidelity (or hybrid) so CatVTON lower is used by default.
    """
    if not is_lower_garment_category(garment_category):
        return mode
    if mode in _LOW_QUALITY_MODES_FOR_LOWER:
        return preferred if preferred in {"detail_fidelity", "hybrid"} else "detail_fidelity"
    return mode
