"""Garment classification for try-on routing.

Problem: Skirts and dresses are often misclassified as "upper", causing
wrong routing in CatVTON. This module provides accurate garment type detection.

Supported categories:
- upper: tops, t-shirts, sweaters, jackets
- lower: pants, shorts
- skirt: skirts
- dress: dresses
- outer: coats, jackets (treated like upper)

Usage:
    from app.services.garment_classifier import classify_garment

    category = classify_garment(garment_image)
    # Returns: "upper" | "lower" | "skirt" | "dress" | "outer"
"""

from __future__ import annotations

import numpy as np
from PIL import Image

__all__ = ["classify_garment", "GarmentClassifier"]


# Aspect ratio thresholds for quick heuristic classification
_UPPER_MIN_ASPECT = 0.5  # height/width >= 0.5
_UPPER_MAX_ASPECT = 2.5  # height/width <= 2.5
_LOWER_MIN_ASPECT = 1.2  # height/width >= 1.2 (taller than wide)
_SKIRT_MAX_ASPECT = 0.9  # height/width <= 0.9 (wider than tall)


class GarmentClassifier:
    """
    Garment type classifier combining multiple signals.

    Strategy:
    1. Aspect ratio heuristic (fast, covers 70% of cases)
    2. Color/saturation analysis (dresses often have distinctive patterns)
    3. Shape contour analysis (skirts have wide bottom edge)
    4. CLIP-based classification (if available, for edge cases)
    """

    def __init__(self, use_clip: bool = False):
        self.use_clip = use_clip
        self._clip_model = None

    def _load_clip(self):
        """Lazy-load CLIP model for accurate classification."""
        if self._clip_model is not None:
            return

        try:
            import clip
            
            self._clip_model, self._clip_preprocess = clip.load("ViT-B/32", device="cpu")
        except ImportError:
            self._clip_model = None

    def classify(
        self,
        image: Image.Image,
        user_hint: str | None = None,
    ) -> str:
        """
        Classify a garment image into try-on categories.

        Args:
            image: PIL RGB image of the garment.
            user_hint: Optional user-provided category hint (e.g. "skirt").

        Returns:
            One of: "upper", "lower", "skirt", "dress", "outer"
        """
        w, h = image.size
        aspect = h / max(w, 1)

        # ── Step 1: Aspect ratio heuristic ───────────────────────────────
        cat = self._classify_by_aspect(aspect, w, h, image)
        if cat != "unknown":
            return cat

        # ── Step 2: Color/saturation analysis ───────────────────────────
        cat = self._classify_by_color(image)
        if cat != "unknown":
            return cat

        # ── Step 3: Shape contour analysis ─────────────────────────────
        cat = self._classify_by_shape(image)
        if cat != "unknown":
            return cat

        # ── Step 4: CLIP-based (if available) ─────────────────────────
        if self.use_clip:
            self._load_clip()
            if self._clip_model is not None:
                cat = self._classify_by_clip(image)
                if cat != "unknown":
                    return cat

        # ── Fallback ───────────────────────────────────────────────────
        return "upper"

    def _classify_by_aspect(
        self,
        aspect: float,
        w: int,
        h: int,
        image: Image.Image,
    ) -> str:
        """
        Classify based on aspect ratio and fill ratio.

        - Dresses: tall (aspect 1.5-3.0) and have moderate fill
        - Skirts: wide (aspect 0.4-0.9) and full fill
        - Upper: moderate (aspect 0.8-2.5) and central fill
        - Lower: tall (aspect 1.2-3.0) and narrow fill
        """
        fill_ratio = self._compute_fill_ratio(image)

        if 0.4 <= aspect <= 0.9 and fill_ratio > 0.3:
            # Wide and relatively full → likely skirt
            return "skirt"
        elif 1.5 <= aspect <= 3.5 and fill_ratio > 0.25:
            # Tall and moderate fill → likely dress
            return "dress"
        elif 1.2 <= aspect <= 3.5 and fill_ratio < 0.25:
            # Tall but narrow → likely pants
            return "lower"
        elif 0.8 <= aspect <= 2.5 and fill_ratio > 0.2:
            return "upper"
        return "unknown"

    def _classify_by_color(self, image: Image.Image) -> str:
        """
        Classify by color/saturation patterns.

        Dresses often have continuous color from top to bottom.
        Skirts are often solid colors with visible hem.
        """
        try:
            
            arr = np.array(image.convert("RGB"))
            h, w = arr.shape[:2]

            # Split into top/bottom halves
            mid_y = h // 2
            top = arr[:mid_y]
            bot = arr[mid_y:]

            # Compute saturation for each half
            hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
            sat = hsv[:, :, 1].astype(float) / 255.0
            brightness = hsv[:, :, 2].astype(float) / 255.0

            top_sat = sat[:mid_y].mean()
            bot_sat = sat[mid_y:].mean()
            top_bright = brightness[:mid_y].mean()
            bot_bright = brightness[mid_y:].mean()

            # Check for strapless/halter patterns (dress indicator)
            # Top ~15% of image should be garment, not skin
            top_band = arr[: int(h * 0.12)]
            top_band_sat = top_band.mean(axis=2).std()

            # Dresses: similar color throughout (low top/bottom difference)
            sat_diff = abs(top_sat - bot_sat)
            bright_diff = abs(top_bright - bot_bright)

            if sat_diff < 0.08 and bright_diff < 0.08:
                # Very uniform → likely dress
                return "dress"

            # Skirts: distinctive hem edge (high gradient at hem)
            # Check bottom ~15% for sharp horizontal edge
            bot_region = arr[int(h * 0.80) :]
            gray_bot = bot_region.mean(axis=2)
            grad_y = np.abs(np.gradient(gray_bot.mean(axis=1)))
            if grad_y.max() > 20 and h / max(w, 1) < 1.0:
                return "skirt"

            return "unknown"
        except Exception:
            return "unknown"

    def _classify_by_shape(self, image: Image.Image) -> str:
        """
        Classify by analyzing the garment's outer contour.

        Uses edge detection to find the garment silhouette and
        measures width at different heights.
        """
        try:
            
            arr = np.array(image.convert("RGB"))
            h, w = arr.shape[:2]

            # Detect edges
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 50, 150)

            # For each row, find left/right garment boundary
            widths = []
            for y in range(h // 4, int(h * 0.85), max(1, h // 20)):
                row = edges[y, :]
                edge_positions = np.where(row > 0)[0]
                if len(edge_positions) >= 2:
                    left = edge_positions[0]
                    right = edge_positions[-1]
                    widths.append((y, right - left))

            if len(widths) < 3:
                return "unknown"

            widths.sort()
            y_vals = [w_[0] for w_ in widths]
            w_vals = [w_[1] for w_ in widths]

            # Normalize
            w_norm = np.array(w_vals) / max(w_vals[-1], 1)
            y_norm = np.array(y_vals) / max(y_vals[-1], 1)

            # Check width gradient
            # Skirts: width increases toward bottom (A-line)
            # Dresses: relatively constant then may taper
            # Pants: narrow at top, wider at bottom, then tapers

            # Compute width change from top to bottom
            top_w = w_norm[0]
            mid_w = w_norm[len(w_norm) // 2]
            bot_w = w_norm[-1]

            if bot_w > top_w * 1.3:
                # A-line: wider at bottom → skirt or flared dress
                if h / max(w, 1) < 1.0:
                    return "skirt"
                else:
                    return "dress"
            elif top_w < 0.4 and bot_w > 0.7:
                # Narrow top, wide bottom → pants
                return "lower"
            elif 0.4 <= top_w <= 0.8 and 0.5 <= bot_w <= 0.9:
                # Relatively constant → upper garment or straight dress
                return "upper"

            return "unknown"
        except Exception:
            return "unknown"

    def _classify_by_clip(self, image: Image.Image) -> str:
        """Classify using CLIP."""
        try:
            import clip
            
            if self._clip_model is None:
                return "unknown"

            device = "cuda" if torch.cuda.is_available() else "cpu"
            img = self._clip_preprocess(image).unsqueeze(0).to(device)

            with torch.no_grad():
                img_features = self._clip_model.encode_image(img)

            candidates = [
                "a photo of a shirt or top",
                "a photo of pants or trousers",
                "a photo of a skirt",
                "a photo of a dress",
                "a photo of a jacket or coat",
            ]

            text = clip.tokenize(candidates).to(device)
            with torch.no_grad():
                text_features = self._clip_model.encode_text(text)

            similarity = torch.cosine_similarity(img_features, text_features)
            best_idx = similarity.argmax().item()

            labels = ["upper", "lower", "skirt", "dress", "outer"]
            return labels[best_idx]
        except Exception:
            return "unknown"

    def _compute_fill_ratio(self, image: Image.Image) -> float:
        """Compute how much of the image is filled by the garment."""
        try:
            
            arr = np.array(image.convert("RGB"))
            h, w = arr.shape[:2]

            gray = arr.mean(axis=2)
            sat = arr.max(axis=2) - arr.min(axis=2)

            # Garment pixels: not white background
            fg_mask = ~((gray > 235) & (sat < 15))
            return float(fg_mask.mean())
        except Exception:
            return 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────────────────────────────────────

_classifier: GarmentClassifier | None = None


def classify_garment(
    garment_image: Image.Image,
    user_hint: str | None = None,
) -> str:
    """
    Classify a garment image into try-on category.

    This is the primary entry point for Part 6 of the optimization.

    Args:
        garment_image: PIL RGB image of the garment product photo.
        user_hint: Optional user-provided category string (e.g. "skirt", "dress").
                   If provided and valid, this takes priority.

    Returns:
        One of: "upper" | "lower" | "skirt" | "dress" | "outer"
    """
    global _classifier

    # Use user hint if provided and valid
    if user_hint:
        hint_lower = user_hint.strip().lower()
        # Normalize user hint
        if any(
            k in hint_lower
            for k in ("top", "upper", "上衣", "t恤", "衬衫", "毛衣", "外套", "jacket")
        ):
            return "upper"
        if any(k in hint_lower for k in ("bottom", "lower", "pants", "裤", "短裤", "牛仔裤")):
            return "lower"
        if any(k in hint_lower for k in ("skirt", "裙", "半身裙")):
            return "skirt"
        if any(k in hint_lower for k in ("dress", "连衣裙", "onepiece")):
            return "dress"
        if any(k in hint_lower for k in ("outer", "coat", "外套", "大衣")):
            return "outer"

    # Use classifier
    if _classifier is None:
        _classifier = GarmentClassifier()

    return _classifier.classify(garment_image, user_hint=user_hint)
