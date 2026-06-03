"""
Color extraction and recognition module using K-Means clustering
"""

import colorsys
from typing import List, Optional, Tuple, Union

import numpy as np
from PIL import Image

try:
    from sklearn.cluster import KMeans
except Exception:  # pragma: no cover - optional dependency
    KMeans = None

from app.core.logging import setup_logging
from app.schemas.garment import ColorSchema

logger = setup_logging()


# Extended color mapping rules (20+ colors for finer recognition)
# HSV ranges based on colorsys (H: 0-360, S: 0-100, V: 0-100)
STANDARD_COLORS = {
    # Reds / pinks
    "红": {"h_range": (0, 8), "s_min": 50, "v_min": 50},
    "粉": {"h_range": (331, 360), "s_min": 20, "s_max": 80, "v_min": 50},
    "酒红": {"h_range": (0, 10), "s_min": 30, "v_max": 50},
    # Oranges / browns
    "橙": {"h_range": (16, 30), "s_min": 50, "v_min": 50},
    "棕": {"h_range": (16, 30), "s_min": 20, "v_max": 60},
    "米": {"h_range": (31, 50), "s_min": 10, "s_max": 50, "v_min": 55, "v_max": 85},
    "卡其": {"h_range": (31, 55), "s_min": 15, "s_max": 60, "v_min": 45, "v_max": 80},
    # Yellows / greens
    "黄": {"h_range": (31, 60), "s_min": 50, "v_min": 50},
    "绿": {"h_range": (61, 150), "s_min": 30, "v_min": 30},
    "青": {"h_range": (151, 175), "s_min": 40, "v_min": 40},
    "墨绿": {"h_range": (90, 160), "s_min": 30, "v_max": 60},
    # Blues / purples
    "蓝": {"h_range": (176, 240), "s_min": 40, "v_min": 35},
    "藏青": {"h_range": (216, 260), "s_min": 40, "v_max": 55},
    "紫": {"h_range": (261, 310), "s_min": 30, "v_min": 35},
    # Achromatic
    "黑": {"s_max": 30, "v_max": 28},
    "白": {"s_max": 25, "v_min": 75},
    "灰": {"s_max": 30, "v_range": (29, 74)},
    # Special
    "金": {"h_range": (31, 50), "s_min": 40, "v_min": 55, "v_max": 85},
    "银": {"s_max": 15, "v_range": (45, 80)},
}


