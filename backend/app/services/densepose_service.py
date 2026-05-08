"""DensePose service using Detectron2 for body surface mapping.

DensePose provides dense human body surface coordinates (IUV mapping)
that describe:
- Body part labels (torso, arms, head, etc.)
- U coordinate (horizontal position within body part)
- V coordinate (vertical position within body part)

This enables:
- Shoulder curvature and orientation
- Arm depth/angle
- Chest/bust curvature
- Natural cloth draping on body surface

Detectron2 + DensePose installation:
    pip install 'git+https://github.com/facebookresearch/detectron2.git'
    # Or use the lighter community fork:
    # pip install detectron2 (with pre-built wheels from https://dl.fbaipublicfiles.com/detectron2/)

Usage:
    from app.services.densepose_service import DensePoseWrapper

    dp = DensePoseWrapper()
    result = dp.detect(image)  # returns IUV map
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Dict, Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

__all__ = ["DensePoseWrapper", "DensePoseResult", "apply_densepose_warp"]


@dataclass
class DensePoseResult:
    """DensePose detection result."""

    iuv_image: Image.Image
    iuv_array: np.ndarray  # (H, W, 3) — I=part_id, U, V channels
    person_mask: np.ndarray  # (H, W) — 1 = person, 0 = background
    part_labels: dict[int, str]  # part_id → name
    success: bool
    method: str  # "detectron2" | "mediapipe_body" | "none"


# DensePose part IDs (from Detectron2 DensePose)
_DENSEPOSE_PARTS = {
    0: "background",
    1: "head",
    2: "torso_back",
    3: "torso_front",
    4: "left_arm_back",
    5: "left_arm_front",
    6: "right_arm_back",
    7: "right_arm_front",
    8: "left_leg_back",
    9: "left_leg_front",
    10: "right_leg_back",
    11: "right_leg_front",
}


def _create_body_surface_map(
    image: Image.Image,
    landmarks: list,
) -> np.ndarray:
    """Create a simplified body surface map from MediaPipe pose landmarks.

    This is a fallback when Detectron2 DensePose is not available.
    It estimates body parts from pose keypoints.

    Returns:
        IUV array: (H, W, 3) with I=part_id, U=x/width, V=y/height
    """
    w, h = image.size
    iuv = np.zeros((h, w, 3), dtype=np.float32)

    if not landmarks or len(landmarks) < 24:
        return iuv

    def lm(idx: int) -> tuple[float, float] | None:
        if len(landmarks) <= idx:
            return None
        lm = landmarks[idx]
        return (lm.x * w, lm.y * h)

    # Map keypoints to pixel coords
    nose = lm(0)
    ls = lm(11)  # left_shoulder
    rs = lm(12)  # right_shoulder
    lh = lm(23)  # left_hip
    rh = lm(24)  # right_hip
    la = lm(27)  # left_ankle
    ra = lm(28)  # right_ankle

    if not (ls and rs and lh and rh):
        return iuv

    # Build body polygons
    # Torso: shoulder line → hip line
    torso_pts = []
    if ls:
        torso_pts.append(ls)
    if rs:
        torso_pts.append(rs)
    if rh:
        torso_pts.append(rh)
    if lh:
        torso_pts.append(lh)

    if len(torso_pts) >= 3:
        
        torso_np = np.array(torso_pts, dtype=np.int32)
        torso_np[:, 0] = np.clip(torso_np[:, 0], 0, w - 1)
        torso_np[:, 1] = np.clip(torso_np[:, 1], 0, h - 1)
        torso_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(torso_mask, [torso_np], 255)
        # Torso front (I=3), U=(x-ls.x)/(rs.x-ls.x), V=(y-ls.y)/(lh.y-ls.y)
        for y in range(h):
            for x in range(w):
                if torso_mask[y, x] > 0:
                    u_val = (x - ls[0]) / max(rs[0] - ls[0], 1)
                    v_val = (y - ls[1]) / max(lh[1] - ls[1], 1)
                    iuv[y, x] = [3, u_val, v_val]

    # Arms
    for shoulder_idx, elbow_idx, wrist_idx, part_id_back, part_id_front in [
        (11, 13, 15, 4, 5),  # left arm
        (12, 14, 16, 6, 7),  # right arm
    ]:
        sh = lm(shoulder_idx)
        el = lm(elbow_idx)
        wr = lm(wrist_idx)
        if sh and el and wr:
            
            arm_pts = [sh, el, wr]
            arm_np = np.array(arm_pts, dtype=np.int32)
            arm_np[:, 0] = np.clip(arm_np[:, 0], 0, w - 1)
            arm_np[:, 1] = np.clip(arm_np[:, 1], 0, h - 1)
            # Thicken arm
            arm_mask = np.zeros((h, w), dtype=np.uint8)
            cv2.line(arm_mask, (int(sh[0]), int(sh[1])), (int(el[0]), int(el[1])), 255, 10)
            cv2.line(arm_mask, (int(el[0]), int(el[1])), (int(wr[0]), int(wr[1])), 255, 8)
            for y in range(h):
                for x in range(w):
                    if arm_mask[y, x] > 0 and iuv[y, x, 0] == 0:
                        iuv[y, x] = [part_id_front, x / max(w, 1), y / max(h, 1)]

    return iuv


class DensePoseWrapper:
    """Wrapper for Detectron2 DensePose (with MediaPipe fallback)."""

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        self._predictor = None
        self._initialized = False

    def _load(self):
        """Lazy-load Detectron2 model."""
        if self._initialized:
            return

        try:
            from detectron2.config import get_cfg
            from detectron2.engine.defaults import DefaultPredictor
            from detectron2.model_zoo import get_checkpoint_url, model_zoo

            cfg = get_cfg()
            cfg.merge_from_file(
                model_zoo.get_checkpoint_url("COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml")
            )
            cfg.MODEL.DEVICE = "cuda" if _has_cuda() else "cpu"

            if self.model_path and Path(self.model_path).exists():
                cfg.MODEL.WEIGHTS = self.model_path
            else:
                # Use DensePose model
                cfg.merge_from_file(
                    model_zoo.get_checkpoint_url(
                        "COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml"
                    )
                )
                try:
                    cfg.MODEL.WEIGHTS = get_checkpoint_url("COCO-DensePose/R_50_FPN.yaml")
                except Exception:
                    logger.warning("DensePose checkpoint not found, using standard mask_rcnn")
                    cfg.MODEL.WEIGHTS = get_checkpoint_url(
                        "COCO-InstanceSegmentation/mask_rcnn_R_50_FPN_3x.yaml"
                    )

            cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.5
            cfg.MODEL.ROI_HEADS.NMS_THRESH_TEST = 0.3

            self._predictor = DefaultPredictor(cfg)
            self._initialized = True
            logger.info("[DENSEPOSE] Detectron2 DensePose model loaded")
        except ImportError:
            logger.warning("[DENSEPOSE] detectron2 not installed, using MediaPipe fallback")
            self._predictor = None
            self._initialized = True
        except Exception as e:
            logger.warning(f"[DENSEPOSE] Failed to load Detectron2: {e}")
            self._predictor = None
            self._initialized = True

    def detect(self, image: Image.Image) -> DensePoseResult:
        """Detect DensePose on the given image.

        Args:
            image: PIL RGB image of a person.

        Returns:
            DensePoseResult with IUV map and metadata.
        """
        self._load()

        arr = np.array(image.convert("RGB"))

        if self._predictor is not None:
            return self._detect_detectron2(arr, image)
        else:
            return self._detect_mediapipe_fallback(image)

    def _detect_detectron2(self, arr: np.ndarray, image: Image.Image) -> DensePoseResult:
        """Use Detectron2 DensePose."""
        try:
            
            outputs = self._predictor(arr)
            instances = outputs.get("instances")
            if instances is None or len(instances) == 0:
                logger.warning("[DENSEPOSE] No person detected by Detectron2")
                return self._detect_mediapipe_fallback(image)

            pred_classes = instances.pred_classes
            masks = instances.pred_masks
            if pred_classes is None or masks is None:
                return self._detect_mediapipe_fallback(image)

            # Find person instance (class 0 = person in COCO)
            person_idx = None
            for i, cls in enumerate(pred_classes):
                if int(cls) == 0:
                    person_idx = i
                    break

            if person_idx is None:
                return self._detect_mediapipe_fallback(image)

            mask = masks[person_idx].cpu().numpy().astype(np.uint8) * 255

            # Try to get DensePose IUV
            densepose = instances.get("pred_densepose")
            if densepose is not None:
                iuv = densepose[person_idx]
                # IUV format: I=part_id, U, V
                i_image = (iuv.invmask * 255).cpu().numpy().astype(np.uint8)
                u_image = (iuv.u * 255).clamp(0, 255).cpu().numpy().astype(np.uint8)
                v_image = (iuv.v * 255).clamp(0, 255).cpu().numpy().astype(np.uint8)
                iuv_combined = np.stack([i_image, u_image, v_image], axis=-1)
                logger.info("[DENSEPOSE] Detectron2 DensePose detected successfully")
                return DensePoseResult(
                    iuv_image=Image.fromarray(iuv_combined),
                    iuv_array=iuv_combined,
                    person_mask=mask,
                    part_labels=_DENSEPOSE_PARTS,
                    success=True,
                    method="detectron2",
                )

            # No DensePose output, use segmentation mask only
            iuv_np = np.zeros((arr.shape[0], arr.shape[1], 3), dtype=np.uint8)
            iuv_np[:, :, 0] = mask
            iuv_np[:, :, 1] = np.linspace(0, 255, arr.shape[1]).astype(np.uint8)
            iuv_np[:, :, 2] = np.linspace(0, 255, arr.shape[0]).astype(np.uint8)
            return DensePoseResult(
                iuv_image=Image.fromarray(iuv_np),
                iuv_array=iuv_np,
                person_mask=mask,
                part_labels=_DENSEPOSE_PARTS,
                success=True,
                method="detectron2_segmentation",
            )
        except Exception as e:
            logger.warning(f"[DENSEPOSE] Detectron2 detection failed: {e}")
            return self._detect_mediapipe_fallback(image)

    def _detect_mediapipe_fallback(self, image: Image.Image) -> DensePoseResult:
        """Use MediaPipe PoseLandmarker as fallback for body surface map."""
        try:
            from app.services.person_crop import _detect_mediapipe_pose_fast

            landmarks, seg_mask = _detect_mediapipe_pose_fast(image)
            if not landmarks:
                w, h = image.size
                return DensePoseResult(
                    iuv_image=Image.new("RGB", (w, h)),
                    iuv_array=np.zeros((h, w, 3), dtype=np.float32),
                    person_mask=np.zeros((h, w), dtype=np.uint8),
                    part_labels=_DENSEPOSE_PARTS,
                    success=False,
                    method="none",
                )

            iuv_np = _create_body_surface_map(image, landmarks)
            person_mask = (iuv_np[:, :, 0] > 0).astype(np.uint8) * 255

            # Convert to uint8 for PIL
            iuv_u8 = np.clip(iuv_np * 255, 0, 255).astype(np.uint8)
            iuv_image = Image.fromarray(iuv_u8, mode="RGB")

            return DensePoseResult(
                iuv_image=iuv_image,
                iuv_array=iuv_np,
                person_mask=person_mask,
                part_labels=_DENSEPOSE_PARTS,
                success=True,
                method="mediapipe_body",
            )
        except Exception as e:
            logger.warning(f"[DENSEPOSE] MediaPipe fallback failed: {e}")
            w, h = image.size
            return DensePoseResult(
                iuv_image=Image.new("RGB", (w, h)),
                iuv_array=np.zeros((h, w, 3), dtype=np.float32),
                person_mask=np.zeros((h, w), dtype=np.uint8),
                part_labels=_DENSEPOSE_PARTS,
                success=False,
                method="none",
            )


def _has_cuda() -> bool:
    """Check if CUDA is available."""
    try:
        import torch

        return torch.cuda.is_available()
    except ImportError:
        return False


def apply_densepose_warp(
    cloth: Image.Image,
    densepose_result: DensePoseResult,
    cloth_type: str = "upper",
) -> np.ndarray:
    """Use DensePose IUV map to warp cloth onto body surface.

    This provides natural cloth draping on body curves:
    - Shoulders: cloth follows shoulder curvature
    - Arms: cloth stretches around arm
    - Torso: cloth follows chest/stomach curve

    Args:
        cloth: PIL Image of the garment (RGBA or RGB).
        densepose_result: DensePose detection result.
        cloth_type: "upper" | "lower" | "overall"

    Returns:
        Warp field: (H, W, 2) — (x_disp, y_disp) for each pixel
    """
    iuv = densepose_result.iuv_array
    person_mask = densepose_result.person_mask
    h, w = iuv.shape[:2]

    warp_field = np.zeros((h, w, 2), dtype=np.float32)

    if not densepose_result.success or person_mask.sum() < 1000:
        logger.warning("[DENSEPOSE-WARP] No valid DensePose data, returning zero warp")
        return warp_field

    # For each body part, compute a warp vector
    for part_id, part_name in densepose_result.part_labels.items():
        if part_id == 0:
            continue

        part_mask = (iuv[:, :, 0] == part_id).astype(np.uint8)

        if part_mask.sum() < 100:
            continue

        u_coords = iuv[:, :, 1][part_mask > 0]
        v_coords = iuv[:, :, 2][part_mask > 0]

        if len(u_coords) == 0:
            continue

        # Compute cloth target positions from IUV
        # U → x position in cloth
        # V → y position in garment
        cw, ch = cloth.size
        cloth_u = u_coords * cw
        cloth_v = v_coords * ch

        # Actual pixel positions in the result image
        ys, xs = np.where(part_mask > 0)

        # Warp: where should each pixel source from in the cloth?
        # This is an inverse warp — for each output pixel, find source position
        for i in range(len(ys)):
            y, x = ys[i], xs[i]
            src_x = int(cloth_u[i])
            src_y = int(cloth_v[i])
            src_x = np.clip(src_x, 0, cw - 1)
            src_y = np.clip(src_y, 0, ch - 1)

            # The garment is positioned so that shoulders map to the cloth top
            if cloth_type == "upper":
                # Torso front (3): cloth maps to upper body
                if part_id == 3:
                    # Simple centering warp
                    warp_field[y, x] = [
                        (src_x - cw / 2) * 0.3,
                        (src_y - ch * 0.3) * 0.2,
                    ]
                elif part_id in (5, 7):  # arms
                    warp_field[y, x] = [
                        (src_x - cw / 2) * 0.4,
                        (src_y - ch * 0.4) * 0.3,
                    ]
            elif cloth_type == "lower":
                if part_id in (9, 11):  # legs
                    warp_field[y, x] = [
                        (src_x - cw / 2) * 0.3,
                        (src_y - ch * 0.2) * 0.3,
                    ]

    logger.info(f"[DENSEPOSE-WARP] Warp field computed for cloth_type={cloth_type}")
    return warp_field
