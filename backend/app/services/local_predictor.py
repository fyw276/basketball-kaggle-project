"""Lightweight local predictor used when sklearn training is unavailable."""

from __future__ import annotations

from typing import Any

import numpy as np


class RuleBasedPredictor:
    """A tiny rule-based predictor that mimics a sklearn-like .predict API."""

    _COLOR_GROUP = {
        "黑": "dark",
        "白": "light",
        "灰": "neutral",
        "蓝": "cool",
        "绿": "cool",
        "紫": "cool",
        "红": "warm",
        "橙": "warm",
        "黄": "warm",
        "棕": "earth",
        "米": "earth",
        "卡其": "earth",
    }

    _SEASON_BONUS = {
        "春": 0.2,
        "夏": 0.15,
        "秋": 0.2,
        "冬": 0.25,
    }

    _OCCASION_BONUS = {
        "通勤": 0.2,
        "商务": 0.25,
        "日常": 0.1,
        "休闲": 0.1,
        "约会": 0.2,
        "运动": 0.05,
    }

    def _group(self, color_name: str) -> str:
        name = (color_name or "").strip()
        for key, group in self._COLOR_GROUP.items():
            if key in name:
                return group
        return "other"

    def _season_bonus(self, season: str) -> float:
        s = (season or "").strip()
        for key, bonus in self._SEASON_BONUS.items():
            if key in s:
                return bonus
        return 0.0

    def _occasion_bonus(self, occasion: str) -> float:
        oc = (occasion or "").strip()
        for key, bonus in self._OCCASION_BONUS.items():
            if key in oc:
                return bonus
        return 0.0

    def predict(self, X: Any) -> np.ndarray:
        """Return style scores in [0, 10] for a pandas DataFrame-like object."""
        scores: list[float] = []
        for _, row in X.iterrows():
            top = str(row.get("top", "")).strip()
            bottom = str(row.get("bottom", "")).strip()
            color_top = str(row.get("color_top", "")).strip()
            color_bottom = str(row.get("color_bottom", "")).strip()
            season = str(row.get("season", "")).strip()
            occasion = str(row.get("occasion", "")).strip()

            score = 6.0

            # Color harmony
            g_top = self._group(color_top)
            g_bottom = self._group(color_bottom)
            if g_top == g_bottom and g_top != "other":
                score += 1.4
            elif {g_top, g_bottom} <= {"dark", "light", "neutral", "earth", "cool", "warm"}:
                score += 0.6
            else:
                score -= 0.4

            # Basic category sanity
            if top and bottom:
                score += 0.5
            if any(k in top for k in ("衬", "西", "针织")) and any(
                k in bottom for k in ("西裤", "长裤", "半裙")
            ):
                score += 0.5

            score += self._season_bonus(season)
            score += self._occasion_bonus(occasion)

            scores.append(float(max(0.0, min(10.0, score))))

        return np.array(scores, dtype=float)
