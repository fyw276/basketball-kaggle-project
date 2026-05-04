"""
CatVTON inference engine for virtual try-on.

Architecture:
- CatVTONPipeline: Core diffusion model (SD v1.5 inpainting base + CatVTON attention)
- MediaPipe PoseLandmarker: Body keypoints + person segmentation mask (no SCHP/DensePose needed)
- Supports: upper body, lower body, and overall (dress) garments

Requirements:
- Python 3.9
- CUDA GPU with >= 8GB VRAM (bf16 mixed precision)
- CatVTON dependencies: pip install -r requirements.txt (see CatVTON repo)
- MediaPipe (auto-installed)

Inputs:
- person_image: PIL Image, full-body person photo
- garment_image: PIL Image, garment product photo (no model)
- cloth_type: "upper" | "lower" | "overall"

Outputs:
- PIL Image: person wearing the garment

Installation:
    git clone https://github.com/Zheng-Chong/CatVTON.git
    cd CatVTON
    conda create -n catvton python==3.9.0
    conda activate catvton
    pip install -r requirements.txt
    # CatVTON checkpoints auto-download from HuggingFace on first run
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)

CATVTON_PATH = os.environ.get("CATVTON_PATH", str(Path.home() / "CatVTON"))

CatVTONPipeline = None
VaeImageProcessor = None

try:
    sys.path.insert(0, CATVTON_PATH)
    from model.pipeline import CatVTONPipeline as _Pipeline
    from diffusers.image_processor import VaeImageProcessor as _VaeImageProcessor
    CatVTONPipeline = _Pipeline
    VaeImageProcessor = _VaeImageProcessor
    logger.info(f"CatVTON loaded from {CATVTON_PATH}")
except ImportError as e:
    logger.warning(f"CatVTON not available: {e}")
    logger.warning(f"Expected path: {CATVTON_PATH}")


# ─── MediaPipe-based mask generation (no SCHP/DensePose required) ──────────────

_MP_POSE_MODEL_PATH: str | None = None


def _get_mediapipe_pose_path() -> str | None:
    """Find or return None (will use fallback)."""
    global _MP_POSE_MODEL_PATH
    if _MP_POSE_MODEL_PATH:
        return _MP_POSE_MODEL_PATH
    candidates = [
        Path.home() / ".cache" / "mediapipe-assets" / "pose_landmarker_heavy.task",
        Path("D:/models/pose_landmarker_heavy.task"),
    ]
    for p in candidates:
        if p.exists():
            _MP_POSE_MODEL_PATH = str(p.resolve())
            return _MP_POSE_MODEL_PATH
    return None


def _run_mediapipe_pose(img: Image.Image):
    """
    Run MediaPipe PoseLandmarker on a PIL image.
    Returns (landmarks_list, segmentation_masks) or (None, None) on failure.
    landmarks_list: list of PoseLandmarkerResult-style landmark objects with .x, .y, .visibility
    """
    try:
        from mediapipe import Image as MPImage
        from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
        import mediapipe.tasks

        model_path = _get_mediapipe_pose_path()
        if model_path is None:
            return None, None

        options = PoseLandmarkerOptions(
            base_options=mediapipe.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.IMAGE,
            output_segmentation_masks=True,
        )
        landmarker = PoseLandmarker.create_from_options(options)
        # MediaPipe 0.10.x Image has no create_from_array; save to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp_path = f.name
        img.convert("RGB").save(tmp_path, format="JPEG", quality=95)
        mp_img = MPImage.create_from_file(tmp_path)
        result = landmarker.detect(mp_img)
        landmarker.close()
        os.unlink(tmp_path)
        if not result.pose_landmarks:
            return None, None
        return result.pose_landmarks[0], result.segmentation_masks
    except Exception as e:
        logger.warning(f"MediaPipe pose failed: {e}")
        return None, None


def _make_body_mask_from_pose(
    person_img: Image.Image,
    cloth_type: str,
) -> Image.Image:
    """
    Generate cloth-agnostic body mask using MediaPipe PoseLandmarker.
    Falls back to polygon mask if MediaPipe fails.

    改进（v2）：使用 polygon fillPoly 替代矩形 mask，更贴合人体轮廓。
    Returns PIL Image (L mode, 255=garment region to edit).
    """
    landmarks, seg_masks = _run_mediapipe_pose(person_img)
    pw, ph = person_img.size

    # Use segmentation mask if available
    if seg_masks and len(seg_masks) > 0:
        seg = seg_masks[0]
        seg_np = (seg.numpy_view() * 255).astype(np.uint8)
        person_mask = Image.fromarray(seg_np, mode="L").resize((pw, ph), Image.LANCZOS)
    else:
        person_mask = _make_polygon_person_mask(pw, ph, cloth_type)

    # Intersect with cloth-type region
    if landmarks:
        polygon = _get_cloth_region_polygon(landmarks, cloth_type, pw, ph)
        region_mask = _polygon_to_mask(polygon, pw, ph)
        pm = np.array(person_mask)
        rm = np.array(region_mask)
        combined = cv2.bitwise_and(pm, rm)

        # Key fix: when MediaPipe segmentation is too sparse (dark clothes),
        # fall back to the keypoint polygon directly so CatVTON has a usable region
        white_ratio = int(np.sum(combined > 0)) / max(1, pm.size)
        if white_ratio < 0.05:
            logger.warning(
                f"MediaPipe segmentation sparse (ratio={white_ratio:.3f}), "
                "using keypoint polygon mask"
            )
            kernel = np.ones((5, 5), np.uint8)
            combined = cv2.dilate(rm, kernel, iterations=2)
        else:
            kernel = np.ones((3, 3), np.uint8)
            combined = cv2.dilate(combined, kernel, iterations=1)

        person_mask = Image.fromarray(combined, mode="L")

    # Protect face
    if landmarks and len(landmarks) > 0:
        person_mask = _clear_face(person_mask, landmarks, pw, ph)

    return person_mask


def _get_cloth_region_polygon(landmarks, cloth_type: str, pw: int, ph: int):
    """Return polygon vertices (list of (x,y) pixel tuples) for cloth region.

    改进（v2）：使用 polygon 替代矩形，更贴合人体轮廓。
    """
    def pt(idx):
        if len(landmarks) <= idx:
            return None
        lm = landmarks[idx]
        return (lm.x * pw, lm.y * ph)

    def clamp(val, lo, hi):
        return max(lo, min(hi, int(val)))

    if cloth_type == "upper":
        ls, rs = pt(11), pt(12)
        lh, rh = pt(23), pt(24)

        if not (ls and rs and lh and rh):
            return _upper_polygon_fallback(pw, ph)

        pts = []
        pts.append((clamp(ls[0], 0, pw), clamp(ls[1], 0, ph)))
        pts.append((clamp(rs[0], 0, pw), clamp(rs[1], 0, ph)))
        pts.append((clamp(rh[0], 0, pw), clamp(rh[1], 0, ph)))
        pts.append((clamp(lh[0], 0, pw), clamp(lh[1], 0, ph)))

        le, re = pt(13), pt(14)
        if le:
            pts.insert(1, (clamp(int(le[0] * 0.6 + ls[0] * 0.4), 0, pw), clamp(int(le[1] * 0.6 + ls[1] * 0.4), 0, ph)))
        if re:
            pts.insert(len(pts) - 1, (clamp(int(re[0] * 0.6 + rs[0] * 0.4), 0, pw), clamp(int(re[1] * 0.6 + rs[1] * 0.4), 0, ph)))

        return pts

    elif cloth_type == "lower":
        lh, rh = pt(23), pt(24)
        la, ra = pt(27), pt(28)
        lk, rk = pt(25), pt(26)

        if not (lh and rh):
            return _lower_polygon_fallback(pw, ph)

        pts = []
        pts.append((clamp(lh[0], 0, pw), clamp(lh[1], 0, ph)))
        pts.append((clamp(rh[0], 0, pw), clamp(rh[1], 0, ph)))
        if ra:
            pts.append((clamp(ra[0], 0, pw), clamp(ra[1], 0, ph)))
        if la:
            pts.append((clamp(la[0], 0, pw), clamp(la[1], 0, ph)))
        if lk:
            pts.append((clamp(lk[0], 0, pw), clamp(lk[1], 0, ph)))
        if rk:
            pts.append((clamp(rk[0], 0, pw), clamp(rk[1], 0, ph)))

        return pts

    else:  # overall
        u = _get_cloth_region_polygon(landmarks, "upper", pw, ph)
        l = _get_cloth_region_polygon(landmarks, "lower", pw, ph)
        if not u and not l:
            return _full_polygon_fallback(pw, ph)
        return u if u else l


def _upper_polygon_fallback(pw: int, ph: int):
    cx = pw // 2
    return [
        (cx - int(pw * 0.18), int(ph * 0.16)),
        (cx + int(pw * 0.18), int(ph * 0.16)),
        (cx + int(pw * 0.14), int(ph * 0.52)),
        (cx - int(pw * 0.14), int(ph * 0.52)),
    ]


def _lower_polygon_fallback(pw: int, ph: int):
    cx = pw // 2
    return [
        (cx - int(pw * 0.14), int(ph * 0.46)),
        (cx + int(pw * 0.14), int(ph * 0.46)),
        (cx + int(pw * 0.10), int(ph * 0.95)),
        (cx - int(pw * 0.10), int(ph * 0.95)),
    ]


def _full_polygon_fallback(pw: int, ph: int):
    cx = pw // 2
    return [
        (cx - int(pw * 0.18), int(ph * 0.16)),
        (cx + int(pw * 0.18), int(ph * 0.16)),
        (cx + int(pw * 0.10), int(ph * 0.95)),
        (cx - int(pw * 0.10), int(ph * 0.95)),
    ]


def _polygon_to_mask(polygon: list, pw: int, ph: int) -> Image.Image:
    """Create binary mask from polygon vertices using cv2.fillPoly."""
    m = np.zeros((ph, pw), dtype=np.uint8)
    if len(polygon) >= 3:
        cv2.fillPoly(m, [np.array(polygon, dtype=np.int32)], 255)
    return Image.fromarray(m, mode="L")


def _make_polygon_person_mask(pw: int, ph: int, cloth_type: str) -> Image.Image:
    """Create polygon-based person mask fallback using proportional estimates.

    改进（v2）：使用 polygon 替代矩形 mask。
    """
    if cloth_type == "upper":
        pts = _upper_polygon_fallback(pw, ph)
    elif cloth_type == "lower":
        pts = _lower_polygon_fallback(pw, ph)
    else:
        pts = _full_polygon_fallback(pw, ph)

    m = np.zeros((ph, pw), dtype=np.uint8)
    if len(pts) >= 3:
        cv2.fillPoly(m, [np.array(pts, dtype=np.int32)], 255)
    return Image.fromarray(m, mode="L")


def _clear_face(mask: Image.Image, landmarks, pw: int, ph: int) -> Image.Image:
    """Clear face region from mask to prevent AI from modifying face."""
    nose = landmarks[0] if len(landmarks) > 0 else None
    if nose is None:
        # FIX: 无关键点时保护顶部40%区域
        m = np.asarray(mask)
        m[0:int(ph * 0.40), :] = 0
        return Image.fromarray(m, mode="L")

    cx = int(nose.x * pw)
    cy = int(nose.y * ph)
    l_ear = landmarks[7] if len(landmarks) > 7 else None
    r_ear = landmarks[8] if len(landmarks) > 8 else None
    ew = int(abs(l_ear.x - r_ear.x) * pw * 0.75) if l_ear and r_ear else max(5, int(pw * 0.15))
    eh = int(ew * 1.8)  # FIX: 使用更大的高度覆盖整个头部

    m = np.asarray(mask)
    rows, cols = m.shape
    y_g, x_g = np.ogrid[:rows, :cols]

    # 主面部椭圆（覆盖更大的区域）
    ellipse = (
        ((x_g - cx) ** 2) // max(1, ew**2)
        + ((y_g - (cy - int(ew*0.3))) ** 2) // max(1, eh**2)
    ) <= 1
    m[ellipse] = 0

    # FIX: 额外保护脖颈以上区域
    shoulder_l = landmarks[11] if len(landmarks) > 11 else None
    shoulder_r = landmarks[12] if len(landmarks) > 12 else None
    if shoulder_l and shoulder_r:
        neck_y = int((shoulder_l.y + shoulder_r.y) / 2 * ph * 0.95)
        m[0:neck_y, :] = 0

    return Image.fromarray(m, mode="L")


class CatVTONEngine:
    """
    High-level CatVTON inference wrapper.

    Supports:
    - MediaPipe-based automatic mask generation (no SCHP/DensePose required)
    - Manual mask override if provided
    - bf16 / fp16 / fp32 precision
    - Background repaint (--repaint mode)
    """

    def __init__(
        self,
        catvton_path: Optional[str] = None,
        width: int = 768,
        height: int = 1024,
        mixed_precision: str = "bf16",
        allow_tf32: bool = True,
        repaint: bool = True,
        device: Optional[str] = None,
    ):
        if CatVTONPipeline is None:
            raise ImportError(
                "CatVTON not found. Please install it first.\n"
                f"Expected path: {catvton_path or CATVTON_PATH}\n"
                "Set CATVTON_PATH environment variable to CatVTON directory.\n"
                "Installation: git clone https://github.com/Zheng-Chong/CatVTON.git"
            )

        self.catvton_path = catvton_path or CATVTON_PATH
        self.width = width
        self.height = height
        self.repaint = repaint

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        if self.device == "cpu":
            logger.warning("CatVTON requires CUDA GPU. Running on CPU will be extremely slow.")

        weight_dtype_map = {"no": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}
        self.weight_dtype = weight_dtype_map.get(mixed_precision, torch.bfloat16)
        self.mixed_precision = mixed_precision

        if self.device == "cpu" and self.weight_dtype != torch.float32:
            logger.warning("CPU mode: forcing float32 precision")
            self.weight_dtype = torch.float32

        logger.info(f"Initializing CatVTONEngine on {self.device}, dtype={self.weight_dtype}")
        logger.info(f"Image size: {width}x{height}, mixed_precision={mixed_precision}")

        self._init_models()

    def _init_models(self):
        import os
        from huggingface_hub import snapshot_download
        from utils import init_weight_dtype

        repo_path = os.path.join(self.catvton_path, "zhengchong_CatVTON")
        if not os.path.exists(repo_path):
            logger.info("Downloading CatVTON checkpoints from HuggingFace (first run)...")
            repo_path = snapshot_download(repo_id="zhengchong/CatVTON")

        self.pipeline = CatVTONPipeline(
            base_ckpt="runwayml/stable-diffusion-inpainting",
            attn_ckpt=repo_path,
            attn_ckpt_version="mix",
            weight_dtype=self.weight_dtype,
            use_tf32=(self.mixed_precision in ("fp16", "bf16")),
            device=self.device,
            skip_safety_check=True,
        )

        # Mask processor for post-processing (feathering)
        self.mask_processor = VaeImageProcessor(
            vae_scale_factor=8,
            do_normalize=False,
            do_binarize=True,
            do_convert_grayscale=True,
        )

        logger.info("CatVTONEngine initialized successfully (MediaPipe mask generation)")

    def infer(
        self,
        person_image: Image.Image,
        garment_image: Image.Image,
        cloth_type: str = "upper",
        num_inference_steps: int = 50,
        guidance_scale: float = 2.5,
        seed: Optional[int] = None,
        mask_image: Optional[Image.Image] = None,
    ) -> Image.Image:
        if cloth_type not in {"upper", "lower", "overall"}:
            raise ValueError(
                f"Invalid cloth_type: {cloth_type}. Must be 'upper', 'lower', or 'overall'."
            )

        logger.info(
            f"CatVTON inference: cloth_type={cloth_type}, "
            f"steps={num_inference_steps}, guidance={guidance_scale}, "
            f"mask={'manual' if mask_image else 'MediaPipe-auto'}, seed={seed}"
        )

        # ── 强制验证：pipe 类型必须为 CatVTONPipeline ───────────────────────
        if not isinstance(self.pipeline, type(CatVTONPipeline)):
            raise TypeError(
                f"Pipeline type mismatch: expected CatVTONPipeline, got {type(self.pipeline).__name__}. "
                f"Model may not be loaded correctly."
            )

        try:
            person_image = person_image.convert("RGB")
            garment_image = garment_image.convert("RGB")

            # Generate or use provided mask
            if mask_image is not None:
                mask_resized = mask_image.convert("L").resize(
                    (self.width, self.height), Image.NEAREST
                )
                m = np.array(mask_resized)
                m[m > 0] = 255
                mask_resized = Image.fromarray(m)
            else:
                body_mask = _make_body_mask_from_pose(person_image, cloth_type)
                body_mask = body_mask.resize(
                    (self.width, self.height), Image.NEAREST
                )
                mask_resized = body_mask

            # Generator for reproducibility
            generator = None
            if seed is not None and seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            # ── 预处理（不计推理耗时）──────────────────────────────────────
            from utils import resize_and_crop, resize_and_padding
            from app.services.garment_preprocess import preprocess_garment

            garment_np = preprocess_garment(garment_image, canvas_size=512)
            garment_clean = Image.fromarray(garment_np, mode="RGB")
            garment_resized = resize_and_padding(garment_clean, (self.width, self.height))
            person_resized = resize_and_crop(person_image, (self.width, self.height))

            # ── CatVTON 扩散推理 ───────────────────────────────────────────
            import time
            print("START CATVTON", flush=True)
            infer_start = time.perf_counter()

            result = self.pipeline(
                image=person_resized,
                condition_image=garment_resized,
                mask=mask_resized,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                width=self.width,
                height=self.height,
                generator=generator,
            )[0]

            infer_elapsed = time.perf_counter() - infer_start
            print(f"END CATVTON (duration={infer_elapsed:.2f}s)", flush=True)

            if infer_elapsed < 2.0:
                raise RuntimeError(
                    f"Inference completed in {infer_elapsed:.2f}s — suspiciously fast. "
                    f"Model may not be running on GPU or may be using a stub."
                )

            # Repaint with original background
            if self.repaint:
                result = self._repaint_result(result, person_resized, mask_resized)

            logger.info("CatVTON inference completed successfully")
            return result

        except Exception as e:
            print(f"[CATVTON-ERROR] {type(e).__name__}: {e}", flush=True)
            raise RuntimeError(f"CatVTON inference failed: {e}") from e

    def _feather_mask(self, mask: Image.Image, feather_radius: int = 3) -> Image.Image:
        """Apply Gaussian blur to mask edges for smooth garment boundaries."""
        mask_np = np.asarray(mask.convert("L"))
        blurred = cv2.GaussianBlur(mask_np, (0, 0), sigmaX=feather_radius, sigmaY=feather_radius)
        return Image.fromarray(blurred, mode="L")

    def _repaint_result(
        self, result: Image.Image, person: Image.Image, mask: Image.Image
    ) -> Image.Image:
        result_np = np.array(result).astype(np.float32)
        person_np = np.array(person).astype(np.float32)
        mask_np = np.asarray(mask.convert("L")).astype(np.float32) / 255.0
        # Feather mask edges to eliminate ghosting at blend boundary
        mask_np = cv2.GaussianBlur(mask_np, (0, 0), sigmaX=3, sigmaY=3)
        mask_3ch = np.stack([mask_np] * 3, axis=-1)
        repainted = result_np * mask_3ch + person_np * (1 - mask_3ch)
        return Image.fromarray(repainted.astype(np.uint8))

    def warmup(self, num_steps: int = 1):
        logger.info("Warming up CatVTONEngine...")
        dummy_person = Image.fromarray(
            np.random.randint(0, 255, (self.height, self.width, 3), dtype=np.uint8)
        )
        dummy_garment = Image.fromarray(
            np.random.randint(0, 255, (self.height, self.width, 3), dtype=np.uint8)
        )
        try:
            self.infer(dummy_person, dummy_garment, "upper", num_steps=num_steps, seed=0)
            logger.info("CatVTONEngine warmup completed")
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")


_engine: Optional[CatVTONEngine] = None


def get_engine(catvton_path: Optional[str] = None, **kwargs) -> CatVTONEngine:
    global _engine
    if _engine is None:
        logger.info("Creating CatVTONEngine singleton")
        _engine = CatVTONEngine(catvton_path=catvton_path, **kwargs)
    return _engine


def is_available() -> bool:
    return CatVTONPipeline is not None


def get_device_info() -> dict:
    return {
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "catvton_path": CATVTON_PATH,
        "catvton_available": is_available(),
    }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="CatVTON inference")
    parser.add_argument("--person", required=True)
    parser.add_argument("--garment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--type", default="upper", choices=["upper", "lower", "overall"])
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--guidance", type=float, default=2.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--no-repaint", action="store_true")
    args = parser.parse_args()

    print("Device Info:")
    for k, v in get_device_info().items():
        print(f"  {k}: {v}")

    if not is_available():
        print("ERROR: CatVTON not available. Set CATVTON_PATH.")
        sys.exit(1)

    engine = get_engine(width=args.width, height=args.height, repaint=not args.no_repaint)
    engine.warmup()

    person = Image.open(args.person).convert("RGB")
    garment = Image.open(args.garment).convert("RGB")

    result = engine.infer(
        person_image=person,
        garment_image=garment,
        cloth_type=args.type,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        seed=args.seed,
    )

    result.save(args.output)
    print(f"Saved result to {args.output}")
