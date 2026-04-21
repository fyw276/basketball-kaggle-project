"""Deterministic 2D warp + paste engine for Try-on v2 pipeline A (bottom garments).

Goal: keep identity/background, only replace bottom garment area using
simple geometric warps. This is not a physics simulation; it's a stable,
explainable heuristic intended for the v2 MVP and regression testing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageFilter

from app.services.tryon_v2.garment_struct import cutout_garment_rgba, split_pants_parts


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
        pad = int((x1 - x0) * 0.10)
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


def _compute_target_boxes(person_image: Image.Image) -> tuple[tuple[int, int, int, int], ...]:
    """Adaptive target boxes (waist, left leg, right leg) in person coordinates."""
    gray = np.asarray(person_image.convert("L"), dtype=np.float32)
    ph, pw = gray.shape[:2]

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
    """Return (result_rgb, metadata)."""
    base = person_image.convert("RGBA")
    pw, ph = base.size

    cutout = cutout_garment_rgba(garment_image)
    parts = split_pants_parts(cutout.cropped)

    waistband_box, left_leg_box, right_leg_box = _compute_target_boxes(person_image)

    def _warp_into_box(src: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
        x0, y0, x1, y1 = box
        tw = max(2, x1 - x0)
        th = max(2, y1 - y0)
        # Use QUAD with a mild taper to mimic leg narrowing.
        inset = int(tw * 0.06)
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
    meta = WarpMetadata(
        engine="pants_warp_v1",
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
    alpha_feather_ratio: float = 0.012,
) -> tuple[Image.Image, WarpMetadata]:
    base = person_image.convert("RGBA")
    pw, ph = base.size

    cutout = cutout_garment_rgba(garment_image)
    g = cutout.cropped.convert("RGBA")
    gw, gh = g.size
    if gw < 16 or gh < 16:
        raise ValueError("garment too small for top warp")

    # Torso box: a bit wider, centered; do not touch head region.
    x0 = int(pw * 0.20)
    x1 = int(pw * 0.80)
    y0 = int(ph * 0.14)
    y1 = int(ph * 0.62)
    tw = max(2, x1 - x0)
    th = max(2, y1 - y0)

    g = g.resize((tw, th), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    layer.paste(g, (x0, y0), g)

    feather_px = _clamp_int(int(max(pw, ph) * float(alpha_feather_ratio)), 1, 12)
    layer = _feather_alpha(layer, radius_px=feather_px)

    # Protect head/upper face and lower legs area.
    protect = _upper_protect_mask((pw, ph), protect_until_y=int(ph * 0.12))
    r, gg, b, a = layer.split()
    a = ImageChops.multiply(a, protect)
    layer = Image.merge("RGBA", (r, gg, b, a))

    out = Image.alpha_composite(base, layer).convert("RGB")
    meta = WarpMetadata(
        engine="top_warp_v1",
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
