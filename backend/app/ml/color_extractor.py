"""Color extraction and recognition for garment images."""

from __future__ import annotations

import colorsys
from io import BytesIO
from typing import List, Optional, Tuple, Union

import numpy as np
from PIL import Image

try:
    from sklearn.cluster import KMeans
except Exception:  # pragma: no cover - optional dependency
    KMeans = None

from app.core.logging import setup_logging
from app.schemas.garment import ColorSchema
from app.services.garment_taxonomy import normalize_color_name

logger = setup_logging()

CHROMATIC_COLOR_NAMES = {"红", "黄", "绿", "蓝", "紫", "粉", "棕"}
NEUTRAL_COLOR_NAMES = {"黑", "白", "灰"}


class ColorExtractor:
    """Extract dominant garment colors with lightweight background suppression."""

    def __init__(self, n_colors: int = 3, resize_dim: int = 150):
        self.n_colors = n_colors
        self.resize_dim = resize_dim
        self._kmeans_available = KMeans is not None
        logger.info(
            "ColorExtractor initialized with n_colors=%s, resize_dim=%s",
            n_colors,
            resize_dim,
        )

    def extract_colors(self, image: Union[Image.Image, np.ndarray, bytes]) -> List[ColorSchema]:
        try:
            pil = self._to_pil(image)
            rgb, alpha = self._resize_rgb_alpha(pil)
            mask = self._garment_pixel_mask(rgb, alpha)
            pixels = rgb[mask]
            if len(pixels) < 64:
                logger.warning("Garment color mask too small; falling back to all image pixels")
                pixels = rgb.reshape(-1, 3)

            colors_rgb, percentages = self._cluster_pixels(pixels)
            return self._to_color_schemas(colors_rgb, percentages)
        except Exception as e:
            logger.error("Failed to extract colors: %s", e)
            raise ValueError(f"Color extraction failed: {e}")

    def _to_pil(self, image: Union[Image.Image, np.ndarray, bytes]) -> Image.Image:
        if isinstance(image, bytes):
            image = Image.open(BytesIO(image))
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image.astype("uint8"))
        if not isinstance(image, Image.Image):
            raise TypeError("image must be PIL Image, numpy array, or bytes")
        return image

    def _resize_rgb_alpha(self, image: Image.Image) -> tuple[np.ndarray, Optional[np.ndarray]]:
        rgba = image.convert("RGBA").resize(
            (self.resize_dim, self.resize_dim),
            Image.Resampling.BILINEAR,
        )
        arr = np.asarray(rgba)
        rgb = arr[:, :, :3].astype(np.uint8)
        alpha = arr[:, :, 3].astype(np.uint8)
        has_alpha = np.any(alpha < 250)
        return rgb, alpha if has_alpha else None

    def _garment_pixel_mask(
        self,
        rgb: np.ndarray,
        alpha: Optional[np.ndarray],
    ) -> np.ndarray:
        if alpha is not None:
            mask = alpha > 16
            if mask.mean() >= 0.03:
                return mask

        h, w, _ = rgb.shape
        corner = max(4, min(h, w) // 8)
        samples = np.concatenate(
            [
                rgb[:corner, :corner].reshape(-1, 3),
                rgb[:corner, -corner:].reshape(-1, 3),
                rgb[-corner:, :corner].reshape(-1, 3),
                rgb[-corner:, -corner:].reshape(-1, 3),
            ],
            axis=0,
        ).astype(np.float32)
        bg = np.median(samples, axis=0)
        dist = np.linalg.norm(rgb.astype(np.float32) - bg.reshape(1, 1, 3), axis=2)

        hsv = self._rgb_array_to_hsv(rgb)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        near_white = (sat < 12.0) & (val > 92.0)

        # Keep pixels that differ from the corner background. Low-saturation white
        # pixels are allowed when they are not background-like, so white shirts still work.
        mask = (dist > 24.0) & ~(near_white & (dist < 42.0))

        # If the image is a clean product cutout on white/black, this catches the
        # garment while dropping screenshot bars and white canvas.
        if mask.mean() < 0.03:
            mask = dist > 16.0
        if mask.mean() < 0.03:
            y, x = np.ogrid[:h, :w]
            cy, cx = h / 2.0, w / 2.0
            central = ((y - cy) / (h * 0.44)) ** 2 + ((x - cx) / (w * 0.44)) ** 2 < 1.0
            mask = central & (val > 4.0)
        return mask

    def _cluster_pixels(self, pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        pixels = pixels.reshape(-1, 3).astype(np.float32)
        if len(pixels) == 0:
            pixels = np.array([[128, 128, 128]], dtype=np.float32)

        unique_count = len(np.unique(pixels.astype(np.uint8), axis=0))
        cluster_count = max(1, min(self.n_colors + 2, unique_count, len(pixels)))
        if self._kmeans_available and cluster_count > 1:
            kmeans = KMeans(n_clusters=cluster_count, random_state=42, n_init=10)
            labels = kmeans.fit_predict(pixels)
            centers = kmeans.cluster_centers_
            counts = np.bincount(labels, minlength=cluster_count).astype(np.float64)
            percentages = counts / max(1.0, counts.sum())
        else:
            centers = np.array([np.mean(pixels, axis=0)], dtype=np.float32)
            percentages = np.array([1.0], dtype=np.float64)
        order = np.argsort(percentages)[::-1]
        return centers[order].astype(int), percentages[order]

    def _to_color_schemas(
        self,
        colors_rgb: np.ndarray,
        percentages: np.ndarray,
    ) -> List[ColorSchema]:
        merged: dict[str, dict[str, object]] = {}
        for rgb_arr, pct in zip(colors_rgb, percentages):
            rgb = tuple(int(np.clip(v, 0, 255)) for v in rgb_arr)
            name = self.map_to_standard_color(rgb)
            slot = merged.setdefault(name, {"weight": 0.0, "rgb": np.zeros(3, dtype=np.float64)})
            slot["weight"] = float(slot["weight"]) + float(pct)
            slot["rgb"] = slot["rgb"] + np.array(rgb, dtype=np.float64) * float(pct)

        merged = self._drop_likely_shadow_black(merged)
        ordered = sorted(merged.items(), key=self._color_sort_key, reverse=True)
        out: List[ColorSchema] = []
        for name, data in ordered:
            weight = max(float(data["weight"]), 1e-6)
            rgb = tuple(int(np.clip(round(v / weight), 0, 255)) for v in data["rgb"])
            out.append(
                ColorSchema(
                    name=name,
                    rgb=rgb,
                    hsv=self.rgb_to_hsv(rgb),
                    hex_code=self.rgb_to_hex(rgb),
                    confidence=float(np.clip(weight, 0.0, 1.0)),
                )
            )
            if len(out) >= self.n_colors:
                break
        return out

    @staticmethod
    def _drop_likely_shadow_black(
        merged: dict[str, dict[str, object]],
    ) -> dict[str, dict[str, object]]:
        black = merged.get("黑")
        if not black:
            return merged

        black_weight = float(black["weight"])
        light_neutral_weight = sum(
            float((merged.get(name) or {}).get("weight", 0.0)) for name in ("白", "灰")
        )
        chromatic_weight = sum(
            float((merged.get(name) or {}).get("weight", 0.0)) for name in CHROMATIC_COLOR_NAMES
        )

        if black_weight <= 0.22 and light_neutral_weight >= 0.30 and chromatic_weight < 0.18:
            filtered = dict(merged)
            filtered.pop("黑", None)
            return filtered
        return merged

    @staticmethod
    def _color_sort_key(item: tuple[str, dict[str, object]]) -> tuple[float, float]:
        name, data = item
        weight = float(data["weight"])
        if name in CHROMATIC_COLOR_NAMES and weight >= 0.08:
            return (3.0, weight)
        if name == "黑" and weight >= 0.12:
            return (2.2, weight)
        if name in CHROMATIC_COLOR_NAMES and weight >= 0.04:
            return (2.0, weight)
        if name in NEUTRAL_COLOR_NAMES:
            return (1.0, weight)
        return (0.0, weight)

    def map_to_standard_color(self, rgb: Tuple[int, int, int]) -> str:
        h, s, v = self.rgb_to_hsv(rgb)
        if s <= 18:
            if v <= 28:
                return "黑"
            if v >= 76:
                return "白"
            return "灰"
        if 345 <= h or h <= 12:
            return "红"
        if 12 < h <= 30:
            return "棕" if v < 72 else "黄"
        if 30 < h <= 62:
            return "黄"
        if 62 < h <= 155:
            return "绿"
        if 155 < h <= 245:
            return "蓝"
        if 245 < h <= 285:
            return "紫"
        if 285 < h < 345:
            return "粉" if v >= 45 else "紫"
        return "其他"

    @staticmethod
    def _rgb_array_to_hsv(rgb: np.ndarray) -> np.ndarray:
        flat = rgb.reshape(-1, 3).astype(np.float32) / 255.0
        out = np.empty((flat.shape[0], 3), dtype=np.float32)
        for i, (r, g, b) in enumerate(flat):
            h, s, v = colorsys.rgb_to_hsv(float(r), float(g), float(b))
            out[i] = (h * 360.0, s * 100.0, v * 100.0)
        return out.reshape(rgb.shape[:2] + (3,))

    @staticmethod
    def rgb_to_hsv(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
        r, g, b = [x / 255.0 for x in rgb]
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        return (h * 360, s * 100, v * 100)

    @staticmethod
    def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def get_main_color(self, image: Union[Image.Image, np.ndarray, bytes]) -> ColorSchema:
        colors = self.extract_colors(image)
        return colors[0] if colors else None

    def get_secondary_colors(
        self, image: Union[Image.Image, np.ndarray, bytes]
    ) -> List[ColorSchema]:
        colors = self.extract_colors(image)
        return colors[1:] if len(colors) > 1 else []

    def normalize_color_name(self, raw: Optional[str], default: str = "其他") -> str:
        return normalize_color_name(raw, default=default)
