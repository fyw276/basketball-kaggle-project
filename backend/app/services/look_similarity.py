from collections import Counter
from typing import Any

import numpy as np

from app.services.garment import filter_garments_for_part_role, infer_part_role_from_category
from app.services.look_clip_adapter import LookClipAdapter
from app.services.look_complement import LookComplementService
from app.services.look_parsers import HybridLookParser
from app.services.similarity import SimilarityAnalyzer


class LookSimilarityService:
    def __init__(self, analyzer=None, clip_adapter=None, parser=None, complement_service=None):
        self.analyzer = analyzer or SimilarityAnalyzer(
            high_threshold=0.8,
            medium_threshold=0.5,
            calibration_offset=0.0,
            calibration_power=1.0,
        )
        self.clip_adapter = clip_adapter or LookClipAdapter()
        self.parser = parser or HybridLookParser()
        self.complement_service = complement_service or LookComplementService()

    def analyze_look(
        self,
        image_bytes: bytes,
        wardrobe_garments: list,
        source_type: str = "photo",
        scene_hint: str | None = None,
        include_tryon_candidates: bool = True,
        include_accessories: bool = True,
    ) -> dict:
        parsed = self.parser.parse(image_bytes, source_type=source_type)
        part_results = [
            self.match_part_to_wardrobe(part, wardrobe_garments)
            for part in parsed.parts
            if part.part_role != "full-look"
        ]
        scores = self.score_overall(part_results)
        missing = self.complement_service.infer_missing_categories(
            part_results,
            scene_hint=scene_hint,
            include_accessories=include_accessories,
        )

        return {
            "source_type": parsed.source_type,
            "overall_similarity": scores["overall_similarity"],
            "coverage_score": scores["coverage_score"],
            "style_consistency": scores["style_consistency"],
            "color_harmony": scores["color_harmony"],
            "missing_categories": missing,
            "look_summary": self._build_summary(part_results, scene_hint),
            "parts": part_results,
            "recommended_tryon_candidates": (
                self.build_tryon_candidates(part_results) if include_tryon_candidates else []
            ),
        }

    def match_part_to_wardrobe(self, part, wardrobe_garments: list, top_k: int = 5) -> dict:
        enriched = self.clip_adapter.enrich_part(part)
        part_role = part.part_role or self._infer_role_from_category(enriched.get("category"))
        candidates = self._filter_candidates_by_role(wardrobe_garments, part_role)
        part_feature = list(enriched.get("feature_vector") or [])

        matches: list[dict] = []
        for garment in candidates:
            score = self._similarity(part_feature, getattr(garment, "feature_vector", None) or [])
            matches.append(
                {
                    "garment_id": str(getattr(garment, "garment_id", "")),
                    "name": getattr(garment, "name", None),
                    "category": getattr(garment, "category", ""),
                    "image_url": getattr(garment, "image_url", ""),
                    "similarity_score": score,
                    "match_reason": self._match_reason(score),
                }
            )

        matches.sort(key=lambda item: item["similarity_score"], reverse=True)
        matches = matches[:top_k]
        best = matches[0]["similarity_score"] if matches else 0.0

        return {
            "part_role": part_role,
            "detected_category": enriched.get("category") or "",
            "bbox": part.bbox or [],
            "style_tags": list(enriched.get("style_tags") or []),
            "main_color": enriched.get("main_color"),
            "similarity": best,
            "matched_garments": matches,
        }

    def score_overall(self, part_results: list[dict]) -> dict:
        part_match_score = self._avg([float(p.get("similarity") or 0.0) for p in part_results])
        coverage_score = self._calc_coverage_score(part_results)
        style_consistency = self._calc_style_consistency(part_results)
        color_harmony = self._calc_color_harmony(part_results)
        overall = 0.0
        if coverage_score > 0.0:
            overall = self._calc_overall_similarity(
                part_match_score,
                coverage_score,
                style_consistency,
                color_harmony,
            )
        return {
            "part_match_score": part_match_score,
            "coverage_score": coverage_score,
            "style_consistency": style_consistency,
            "color_harmony": color_harmony,
            "overall_similarity": overall,
        }

    def build_tryon_candidates(self, part_results: list[dict]) -> list[dict]:
        candidates: list[dict] = []
        preferred = {"top": 0, "bottom": 1}
        for part in sorted(part_results, key=lambda p: preferred.get(p.get("part_role"), 99)):
            role = part.get("part_role")
            if role not in preferred:
                continue
            matches = part.get("matched_garments") or []
            if not matches:
                continue
            best = matches[0]
            candidates.append(
                {
                    "part_role": role,
                    "garment_id": best.get("garment_id"),
                    "image_url": best.get("image_url"),
                    "category": best.get("category"),
                    "similarity_score": best.get("similarity_score", 0.0),
                }
            )
        return candidates

    def _filter_candidates_by_role(self, garments: list, part_role: str) -> list:
        filtered = filter_garments_for_part_role(garments, part_role)
        return filtered if filtered else garments

    def _infer_role_from_category(self, category: str | None) -> str:
        return infer_part_role_from_category(category or "")

    def _calc_coverage_score(self, part_results: list[dict]) -> float:
        if not part_results:
            return 0.0
        matched = sum(1 for p in part_results if p.get("matched_garments"))
        return matched / len(part_results)

    def _calc_style_consistency(self, part_results: list[dict]) -> float:
        tag_sets = [set(p.get("style_tags") or []) for p in part_results if p.get("style_tags")]
        if len(tag_sets) <= 1:
            return 1.0 if tag_sets else 0.0
        intersection = set.intersection(*tag_sets)
        union = set.union(*tag_sets)
        return len(intersection) / len(union) if union else 0.0

    def _calc_color_harmony(self, part_results: list[dict]) -> float:
        colors = []
        for part in part_results:
            color = part.get("main_color") or {}
            colors.append(color.get("hex_code") or color.get("name"))
        colors = [c for c in colors if c]
        if not colors:
            return 0.0
        most_common = Counter(colors).most_common(1)[0][1]
        return most_common / len(colors)

    def _calc_overall_similarity(
        self,
        part_match_score: float,
        category_coverage: float,
        style_consistency: float,
        color_harmony: float,
    ) -> float:
        return self._clamp(
            0.40 * part_match_score
            + 0.20 * category_coverage
            + 0.20 * style_consistency
            + 0.20 * color_harmony
        )

    def _similarity(self, first: list[float], second: list[float]) -> float:
        if not first or not second:
            return 0.0
        max_len = max(len(first), len(second))
        f1 = np.array(first + [0.0] * (max_len - len(first)), dtype=float)
        f2 = np.array(second + [0.0] * (max_len - len(second)), dtype=float)
        return self._clamp(self.analyzer.calculate_similarity(f1, f2))

    def _build_summary(self, part_results: list[dict], scene_hint: str | None) -> dict:
        tags: list[str] = []
        colors: list[str] = []
        for part in part_results:
            tags.extend([str(t) for t in part.get("style_tags") or []])
            color = part.get("main_color") or {}
            if color.get("name"):
                colors.append(str(color["name"]))
        return {
            "dominant_style_tags": [t for t, _ in Counter(tags).most_common(5)],
            "dominant_colors": [c for c, _ in Counter(colors).most_common(5)],
            "scene": scene_hint,
        }

    def _match_reason(self, score: float) -> str:
        if score >= 0.8:
            return "high visual similarity"
        if score >= 0.5:
            return "moderate visual similarity"
        return "low visual similarity"

    def _avg(self, values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _clamp(self, value: Any) -> float:
        return max(0.0, min(1.0, float(value or 0.0)))
