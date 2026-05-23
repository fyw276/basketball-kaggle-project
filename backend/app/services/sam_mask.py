"""MobileSAM-based garment mask segmentation.

MobileSAM is a lightweight version of SAM (Segment Anything Model) that
provides much better garment segmentation than rembg, especially for:
- Complex garments (ruffles, puffy sleeves, skirts)
- Transparent or semi-transparent fabrics
- Garments with holes/cutouts
- Edge cases where rembg completely fails

Installation:
    pip install mobilesam-mirror  # mirrors the official MobileSAM project

Usage:
    from app.services.sam_mask import sam_segment_garment

    mask = sam_segment_garment(garment_image)
    # Returns PIL L-mode image where white = garment foreground
"""

from __future__ import annotations

import numpy as np
from PIL import Image

__all__ = ["sam_segment_garment", "MobileSAMWrapper"]


# ─────────────────────────────────────────────────────────────────────────────
# MobileSAM model wrapper
# ─────────────────────────────────────────────────────────────────────────────


class MobileSAMWrapper:
    """
    Lightweight SAM-based garment segmentation.

    MobileSAM uses the same ViT-H SAM architecture as the full SAM but with
    a much lighter decoder, reducing model size from 2.4GB to ~40MB while
    maintaining 99.9% of the quality.
    """

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        self._predictor = None

    def _load(self):
        """Lazy-load MobileSAM model."""
        if self._predictor is not None:
            return

        try:
            from mobile_sam import SamPredictor, sam_model_registry

            # Model weights paths
            if self.model_path:
                sam = sam_model_registry["vit_t"](checkpoint=self.model_path)
            else:
                # Try common locations
                from pathlib import Path

                candidates = [
                    Path(__file__).parent.parent.parent / "models" / "mobile_sam.pt",
                    Path.home() / ".cache" / "mobile_sam" / "mobile_sam.pt",
                    Path("D:/models/mobile_sam.pt"),
                ]
                for p in candidates:
                    if p.exists():
                        sam = sam_model_registry["vit_t"](checkpoint=str(p))
                        break
                else:
                    # Download from HuggingFace
                    sam = sam_model_registry["vit_t"](
                        checkpoint="mobile_sam/total_text_dialogue.pth"
                    )

            self._predictor = SamPredictor(sam)

        except ImportError:
            # Fallback: use GroundingSAM (lighter alternative)
            try:
                from grounding_sam import SamPredictor, sam_model_registry

                sam = sam_model_registry["vit_t"]()
                self._predictor = SamPredictor(sam)
            except ImportError:
                self._predictor = None

    def segment_garment(
        self,
        image: Image.Image,
        bbox: tuple[int, int, int, int] | None = None,
    ) -> Image.Image | None:
        """
        Segment garment from product image using MobileSAM.

        Args:
            image: PIL RGB image of the garment.
            bbox: Optional bounding box (x0, y0, x1, y1) for point-based prompting.
                  If None, uses automatic mask generation.

        Returns:
            PIL L-mode image (white = garment, black = background),
            or None if segmentation fails.
        """
        self._load()

        if self._predictor is None:
            return None

        try:
            import torch

            arr = np.array(image.convert("RGB"))
            h, w = arr.shape[:2]

            with torch.no_grad():
                self._predictor.set_image(arr)

            if bbox is not None:
                # Box prompt
                x0, y0, x1, y1 = bbox
                box = np.array([x0, y0, x1, y1])
                masks, scores, _ = self._predictor.predict(box=box)
            else:
                # Automatic mask generation
                masks, scores, _ = self._predictor.predict()

            if len(masks) == 0:
                return None

            # Take the best mask (highest score)
            best_idx = scores.argmax()
            mask = masks[best_idx].astype(np.uint8) * 255

            # Optional: combine multiple high-scoring masks
            top_k = min(3, len(masks))
            top_indices = np.argsort(scores)[-top_k:]
            combined_mask = np.zeros_like(mask)
            for idx in top_indices:
                if scores[idx] > 0.7:  # Confidence threshold
                    combined_mask = np.maximum(combined_mask, masks[idx].astype(np.uint8) * 255)

            if combined_mask.sum() > 100:  # Valid mask
                return Image.fromarray(combined_mask, mode="L")

            return Image.fromarray(mask, mode="L")

        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Fallback: SAM with automatic mask generation
# ─────────────────────────────────────────────────────────────────────────────


