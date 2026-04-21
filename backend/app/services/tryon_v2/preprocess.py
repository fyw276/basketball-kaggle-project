"""Try-on v2 garment preprocessing.

Pipeline:
1) Remove background / keep main garment blob (rembg if available, else heuristics)
2) Composite on white background to get a standardized product photo
3) Auto recognize garment category and map to try-on categories: top/bottom/skirt

Designed to be CPU-friendly and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image

from app.services.tryon_v2.garment_struct import cutout_garment_rgba


@dataclass
class PreprocessResult:
    image: Image.Image
    tryon_category: str
    confidence: float
    raw_category: str
    metadata: dict[str, Any]


def _pil_to_jpeg_bytes(img: Image.Image, quality: int = 92) -> bytes:
    rgb = img.convert("RGB")
    buf = BytesIO()
    rgb.save(buf, format="JPEG", quality=int(quality), optimize=False)
    return buf.getvalue()


def _standardize_white_background(rgba: Image.Image, canvas: int = 768) -> Image.Image:
    im = rgba.convert("RGBA")
    bbox = im.split()[3].getbbox()
    if bbox:
        im = im.crop(bbox)

    # Composite onto white background.
    white = Image.new("RGB", im.size, (255, 255, 255))
    white.paste(im.convert("RGB"), (0, 0), im.split()[3])

    # Pad to square canvas and resize.
    w, h = white.size
    side = max(w, h, 64)
    padded = Image.new("RGB", (side, side), (255, 255, 255))
    padded.paste(white, ((side - w) // 2, (side - h) // 2))
    if side != int(canvas):
        padded = padded.resize((int(canvas), int(canvas)), Image.Resampling.LANCZOS)
    return padded


def _recognize_category(image_bytes: bytes) -> tuple[str, float]:
    """Return (raw_category, confidence)."""
    try:
        from app.ml.image_recognizer import ImageRecognizer

        r = ImageRecognizer().recognize(image_bytes)
        return str(r.category), float(r.category_confidence or 0.0)
    except Exception:
        return "unknown", 0.0


def _map_to_tryon_category(raw_category: str) -> str:
    c = (raw_category or "").strip().lower()
    if not c:
        return "unknown"
    # Chinese labels from ImageRecognizer / CLIP candidates.
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
    if any(k in c for k in ("裙", "裙子", "裙装", "连衣裙", "dress", "skirt")):
        return "skirt"
    return "unknown"


def preprocess_garment_image(
    garment_image: Image.Image,
    *,
    canvas: int = 768,
) -> PreprocessResult:
    cutout = cutout_garment_rgba(garment_image)
    standardized = _standardize_white_background(cutout.cropped, canvas=canvas)
    img_bytes = _pil_to_jpeg_bytes(standardized)

    raw_cat, conf = _recognize_category(img_bytes)
    tryon_cat = _map_to_tryon_category(raw_cat)

    return PreprocessResult(
        image=standardized,
        tryon_category=tryon_cat,
        confidence=float(conf),
        raw_category=raw_cat,
        metadata={"canvas": int(canvas)},
    )
