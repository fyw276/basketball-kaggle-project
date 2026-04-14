"""Post-ranking helpers for smart outfit cards.

Implements a lightweight two-stage strategy:
1) metadata prefilter (scene/style overlap)
2) semantic-ish text similarity ranking

This module is dependency-light and safe for local/offline runs.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,}")


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _tokens(text: str) -> List[str]:
    if not text:
        return []
    return [t.strip().lower() for t in TOKEN_PATTERN.findall(text) if t.strip()]


def _bag_cosine(a: Sequence[str], b: Sequence[str]) -> float:
    if not a or not b:
        return 0.0
    ca = Counter(a)
    cb = Counter(b)
    dot = 0.0
    for k, va in ca.items():
        vb = cb.get(k)
        if vb:
            dot += float(va * vb)
    na = math.sqrt(sum(float(v * v) for v in ca.values()))
    nb = math.sqrt(sum(float(v * v) for v in cb.values()))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _card_text(card: Dict[str, Any]) -> str:
    parts: List[str] = []
    parts.append(_norm_text(card.get("scene")))
    parts.append(_norm_text(card.get("description")))
    parts.extend([_norm_text(x) for x in (card.get("style_tags") or [])])
    for item in card.get("items") or []:
        if not isinstance(item, dict):
            continue
        parts.append(_norm_text(item.get("name")))
        parts.append(_norm_text(item.get("category")))
        parts.extend([_norm_text(x) for x in (item.get("style_tags") or [])])
    return " ".join([p for p in parts if p])


def _query_text(
    *,
    scene: str,
    weather_note: str,
    mood: str,
    style_preferences: Iterable[str],
) -> str:
    parts = [
        _norm_text(scene),
        _norm_text(weather_note),
        _norm_text(mood),
    ]
    parts.extend([_norm_text(x) for x in style_preferences])
    return " ".join([p for p in parts if p])


def rerank_outfit_cards(
    cards: List[Dict[str, Any]],
    *,
    preferred_scene: str,
    style_preferences: List[str],
    weather_note: str,
    mood: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    """Rerank outfit cards with metadata prefilter + semantic score.

    Returns at most top_k cards and preserves original cards when signals are weak.
    """
    if not cards:
        return []

    normalized_styles = [_norm_text(x) for x in style_preferences if _norm_text(x)]
    query = _query_text(
        scene=preferred_scene,
        weather_note=weather_note,
        mood=mood,
        style_preferences=normalized_styles,
    )
    query_tokens = _tokens(query)

    with_meta: List[Dict[str, Any]] = []
    for idx, card in enumerate(cards):
        scene = _norm_text(card.get("scene"))
        card_styles = [_norm_text(x) for x in (card.get("style_tags") or []) if _norm_text(x)]

        scene_hit = 1.0 if preferred_scene and _norm_text(preferred_scene) == scene else 0.0
        style_hits = len(set(card_styles) & set(normalized_styles)) if normalized_styles else 0
        style_score = min(1.0, style_hits / 2.0) if normalized_styles else 0.0
        meta_score = 0.65 * scene_hit + 0.35 * style_score

        with_meta.append(
            {
                "idx": idx,
                "card": card,
                "meta_score": float(meta_score),
            }
        )

    # Stage A: prefilter. If at least one card hits metadata, keep only hits.
    prefiltered = [x for x in with_meta if x["meta_score"] > 0.0]
    if not prefiltered:
        prefiltered = with_meta

    # Stage B: semantic ranking on prefiltered subset.
    ranked: List[Dict[str, Any]] = []
    for row in prefiltered:
        card = row["card"]
        sem = _bag_cosine(query_tokens, _tokens(_card_text(card)))
        base_overall = 0.0
        try:
            base_overall = float(card.get("overall_score") or 0.0)
        except Exception:
            base_overall = 0.0
        final = 0.50 * row["meta_score"] + 0.40 * sem + 0.10 * max(0.0, min(1.0, base_overall))
        enriched = dict(card)
        enriched["rerank_score"] = round(final, 4)
        ranked.append({"card": enriched, "final": final, "idx": row["idx"]})

    ranked.sort(key=lambda x: (x["final"], -x["idx"]), reverse=True)
    out = [x["card"] for x in ranked[: max(1, int(top_k))]]

    # Backfill if prefilter narrowed too much.
    if len(out) < min(len(cards), int(top_k)):
        chosen_ids = {id(c) for c in out}
        for card in cards:
            if id(card) in chosen_ids:
                continue
            out.append(card)
            if len(out) >= min(len(cards), int(top_k)):
                break

    return out
