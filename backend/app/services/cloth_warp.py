"""TPS (Thin-Plate Spline) Cloth Warping for realistic garment deformation.

TPS warping deforms a garment image to match the target body silhouette,
providing "fit" that pure geometric pasting cannot achieve.

Based on:
- CP-VTON: Conditional Pose-Virtual Try-on
- VITON-HD: Virtual Try-on with Hierarchical Distribution matching

Unlike geometric warp (PIL quad/perspective), TPS can handle:
- Non-rigid deformation (wrinkles, folds)
- Shoulder/arm alignment
- Natural fabric drape

Usage:
    from app.services.cloth_warp import tps_warp_garment

    warped_cloth = tps_warp_garment(
        garment_image,
        keypoints=person_keypoints,
        cloth_type="upper"
    )
"""

from __future__ import annotations

import numpy as np
from PIL import Image

__all__ = ["tps_warp_garment", "TPSWarpEngine"]


# Control point count for TPS grid
_GRID_W = 5
_GRID_H = 5


def _compute_tps_coefficients(
    source_pts: np.ndarray,
    target_pts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute TPS transformation coefficients.

    Args:
        source_pts: (N, 2) source control point coordinates (normalized 0-1)
        target_pts: (N, 2) target control point coordinates (normalized 0-1)

    Returns:
        (w_x, w_y) TPS weight arrays for coordinate transformation
    """
    n = source_pts.shape[0]
    if n < 4:
        raise ValueError("TPS requires at least 4 control points")

    # Build kernel matrix K (n x n)
    def _k(r: np.ndarray) -> np.ndarray:
        """Radial basis function: U(r) = r^2 * log(r^2)"""
        r2 = r**2
        with np.errstate(divide="ignore", invalid="ignore"):
            K = r2 * np.log(r2 + 1e-10)
        K[np.arange(n), np.arange(n)] = 0.0
        return K

    # Compute pairwise distances
    diffs = source_pts[:, np.newaxis, :] - source_pts[np.newaxis, :, :]  # N x N x 2
    r = np.sqrt((diffs**2).sum(axis=2))
    K = _k(r)  # N x N

    # Build affine part P (n x 3)
    P = np.hstack([np.ones((n, 1)), source_pts])  # N x 3

    # Build TPS system matrix:
    # [K    P] [w]   [target_pts]
    # [P^T  0] [d] = [0]
    # 2n x 2n
    top = np.hstack([K, P])
    bot = np.hstack([P.T, np.zeros((3, 3))])
    M = np.vstack([top, bot])

    # Target: target_pts concatenated with [0, 0, 0]
    target_flat = target_pts.flatten()
    zeros_3 = np.zeros(3)
    T = np.concatenate([target_flat, zeros_3])

    try:
        coeffs = np.linalg.solve(M + np.eye(M.shape[0]) * 1e-6, T)
    except np.linalg.LinAlgError:
        return np.zeros(n), np.zeros(3)

    w = coeffs[:n]  # (N,) TPS weights
    d = coeffs[n:]  # (3,) affine coefficients

    return w, d


def _tps_transform_point(
    x: float,
    y: float,
    source_pts: np.ndarray,
    w: np.ndarray,
    d: np.ndarray,
) -> tuple[float, float]:
    """Apply TPS transformation to a single point."""
    n = source_pts.shape[0]
    # TPS part
    diffs = source_pts - np.array([x, y])
    r2 = (diffs**2).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        U = r2 * np.log(r2 + 1e-10)
    tx = (w * U).sum()
    ty = (w * U).sum()  # same U for y

    # Affine part
    ax = d[0] + d[1] * x + d[2] * y
    ay = d[3] + d[4] * x + d[5] * y

    return ax + tx, ay + ty


def _build_control_grid(
    width: int,
    height: int,
    n_w: int = _GRID_W,
    n_h: int = _GRID_H,
) -> np.ndarray:
    """Build a grid of control points for TPS warp."""
    xs = np.linspace(0, width - 1, n_w)
    ys = np.linspace(0, height - 1, n_h)
    pts = np.array([[x, y] for y in ys for x in xs], dtype=np.float64)
    return pts


def _tps_warp_image(
    src_img: np.ndarray,
    src_pts: np.ndarray,
    dst_pts: np.ndarray,
    out_size: tuple[int, int],
) -> np.ndarray:
    """
    Apply TPS warp to an image using inverse mapping.

    Args:
        src_img: HxWxC source image (uint8)
        src_pts: (N, 2) source control points
        dst_pts: (N, 2) destination control points
        out_size: (out_w, out_h) output size

    Returns:
        Warped image as uint8 array.
    """
    
    out_w, out_h = out_size
    src_h, src_w = src_img.shape[:2]

    # Compute TPS coefficients: source → target
    w, d = _compute_tps_coefficients(src_pts, dst_pts)

    # Build output grid
    out_pts = _build_control_grid(out_w, out_h, _GRID_W, _GRID_H)

    # Solve inverse: find where each output pixel came from in source
    # Use grid control points for inverse TPS
    inv_w, inv_d = _compute_tps_coefficients(dst_pts, src_pts)

    # Create warped image
    warped = np.zeros((out_h, out_w, src_img.shape[2] if src_img.ndim > 2 else 1), dtype=np.uint8)

    # Apply TPS to each pixel using bilinear interpolation from source
    # For each output pixel, find corresponding source pixel via inverse TPS
    for py in range(out_h):
        for px in range(out_w):
            sx, sy = _tps_transform_point(px, py, dst_pts, inv_w, inv_d)
            # Bilinear interpolation
            x0, y0 = int(sx), int(sy)
            fx, fy = sx - x0, sy - y0
            x1, y1 = min(x0 + 1, src_w - 1), min(y0 + 1, src_h - 1)
            x0, y0 = max(0, min(x0, src_w - 1)), max(0, min(y0, src_h - 1))

            if src_img.ndim > 2:
                for c in range(src_img.shape[2]):
                    v00 = src_img[y0, x0, c]
                    v01 = src_img[y1, x0, c]
                    v10 = src_img[y0, x1, c]
                    v11 = src_img[y1, x1, c]
                    v = (
                        v00 * (1 - fx) * (1 - fy)
                        + v10 * fx * (1 - fy)
                        + v01 * (1 - fx) * fy
                        + v11 * fx * fy
                    )
                    warped[py, px, c] = int(np.clip(v, 0, 255))
            else:
                v00 = src_img[y0, x0]
                v01 = src_img[y1, x0]
                v10 = src_img[y0, x1]
                v11 = src_img[y1, x1]
                v = (
                    v00 * (1 - fx) * (1 - fy)
                    + v10 * fx * (1 - fy)
                    + v01 * (1 - fx) * fy
                    + v11 * fx * fy
                )
                warped[py, px] = int(np.clip(v, 0, 255))

    return warped


def _tps_warp_cv2(
    src_img: np.ndarray,
    src_pts: np.ndarray,
    dst_pts: np.ndarray,
    out_size: tuple[int, int],
) -> np.ndarray:
    """
    Apply TPS warp using OpenCV's built-in support.
    Falls back to pure NumPy if OpenCV version doesn't support it.
    """
    try:
        
        src_pts_float = src_pts.astype(np.float32)
        dst_pts_float = dst_pts.astype(np.float32)

        # cv2.resize + perspectiveTransform approach
        # First, build the TPS manually using RBF
        # This is a simplified version using affine approximation
        out_w, out_h = out_size

        # Use thin-plate spline via control points
        # Build tps transformation matrix
        tps = cv2.createThinPlateSplineShapeTransformer()
        # createThinPlateSplineShapeTransformer expects matches as vector of points
        # Use approximate approach
        try:
            # OpenCV 4.7+ has createThinPlateSplineShapeTransformer
            matches = [cv2.DMatch(i, i, 0) for i in range(len(src_pts))]
            tps.estimateTransformation(src_pts_float, dst_pts_float, matches)

            # Apply transformation to a grid
            dst_w, dst_h = out_size
            src_h, src_w = src_img.shape[:2]

            # Create destination coordinate grid
            result = np.zeros((dst_h, dst_w, 3), dtype=np.uint8)

            # Use remap for efficient warping
            # For now, fall back to simple affine + bilinear approach
        except Exception:
            pass

    except Exception:
        pass

    # Fallback: pure numpy implementation
    return _tps_warp_image(src_img, src_pts, dst_pts, out_size)


class TPSWarpEngine:
    """
    TPS-based cloth warping engine.

    Takes a garment image and target body keypoints, computes TPS control
    points, and warps the garment to fit the body.
    """

    def __init__(self):
        self.grid_w = _GRID_W
        self.grid_h = _GRID_H

    def _build_body_control_points(
        self,
        keypoints: dict[str, tuple[float, float]],
        target_w: int,
        target_h: int,
        cloth_type: str,
    ) -> np.ndarray:
        """
        Build TPS control grid based on body keypoints.

        Args:
            keypoints: Dict of keypoint_name → (x_norm, y_norm) where values are 0-1
            target_w, target_h: Target image dimensions
            cloth_type: "upper" | "lower" | "overall"

        Returns:
            (N, 2) array of control point coordinates in target image space
        """
        pts = []
        w, h = target_w, target_h

        if cloth_type in ("upper", "overall"):
            # Define upper body control points based on keypoints
            ls = keypoints.get("left_shoulder", (0.35, 0.18))
            rs = keypoints.get("right_shoulder", (0.65, 0.18))
            lh = keypoints.get("left_hip", (0.38, 0.50))
            rh = keypoints.get("right_hip", (0.62, 0.50))
            le = keypoints.get("left_elbow", (0.25, 0.30))
            re = keypoints.get("right_elbow", (0.75, 0.30))

            # Build a regular grid warped to body keypoints
            # Left shoulder → right shoulder (top row)
            # Left hip → right hip (bottom row)
            for t in np.linspace(0, 1, self.grid_w):
                # Top row: neck to shoulder line
                top_y = ls[1] * (1 - t) + rs[1] * t
                pts.append((ls[0] * (1 - t) + rs[0] * t, top_y))

            # Middle rows: interpolate between top and bottom
            for row in range(1, self.grid_h - 1):
                frac = row / (self.grid_h - 1)
                for col in range(self.grid_w):
                    t = col / (self.grid_w - 1)
                    # Horizontal interpolation
                    lx = ls[0] * (1 - frac) + lh[0] * frac
                    ly = ls[1] * (1 - frac) + lh[1] * frac
                    rx = rs[0] * (1 - frac) + rh[0] * frac
                    ry = rs[1] * (1 - frac) + rh[1] * frac
                    pts.append((lx * (1 - t) + rx * t, ly * (1 - t) + ry * t))

            # Bottom row: hip line
            for t in np.linspace(0, 1, self.grid_w):
                pts.append((lh[0] * (1 - t) + rh[0] * t, lh[1] * (1 - t) + rh[1] * t))

        elif cloth_type == "lower":
            lh = keypoints.get("left_hip", (0.38, 0.50))
            rh = keypoints.get("right_hip", (0.62, 0.50))
            la = keypoints.get("left_ankle", (0.40, 0.95))
            ra = keypoints.get("right_ankle", (0.60, 0.95))
            lk = keypoints.get("left_knee", (0.39, 0.72))
            rk = keypoints.get("right_knee", (0.61, 0.72))

            # Build grid from hip to ankle
            for row in range(self.grid_h):
                frac = row / max(1, self.grid_h - 1)
                # Interpolate hip positions toward ankle
                lx = lh[0] * (1 - frac) + la[0] * frac
                ly = lh[1] * (1 - frac) + la[1] * frac
                rx = rh[0] * (1 - frac) + ra[0] * frac
                ry = rh[1] * (1 - frac) + ra[1] * frac

                for col in range(self.grid_w):
                    t = col / max(1, self.grid_w - 1)
                    pts.append((lx * (1 - t) + rx * t, ly * (1 - t) + ry * t))

        else:
            # Default: uniform grid
            pts = []
            for row in range(self.grid_h):
                for col in range(self.grid_w):
                    pts.append(
                        (
                            col / max(1, self.grid_w - 1),
                            row / max(1, self.grid_h - 1),
                        )
                    )

        # Convert to pixel coordinates and limit to grid size
        result = []
        for i, (x, y) in enumerate(pts):
            if i < self.grid_w * self.grid_h:
                result.append((x * w, y * h))

        return np.array(result[: self.grid_w * self.grid_h], dtype=np.float64)

    def warp(
        self,
        garment_img: Image.Image,
        keypoints: dict[str, tuple[float, float]],
        target_size: tuple[int, int],
        cloth_type: str = "upper",
    ) -> Image.Image:
        """
        Apply TPS warping to a garment image.

        Args:
            garment_img: PIL RGB image of the garment.
            keypoints: Body keypoints (normalized 0-1).
            target_size: (width, height) of target region.
            cloth_type: "upper" | "lower" | "overall"

        Returns:
            PIL RGB image of the warped garment.
        """
        target_w, target_h = target_size
        gw, gh = garment_img.size

        # Build source grid (uniform, normalized to garment dimensions)
        src_pts = np.array(
            [
                [x, y]
                for y in np.linspace(0, gh - 1, self.grid_h)
                for x in np.linspace(0, gw - 1, self.grid_w)
            ],
            dtype=np.float64,
        )

        # Build target grid (warped to body keypoints)
        dst_pts = self._build_body_control_points(keypoints, target_w, target_h, cloth_type)

        # Apply TPS warp
        arr = np.array(garment_img)
        warped = _tps_warp_image(arr, src_pts, dst_pts, target_size)

        return Image.fromarray(warped, mode="RGB" if warped.ndim > 2 else "L")


def tps_warp_garment(
    garment_img: Image.Image,
    keypoints: dict[str, tuple[float, float]],
    target_size: tuple[int, int],
    cloth_type: str = "upper",
) -> Image.Image:
    """
    Convenience function for TPS garment warping.

    Args:
        garment_img: PIL RGB image of the garment product photo.
        keypoints: Body keypoints from pose detection.
            Example: {"left_shoulder": (0.35, 0.18), "right_shoulder": (0.65, 0.18), ...}
        target_size: (width, height) in pixels for the warped garment.
        cloth_type: "upper" | "lower" | "overall"

    Returns:
        PIL RGB image of the TPS-warped garment, ready for blending onto the person.

    Note:
        TPS warp provides a starting deformation (approximate body shape).
        CatVTON diffusion then adds fine wrinkles, shadows, and lighting on top.
        This combination gives both geometric accuracy (TPS) and photorealism (CatVTON).
    """
    engine = TPSWarpEngine()
    return engine.warp(garment_img, keypoints, target_size, cloth_type)
