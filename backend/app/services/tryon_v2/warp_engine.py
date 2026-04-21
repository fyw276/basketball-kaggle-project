"""Deterministic 2D warp + paste engine for Try-on v2 pipeline A (bottom garments).

Goal: keep identity/background, only replace bottom garment area using
simple geometric warps. This is not a physics simulation; it's a stable,
explainable heuristic intended for the v2 MVP and regression testing.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def _compute_target_boxes(person_size: tuple[int, int]) -> tuple[tuple[int, int, int, int], ...]:
    """Heuristic target boxes (waist, left leg, right leg) in person coordinates."""
    pw, ph = person_size
    # Waist around 38% height, legs start around 44% height.
    waist_y0 = int(ph * 0.34)
    waist_y1 = int(ph * 0.46)
    leg_y0 = int(ph * 0.44)
    leg_y1 = int(ph * 0.96)

    # Slightly inset x to avoid covering background/arms.
    x0 = int(pw * 0.22)
    x1 = int(pw * 0.78)
    mid = (x0 + x1) // 2

    waistband_box = (x0, waist_y0, x1, waist_y1)
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

    waistband_box, left_leg_box, right_leg_box = _compute_target_boxes((pw, ph))

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
