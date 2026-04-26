"""
CatVTON subprocess runner — standalone inference via CatVTONPipeline.

Key innovation: uses MediaPipe PoseLandmarker (instead of CatVTON's AutoMasker
which requires SCHP+DensePose) to generate cloth-agnostic masks. This makes
CatVTON work WITHOUT detectron2 / SCHP / DensePose checkpoints.

Architecture:
- CatVTONPipeline: Core diffusion model (SD v1.5 inpainting + CatVTON attention)
- MediaPipe PoseLandmarker: Body keypoints + person segmentation mask
- Body-region mask: Derived from pose keypoints (upper/lower/overall regions)

Usage (from vton_inference_service/main.py):
    result = subprocess.run([
        sys.executable, "-m", "vton_inference_service.catvton_runner",
        "--person", person_path, "--garment", garment_path,
        "--output", output_path, "--type", cloth_type,
        "--width", "768", "--height", "1024",
        "--steps", "50", "--guidance", "2.5",
        "--seed", "-1",
        "--catvton-path", catvton_path,
    ], capture_output=True, text=True, timeout=600)

Exit codes:
    0 = success
    1 = generic error
    10 = CatVTON not available (import failed)
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from PIL import Image
import numpy as np
import mediapipe


def _load_image(path: str) -> "Image.Image":
    with open(path, "rb") as f:
        return Image.open(f).convert("RGB")


def _save_image(img: "Image.Image", path: str):
    img.save(path, format="JPEG", quality=95)


# ─── MediaPipe-based mask generation ──────────────────────────────────────────

_MP_POSE_LANDMARKER_TASK: str | None = None


def _get_pose_landmarker_model_path() -> str | None:
    """Find or download PoseLandmarker .task model file."""
    global _MP_POSE_LANDMARKER_TASK
    if _MP_POSE_LANDMARKER_TASK:
        return _MP_POSE_LANDMARKER_TASK

    # Search common locations
    candidates = [
        Path(__file__).parent.parent.parent / "models" / "pose_landmarker_heavy.task",
        Path.home() / ".cache" / "mediapipe-assets" / "pose_landmarker_heavy.task",
        Path.home() / "models" / "pose_landmarker_heavy.task",
        Path("D:/models/pose_landmarker_heavy.task"),
    ]
    for p in candidates:
        if p.exists():
            _MP_POSE_LANDMARKER_TASK = str(p.resolve())
            logger.info(f"Found PoseLandmarker model: {_MP_POSE_LANDMARKER_TASK}")
            return _MP_POSE_LANDMARKER_TASK

    # Try to download
    model_url = (
        "https://storage.googleapis.com/mediapipe-models/"
        "pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
    )
    download_path = Path.home() / ".cache" / "mediapipe-assets" / "pose_landmarker_heavy.task"
    try:
        download_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading PoseLandmarker model to {download_path}...")
        import urllib.request
        urllib.request.urlretrieve(model_url, download_path)
        _MP_POSE_LANDMARKER_TASK = str(download_path.resolve())
        logger.info(f"Downloaded PoseLandmarker model: {_MP_POSE_LANDMARKER_TASK}")
        return _MP_POSE_LANDMARKER_TASK
    except Exception as e:
        logger.warning(f"Failed to download PoseLandmarker model: {e}")
        return None


def _draw_pose_skeleton(
    person_img: "Image.Image",
    landmarks: list,
) -> "Image.Image":
    """Draw skeleton lines on the person image for debugging."""
    import cv2
    pw, ph = person_img.size
    canvas = person_img.convert("RGB")
    arr = np.array(canvas)
    arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    # Skeleton connections: (from_idx, to_idx)
    connections = [
        (11, 12),  # shoulders
        (11, 13), (13, 15),  # left arm
        (12, 14), (14, 16),  # right arm
        (11, 23), (12, 24),  # torso
        (23, 24),  # hips
        (23, 25), (25, 27),  # left leg
        (24, 26), (26, 28),  # right leg
    ]
    for i, j in connections:
        if i < len(landmarks) and j < len(landmarks):
            lm_i = landmarks[i]
            lm_j = landmarks[j]
            x1, y1 = int(lm_i.x * pw), int(lm_i.y * ph)
            x2, y2 = int(lm_j.x * pw), int(lm_j.y * ph)
            cv2.line(arr, (x1, y1), (x2, y2), (0, 255, 0), 3)

    # Draw keypoints
    for lm in landmarks:
        x, y = int(lm.x * pw), int(lm.y * ph)
        cv2.circle(arr, (x, y), 5, (0, 0, 255), -1)

    arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(arr, mode="RGB")


def _debug_save_intermediates(
    person_img: "Image.Image",
    cloth_mask: "Image.Image",
    landmarks: list | None,
    output_dir: Path,
    step: str,
):
    """Save intermediate debug images (pose skeleton, cloth mask, person+mask overlay)."""
    try:
        debug_dir = output_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)

        # Save person image
        person_img.save(debug_dir / f"{step}_01_person.jpg", quality=95)

        # Save cloth mask
        cloth_mask.save(debug_dir / f"{step}_02_cloth_mask.jpg")

        # Save skeleton overlay
        if landmarks:
            skeleton = _draw_pose_skeleton(person_img, landmarks)
            skeleton.save(debug_dir / f"{step}_03_skeleton.jpg", quality=95)

        # Save mask overlay on person
        person_np = np.array(person_img.convert("RGB")).astype(np.float32)
        mask_np = np.array(cloth_mask.convert("L")).astype(np.float32) / 255.0
        mask_3ch = np.stack([mask_np] * 3, axis=-1)
        overlay_np = person_np * mask_3ch + person_np * 0.3 * (1 - mask_3ch)
        overlay = Image.fromarray(overlay_np.astype(np.uint8), mode="RGB")
        overlay.save(debug_dir / f"{step}_04_mask_overlay.jpg", quality=95)

        logger.info(f"Debug images saved to {debug_dir}/")
    except Exception as e:
        logger.warning(f"Failed to save debug images: {e}")


def _make_cloth_mask_mediapipe(
    person_img: "Image.Image",
    cloth_type: str,
    debug_output_dir: Path | None = None,
) -> "Image.Image":
    """
    Generate cloth-agnostic mask using MediaPipe PoseLandmarker.

    Returns a PIL Image (L mode, white=garment region to edit, black=preserve).
    Falls back to a simple rectangular mask if MediaPipe fails.
    """
    import cv2
    import numpy as np

    # ── Step 1: Get pose keypoints ──────────────────────────────────────
    mp_pose_path = _get_pose_landmarker_model_path()
    if mp_pose_path is None:
        logger.warning("MediaPipe PoseLandmarker model not found — using fallback mask")
        return _fallback_mask(person_img, cloth_type)

    try:
        from mediapipe import Image as MPImage
        from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

        # MediaPipe 0.10.x Image has no create_from_array; save to temp file then load
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp_path = f.name
        person_img.save(tmp_path, format="JPEG", quality=95)
        options = PoseLandmarkerOptions(
            base_options=mediapipe.tasks.BaseOptions(model_asset_path=mp_pose_path),
            running_mode=RunningMode.IMAGE,
            output_segmentation_masks=True,
        )
        landmarker = PoseLandmarker.create_from_options(options)
        mp_img = MPImage.create_from_file(tmp_path)
        result = landmarker.detect(mp_img)
        landmarker.close()
        os.unlink(tmp_path)

        if not result.pose_landmarks:
            logger.warning("No pose detected — using fallback mask")
            return _fallback_mask(person_img, cloth_type)

        landmarks = result.pose_landmarks[0]
    except Exception as e:
        logger.warning(f"MediaPipe pose detection failed ({e}) — using fallback mask")
        return _fallback_mask(person_img, cloth_type)

    # ── Step 2: Build person segmentation mask from PoseLandmarker ──────
    if result.segmentation_masks and len(result.segmentation_masks) > 0:
        seg_mask = result.segmentation_masks[0]
        seg_np = (seg_mask.numpy_view() * 255).astype(np.uint8)
        if seg_np.ndim == 3:
            seg_np = seg_np[..., 0]
        seg_pil = Image.fromarray(seg_np, mode="L")
    else:
        # Fallback: create mask from keypoints convex hull
        seg_pil = _make_keypoint_hull_mask(person_img, landmarks)

    # ── Step 3: Apply cloth-type region ────────────────────────────────
    pw, ph = person_img.size
    mask = _apply_cloth_region(
        seg_pil, landmarks, cloth_type, pw, ph
    )

    # ── Step 4: Protect face region ─────────────────────────────────────
    mask = _protect_face(mask, landmarks, pw, ph)

    # ── Step 5: Save debug intermediates ───────────────────────────────
    if debug_output_dir is not None:
        _debug_save_intermediates(person_img, mask, landmarks, debug_output_dir, cloth_type)

    return mask


def _make_keypoint_hull_mask(
    person_img: "Image.Image",
    landmarks: list,
) -> "Image.Image":
    """Create person body mask from pose landmarks using convex hull."""
    import cv2
    import numpy as np
    from PIL import Image

    pw, ph = person_img.size
    points = []
    for lm in landmarks:
        x = int(lm.x * pw)
        y = int(lm.y * ph)
        points.append([x, y])

    mask = np.zeros((ph, pw), dtype=np.uint8)
    if len(points) > 3:
        hull = cv2.convexHull(np.array(points, dtype=np.int32))
        cv2.fillPoly(mask, [hull], 255)

    # Dilate slightly to include body edges
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=2)

    return Image.fromarray(mask, mode="L")


def _apply_cloth_region(
    person_mask: "Image.Image",
    landmarks: list,
    cloth_type: str,
    pw: int,
    ph: int,
) -> "Image.Image":
    """Intersect person mask with cloth-type region rectangle."""
    import cv2
    import numpy as np
    from PIL import Image

    person_np = np.asarray(person_mask)
    region = _get_cloth_region_rect(landmarks, cloth_type, pw, ph)
    if region is None:
        return Image.fromarray(person_np, mode="L")

    x0, y0, x1, y1 = region
    cloth_mask = np.zeros_like(person_np)
    cloth_mask[y0:y1, x0:x1] = 255

    # Intersect with person mask (body area)
    combined = cv2.bitwise_and(person_np, cloth_mask)

    # Slight dilation to ensure garment region covers body
    kernel = np.ones((3, 3), np.uint8)
    combined = cv2.dilate(combined, kernel, iterations=1)

    return Image.fromarray(combined, mode="L")


def _get_cloth_region_rect(
    landmarks: list,
    cloth_type: str,
    pw: int,
    ph: int,
) -> tuple[int, int, int, int] | None:
    """Get clothing region rectangle (x0, y0, x1, y1) from pose landmarks."""
    # Build landmark dict
    lm_dict = {lm_idx: (lm.x * pw, lm.y * ph) for lm_idx, lm in enumerate(landmarks)}

    def clamp(val, lo, hi):
        return max(lo, min(hi, int(val)))

    if cloth_type == "upper":
        ls = lm_dict.get(11)  # left_shoulder
        rs = lm_dict.get(12)  # right_shoulder
        lh = lm_dict.get(23)  # left_hip
        rh = lm_dict.get(24)  # right_hip

        shoulder_y = (ls[1] + rs[1]) / 2 if ls and rs else None
        hip_y = (lh[1] + rh[1]) / 2 if lh and rh else None
        if shoulder_y is None or hip_y is None:
            return _upper_fallback(pw, ph)

        x_pts = [p[0] for p in [ls, rs] if p]
        y_top = max(0.0, shoulder_y / ph - 0.09)
        y_bottom = min(1.0, hip_y / ph + 0.04)
        x_left = max(0.0, min(x_pts) / pw - 0.04) if x_pts else 0.12
        x_right = min(1.0, max(x_pts) / pw + 0.04) if x_pts else 0.88

        return (
            clamp(x_left * pw, 0, pw - 2),
            clamp(y_top * ph, 0, ph - 2),
            clamp(x_right * pw, 2, pw),
            clamp(y_bottom * ph, 2, ph),
        )

    elif cloth_type == "lower":
        lh = lm_dict.get(23)
        rh = lm_dict.get(24)
        la = lm_dict.get(27)  # left_ankle
        ra = lm_dict.get(28)  # right_ankle
        lk = lm_dict.get(25)  # left_knee
        rk = lm_dict.get(26)  # right_knee

        hip_y = (lh[1] + rh[1]) / 2 if lh and rh else None
        ankle_y = None
        if la and ra:
            ankle_y = (la[1] + ra[1]) / 2
        elif lk and rk:
            ankle_y = (lk[1] + rk[1]) / 2

        if hip_y is None:
            return _lower_fallback(pw, ph)

        x_pts = [p[0] for p in [lh, rh, la, ra] if p]
        y_top = max(0.0, hip_y / ph - 0.04)
        y_bottom = min(1.0, (ankle_y / ph + 0.03) if ankle_y else 0.97)
        x_left = max(0.0, (min(x_pts) / pw - 0.06) if x_pts else 0.16)
        x_right = min(1.0, (max(x_pts) / pw + 0.06) if x_pts else 0.84)

        return (
            clamp(x_left * pw, 0, pw - 2),
            clamp(y_top * ph, 0, ph - 2),
            clamp(x_right * pw, 2, pw),
            clamp(y_bottom * ph, 2, ph),
        )

    else:  # overall / dress
        # Upper + lower combined = full body
        upper = _get_cloth_region_rect(landmarks, "upper", pw, ph)
        lower = _get_cloth_region_rect(landmarks, "lower", pw, ph)
        if upper is None and lower is None:
            return None
        if upper is None:
            return lower
        if lower is None:
            return upper
        return (
            min(upper[0], lower[0]),
            min(upper[1], lower[1]),
            max(upper[2], lower[2]),
            max(upper[3], lower[3]),
        )


def _upper_fallback(pw: int, ph: int) -> tuple[int, int, int, int]:
    return (
        max(0, int(pw * 0.12)),
        max(0, int(ph * 0.12)),
        min(pw, int(pw * 0.88)),
        min(ph, int(ph * 0.60)),
    )


def _lower_fallback(pw: int, ph: int) -> tuple[int, int, int, int]:
    return (
        max(0, int(pw * 0.16)),
        max(0, int(ph * 0.44)),
        min(pw, int(pw * 0.84)),
        min(ph, int(ph * 0.97)),
    )


def _protect_face(
    mask: "Image.Image",
    landmarks: list,
    pw: int,
    ph: int,
) -> "Image.Image":
    """Protect face region by clearing it from the mask (prevents AI from changing face)."""
    import cv2
    import numpy as np
    from PIL import Image

    # Use nose + ear landmarks to define face ellipse
    nose = landmarks[0] if len(landmarks) > 0 else None
    l_ear = landmarks[7] if len(landmarks) > 7 else None
    r_ear = landmarks[8] if len(landmarks) > 8 else None

    if nose is None:
        return mask

    # Face center: nose position
    cx = int(nose.x * pw)
    cy = int(nose.y * ph)

    # Estimate face size from ear landmarks
    if l_ear and r_ear:
        ear_dist = abs(l_ear.x - r_ear.x) * pw
    else:
        ear_dist = pw * 0.12

    ew = max(5, int(ear_dist * 1.2))
    eh = max(5, int(ew * 1.3))

    mask_np = np.asarray(mask)
    rows, cols = mask_np.shape

    # Create ellipse
    y_grid, x_grid = np.ogrid[:rows, :cols]
    face_ellipse = (
        ((x_grid - cx) ** 2) // max(1, ew ** 2)
        + ((y_grid - (cy - int(ew * 0.1))) ** 2) // max(1, eh ** 2)
    ) <= 1

    mask_np[face_ellipse] = 0
    return Image.fromarray(mask_np, mode="L")


def _fallback_mask(person_img: "Image.Image", cloth_type: str) -> "Image.Image":
    """Simple rectangular mask as last resort."""
    pw, ph = person_img.size
    if cloth_type == "upper":
        region = _upper_fallback(pw, ph)
    elif cloth_type == "lower":
        region = _lower_fallback(pw, ph)
    else:
        # overall: upper + lower
        upper = _upper_fallback(pw, ph)
        lower = _lower_fallback(pw, ph)
        region = (
            min(upper[0], lower[0]),
            min(upper[1], lower[1]),
            max(upper[2], lower[2]),
            max(upper[3], lower[3]),
        )

    import numpy as np
    mask = np.zeros((ph, pw), dtype=np.uint8)
    x0, y0, x1, y1 = region
    mask[y0:y1, x0:x1] = 255

    from PIL import Image
    return Image.fromarray(mask, mode="L")


# ─── Mask & Repaint Post-processing ──────────────────────────────────────────

def resize_and_crop_garment(image, size):
    """Center-crop garment to target size, preserving aspect ratio."""
    w, h = image.size
    target_w, target_h = size
    # Determine crop box to match target aspect ratio
    target_ratio = target_w / target_h
    img_ratio = w / h
    if img_ratio > target_ratio:
        # Image is wider than target: crop width
        new_w = int(h * target_ratio)
        new_h = h
        x0 = (w - new_w) // 2
        y0 = 0
    else:
        # Image is taller than target: crop height
        new_w = w
        new_h = int(w / target_ratio)
        x0 = 0
        y0 = (h - new_h) // 2
    cropped = image.crop((x0, y0, x0 + new_w, y0 + new_h))
    return cropped.resize(size, Image.LANCZOS)


def _feather_mask(mask: "Image.Image", feather_radius: int = 4) -> "Image.Image":
    """Apply Gaussian blur to mask edges for smooth garment transition."""
    import cv2
    mask_np = np.asarray(mask.convert("L"))
    blurred = cv2.GaussianBlur(mask_np, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
    return Image.fromarray(blurred, mode="L")


def _repaint_with_feather(
    result: "Image.Image",
    person: "Image.Image",
    mask: "Image.Image",
    feather_radius: int = 3,
) -> "Image.Image":
    """
    Blend CatVTON result with original person using a feathered mask.
    feather_radius controls edge softness: higher = softer edge (no ghosting).
    """
    import cv2
    mask_np = np.asarray(mask.convert("L")).astype(np.float32) / 255.0
    # Feather the edge
    if feather_radius > 0:
        mask_np = cv2.GaussianBlur(mask_np, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
    mask_3ch = np.stack([mask_np] * 3, axis=-1)
    result_np = np.array(result).astype(np.float32)
    person_np = np.array(person).astype(np.float32)
    blended = result_np * mask_3ch + person_np * (1 - mask_3ch)
    return Image.fromarray(blended.astype(np.uint8))


# ─── Memory optimization helpers ───────────────────────────────────────────────


def _apply_memory_optimizations(pipeline, args):
    """Apply VRAM optimization techniques to the CatVTON pipeline.

    Strategies:
    1. Sequential CPU Offload: moves UNet/VAE to CPU when not computing (saves ~4-6GB VRAM)
    2. Force empty cache before inference
    """
    import gc
    import torch

    applied = []

    # Sequential CPU Offload: moves each component to CPU after use
    # This is the most effective for 8GB cards
    if getattr(args, "cpu_offload", False):
        try:
            from diffusers import enable_sequential_cpu_offload

            enable_sequential_cpu_offload(pipeline.unet)
            enable_sequential_cpu_offload(pipeline.vae)
            applied.append("sequential_cpu_offload")
            logger.info("Applied sequential CPU offload to UNet and VAE")
        except Exception as e:
            logger.warning(f"Could not apply sequential CPU offload: {e}")

    # Force garbage collection and empty cache
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

    # Report VRAM usage
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        logger.info(f"VRAM after optimizations: {allocated:.2f}GB allocated, {reserved:.2f}GB reserved")

    return applied


# ─── Main inference ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CatVTON inference runner (subprocess)")
    parser.add_argument("--person", required=True, help="Path to person image JPEG")
    parser.add_argument("--garment", required=True, help="Path to garment image JPEG")
    parser.add_argument("--output", required=True, help="Path to write result JPEG")
    parser.add_argument(
        "--type", default="upper", choices=["upper", "lower", "overall"],
        help="Garment type"
    )
    parser.add_argument("--width", type=int, default=512,
                        help="Output width (default: 512, use 768 for high quality but needs more VRAM)")
    parser.add_argument("--height", type=int, default=768,
                        help="Output height (default: 768, use 1024 for high quality but needs more VRAM)")
    parser.add_argument("--steps", type=int, default=25,
                        help="Diffusion steps (default: 25, use 50 for high quality but slower)")
    parser.add_argument("--guidance", type=float, default=2.5)
    parser.add_argument("--seed", type=int, default=-1)
    parser.add_argument("--catvton-path", default=None, help="Path to CatVTON repo")
    parser.add_argument("--no-repaint", action="store_true")
    parser.add_argument(
        "--precision", default="bf16",
        choices=["bf16", "fp16", "fp32"],
        help="Weight precision: bf16 (default, ~8GB VRAM), fp16 (~6GB VRAM), fp32 (~10GB VRAM)"
    )
    parser.add_argument(
        "--cpu-offload", action="store_true",
        help="Enable sequential CPU offload for UNet/VAE (reduces VRAM to ~4GB, slower)"
    )
    parser.add_argument(
        "--debug-dir", default=None,
        help="Directory to save debug intermediate images (mask, skeleton, overlays)"
    )
    args = parser.parse_args()

    person_path = args.person
    garment_path = args.garment
    output_path = args.output

    if args.catvton_path:
        os.environ["CATVTON_PATH"] = args.catvton_path

    logger.info(
        f"CatVTON runner: type={args.type}, size={args.width}x{args.height}, "
        f"steps={args.steps}, guidance={args.guidance}, seed={args.seed}, "
        f"repaint={not args.no_repaint}"
    )

    try:
        # ── Import CatVTON ────────────────────────────────────────────────
        catvton_path = args.catvton_path or os.environ.get("CATVTON_PATH", "")
        sys.path.insert(0, catvton_path)

        try:
            from model.pipeline import CatVTONPipeline
        except ImportError as e:
            print(f"ERROR:CATVTON_NOT_AVAILABLE")
            print(f"CatVTON pipeline import failed: {e}")
            print("Set --catvton-path to the CatVTON repository directory.")
            sys.exit(10)

        # ── Load images ────────────────────────────────────────────────────
        person_img = _load_image(person_path)
        garment_img = _load_image(garment_path)

        # ── Generate cloth-agnostic mask via MediaPipe ────────────────────
        logger.info(f"Generating cloth mask (type={args.type}) via MediaPipe...")
        debug_output_dir = Path(args.debug_dir) if args.debug_dir else None
        cloth_mask = _make_cloth_mask_mediapipe(person_img, args.type, debug_output_dir=debug_output_dir)
        logger.info("Mask generated successfully")

        # ── Initialize CatVTON Pipeline ───────────────────────────────────
        import os as _os
        from huggingface_hub import snapshot_download
        from utils import init_weight_dtype, resize_and_crop, resize_and_padding

        repo_path = _os.path.join(catvton_path, "zhengchong_CatVTON")
        if not _os.path.exists(repo_path):
            logger.info("Downloading CatVTON checkpoints from HuggingFace (first run)...")
            repo_path = snapshot_download(repo_id="zhengchong/CatVTON")

        # Use user-specified precision (default bf16, fp16 for 8GB cards)
        precision = getattr(args, "precision", "bf16")
        weight_dtype = init_weight_dtype(precision)

        pipeline = CatVTONPipeline(
            base_ckpt="runwayml/stable-diffusion-inpainting",
            attn_ckpt=repo_path,
            attn_ckpt_version="mix",
            weight_dtype=weight_dtype,
            use_tf32=(precision in ("fp16", "bf16")),
            device="cuda",
            skip_safety_check=True,
        )

        # Apply memory optimizations (CPU offload, cache cleanup)
        _apply_memory_optimizations(pipeline, args)

        # ── Resize images ────────────────────────────────────────────────
        person_resized = resize_and_crop(person_img, (args.width, args.height))
        # Center-crop garment to match output aspect ratio (avoids padding distortion)
        garment_resized = resize_and_crop_garment(garment_img, (args.width, args.height))
        mask_resized = cloth_mask.resize(
            (args.width, args.height), Image.LANCZOS
        )
        # Light feather to smooth mask boundary (prevents harsh edge artifacts)
        mask_resized = _feather_mask(mask_resized, feather_radius=3)

        # Save resized debug inputs
        if debug_output_dir is not None:
            debug_dir = debug_output_dir / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            person_resized.save(debug_dir / "05_person_resized.jpg", quality=95)
            garment_resized.save(debug_dir / "06_garment_resized.jpg", quality=95)
            mask_resized.save(debug_dir / "07_mask_resized.jpg")
            logger.info(f"Resized debug images saved to {debug_dir}/")

        # ── Run inference ─────────────────────────────────────────────────
        seed = args.seed if args.seed >= 0 else None
        generator = None
        if seed is not None:
            import torch
            generator = torch.Generator(device="cuda").manual_seed(seed)

        logger.info("Starting CatVTON diffusion inference...")
        result = pipeline(
            image=person_resized,
            condition_image=garment_resized,
            mask=mask_resized,
            num_inference_steps=args.steps,
            guidance_scale=args.guidance,
            width=args.width,
            height=args.height,
            generator=generator,
        )[0]

        # ── Repaint with feathered blend (no ghosting) ───────────────────
        if not args.no_repaint:
            logger.info("Repainting with feathered blend...")
            result = _repaint_with_feather(result, person_resized, mask_resized, feather_radius=3)

        # ── Save result ───────────────────────────────────────────────────
        _save_image(result, output_path)
        logger.info(f"SUCCESS: result saved to {output_path}")
        print(f"SUCCESS:{output_path}")
        sys.exit(0)

    except Exception as e:
        logger.error(f"CatVTON inference failed: {e}", exc_info=True)
        tb = traceback.format_exc()
        print(f"ERROR:{e}")
        print(f"TRACE:{tb}")
        sys.exit(1)


if __name__ == "__main__":
    main()
