"""Try-on v2 garment preprocessing.

Pipeline:
1) Remove background / keep main garment blob (rembg if available, else heuristics)
2) Composite on white background to get a standardized product photo
3) Auto recognize garment category and map to try-on categories: top/bottom/skirt

Two distinct outputs for different consumers:
  - preview_white: user-visible white-background garment photo (letterbox, preserves aspect ratio)
  - image: model-internal standardized 768x768 (for warp engine consumption)

Designed to be CPU-friendly and deterministic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.services.garment_alignment import align_garment
from app.services.tryon_v2.garment_struct import cutout_garment_rgba

logger = logging.getLogger(__name__)


@dataclass
class PreprocessResult:
    image: Image.Image
    preview_white: Image.Image | None = None
    tryon_category: str = "unknown"
    confidence: float = 0.0
    raw_category: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    cutout_rgba: Image.Image | None = None


def letterbox_resize(
    img: Image.Image,
    canvas_size: int = 768,
    background_color: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Resize image to canvas_size while preserving aspect ratio, padding with background color.

    This is the CORRECT way to resize garment product photos. Unlike simple resize (which
    stretches the garment and distorts patterns), letterbox resize:
      - Preserves the original aspect ratio
      - Pads with white (background_color) on the shorter side
      - Centers the garment within the canvas
      - Never distorts, stretches, or warps the garment

    Args:
        img: Input PIL Image (will be converted to RGBA internally)
        canvas_size: Target canvas size (default 768). Output will be canvas_size x canvas_size.
        background_color: RGB tuple for padding. Default white (255, 255, 255).

    Returns:
        PIL Image of exactly canvas_size x canvas_size with letterbox padding.
    """
    im = img.convert("RGBA")
    w, h = im.size
    if w <= 0 or h <= 0:
        return Image.new("RGB", (canvas_size, canvas_size), background_color)

    scale = canvas_size / max(w, h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (canvas_size, canvas_size), background_color)
    paste_x = (canvas_size - new_w) // 2
    paste_y = (canvas_size - new_h) // 2
    canvas.paste(
        resized.convert("RGB"),
        (paste_x, paste_y),
        resized.split()[3] if resized.mode == "RGBA" else None,
    )

    logger.debug(
        f"[letterbox_resize] {w}x{h} -> {new_w}x{new_h} (scale={scale:.3f}), "
        f"canvas={canvas_size}, pad=({paste_x},{paste_y})"
    )
    return canvas


def generate_preview_white(
    original_garment: Image.Image,
    cloth_type: str = "upper",
) -> Image.Image | None:
    """Generate a user-visible white-background garment preview.

    This produces the image that users see in the UI as "白底商品图". It is NOT
    warped, NOT stretched, and NOT resized to a distorted shape. Instead it:
      1. Removes background (via cutout_garment_rgba)
      2. Composites the garment on a pure white background
      3. Applies letterbox resize to preserve aspect ratio
      4. Does NOT apply TPS warp, geometric deformation, or any body-fitting transform

    This is purely for user display. The model internally uses the separate
    `image` field (768x768 standardized for warp consumption).

    Args:
        original_garment: Raw garment product photo (RGB PIL Image).
        cloth_type: Hint for segmentation ("upper" | "lower" | "dress").

    Returns:
        PIL RGB Image of canvas_size x canvas_size with letterboxed white background,
        or None if cutout fails.
    """
    try:
        cutout = cutout_garment_rgba(original_garment, cloth_type=cloth_type)
        rgba = cutout.rgba
        if rgba is None:
            return None

        # Apply tight crop: crop RGBA to alpha bbox before any resize/letterbox.
        # This removes surrounding white/transparent background, making the
        # garment fill more of the preview canvas and improving classifier signal.
        rgba_w, rgba_h = rgba.size
        alpha = rgba.split()[-1]
        bbox = alpha.getbbox()
        if bbox:
            rgba = rgba.crop(bbox)
            logger.info(
                f"[CROP] generate_preview_white tight bbox: "
                f"{rgba_w}x{rgba_h} -> {rgba.size[0]}x{rgba.size[1]} (bbox={bbox})"
            )
        else:
            logger.warning("[CROP] generate_preview_white: alpha bbox is None, no crop applied")

        rgb = rgba.convert("RGB")
        preview = letterbox_resize(rgb, canvas_size=768, background_color=(255, 255, 255))
        logger.info(
            f"[generate_preview_white] generated preview from {original_garment.size} "
            f"-> {preview.size}, cutout area={rgba.size}"
        )
        return preview
    except Exception as e:
        logger.warning(f"[generate_preview_white] failed: {e}")
        return None