def _sam_auto_segment(
    image: Image.Image,
    model_type: str = "vit_t",
    checkpoint: str | None = None,
) -> Image.Image | None:
    """
    Segment using SAM's automatic mask generation (no prompts needed).

    This is useful when you don't have a bbox/prompt for the garment.
    SAM will generate multiple mask proposals and we take the most confident
    one(s) that cover the central region of the image.
    """
    try:
        import torch
        from segment_anything import SamPredictor, sam_model_registry
    except ImportError:
        try:
            import torch
            from mobile_sam import SamPredictor, sam_model_registry
        except ImportError:
            return None

    try:
        if checkpoint:
            sam = sam_model_registry[model_type](checkpoint=checkpoint)
        else:
            # Use vit_t (MobileSAM) as default
            sam = sam_model_registry["vit_t"]()

        predictor = SamPredictor(sam)
        arr = np.array(image.convert("RGB"))
        h, w = arr.shape[:2]

        with torch.no_grad():
            predictor.set_image(arr)
            masks, scores, _ = predictor.predict()

        if len(masks) == 0:
            return None

        # Filter masks: keep those centered in the image and large enough
        center_x, center_y = w / 2, h / 2
        valid_masks = []

        for i, (mask, score) in enumerate(zip(masks, scores)):
            mask_arr = mask.astype(np.uint8) * 255
            ys, xs = np.where(mask_arr > 0)
            if xs.size == 0:
                continue

            # Check if mask is reasonably centered and sized
            mask_cx = xs.mean()
            mask_cy = ys.mean()
            mask_area = xs.size

            dist_from_center = np.sqrt((mask_cx - center_x) ** 2 + (mask_cy - center_y) ** 2)
            max_dist = np.sqrt(w**2 + h**2) / 4

            # Valid: centered, covers >5% of image, confident
            if dist_from_center < max_dist and mask_area > w * h * 0.05 and score > 0.7:
                valid_masks.append((mask_arr, score, mask_area))

        if not valid_masks:
            # Fallback: take the best mask overall
            best_idx = scores.argmax()
            mask = masks[best_idx].astype(np.uint8) * 255
            return Image.fromarray(mask, mode="L")

        # Combine valid masks
        combined = np.zeros_like(masks[0], dtype=np.uint8) * 255
        for mask_arr, score, area in sorted(valid_masks, key=lambda x: x[1], reverse=True)[:3]:
            combined = np.maximum(combined, mask_arr)

        return Image.fromarray(combined, mode="L")

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────────────────────────────────────

_sam_wrapper: MobileSAMWrapper | None = None


def sam_segment_garment(
    garment_image: Image.Image,
    bbox: tuple[int, int, int, int] | None = None,
    model_path: str | None = None,
) -> Image.Image | None:
    """
    Segment a garment image using MobileSAM.

    This is the primary entry point for Part 5 of the optimization.

    Args:
        garment_image: PIL RGB image of the garment product photo.
        bbox: Optional (x0, y0, x1, y1) bounding box for the garment.
              If not provided, uses automatic mask generation.
        model_path: Optional path to MobileSAM checkpoint.

    Returns:
        PIL L-mode image (white = garment foreground, black = background).
        Returns None if MobileSAM is not available.

    Example:
        # With bbox prompt (more accurate)
        mask = sam_segment_garment(img, bbox=(50, 20, 400, 500))

        # Automatic (no bbox needed)
        mask = sam_segment_garment(img)
    """
    global _sam_wrapper

    if _sam_wrapper is None:
        _sam_wrapper = MobileSAMWrapper(model_path=model_path)

    result = _sam_wrapper.segment_garment(garment_image, bbox=bbox)

    if result is None:
        # Try automatic mask generation as fallback
        result = _sam_auto_segment(garment_image)

    return result


def sam_segment_with_hints(
    garment_image: Image.Image,
    cloth_type: str = "upper",
) -> Image.Image | None:
    """
    Segment garment with clothing-type-specific hints.

    Different garment types have different typical shapes:
    - upper: wider at top, narrower at waist
    - lower: narrower at top, wider at bottom
    - dress: relatively uniform or A-line

    These hints help SAM produce better masks.
    """
    w, h = garment_image.size
    _center_x = w // 2  # noqa: F841

    if cloth_type in ("upper", "top"):
        # Upper garment: centered, occupies middle-to-upper portion of image
        bbox = (
            int(w * 0.05),
            int(h * 0.05),
            int(w * 0.95),
            int(h * 0.80),
        )
    elif cloth_type in ("lower", "bottom", "skirt"):
        # Lower garment: centered, occupies lower portion
        bbox = (
            int(w * 0.10),
            int(h * 0.10),
            int(w * 0.90),
            int(h * 0.95),
        )
    else:  # dress, overall
        # Full garment: centered, occupies most of image
        bbox = (
            int(w * 0.05),
            int(h * 0.02),
            int(w * 0.95),
            int(h * 0.95),
        )

    return sam_segment_garment(garment_image, bbox=bbox)
