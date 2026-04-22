"""Deterministic 2D warp + paste engine for Try-on v2 pipeline A (bottom garments).

Goal: keep identity/background, only replace bottom garment area using
simple geometric warps. This is not a physics simulation; it's a stable,
explainable heuristic intended for the v2 MVP and regression testing.

v2 upgrade: uses MediaPipe Pose keypoints (shoulders/hips/ankles) when available
for accurate garment placement. Falls back to gradient energy estimation if
MediaPipe is unavailable or pose detection fails.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageFilter

from app.services.tryon_v2.garment_struct import cutout_garment_rgba, split_pants_parts
from app.services.tryon_v2.pose_utils import detect_pose_keypoints, get_body_bounds_from_keypoints


@dataclass
class WarpMetadata:
    engine: str
    waistband_box: tuple[int, int, int, int]
    left_leg_box: tuple[int, int, int, int]
    right_leg_box: tuple[int, int, int, int]
    alpha_feather_px: int


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def _pil_quad_warp(
    src_rgba: Image.Image, dst_size: tuple[int, int], quad: tuple[int, ...]
) -> Image.Image:
    """Warp src into dst_size using a quad mapping (PIL perspective)."""
    return src_rgba.transform(
        dst_size,
        Image.Transform.QUAD,
        quad,
        resample=Image.Resampling.BICUBIC,
    )


def _feather_alpha(rgba: Image.Image, radius_px: int) -> Image.Image:
    if rgba.mode != "RGBA":
        rgba = rgba.convert("RGBA")
    r, g, b, a = rgba.split()
    if radius_px <= 0:
        return rgba
    a2 = a.filter(ImageFilter.GaussianBlur(radius=float(radius_px)))
    return Image.merge("RGBA", (r, g, b, a2))


def _upper_protect_mask(size: tuple[int, int], protect_until_y: int) -> Image.Image:
    """Build L mask where protected area has alpha=0 (no overwrite)."""
    w, h = size
    protect_until_y = _clamp_int(protect_until_y, 0, h)
    mask = Image.new("L", (w, h), color=255)
    if protect_until_y > 0:
        mask.paste(0, (0, 0, w, protect_until_y))
    return mask


def _person_foreground_mask(person_image: Image.Image) -> np.ndarray | None:
    """Best-effort person foreground mask (H,W) bool.

    Uses OpenCV GrabCut if available. This mask is used to better localize torso/legs
    so garments can auto-adjust position and size based on the person's shape.
    """
    try:
        import cv2  # type: ignore

        arr = np.asarray(person_image.convert("RGB"))
        h, w = arr.shape[:2]
        if h < 96 or w < 96:
            return None

        mask = np.zeros((h, w), np.uint8)
        bgdModel = np.zeros((1, 65), np.float64)
        fgdModel = np.zeros((1, 65), np.float64)
        rect = (int(w * 0.10), int(h * 0.06), int(w * 0.80), int(h * 0.90))
        cv2.grabCut(arr, mask, rect, bgdModel, fgdModel, 2, cv2.GC_INIT_WITH_RECT)
        fg = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
        if fg.mean() < 0.05:
            return None
        return fg
    except Exception:
        return None


def _bounds_from_mask(
    fg: np.ndarray, *, y0: int, y1: int, col_q: float, row_q: float
) -> tuple[int, int, int, int] | None:
    """Estimate (x0,x1, y_top, y_bottom) from a foreground mask within a y-range."""
    h, w = fg.shape[:2]
    y0 = _clamp_int(int(y0), 0, h - 2)
    y1 = _clamp_int(int(y1), y0 + 2, h)
    roi = fg[y0:y1, :]
    if roi.size == 0:
        return None

    col = roi.mean(axis=0)
    cthr = float(np.quantile(col, col_q))
    xs = np.where(col >= max(cthr, 0.05))[0]
    if xs.size < max(10, int(w * 0.10)):
        return None
    x0, x1 = int(xs.min()), int(xs.max()) + 1

    row = fg[:, x0:x1].mean(axis=1)
    seg = row[y0:y1]
    rthr = float(np.quantile(seg, row_q)) if seg.size else float(np.quantile(row, row_q))
    ys = np.where(row >= max(rthr, 0.06))[0]
    ys = ys[(ys >= y0) & (ys <= y1)]
    if ys.size < 10:
        return None
    yt, yb = int(ys.min()), int(ys.max()) + 1
    return _clamp_int(x0, 0, w - 2), _clamp_int(x1, x0 + 2, w), yt, yb


def _estimate_lower_body_bounds(gray: np.ndarray) -> tuple[int, int, int, int]:
    """Estimate (x0, x1, waist_y, ankle_y) for person image.

    Uses gradient energy distribution (model-free, fast) to reduce the
    "floating pants" effect when the person is off-center or legs are long.
    """
    h, w = gray.shape[:2]
    if h < 32 or w < 32:
        return int(w * 0.22), int(w * 0.78), int(h * 0.40), int(h * 0.96)

    gy, gx = np.gradient(gray)
    grad = np.sqrt(gx * gx + gy * gy)

    y_roi0 = int(h * 0.28)
    y_roi1 = int(h * 0.98)
    roi = grad[y_roi0:y_roi1, :]
    if roi.size == 0:
        return int(w * 0.22), int(w * 0.78), int(h * 0.40), int(h * 0.96)

    col_energy = roi.mean(axis=0)
    thr = float(np.quantile(col_energy, 0.80))
    cols = np.where(col_energy >= thr)[0]
    if cols.size >= max(8, int(w * 0.06)):
        x0 = int(cols.min())
        x1 = int(cols.max()) + 1
        # Keep pad conservative; too much pad causes "floating cloth" on sides.
        pad = int((x1 - x0) * 0.06)
        x0 = _clamp_int(x0 - pad, 0, w - 2)
        x1 = _clamp_int(x1 + pad, x0 + 2, w)
    else:
        x0 = int(w * 0.22)
        x1 = int(w * 0.78)

    row_energy = grad[:, x0:x1].mean(axis=1)
    waist_search0 = int(h * 0.26)
    waist_search1 = int(h * 0.60)
    seg = row_energy[waist_search0:waist_search1]
    rthr = float(np.quantile(seg, 0.70)) if seg.size else float(np.quantile(row_energy, 0.70))
    candidates = np.where(row_energy >= rthr)[0]
    candidates = candidates[(candidates >= waist_search0) & (candidates <= waist_search1)]
    waist_y = int(candidates.min()) if candidates.size else int(h * 0.40)

    ankle_search0 = int(h * 0.65)
    ankle_search1 = int(h * 0.98)
    seg2 = row_energy[ankle_search0:ankle_search1]
    rthr2 = float(np.quantile(seg2, 0.55)) if seg2.size else rthr
    candidates2 = np.where(row_energy >= rthr2)[0]
    candidates2 = candidates2[(candidates2 >= ankle_search0) & (candidates2 <= ankle_search1)]
    ankle_y = int(candidates2.max()) if candidates2.size else int(h * 0.96)

    waist_y = _clamp_int(waist_y, int(h * 0.30), int(h * 0.55))
    ankle_y = _clamp_int(ankle_y, int(h * 0.75), int(h * 0.98))
    return x0, x1, waist_y, ankle_y


def _estimate_upper_body_bounds(gray: np.ndarray) -> tuple[int, int, int, int]:
    """Estimate (x0, x1, neck_y, waist_y) for upper body placement."""
    h, w = gray.shape[:2]
    if h < 32 or w < 32:
        return int(w * 0.20), int(w * 0.80), int(h * 0.14), int(h * 0.62)

    gy, gx = np.gradient(gray)
    grad = np.sqrt(gx * gx + gy * gy)

    y_roi0 = int(h * 0.08)
    y_roi1 = int(h * 0.70)
    roi = grad[y_roi0:y_roi1, :]
    if roi.size == 0:
        return int(w * 0.20), int(w * 0.80), int(h * 0.14), int(h * 0.62)

    col_energy = roi.mean(axis=0)
    thr = float(np.quantile(col_energy, 0.82))
    cols = np.where(col_energy >= thr)[0]
    if cols.size >= max(8, int(w * 0.06)):
        x0 = int(cols.min())
        x1 = int(cols.max()) + 1
        pad = int((x1 - x0) * 0.10)
        x0 = _clamp_int(x0 - pad, 0, w - 2)
        x1 = _clamp_int(x1 + pad, x0 + 2, w)
    else:
        x0 = int(w * 0.20)
        x1 = int(w * 0.80)

    row_energy = grad[:, x0:x1].mean(axis=1)
    neck_search0 = int(h * 0.06)
    neck_search1 = int(h * 0.30)
    seg = row_energy[neck_search0:neck_search1]
    rthr = float(np.quantile(seg, 0.72)) if seg.size else float(np.quantile(row_energy, 0.72))
    candidates = np.where(row_energy >= rthr)[0]
    candidates = candidates[(candidates >= neck_search0) & (candidates <= neck_search1)]
    neck_y = int(candidates.min()) if candidates.size else int(h * 0.14)

    waist_search0 = int(h * 0.30)
    waist_search1 = int(h * 0.72)
    seg2 = row_energy[waist_search0:waist_search1]
    rthr2 = float(np.quantile(seg2, 0.58)) if seg2.size else rthr
    candidates2 = np.where(row_energy >= rthr2)[0]
    candidates2 = candidates2[(candidates2 >= waist_search0) & (candidates2 <= waist_search1)]
    waist_y = int(candidates2.max()) if candidates2.size else int(h * 0.62)

    neck_y = _clamp_int(neck_y, int(h * 0.08), int(h * 0.28))
    waist_y = _clamp_int(waist_y, int(h * 0.42), int(h * 0.78))
    return x0, x1, neck_y, waist_y


def _compute_target_boxes(person_image: Image.Image) -> tuple[tuple[int, int, int, int], ...]:
    """Adaptive target boxes (waist, left leg, right leg) in person coordinates."""
    gray = np.asarray(person_image.convert("L"), dtype=np.float32)
    ph, pw = gray.shape[:2]

    fg = _person_foreground_mask(person_image)
    if fg is not None:
        b = _bounds_from_mask(fg, y0=int(ph * 0.28), y1=int(ph * 0.98), col_q=0.70, row_q=0.55)
    else:
        b = None
    if b is not None:
        x0, x1, y_top, y_bottom = b
        waist_y = _clamp_int(int(y_top + (y_bottom - y_top) * 0.20), int(ph * 0.30), int(ph * 0.55))
        ankle_y = _clamp_int(int(y_bottom), int(ph * 0.75), int(ph * 0.98))
    else:
        x0, x1, waist_y, ankle_y = _estimate_lower_body_bounds(gray)
    body_w = max(2, x1 - x0)
    mid = x0 + body_w // 2

    waist_h = _clamp_int(int(ph * 0.11), 24, int(ph * 0.18))
    wy0 = _clamp_int(waist_y - waist_h // 2, 0, ph - 2)
    wy1 = _clamp_int(waist_y + waist_h // 2, wy0 + 2, ph)
    waistband_box = (x0, wy0, x1, wy1)

    leg_y0 = _clamp_int(int(wy1 + ph * 0.01), 0, ph - 2)
    leg_y1 = _clamp_int(ankle_y, leg_y0 + 2, ph)
    mid = _clamp_int(mid, x0 + 2, x1 - 2)

    left_leg_box = (x0, leg_y0, mid, leg_y1)
    right_leg_box = (mid, leg_y0, x1, leg_y1)
    return waistband_box, left_leg_box, right_leg_box


def tryon_pants_warp(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    alpha_feather_ratio: float = 0.012,
) -> tuple[Image.Image, WarpMetadata]:
    """Return (result_rgb, metadata).

    Uses MediaPipe Pose keypoints (hips/knees/ankles) when available for
    accurate waist and leg placement; falls back to gradient energy estimation.
    """
    base = person_image.convert("RGBA")
    pw, ph = base.size

    cutout = cutout_garment_rgba(garment_image)
    parts = split_pants_parts(cutout.cropped)

    # ── MediaPipe 优先路径 ──────────────────────────────────────────────────
    kpts = detect_pose_keypoints(person_image)
    if kpts:
        bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "bottom")
        if bounds.get("valid"):
            x0 = bounds["x0"]
            x1 = bounds["x1"]
            waist_y = bounds["waist_y"]
            ankle_y = bounds["ankle_y"]
            body_w = max(2, x1 - x0)
            mid = x0 + body_w // 2

            waist_h = _clamp_int(int(ph * 0.11), 24, int(ph * 0.18))
            wy0 = _clamp_int(waist_y - waist_h // 2, 0, ph - 2)
            wy1 = _clamp_int(waist_y + waist_h // 2, wy0 + 2, ph)
            waistband_box: tuple[int, int, int, int] = (x0, wy0, x1, wy1)

            leg_y0 = _clamp_int(wy1 + max(1, int(ph * 0.01)), 0, ph - 2)
            leg_y1 = _clamp_int(ankle_y, leg_y0 + 2, ph)
            mid = _clamp_int(mid, x0 + 2, x1 - 2)
            left_leg_box: tuple[int, int, int, int] = (x0, leg_y0, mid, leg_y1)
            right_leg_box: tuple[int, int, int, int] = (mid, leg_y0, x1, leg_y1)
            _used_pose = True
        else:
            waistband_box, left_leg_box, right_leg_box = _compute_target_boxes(person_image)
            _used_pose = False
    else:
        waistband_box, left_leg_box, right_leg_box = _compute_target_boxes(person_image)
        _used_pose = False

    def _warp_into_box(src: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
        x0, y0, x1, y1 = box
        tw = max(2, x1 - x0)
        th = max(2, y1 - y0)
        # Use QUAD with a mild taper to mimic leg narrowing.
        # Stronger taper improves leg fit for straight-standing photos.
        inset = int(tw * 0.10)
        quad = (
            0,
            0,
            src.size[0],
            0,
            src.size[0],
            src.size[1],
            0,
            src.size[1],
        )
        warped = _pil_quad_warp(src, (tw, th), quad)
        if box in (left_leg_box, right_leg_box) and tw >= 12:
            # Taper top slightly for leg fit.
            tw2, th2 = warped.size
            quad2 = (
                inset,
                0,
                tw2 - inset,
                0,
                tw2,
                th2,
                0,
                th2,
            )
            warped = _pil_quad_warp(warped, (tw2, th2), quad2)
        canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        canvas.paste(warped, (x0, y0), warped)
        return canvas

    layer_waist = _warp_into_box(parts.waistband, waistband_box)
    layer_left = _warp_into_box(parts.left_leg, left_leg_box)
    layer_right = _warp_into_box(parts.right_leg, right_leg_box)

    merged = Image.alpha_composite(Image.alpha_composite(layer_left, layer_right), layer_waist)

    # Feather alpha edges for smoother boundary.
    feather_px = _clamp_int(int(max(pw, ph) * float(alpha_feather_ratio)), 1, 12)
    merged = _feather_alpha(merged, radius_px=feather_px)

    # Protect upper body: do not overwrite above ~30% height.
    protect = _upper_protect_mask((pw, ph), protect_until_y=int(ph * 0.30))
    if merged.mode != "RGBA":
        merged = merged.convert("RGBA")
    r, g, b, a = merged.split()
    a = ImageChops.multiply(a, protect)
    merged = Image.merge("RGBA", (r, g, b, a))

    out = Image.alpha_composite(base, merged).convert("RGB")
    engine_tag = "pants_warp_v2_pose" if _used_pose else "pants_warp_v1_gradient"
    meta = WarpMetadata(
        engine=engine_tag,
        waistband_box=waistband_box,
        left_leg_box=left_leg_box,
        right_leg_box=right_leg_box,
        alpha_feather_px=feather_px,
    )
    return out, meta


def tryon_top_warp(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    alpha_feather_ratio: float = 0.009,
) -> tuple[Image.Image, WarpMetadata]:
    """Warp upper garment onto person using MediaPipe keypoints when available.

    When MediaPipe keypoints are available, uses shoulder/hip landmarks for precise
    placement and applies a perspective trapezoid warp (shoulder-width at top,
    hip-width at bottom) to simulate the garment conforming to the body silhouette.
    Falls back to gradient energy estimation if keypoints are unavailable.
    """
    base = person_image.convert("RGBA")
    pw, ph = base.size

    cutout = cutout_garment_rgba(garment_image)
    g = cutout.cropped.convert("RGBA")
    gw, gh = g.size
    if gw < 16 or gh < 16:
        raise ValueError("garment too small for top warp")

    # ── MediaPipe 优先路径 ──────────────────────────────────────────────────
    kpts = detect_pose_keypoints(person_image)
    _used_pose = False
    _shoulder_w_px: int | None = None
    _hip_w_px: int | None = None

    if kpts:
        bounds = get_body_bounds_from_keypoints(kpts, pw, ph, "top")
        if bounds.get("valid"):
            x0 = bounds["x0"]
            x1 = bounds["x1"]
            neck_y = bounds["neck_y"]
            waist_y = bounds["waist_y"]
            _shoulder_w_px = max(2, int(bounds.get("shoulder_width", x1 - x0)))
            _hip_w_px = max(2, int(bounds.get("hip_width", (x1 - x0) * 0.85)))
            _used_pose = True

    if not _used_pose:
        # ── 梯度能量 fallback ────────────────────────────────────────────────
        gray = np.asarray(person_image.convert("L"), dtype=np.float32)
        fg = _person_foreground_mask(person_image)
        b = None
        if fg is not None:
            b = _bounds_from_mask(fg, y0=int(ph * 0.06), y1=int(ph * 0.74), col_q=0.72, row_q=0.55)
        if b is not None:
            x0, x1, y_top, y_bottom = b
            span = max(2, int(y_bottom - y_top))
            neck_y = _clamp_int(int(y_top + span * 0.18), int(ph * 0.12), int(ph * 0.32))
            waist_y = _clamp_int(int(y_top + span * 0.70), int(ph * 0.45), int(ph * 0.82))
        else:
            x0, x1, neck_y, waist_y = _estimate_upper_body_bounds(gray)
        # Stabilize horizontal center.
        mid = (x0 + x1) // 2
        center = pw // 2
        drift = int(mid - center)
        if abs(drift) > int(pw * 0.12):
            shift = int(-0.65 * drift)
            bw = x1 - x0
            x0 = _clamp_int(x0 + shift, 0, pw - 2)
            x1 = _clamp_int(x0 + bw, x0 + 2, pw)
        pad_x = int((x1 - x0) * 0.03)
        x0 = _clamp_int(x0 - pad_x, 0, pw - 2)
        x1 = _clamp_int(x1 + pad_x, x0 + 2, pw)

    # Force garment top below face/chin.
    y0 = _clamp_int(int(neck_y + ph * 0.02), int(ph * 0.12), int(ph * 0.42))
    y1 = _clamp_int(int(waist_y + ph * 0.03), y0 + 2, int(ph * 0.86))
    tw = max(2, x1 - x0)
    th = max(2, y1 - y0)

    # Fit garment into target box preserving aspect ratio.
    max_w = max(2, int(tw * 0.88))
    max_h = max(2, int(th * 0.94))
    scale = min(max_w / float(gw), max_h / float(gh))
    itw = max(2, int(gw * scale))
    ith = max(2, int(gh * scale))
    g = g.resize((itw, ith), Image.Resampling.LANCZOS)

    # ── 透视梯形变形（肩宽 → 腰宽，模拟 3D 贴合感）──────────────────────
    # 只在 MediaPipe 关键点可用且肩腰宽度差值明显时做梯形透视。
    if _used_pose and _shoulder_w_px and _hip_w_px and itw >= 16:
        top_half_w = _clamp_int(int(min(itw, _shoulder_w_px * scale)), 4, itw)
        bot_half_w = _clamp_int(int(min(itw, _hip_w_px * scale)), 4, itw)
        # 只在差值 > 4px 时才做 QUAD 变换，避免微小差值引入不必要失真。
        if abs(top_half_w - bot_half_w) > 4:
            top_inset = (itw - top_half_w) // 2
            bot_inset = (itw - bot_half_w) // 2
            quad = (
                top_inset,
                0,  # 左上
                itw - top_inset,
                0,  # 右上
                itw - bot_inset,
                ith,  # 右下
                bot_inset,
                ith,  # 左下
            )
            g = _pil_quad_warp(g, (itw, ith), quad)

    # Additional horizontal "slim" without shear.
    if itw >= 16 and not (_used_pose and _shoulder_w_px):
        slim = 0.92
        itw2 = max(2, int(itw * slim))
        if itw2 != itw:
            g = g.resize((itw2, ith), Image.Resampling.LANCZOS)
            itw = itw2

    layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    ox = x0 + (tw - itw) // 2
    oy = y0 + (th - ith) // 2
    layer.paste(g, (ox, oy), g)

    feather_px = _clamp_int(int(max(pw, ph) * float(alpha_feather_ratio)), 1, 8)
    layer = _feather_alpha(layer, radius_px=feather_px)

    protect = _upper_protect_mask((pw, ph), protect_until_y=int(ph * 0.18))
    r, gg, b, a = layer.split()
    a = ImageChops.multiply(a, protect)
    layer = Image.merge("RGBA", (r, gg, b, a))

    out = Image.alpha_composite(base, layer).convert("RGB")
    engine_tag = "top_warp_v2_pose" if _used_pose else "top_warp_v1_gradient"
    meta = WarpMetadata(
        engine=engine_tag,
        waistband_box=(x0, y0, x1, y0 + max(2, int((y1 - y0) * 0.18))),
        left_leg_box=(x0, y0 + max(2, int((y1 - y0) * 0.18)), (x0 + x1) // 2, y1),
        right_leg_box=((x0 + x1) // 2, y0 + max(2, int((y1 - y0) * 0.18)), x1, y1),
        alpha_feather_px=feather_px,
    )
    return out, meta


def tryon_skirt_warp(
    person_image: Image.Image,
    garment_image: Image.Image,
    *,
    alpha_feather_ratio: float = 0.012,
) -> tuple[Image.Image, WarpMetadata]:
    base = person_image.convert("RGBA")
    pw, ph = base.size

    cutout = cutout_garment_rgba(garment_image)
    g = cutout.cropped.convert("RGBA")
    gw, gh = g.size
    if gw < 16 or gh < 16:
        raise ValueError("garment too small for skirt warp")

    # Reuse pants adaptive bounds, but warp a single piece (skirt/dress has no leg split).
    gray = np.asarray(person_image.convert("L"), dtype=np.float32)
    _x0, _x1, waist_y, ankle_y = _estimate_lower_body_bounds(gray)
    x0 = _clamp_int(_x0 - int((_x1 - _x0) * 0.02), 0, pw - 2)
    x1 = _clamp_int(_x1 + int((_x1 - _x0) * 0.02), x0 + 2, pw)
    y0 = _clamp_int(int(waist_y - ph * 0.06), int(ph * 0.22), int(ph * 0.70))
    y1 = _clamp_int(int(ankle_y), y0 + 2, ph)
    tw = max(2, x1 - x0)
    th = max(2, y1 - y0)

    g = g.resize((tw, th), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    layer.paste(g, (x0, y0), g)

    feather_px = _clamp_int(int(max(pw, ph) * float(alpha_feather_ratio)), 1, 12)
    layer = _feather_alpha(layer, radius_px=feather_px)

    protect = _upper_protect_mask((pw, ph), protect_until_y=int(ph * 0.24))
    r, gg, b, a = layer.split()
    a = ImageChops.multiply(a, protect)
    layer = Image.merge("RGBA", (r, gg, b, a))

    out = Image.alpha_composite(base, layer).convert("RGB")
    meta = WarpMetadata(
        engine="skirt_warp_v1",
        waistband_box=(x0, y0, x1, y0 + max(2, int((y1 - y0) * 0.15))),
        left_leg_box=(x0, y0, (x0 + x1) // 2, y1),
        right_leg_box=((x0 + x1) // 2, y0, x1, y1),
        alpha_feather_px=feather_px,
    )
    return out, meta