def _standardize_white_background(rgba: Image.Image, canvas: int = 768) -> Image.Image:
    """Convert RGBA cutout to 768x768 white-background image for model consumption.

    This is the MODEL-INTERNAL standardized image used for warp/TPS processing.
    It is NOT intended for user display — use generate_preview_white() for UI.

    This function uses letterbox resize to minimize distortion while still
    producing a fixed-size 768x768 tensor input for the warp engine.
    """
    im = rgba.convert("RGBA")
    orig_w, orig_h = im.size
    bbox = im.split()[3].getbbox()
    if bbox:
        im = im.crop(bbox)
        cropped_w, cropped_h = im.size
        logger.info(
            f"[CROP] _standardize_white_background tight bbox: "
            f"{orig_w}x{orig_h} → {cropped_w}x{cropped_h} (bbox={bbox})"
        )
    else:
        logger.warning("[CROP] _standardize_white_background: alpha bbox is None, no crop applied")

    white = Image.new("RGB", im.size, (255, 255, 255))
    white.paste(im.convert("RGB"), (0, 0), im.split()[3])

    w, h = white.size
    side = max(w, h, 64)
    padded = Image.new("RGB", (side, side), (255, 255, 255))
    padded.paste(white, ((side - w) // 2, (side - h) // 2))
    if side != int(canvas):
        padded = padded.resize((int(canvas), int(canvas)), Image.Resampling.LANCZOS)
    return padded


def _pil_to_jpeg_bytes(img: Image.Image, quality: int = 92) -> bytes:
    rgb = img.convert("RGB")
    buf = BytesIO()
    rgb.save(buf, format="JPEG", quality=int(quality), optimize=False)
    return buf.getvalue()


def _recognize_category(image_bytes: bytes) -> tuple[str, float]:
    """Return (raw_category, confidence)."""
    try:
        from app.ml.image_recognizer import get_recognizer

        r = get_recognizer().recognize(image_bytes)
        return str(r.category), float(r.category_confidence or 0.0)
    except Exception:
        pass

    # Part 6 fallback: use the new garment classifier when ImageRecognizer is unavailable
    try:
        import io

        from PIL import Image

        from app.services.garment_classifier import classify_garment

        img = Image.open(io.BytesIO(image_bytes))
        category = classify_garment(img)
        return category, 0.6  # Moderate confidence since this is a heuristic fallback
    except Exception:
        return "unknown", 0.0


def _map_to_tryon_category(
    raw_category: str, confidence: float = 1.0, cropped_image_size: tuple[int, int] | None = None
) -> str:
    c = (raw_category or "").strip().lower()
    if not c:
        return "unknown"
    # Chinese labels from ImageRecognizer / CLIP candidates.
    if any(k in c for k in ("鞋", "shoes", "shoe", "boot", "包", "bag", "handbag", "backpack")):
        # Low-confidence shoe/bag → treat as upper garment instead of blocking try-on.
        # This prevents T-shirt misclassifications from being rejected as accessories.
        if confidence < 0.20:
            ratio = 0.0
            if cropped_image_size is not None:
                w, h = cropped_image_size
                ratio = w / max(h, 1)
            logger.warning(
                f"[CATEGORY] accessory ignored " f"(ratio={ratio:.2f}, confidence={confidence:.3f})"
            )
            return "top"
        return "accessory"
    if any(
        k in c
        for k in (
            "上衣",
            "上装",
            "t恤",
            "t-shirt",
            "shirt",
            "hoodie",
            "sweater",
            "外套",
            "coat",
            "jacket",
        )
    ):
        return "top"
    if any(k in c for k in ("裤", "下装", "裤子", "短裤", "长裤", "jeans", "pants", "bottom")):
        return "bottom"
    # Part 6: skirt/dress detection — must come BEFORE "裙" generic check
    if c in ("skirt", "裙子", "半身裙", "短裙", "长裙"):
        return "skirt"
    if any(k in c for k in ("裙", "连衣裙", "dress", "onepiece")):
        return "skirt"  # Default to skirt for ambiguous dress-like items
    return "unknown"


def _looks_like_scarf_or_accessory_shape(rgba: Image.Image) -> bool:
    """Heuristic: long-narrow + low fill ratio often indicates scarf/shawl/accessory.

    This prevents routing scarf-like items into "top" replacement which looks wrong.
    """
    im = rgba.convert("RGBA")
    a = np.asarray(im.split()[3], dtype=np.uint8)
    if a.size == 0:
        return False
    ys, xs = np.where(a > 10)
    if xs.size < 50:
        return False
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)
    box_area = float(bw * bh)
    fg_area = float((a[y0:y1, x0:x1] > 10).sum())
    fill = fg_area / max(box_area, 1.0)
    aspect = max(bw, bh) / max(min(bw, bh), 1.0)

    # Typical scarf: very long/narrow, and occupies small area within bbox due to fringes.
    return (aspect >= 2.6 and fill <= 0.30) or (aspect >= 3.2 and fill <= 0.42)


def _looks_like_pants_shape(rgba: Image.Image) -> bool:
    """Detect pants from the cutout silhouette.

    Product-photo classifiers often confuse light jeans on a white square canvas with
    shoes/boots. The pants silhouette is more reliable: tall garment, visible left
    and right leg mass, and a vertical center gap through the lower half.
    """
    im = rgba.convert("RGBA")
    arr = np.asarray(im, dtype=np.uint8)
    if arr.size == 0:
        return False
    rgb = arr[:, :, :3]
    a = arr[:, :, 3]

    alpha_mask = a > 10
    gray = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    # For pants detection, low-chroma gray shadow in the crotch gap should behave
    # like background; otherwise light jeans become one solid rectangle. Keep dark
    # low-chroma garments as foreground via the brightness branch.
    color_mask = (chroma > 22) | (gray < 150)
    if float(color_mask.mean()) > 0.08:
        fg_mask = alpha_mask & color_mask
    elif float(alpha_mask.mean()) > 0.98 and float(color_mask.mean()) > 0.02:
        fg_mask = color_mask
    else:
        fg_mask = alpha_mask

    ys, xs = np.where(fg_mask)
    if xs.size < 100:
        return False

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    mask = fg_mask[y0:y1, x0:x1]
    bh, bw = mask.shape
    if bw < 20 or bh < 40:
        return False

    aspect = bh / max(bw, 1)
    fill = float(mask.mean())
    if aspect < 1.25 or fill < 0.25 or fill > 0.94:
        return False

    left = mask[:, : bw // 2]
    right = mask[:, bw // 2 :]
    center = mask[:, int(bw * 0.43) : max(int(bw * 0.57), int(bw * 0.43) + 1)]

    sampled = 0
    split_rows = 0
    for y in range(int(bh * 0.34), int(bh * 0.96), max(1, bh // 80)):
        row = mask[y]
        if float(row.mean()) < 0.12:
            continue
        sampled += 1
        left_fg = float(left[y].mean()) if left.shape[1] else 0.0
        right_fg = float(right[y].mean()) if right.shape[1] else 0.0
        center_fg = float(center[y].mean()) if center.shape[1] else 1.0
        if left_fg > 0.10 and right_fg > 0.10 and center_fg < 0.38:
            split_rows += 1

    if sampled < 8:
        return False

    split_ratio = split_rows / max(sampled, 1)
    top_band = mask[: max(1, int(bh * 0.22))]
    top_connected = float(top_band.mean()) > 0.18
    return bool(split_ratio >= 0.28 and top_connected)


def evaluate_lower_garment_qc(rgba: Image.Image) -> dict[str, Any]:
    """QC for pants product photos (waist + both legs + hem completeness).

    Returns a dict with passed/score/reasons for input_gate and preprocess metadata.
    """
    reasons: list[str] = []
    pants_shape = _looks_like_pants_shape(rgba)
    if not pants_shape:
        reasons.append("silhouette_not_pants")

    im = rgba.convert("RGBA")
    arr = np.asarray(im, dtype=np.uint8)
    a = arr[:, :, 3]
    ys, xs = np.where(a > 10)
    fill_score = 0.0
    aspect_score = 0.0
    if xs.size >= 50:
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        bw = max(1, x1 - x0)
        bh = max(1, y1 - y0)
        fg = float((a[y0:y1, x0:x1] > 10).sum())
        fill_score = fg / float(max(bw * bh, 1))
        aspect = bh / float(max(bw, 1))
        aspect_score = 1.0 if 1.2 <= aspect <= 3.5 else 0.35
        if aspect < 1.15:
            reasons.append("too_short_or_cropped")
        if fill_score > 0.92:
            reasons.append("possible_poster_or_solid_block")
    else:
        reasons.append("foreground_too_small")

    # Clean / white-ish background check on original RGB if available.
    rgb = arr[:, :, :3]
    gray = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    bg_ratio = float(((gray > 235) & (chroma < 18)).mean())
    bg_score = 1.0 if bg_ratio >= 0.18 else (0.0 if bg_ratio <= 0.04 else (bg_ratio - 0.04) / 0.14)
    if bg_score < 0.35:
        reasons.append("background_not_clean")

    shape_score = 1.0 if pants_shape else 0.15
    score = max(
        0.0,
        min(1.0, 0.45 * shape_score + 0.25 * aspect_score + 0.15 * fill_score + 0.15 * bg_score),
    )
    passed = bool(pants_shape and score >= 0.45 and "foreground_too_small" not in reasons)
    return {
        "passed": passed,
        "score": round(float(score), 3),
        "pants_shape": bool(pants_shape),
        "bg_clean_score": round(float(bg_score), 3),
        "reasons": reasons,
        "message": (None if passed else "请上传单条裤子的正面白底商品图，裤腰和裤脚需要完整入镜。"),
    }


# Backwards-compatible alias used by callers / tests.
pants_qc = evaluate_lower_garment_qc


def preprocess_garment_image(
    garment_image: Image.Image,
    *,
    canvas: int = 768,
    cloth_type_hint: str | None = None,
    debug_dir: str | Path | None = None,
) -> PreprocessResult:
    """Preprocess a garment image for CatVTON try-on.

    Returns TWO distinct images:
      - image (768x768): model-internal standardized for warp consumption
      - preview_white: user-visible white-background garment photo (letterbox)

    Args:
        garment_image: Raw garment product photo.
        canvas: Output canvas size (default 768).
        cloth_type_hint: Optional hint for SAM segmentation ("upper" | "lower" | "dress").
            If not provided, uses a fast heuristic based on image aspect ratio.
        debug_dir: Optional directory path to save intermediate debug images:
            01_original.jpg, 02_cutout.png, 03_aligned.jpg, 04_preview_white.jpg,
            05_standardized.jpg
    """

    debug_path: Path | None = None
    if debug_dir:
        debug_path = Path(debug_dir)
        debug_path.mkdir(parents=True, exist_ok=True)

    # Fast cloth type heuristic (needed for SAM hints before category recognition).
    # Recognition via _recognize_category happens after cutout, so we need a quick guess.
    if cloth_type_hint:
        cloth_type = cloth_type_hint
    else:
        w, h = garment_image.size
        aspect = h / max(w, 1)
        cloth_type = "upper" if aspect < 1.8 else "lower"

    # Debug: save original
    if debug_path:
        try:
            garment_image_rgb = garment_image.convert("RGB")
            garment_image_rgb.save(debug_path / "01_original.jpg", quality=95)
        except Exception as e:
            logger.warning(f"[DEBUG] failed to save 01_original: {e}")

    cutout = cutout_garment_rgba(garment_image, cloth_type=cloth_type)
    pants_shape = _looks_like_pants_shape(cutout.cropped)
    if pants_shape and cloth_type != "lower":
        logger.info(
            "[AUTO-PREPROCESS] pants silhouette detected; overriding cloth_type %r -> 'lower'",
            cloth_type,
        )
        cloth_type = "lower"

    # Debug: save cutout RGBA
    if debug_path:
        try:
            rgba_debug = cutout.rgba.convert("RGBA")
            rgba_debug.save(debug_path / "02_cutout.png")
        except Exception as e:
            logger.warning(f"[DEBUG] failed to save 02_cutout: {e}")

    try:
        aligned = align_garment(cutout.cropped, cloth_type=cloth_type, canvas_size=canvas)
        alignment_applied = True
    except Exception:
        aligned = cutout.cropped
        alignment_applied = False

    # Debug: save aligned
    if debug_path:
        try:
            aligned_rgb = aligned.convert("RGB") if aligned.mode != "RGB" else aligned
            aligned_rgb.save(debug_path / "03_aligned.jpg", quality=95)
        except Exception as e:
            logger.warning(f"[DEBUG] failed to save 03_aligned: {e}")

    standardized = _standardize_white_background(aligned, canvas=canvas)

    # Generate preview_white: user-visible white-background image (letterbox, no stretch)
    preview_white = generate_preview_white(garment_image, cloth_type=cloth_type)

    # Debug: save preview_white and standardized
    if debug_path:
        try:
            if preview_white is not None:
                preview_white.save(debug_path / "04_preview_white.jpg", quality=95)
            standardized_rgb = (
                standardized.convert("RGB") if standardized.mode != "RGB" else standardized
            )
            standardized_rgb.save(debug_path / "05_standardized.jpg", quality=95)
        except Exception as e:
            logger.warning(f"[DEBUG] failed to save debug images: {e}")

    img_bytes = _pil_to_jpeg_bytes(standardized)

    raw_cat, conf = _recognize_category(img_bytes)
    cropped_size = cutout.cropped.size
    tryon_cat = _map_to_tryon_category(raw_cat, conf, cropped_size)
    accessory_shape = _looks_like_scarf_or_accessory_shape(cutout.cropped)

    # When the model is uncertain (conf < 0.15) AND classifies as accessory,
    # use aspect-ratio heuristic instead of blindly treating it as accessory.
    # White/light garments on white backgrounds often get misclassified as shoes
    # by the ImageNet-based classifier. Aspect ratio is a reliable fallback.
    if tryon_cat == "accessory" and conf < 0.15:
        w, h = garment_image.size
        aspect = h / max(w, 1)
        if aspect < 1.8:
            tryon_cat = "top"
            logger.info(
                f"[AUTO-PREPROCESS] Low-confidence accessory (conf={conf:.3f}) "
                f"reclassified as 'top' based on aspect ratio ({aspect:.2f})"
            )
        else:
            tryon_cat = "bottom"
            logger.info(
                f"[AUTO-PREPROCESS] Low-confidence accessory (conf={conf:.3f}) "
                f"reclassified as 'bottom' based on aspect ratio ({aspect:.2f})"
            )
    elif pants_shape and tryon_cat in {"top", "accessory", "unknown"}:
        previous_tryon_cat = tryon_cat
        tryon_cat = "bottom"
        logger.info(
            "[AUTO-PREPROCESS] pants silhouette overrides category %r "
            "(raw=%r, conf=%.3f) -> 'bottom'",
            previous_tryon_cat,
            raw_cat,
            conf,
        )
    elif accessory_shape and tryon_cat in {"top", "unknown"}:
        tryon_cat = "accessory"
    elif tryon_cat == "top" and conf < 0.15 and cloth_type == "lower":
        tryon_cat = "bottom"
        logger.info(
            "[AUTO-PREPROCESS] Low-confidence top category "
            "(conf=%.3f) reclassified as 'bottom' from cloth_type='lower'",
            conf,
        )
    elif tryon_cat == "unknown" and conf < 0.15:
        if cloth_type == "lower":
            tryon_cat = "bottom"
        elif cloth_type == "dress":
            tryon_cat = "skirt"
        else:
            tryon_cat = "top"
        logger.info(
            "[AUTO-PREPROCESS] Low-confidence unknown category "
            "(conf=%.3f) reclassified as %r from cloth_type=%r",
            conf,
            tryon_cat,
            cloth_type,
        )

    logger.info(
        f"[preprocess_garment_image] category={tryon_cat} confidence={conf:.3f} "
        f"cloth_type={cloth_type} alignment_applied={alignment_applied} "
        f"preview_white={'OK' if preview_white else 'FAILED'}"
    )

    return PreprocessResult(
        image=standardized,
        preview_white=preview_white,
        tryon_category=tryon_cat,
        confidence=float(conf),
        raw_category=raw_cat,
        metadata={
            "canvas": int(canvas),
            "accessory_shape": bool(accessory_shape),
            "pants_shape": bool(pants_shape),
            "pants_qc": (
                evaluate_lower_garment_qc(cutout.cropped)
                if (pants_shape or tryon_cat == "bottom" or cloth_type == "lower")
                else None
            ),
            "cloth_type_used": cloth_type,
            "alignment_applied": alignment_applied,
            "preview_white_generated": preview_white is not None,
            "cutout_size": cutout.rgba.size,
            "cropped_size": cutout.cropped.size,
            "debug_session_dir": str(debug_path) if debug_path else None,
        },
        cutout_rgba=cutout.rgba,
    )
