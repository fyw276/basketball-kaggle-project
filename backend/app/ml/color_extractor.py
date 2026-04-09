"""
Color extraction and recognition module using K-Means clustering
"""

import colorsys
from typing import List, Tuple, Union

import numpy as np
from PIL import Image

try:
    from sklearn.cluster import KMeans
except Exception:  # pragma: no cover - optional dependency
    KMeans = None

from app.core.logging import setup_logging
from app.schemas.garment import ColorSchema

logger = setup_logging()


# Standard color mapping rules (10 standard colors)
STANDARD_COLORS = {
    "红": {"h_range": (0, 15), "s_min": 50, "v_min": 50},
    "橙": {"h_range": (16, 30), "s_min": 50, "v_min": 50},
    "黄": {"h_range": (31, 60), "s_min": 50, "v_min": 50},
    "绿": {"h_range": (61, 150), "s_min": 50, "v_min": 50},
    "蓝": {"h_range": (151, 240), "s_min": 50, "v_min": 50},
    "紫": {"h_range": (241, 300), "s_min": 50, "v_min": 50},
    "黑": {"s_max": 30, "v_max": 30},
    "白": {"s_max": 30, "v_min": 70},
    "灰": {"s_max": 30, "v_range": (31, 69)},
    "棕": {"h_range": (16, 30), "s_min": 30, "v_max": 60},
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

            # Convert to numpy array and reshape to pixels
            pixels = np.array(image_resized).reshape(-1, 3)

            if self._kmeans_available:
                # Apply K-Means clustering
                kmeans = KMeans(n_clusters=self.n_colors, random_state=42, n_init=10)
                kmeans.fit(pixels)

                # Get cluster centers (dominant colors)
                colors_rgb = kmeans.cluster_centers_.astype(int)

                # Calculate color percentages
                labels = kmeans.labels_
                counts = np.bincount(labels)
                percentages = counts / len(labels)

                # Sort by percentage (descending)
                sorted_indices = np.argsort(percentages)[::-1]
            else:
                # Fallback: no sklearn available, use average color as main color.
                logger.warning("sklearn unavailable; using average-color fallback")
                avg = np.mean(pixels, axis=0).astype(int)
                colors_rgb = np.array([avg], dtype=int)
                sorted_indices = [0]

            # Convert to ColorSchema objects
            color_schemas = []
            for idx in sorted_indices:
                rgb = tuple(colors_rgb[idx])
                hsv = self.rgb_to_hsv(rgb)
                color_name = self.map_to_standard_color(rgb)
                hex_code = self.rgb_to_hex(rgb)

                color_schema = ColorSchema(name=color_name, rgb=rgb, hsv=hsv, hex_code=hex_code)
                color_schemas.append(color_schema)

            logger.debug(
                f"Extracted {len(color_schemas)} colors: " f"{[c.name for c in color_schemas]}"
            )

            return color_schemas

        except Exception as e:
            logger.error(f"Failed to extract colors: {e}")
            raise ValueError(f"Color extraction failed: {e}")

    def map_to_standard_color(self, rgb: Tuple[int, int, int]) -> str:
        """
        Map RGB color to standard color name (10 categories)

        Args:
            rgb: RGB tuple (0-255)

        Returns:
            str: Standard color name (红/橙/黄/绿/蓝/紫/黑/白/灰/棕)
        """
        h, s, v = self.rgb_to_hsv(rgb)

        # Check achromatic colors first (black/white/gray)
        if s <= 30:
            if v <= 30:
                return "黑"
            elif v >= 70:
                return "白"
            else:
                return "灰"

        # Check chromatic colors
        for color_name, rules in STANDARD_COLORS.items():
            if "h_range" in rules:
                h_min, h_max = rules["h_range"]
                s_min = rules.get("s_min", 0)
                v_min = rules.get("v_min", 0)
                v_max = rules.get("v_max", 100)

                if h_min <= h <= h_max and s >= s_min and v_min <= v <= v_max:
                    return color_name

        # Handle red wrap-around (345-360 degrees)
        if h >= 345:
            if s >= 50 and v >= 50:
                return "红"

        # Default to closest color
        return "其他"

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