class ColorExtractor:
    """Extract dominant colors from garment images using K-Means clustering"""

    def __init__(self, n_colors: int = 3, resize_dim: int = 150):
        """
        Initialize color extractor

        Args:
            n_colors: Number of dominant colors to extract
            resize_dim: Resize dimension for faster processing
        """
        self.n_colors = n_colors
        self.resize_dim = resize_dim
        self._kmeans_available = KMeans is not None
        logger.info(
            f"ColorExtractor initialized with n_colors={n_colors}, " f"resize_dim={resize_dim}"
        )

    def extract_colors(self, image: Union[Image.Image, np.ndarray, bytes]) -> List[ColorSchema]:
        """
        Extract dominant colors from image using K-Means clustering

        Args:
            image: PIL Image, numpy array, or bytes

        Returns:
            List[ColorSchema]: List of colors sorted by dominance
        """
        try:
            # Convert to PIL Image if bytes
            if isinstance(image, bytes):
                from io import BytesIO

                image = Image.open(BytesIO(image))
            # Convert to PIL Image if numpy array
            elif isinstance(image, np.ndarray):
                image = Image.fromarray(image.astype("uint8"))

            # Resize image for faster processing
            image_resized = image.resize(
                (self.resize_dim, self.resize_dim), Image.Resampling.BILINEAR
            )

            # Convert to RGB if needed
            if image_resized.mode != "RGB":
                image_resized = image_resized.convert("RGB")

            # Convert to numpy array and reshape to pixels. Product photos often
            # contain large white/light backgrounds; filtering those pixels keeps
            # K-Means focused on the garment instead of the canvas.
            arr = np.array(image_resized)
            pixels_all = arr.reshape(-1, 3)
            pixels = self._select_foreground_pixels(pixels_all)

            pct_by_cluster: Optional[np.ndarray]
            if self._kmeans_available:
                # Apply K-Means clustering
                kmeans = KMeans(n_clusters=self.n_colors, random_state=42, n_init=10)
                kmeans.fit(pixels)

                # Get cluster centers (dominant colors)
                colors_rgb = kmeans.cluster_centers_.astype(int)

                # Calculate color percentages
                labels = kmeans.labels_
                counts = np.bincount(labels, minlength=self.n_colors)
                percentages = counts.astype(np.float64) / float(len(labels))

                # Sort by percentage (descending)
                sorted_indices = np.argsort(percentages)[::-1]
                pct_by_cluster = percentages
            else:
                # Fallback: no sklearn available, use average color as main color.
                logger.warning("sklearn unavailable; using average-color fallback")
                avg = np.mean(pixels, axis=0).astype(int)
                colors_rgb = np.array([avg], dtype=int)
                sorted_indices = [0]
                pct_by_cluster = None

            # Convert to ColorSchema objects
            color_schemas = []
            for idx in sorted_indices:
                rgb = tuple(colors_rgb[idx])
                hsv = self.rgb_to_hsv(rgb)
                color_name = self.map_to_standard_color(rgb)
                hex_code = self.rgb_to_hex(rgb)
                if pct_by_cluster is not None:
                    conf = float(np.clip(pct_by_cluster[int(idx)], 0.0, 1.0))
                else:
                    conf = 0.42

                color_schema = ColorSchema(
                    name=color_name, rgb=rgb, hsv=hsv, hex_code=hex_code, confidence=conf
                )
                color_schemas.append(color_schema)

            logger.debug(
                f"Extracted {len(color_schemas)} colors: " f"{[c.name for c in color_schemas]}"
            )

            return color_schemas

        except Exception as e:
            logger.error(f"Failed to extract colors: {e}")
            raise ValueError(f"Color extraction failed: {e}")

    def _select_foreground_pixels(self, pixels: np.ndarray) -> np.ndarray:
        """Filter likely white/light background pixels before color clustering."""
        if pixels.size == 0:
            return pixels

        pixels_f = pixels.astype(np.float32)
        gray = pixels_f.mean(axis=1)
        chroma = pixels_f.max(axis=1) - pixels_f.min(axis=1)

        # Keep saturated pixels and darker low-chroma fabric. This preserves black,
        # denim, and muted garments while dropping most white product backgrounds.
        mask = (chroma > 18.0) | (gray < 210.0)
        if int(mask.sum()) >= max(80, int(len(pixels) * 0.015)):
            return pixels[mask]

        # Fallback for very light garments: only drop near-pure white background.
        light_bg = (gray > 242.0) & (chroma < 12.0)
        mask = ~light_bg
        if int(mask.sum()) >= max(80, int(len(pixels) * 0.015)):
            return pixels[mask]

        return pixels

    def map_to_standard_color(self, rgb: Tuple[int, int, int]) -> str:
        """
        Map RGB color to a descriptive color name.

        Uses the extended STANDARD_COLORS lookup first, then falls back to
        a HSV-based descriptive name (e.g. "粉红", "墨绿") instead of
        collapsing everything into 10 buckets.

        Args:
            rgb: RGB tuple (0-255)

        Returns:
            str: Descriptive color name (e.g. 红/粉/青/墨绿/藏青/酒红/金 …)
        """
        h, s, v = self.rgb_to_hsv(rgb)

        # ── Dark colours: override hue for very dark values ──────────
        # Dark fabric with low-to-moderate saturation → treat as black
        if v <= 30 and s <= 50:
            return "黑"

        # ── Very low saturation (s <= 15): near-achromatic ───────────
        # For light colours (v > 55), check hue to handle pastels.
        # When s < 10 the hue reading is unreliable for warm/cool bias
        # (lighting can push white toward yellow), so only trust hue at s >= 10.
        if s <= 15:
            if v > 55:
                # 偏蓝 → 浅蓝 / 雾霾蓝 (most reliable even at low s)
                if 190 <= h <= 235:
                    return "浅蓝"
                # 偏红/粉 → 粉色 (only s >= 10 to avoid lighting artifacts)
                if (h >= 335 or h <= 25) and s >= 10:
                    return "粉"
                # 偏绿 → 浅绿
                if 70 <= h <= 155:
                    return "浅绿"
                # 偏青 → 浅青
                if 155 <= h <= 190:
                    return "浅青"
                # 偏紫 → 浅紫
                if 260 <= h <= 320:
                    return "浅紫"
                # 偏黄 → 米色 (only when s >= 12 to avoid lighting artifacts)
                if 30 <= h <= 55 and s >= 12 and v < 92:
                    return "米"
                # v >= 78 and no strong hue bias → 白
                if v >= 78:
                    return "白"
                if v <= 50:
                    return "深灰"
                return "灰"
            elif v <= 50:
                return "深灰"
            else:
                return "灰"

        # ── Low saturation (s <= 40) + high value (浅色衣物处理) ───
        if s <= 40 and v >= 60:
            # 偏黄 → 米色/米黄
            if 30 <= h <= 60:
                return "米"
            # 偏蓝 → 浅蓝/雾霾蓝
            if 180 <= h <= 240:
                return "浅蓝"
            # 偏红 → 粉色 (extended to h=25 for desaturated pinks)
            if h >= 335 or h <= 25:
                return "粉"
            # 偏绿 → 浅绿
            if 80 <= h <= 160:
                return "浅绿"
            # 偏紫 → 浅紫
            if 260 <= h <= 320:
                return "浅紫"
            # 偏青 → 浅青
            if 150 <= h <= 180:
                return "浅青"

        # ── Medium saturation (s <= 60) + high value ──────────────
        if s <= 60 and v >= 60:
            # 偏黄 → 米色/米黄
            if 30 <= h <= 60:
                return "米"
            # 偏蓝 → 浅蓝/雾霾蓝
            if 180 <= h <= 240:
                return "浅蓝"
            # 偏红 → 粉色
            if h >= 335 or h <= 25:
                return "粉"
            # 偏绿 → 浅绿
            if 80 <= h <= 160:
                return "浅绿"
            # 偏紫 → 浅紫
            if 260 <= h <= 320:
                return "浅紫"
            # 偏青 → 浅青
            if 150 <= h <= 180:
                return "浅青"

        # ── Extended STANDARD_COLORS lookup ───────────────────────────
        for color_name, rules in STANDARD_COLORS.items():
            if "h_range" not in rules:
                continue
            h_min, h_max = rules["h_range"]
            s_min = rules.get("s_min", 0)
            s_max = rules.get("s_max", 100)
            v_min = rules.get("v_min", 0)
            v_max = rules.get("v_max", 100)

            if h_min <= h <= h_max and s_min <= s <= s_max and v_min <= v <= v_max:
                return color_name

        # ── HSV-based descriptive fallback (no more "其他") ───────────
        # Hue groups  (wrapping handled by the order)
        if h >= 340 or h <= 15:
            if s < 40:
                return "浅红" if v > 60 else "暗红"
            return "粉红" if s < 70 else "红"

        if h <= 40:
            return "橙红" if h < 25 else "橙"

        if h <= 65:
            return "黄绿" if h > 55 else "黄"

        if h <= 160:
            return "青绿" if h > 140 else "绿"

        if h <= 200:
            return "青" if h > 175 else "蓝绿"

        if h <= 265:
            return "蓝紫" if h > 240 else "蓝"

        if h <= 330:
            return "紫红" if h > 300 else "紫"

        # Should not reach here, but keep as last resort
        return self._describe_by_hsv(h, s, v)

    @staticmethod
    def _describe_by_hsv(h: float, s: float, v: float) -> str:
        """Generate a human-readable colour name from HSV values."""
        # Basic hue name
        if h <= 15 or h >= 345:
            hue_name = "红"
        elif h <= 40:
            hue_name = "橙"
        elif h <= 65:
            hue_name = "黄"
        elif h <= 170:
            hue_name = "绿"
        elif h <= 200:
            hue_name = "青"
        elif h <= 270:
            hue_name = "蓝"
        elif h <= 330:
            hue_name = "紫"
        else:
            hue_name = "红"

        # Saturation / value modifiers
        if s < 30:
            prefix = "灰"
        elif s < 60:
            prefix = "浅"
        elif v < 40:
            prefix = "暗"
        elif v > 80:
            prefix = "亮"
        else:
            prefix = ""

        return f"{prefix}{hue_name}"

    @staticmethod
    def rgb_to_hsv(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
        """
        Convert RGB to HSV color space

        Args:
            rgb: RGB tuple (0-255)

        Returns:
            Tuple[float, float, float]: HSV tuple (H: 0-360, S: 0-100, V: 0-100)
        """
        r, g, b = [x / 255.0 for x in rgb]
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        return (h * 360, s * 100, v * 100)

    @staticmethod
    def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
        """
        Convert RGB to hexadecimal color code

        Args:
            rgb: RGB tuple (0-255)

        Returns:
            str: Hex color code (e.g., "#FF5733")
        """
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def get_main_color(self, image: Union[Image.Image, np.ndarray, bytes]) -> ColorSchema:
        """
        Extract the main (most dominant) color from image

        Args:
            image: PIL Image, numpy array, or bytes

        Returns:
            ColorSchema: Main color
        """
        colors = self.extract_colors(image)
        return colors[0] if colors else None

    def get_secondary_colors(
        self, image: Union[Image.Image, np.ndarray, bytes]
    ) -> List[ColorSchema]:
        """
        Extract secondary colors (excluding main color)

        Args:
            image: PIL Image, numpy array, or bytes

        Returns:
            List[ColorSchema]: Secondary colors
        """
        colors = self.extract_colors(image)
        return colors[1:] if len(colors) > 1 else []
