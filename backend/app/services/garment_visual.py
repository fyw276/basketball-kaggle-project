"""Re-run color (and optionally category) from the stored garment image file."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.logging import setup_logging
from app.ml.color_extractor import ColorExtractor
from app.schemas.garment import ColorSchema

if TYPE_CHECKING:
    from app.models.garment import Garment

logger = setup_logging()


def _fallback_main_color() -> ColorSchema:
    return ColorSchema(
        name="灰",
        rgb=(128, 128, 128),
        hsv=(0.0, 0.0, 50.0),
        hex_code="#808080",
        confidence=0.2,
    )


def refresh_garment_visuals(
    db: Session,
    garment: Garment,
    *,
    recategorize: bool = False,
) -> Garment:
    """
    Read bytes from ``garment.image_path``, refresh ``main_color`` / ``secondary_colors``.
    If ``recategorize`` is True, also re-run the same recognition stack as simple upload
    (fine-tuned API if configured, else local ImageRecognizer; optional CLIP only if
    ``WARDROBE_USE_CLIP_FALLBACK`` is enabled) plus the low-confidence MobileNet fallback.
    """
    path = Path(garment.image_path or "")
    if not path.is_file():
        raise FileNotFoundError(str(path))

    image_bytes = path.read_bytes()
    extractor = ColorExtractor(n_colors=3)
    colors = extractor.extract_colors(image_bytes)
    main = colors[0] if colors else _fallback_main_color()
    secondaries = colors[1:] if len(colors) > 1 else []

    garment.main_color = main.model_dump()
    garment.secondary_colors = [c.model_dump() for c in secondaries]

    if recategorize:
        import os

        from app.api.wardrobe_simple import _normalize_auto_category
        from app.services.finetuned_infer_client import try_finetuned_infer

        recognition_result = try_finetuned_infer(image_bytes, feature="wardrobe_simple_upload")
        if recognition_result is None:
            clip_allowed = str(
                os.environ.get("WARDROBE_USE_CLIP_FALLBACK", "")
            ).strip().lower() in (
                "1",
                "true",
                "yes",
            )
            clip_disabled = str(os.environ.get("DISABLE_CLIP", "")).strip().lower() in (
                "1",
                "true",
                "yes",
            )
            if clip_allowed and not clip_disabled:
                from app.ml.clip_recognizer import get_clip_recognizer

                recognizer = get_clip_recognizer()
                recognition_result = recognizer.recognize(image_bytes)
            else:
                from app.ml.image_recognizer import ImageRecognizer

                logger.warning(
                    "Garment recategorize fell back to ImageRecognizer; skip CLIP download path"
                )
                legacy = ImageRecognizer().recognize(image_bytes)
                recognition_result = {
                    "category": legacy.category,
                    "category_confidence": legacy.category_confidence,
                    "style_tags": legacy.style_tags,
                    "fit_type": None,
                    "feature_vector": list(legacy.feature_vector),
                }

        recognized_category = str(recognition_result.get("category") or "").strip()
        category_confidence = float(recognition_result.get("category_confidence") or 0.0)
        category_for_save = _normalize_auto_category(recognized_category)

        if category_confidence < 0.15:
            try:
                from app.ml.category_classifier import CategoryClassifier

                fallback_category, _ = CategoryClassifier().classify_category(image_bytes)
                category_for_save = _normalize_auto_category(fallback_category)
            except Exception:
                pass

        clip_features = recognition_result["feature_vector"]
        feature_dim = len(clip_features)
        if feature_dim == 768:
            feature_vector = clip_features + [0.0] * 512
        elif feature_dim == 512:
            feature_vector = clip_features + [0.0] * 768
        else:
            feature_vector = clip_features[:1280] + [0.0] * max(0, 1280 - len(clip_features))

        garment.category = category_for_save
        garment.feature_vector = feature_vector
        st = recognition_result.get("style_tags")
        if isinstance(st, list) and st:
            garment.style_tags = st
        fit = recognition_result.get("fit_type")
        if fit:
            garment.fit_type = fit

    db.add(garment)
    db.commit()
    db.refresh(garment)
    return garment
