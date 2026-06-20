"""Person auto-crop module for CatVTON virtual try-on.

Fixes the "person too small" problem by detecting the human body
and cropping so that the person occupies 70-80% of the image height.

Pipeline:
    1. MediaPipe PoseLandmarker → detect body keypoints + segmentation
    2. Compute tight body bounding box from landmarks
    3. Crop to body + margin → pad/resize to standard canvas
    4. Ensure body height = 70-80% of canvas

Usage:
    from app.services.person_crop import crop_person_to_standard

    cropped, info = crop_person_to_standard(person_image)
    # cropped: PIL Image with person occupying 70-80% of height
    # info: dict with crop metadata (bbox, scale, body_height_ratio)
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

__all__ = [
    "crop_person_to_standard",
    "PersonCropInfo",
    "detect_person_bbox",
    "detect_person_bbox_mediapipe",
    "detect_person_bbox_yolo",
]


@dataclass
class PersonCropInfo:
    """Metadata from person cropping."""

    original_size: tuple[int, int]
    cropped_size: tuple[int, int]
    body_bbox: tuple[int, int, int, int]  # (x0, y0, x1, y1) in original coords
    body_height_ratio: float  # body_height / image_height
    scale: float
    method: str  # "mediapipe" | "yolo" | "aspect_ratio" | "center_crop"


def _detect_mediapipe_pose(image: Image.Image) -> tuple[list, Image.Image | None]:
    """Detect person using MediaPipe PoseLandmarker.

    Returns:
        landmarks: list of landmark objects with .x, .y attributes (normalized 0-1)
        seg_mask: PIL L image of person segmentation (or None)
    """
    try:
        from mediapipe import Image as MPImage
        from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
    except ImportError:
        return [], None

    mp_pose_path = _get_pose_landmarker_path()
    if mp_pose_path is None:
        return [], None

    w, h = image.size
    arr = np.array(image.convert("RGB"))

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp_path = f.name

    try:
        Image.fromarray(arr).save(tmp_path, format="JPEG", quality=95)

        options = PoseLandmarkerOptions(
            base_options=mp_pose_path,
            running_mode=RunningMode.IMAGE,
            output_segmentation_masks=True,
        )
        landmarker = PoseLandmarker.create_from_options(options)
        mp_img = MPImage.create_from_file(tmp_path)
        result = landmarker.detect(mp_img)
        landmarker.close()

        landmarks = result.pose_landmarks[0] if result.pose_landmarks else []

        seg_mask = None
        if result.segmentation_masks and len(result.segmentation_masks) > 0:
            seg_np = (result.segmentation_masks[0].numpy_view() * 255).astype(np.uint8)
            if seg_np.ndim == 3:
                seg_np = seg_np[..., 0]
            seg_mask = Image.fromarray(seg_np, mode="L")

        return landmarks, seg_mask
    except Exception as e:
        logger.debug(f"MediaPipe pose detection failed: {e}")
        return [], None
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass


def _detect_mediapipe_pose_fast(image: Image.Image) -> tuple[list, Image.Image | None]:
    """Fast pose detection without segmentation mask (faster)."""
    try:
        from mediapipe import Image as MPImage
        from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
    except ImportError:
        return [], None

    mp_pose_path = _get_pose_landmarker_path()
    if mp_pose_path is None:
        return [], None

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp_path = f.name

    try:
        arr = np.array(image.convert("RGB"))
        Image.fromarray(arr).save(tmp_path, format="JPEG", quality=85)

        options = PoseLandmarkerOptions(
            base_options=mp_pose_path,
            running_mode=RunningMode.IMAGE,
            output_segmentation_masks=False,
        )
        landmarker = PoseLandmarker.create_from_options(options)
        mp_img = MPImage.create_from_file(tmp_path)
        result = landmarker.detect(mp_img)
        landmarker.close()

        landmarks = result.pose_landmarks[0] if result.pose_landmarks else []
        return landmarks, None
    except Exception as e:
        logger.debug(f"MediaPipe fast pose detection failed: {e}")
        return [], None
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass


_MP_POSE_TASK: str | None = None


def _get_pose_landmarker_path() -> str | None:
    """Find or download MediaPipe PoseLandmarker task file."""
    global _MP_POSE_TASK
    if _MP_POSE_TASK:
        return _MP_POSE_TASK

    candidates = [
        Path(__file__).parent.parent.parent.parent / "models" / "pose_landmarker_heavy.task",
        Path.home() / ".cache" / "mediapipe-assets" / "pose_landmarker_heavy.task",
        Path.home() / "models" / "pose_landmarker_heavy.task",
        Path("D:/models/pose_landmarker_heavy.task"),
    ]
    for p in candidates:
        if p.exists():
            _MP_POSE_TASK = str(p.resolve())
            logger.info(f"[PERSON-CROP] Found PoseLandmarker model: {_MP_POSE_TASK}")
            return _MP_POSE_TASK

    model_url = (
        "https://storage.googleapis.com/mediapipe-models/"
        "pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
    )
    download_path = Path.home() / ".cache" / "mediapipe-assets" / "pose_landmarker_heavy.task"
    try:
        download_path.parent.mkdir(parents=True, exist_ok=True)
        import urllib.request

        logger.info(f"[PERSON-CROP] Downloading PoseLandmarker model to {download_path}...")
        urllib.request.urlretrieve(model_url, download_path)
        _MP_POSE_TASK = str(download_path.resolve())
        logger.info(f"[PERSON-CROP] Downloaded PoseLandmarker: {_MP_POSE_TASK}")
        return _MP_POSE_TASK
    except Exception as e:
        logger.warning(f"[PERSON-CROP] Failed to download PoseLandmarker: {e}")
        return None


def _bbox_from_landmarks(
    landmarks: list,
    image_w: int,
    image_h: int,
    margin_frac: float = 0.10,
) -> tuple[int, int, int, int] | None:
    """Compute tight body bounding box from MediaPipe pose landmarks.

    Uses: nose(0), ears(7,8), shoulders(11,12), hips(23,24),
          knees(25,26), ankles(27,28) → full body coverage.

    Returns bbox in pixel coords (x0, y0, x1, y1) or None if not enough landmarks.
    """
    if not landmarks or len(landmarks) < 11:
        return None

    xs = []
    ys = []

    for lm in landmarks:
        xs.append(lm.x * image_w)
        ys.append(lm.y * image_h)

    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)

    bw = x_max - x_min
    bh = y_max - y_min
    if bh <= 0 or bw <= 0:
        return None

    margin_x = int(bw * margin_frac)
    margin_y = int(bh * margin_frac)

    x0 = max(0, int(x_min - margin_x))
    y0 = max(0, int(y_min - margin_y))
    x1 = min(image_w, int(x_max + margin_x))
    y1 = min(image_h, int(y_max + margin_y))

    return (x0, y0, x1, y1)


def _detect_yolo_person(
    image: Image.Image,
) -> tuple[tuple[int, int, int, int] | None, float | None]:
    """Detect person using YOLO (ultralytics).

    Returns:
        bbox: (x0, y0, x1, y1) in pixel coords, or None
        confidence: float or None
    """
    try:
        from ultralytics import YOLO

        arr = np.array(image.convert("RGB"))
        model = YOLO("yolov8n.pt")

        results = model.predict(
            source=arr,
            classes=[0],  # person class
            conf=0.3,
            verbose=False,
        )

        if len(results) == 0:
            return None, None

        result = results[0]
        if result.boxes is None or len(result.boxes) == 0:
            return None, None

        best = result.boxes[0]
        x0, y0, x1, y1 = best.xyxy[0].cpu().numpy()
        conf = float(best.conf[0].cpu().numpy())

        return (int(x0), int(y0), int(x1), int(y1)), conf
    except Exception as e:
        logger.debug(f"YOLO person detection failed: {e}")
        return None, None


def _aspect_ratio_crop(image: Image.Image) -> tuple[int, int, int, int]:
    """Fallback: crop by aspect ratio heuristic.

    For typical full-body photos:
    - Person occupies the center 60% width
    - Person occupies the center 75% height
    """
    w, h = image.size

    x0 = int(w * 0.15)
    x1 = int(w * 0.85)
    y0 = int(h * 0.10)
    y1 = int(h * 0.95)

    return (x0, y0, x1, y1)


def crop_person_to_standard(
    image: Image.Image,
    target_height: int = 1024,
    body_height_ratio: float = 0.75,
    margin_frac: float = 0.10,
) -> tuple[Image.Image, PersonCropInfo]:
    """Auto-crop person image so the body occupies 70-80% of canvas height.

    Detection methods (in priority order):
        1. MediaPipe PoseLandmarker → precise body keypoints + segmentation
        2. YOLO person detection → bounding box
        3. Aspect ratio heuristic → last resort

    The cropped image is then padded to a standard canvas and resized.

    Args:
        image: Raw person photo (any size).
        target_height: Output height in pixels (default 1024).
        body_height_ratio: Desired body height / image height (default 0.75 = 75%).
        margin_frac: Margin around body as fraction of body size (default 0.10 = 10%).

    Returns:
        cropped: PIL Image resized to target_height with body at body_height_ratio.
        info: PersonCropInfo metadata.
    """
    orig_w, orig_h = image.size
    _arr = np.array(image.convert("RGB"))  # noqa: F841

    bbox: tuple[int, int, int, int] | None = None
    method = "aspect_ratio"

    # ── Try MediaPipe PoseLandmarker ────────────────────────────────────────
    landmarks, seg_mask = _detect_mediapipe_pose_fast(image)
    if landmarks:
        bbox = _bbox_from_landmarks(landmarks, orig_w, orig_h, margin_frac=margin_frac)
        method = "mediapipe"
        logger.info(
            f"[PERSON-CROP] MediaPipe detected body, bbox={bbox}, "
            f"num_landmarks={len(landmarks)}"
        )

    # ── Try YOLO if MediaPipe failed ──────────────────────────────────────
    if bbox is None:
        yolo_bbox, yolo_conf = _detect_yolo_person(image)
        if yolo_bbox is not None:
            bbox = yolo_bbox
            method = "yolo"
            logger.info(f"[PERSON-CROP] YOLO detected person, bbox={bbox}, conf={yolo_conf:.2f}")

    # ── Fallback: aspect ratio heuristic ─────────────────────────────────────
    if bbox is None:
        bbox = _aspect_ratio_crop(image)
        method = "aspect_ratio"
        logger.info(f"[PERSON-CROP] Using aspect-ratio fallback, bbox={bbox}")

    x0, y0, x1, y1 = bbox
    body_h = y1 - y0

    if body_h <= 0:
        bbox = (0, 0, orig_w, orig_h)
        x0, y0, x1, y1 = bbox
        body_h = orig_h

    # ── Compute crop: ensure body occupies body_height_ratio of output ──────────
    # target_body_height = target_height * body_height_ratio
    # scale = target_body_height / body_h
    target_body_h = int(target_height * body_height_ratio)
    scale = target_body_h / body_h

    canvas_w, canvas_h = 768, target_height
    scaled_w = max(1, int(round(orig_w * scale)))
    scaled_h = max(1, int(round(orig_h * scale)))
    resized = image.convert("RGB").resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    # Preserve the person geometry by scaling the complete source uniformly.
    # The canvas crop is centered on the detected person rather than stretching
    # the detected body box to the 3:4 target aspect ratio.
    bbox_center_x = ((x0 + x1) / 2.0) * scale
    bbox_center_y = ((y0 + y1) / 2.0) * scale
    x_offset = int(round((canvas_w / 2.0) - bbox_center_x))
    y_offset = int(round((canvas_h / 2.0) - bbox_center_y))

    canvas = Image.new("RGB", (canvas_w, canvas_h), (128, 128, 128))
    canvas.paste(resized, (x_offset, y_offset))

    # Compute actual body_height_ratio in output canvas
    actual_body_h = body_h * scale
    actual_ratio = actual_body_h / canvas_h

    info = PersonCropInfo(
        original_size=(orig_w, orig_h),
        cropped_size=(canvas_w, canvas_h),
        body_bbox=bbox,
        body_height_ratio=round(actual_ratio, 3),
        scale=round(scale, 3),
        method=method,
    )

    logger.info(
        f"[PERSON-CROP] Done: method={method}, "
        f"body_ratio={actual_ratio:.2%}, scale={scale:.2f}, "
        f"original={orig_w}x{orig_h} → cropped={canvas_w}x{canvas_h}"
    )

    return canvas, info


def detect_person_bbox(
    image: Image.Image,
) -> tuple[tuple[int, int, int, int] | None, str]:
    """Convenience: detect person body bbox only (no crop).

    Returns:
        bbox: (x0, y0, x1, y1) in pixel coords, or None
        method: "mediapipe" | "yolo" | "aspect_ratio" | "none"
    """
    orig_w, orig_h = image.size

    landmarks, _ = _detect_mediapipe_pose_fast(image)
    if landmarks:
        bbox = _bbox_from_landmarks(landmarks, orig_w, orig_h)
        if bbox:
            return bbox, "mediapipe"

    yolo_bbox, _ = _detect_yolo_person(image)
    if yolo_bbox is not None:
        return yolo_bbox, "yolo"

    bbox = _aspect_ratio_crop(image)
    return bbox, "aspect_ratio"


def detect_person_bbox_mediapipe(image: Image.Image) -> tuple[list, Image.Image | None]:
    """Direct MediaPipe pose detection."""
    return _detect_mediapipe_pose(image)


def detect_person_bbox_yolo(
    image: Image.Image,
) -> tuple[tuple[int, int, int, int] | None, float | None]:
    """Direct YOLO person detection."""
    return _detect_yolo_person(image)
