"""Shared garment taxonomy and slot validation helpers."""

from __future__ import annotations

from typing import Iterable, Optional

CATEGORY_TOP = "上衣"
CATEGORY_PANTS = "裤子"
CATEGORY_SKIRT = "裙子"
CATEGORY_OUTER = "外套"
CATEGORY_SHOES = "鞋"
CATEGORY_BAG = "包"

VALID_CATEGORIES = {
    CATEGORY_TOP,
    CATEGORY_PANTS,
    CATEGORY_SKIRT,
    CATEGORY_OUTER,
    CATEGORY_SHOES,
    CATEGORY_BAG,
}

LOWER_CATEGORIES = {CATEGORY_PANTS, CATEGORY_SKIRT}

CATEGORY_SLOT = {
    CATEGORY_TOP: "upper",
    CATEGORY_OUTER: "outer",
    CATEGORY_PANTS: "lower",
    CATEGORY_SKIRT: "lower",
    CATEGORY_SHOES: "shoes",
    CATEGORY_BAG: "bag",
}

VALID_COLORS = {"黑", "白", "灰", "蓝", "粉", "红", "绿", "黄", "棕", "紫", "其他"}

_CATEGORY_ALIASES = {
    CATEGORY_TOP: {
        "top",
        "upper",
        "shirt",
        "tshirt",
        "t-shirt",
        "tee",
        "blouse",
        "sweater",
        "hoodie",
        "上装",
        "上衣",
        "衬衫",
        "t恤",
        "T恤",
        "卫衣",
        "毛衣",
        "针织衫",
        "内搭",
    },
    CATEGORY_PANTS: {
        "bottom",
        "lower",
        "pants",
        "trouser",
        "trousers",
        "jeans",
        "shorts",
        "裤",
        "裤子",
        "长裤",
        "短裤",
        "牛仔裤",
        "休闲裤",
        "西裤",
        "下装",
    },
    CATEGORY_SKIRT: {
        "skirt",
        "dress",
        "onepiece",
        "one-piece",
        "裙",
        "裙子",
        "半身裙",
        "短裙",
        "长裙",
        "连衣裙",
        "马面裙",
    },
    CATEGORY_OUTER: {
        "outer",
        "outerwear",
        "coat",
        "jacket",
        "blazer",
        "cardigan",
        "外套",
        "夹克",
        "大衣",
        "风衣",
        "西装外套",
        "开衫",
    },
    CATEGORY_SHOES: {
        "shoe",
        "shoes",
        "sneaker",
        "sneakers",
        "boot",
        "boots",
        "鞋",
        "鞋子",
        "运动鞋",
        "靴子",
        "凉鞋",
        "高跟鞋",
    },
    CATEGORY_BAG: {
        "bag",
        "bags",
        "handbag",
        "backpack",
        "purse",
        "包",
        "包包",
        "手提包",
        "双肩包",
        "斜挎包",
    },
}


def normalize_category(raw: Optional[str], default: str = CATEGORY_TOP) -> str:
    """Map model/user labels to the six public wardrobe categories."""

    s = (raw or "").strip()
    if not s:
        return default
    if s in VALID_CATEGORIES:
        return s
    low = s.lower()
    for category, aliases in _CATEGORY_ALIASES.items():
        if low in {a.lower() for a in aliases}:
            return category
    if any(k in s for k in ("裤", "下装")):
        return CATEGORY_PANTS
    if any(k in s for k in ("裙", "连衣")):
        return CATEGORY_SKIRT
    if any(k in s for k in ("外套", "夹克", "大衣", "风衣", "开衫")):
        return CATEGORY_OUTER
    if "鞋" in s or "靴" in s:
        return CATEGORY_SHOES
    if "包" in s or "袋" in s:
        return CATEGORY_BAG
    if any(k in s for k in ("衣", "衫", "t恤", "T恤", "卫衣", "毛衣")):
        return CATEGORY_TOP
    return default


def category_slot(category: Optional[str]) -> Optional[str]:
    return CATEGORY_SLOT.get(normalize_category(category, default=""))


def validate_outfit_slots(categories: Iterable[Optional[str]]) -> bool:
    """Reject impossible category mixes before they reach the UI."""

    normalized = [normalize_category(c, default="") for c in categories]
    if any(c not in VALID_CATEGORIES for c in normalized):
        return False
    slots = [CATEGORY_SLOT[c] for c in normalized]
    if slots.count("lower") > 1:
        return False
    return True


def normalize_color_name(raw: Optional[str], default: str = "其他") -> str:
    s = (raw or "").strip()
    if not s:
        return default
    if s in VALID_COLORS:
        return s
    if any(k in s for k in ("粉", "pink")):
        return "粉"
    if any(k in s for k in ("黑", "black")):
        return "黑"
    if any(k in s for k in ("白", "white")):
        return "白"
    if any(k in s for k in ("灰", "gray", "grey")):
        return "灰"
    if any(k in s for k in ("蓝", "blue")):
        return "蓝"
    if any(k in s for k in ("红", "red")):
        return "红"
    if any(k in s for k in ("绿", "green")):
        return "绿"
    if any(k in s for k in ("黄", "yellow")):
        return "黄"
    if any(k in s for k in ("棕", "brown", "咖")):
        return "棕"
    if any(k in s for k in ("紫", "purple")):
        return "紫"
    return default
