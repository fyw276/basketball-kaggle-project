from __future__ import annotations

import numpy as np
from PIL import Image

from app.services.tryon_v2.warp_engine import (
    _estimate_pants_flare_ratio,
    _expand_pants_target_boxes,
    tryon_pants_warp,
    tryon_top_warp_preserve,
)


def test_tryon_pants_warp_returns_same_size_and_preserves_upper_region_reasonably():
    person = Image.new("RGB", (320, 520), color=(180, 180, 180))
    # Add a simple "face/head" marker region (upper band) that should remain unchanged.
    for x in range(110, 210):
        for y in range(20, 120):
            person.putpixel((x, y), (120, 150, 190))

    garment = Image.new("RGB", (280, 420), color=(245, 245, 245))
    # Draw a darker pants-like region so mask detection sees foreground.
    for x in range(70, 210):
        for y in range(60, 400):
            garment.putpixel((x, y), (60, 60, 60))

    out, meta = tryon_pants_warp(person_image=person, garment_image=garment)
    assert out.size == person.size
    assert meta.engine.startswith("pants_warp")

    # Upper protected region should be mostly unchanged.
    out_px = out.crop((0, 0, out.size[0], int(out.size[1] * 0.28))).convert("RGB")
    p_px = person.crop((0, 0, person.size[0], int(person.size[1] * 0.28))).convert("RGB")
    assert list(out_px.getdata()) == list(p_px.getdata())


def test_tryon_top_warp_preserves_head_region_and_changes_torso():
    person = Image.new("RGB", (320, 520), color=(180, 180, 180))
    for x in range(110, 210):
        for y in range(10, 120):
            person.putpixel((x, y), (120, 150, 190))

    garment = Image.new("RGB", (260, 320), color=(245, 245, 245))
    for x in range(40, 220):
        for y in range(30, 290):
            garment.putpixel((x, y), (40, 40, 40))

    out, meta = tryon_top_warp_preserve(person_image=person, garment_image=garment)
    assert out.size == person.size
    assert meta.engine.startswith("top_warp")

    head_out = out.crop((0, 0, out.size[0], int(out.size[1] * 0.12))).convert("RGB")
    head_p = person.crop((0, 0, person.size[0], int(person.size[1] * 0.12))).convert("RGB")
    assert list(head_out.getdata()) == list(head_p.getdata())

    torso_out = out.crop(
        (0, int(out.size[1] * 0.20), out.size[0], int(out.size[1] * 0.55))
    ).convert("RGB")
    torso_p = person.crop(
        (0, int(person.size[1] * 0.20), person.size[0], int(person.size[1] * 0.55))
    ).convert("RGB")
    assert list(torso_out.getdata()) != list(torso_p.getdata())


def test_estimate_pants_flare_ratio_detects_wide_leg_source():
    garment = Image.new("RGBA", (220, 320), (255, 255, 255, 0))
    arr = np.array(garment)
    for y in range(20, 320):
        t = (y - 20) / 299.0
        half_w = int(38 + t * 42)
        cx = 110
        x0 = max(0, cx - half_w)
        x1 = min(220, cx + half_w)
        arr[y, x0:x1, :3] = (40, 45, 60)
        arr[y, x0:x1, 3] = 255
    garment = Image.fromarray(arr, mode="RGBA")

    flare_ratio, wide_leg = _estimate_pants_flare_ratio(garment)

    assert flare_ratio >= 1.18
    assert wide_leg is True


def test_expand_pants_target_boxes_widens_outer_leg_coverage_for_wide_leg():
    waistband_box = (90, 120, 190, 150)
    left_leg_box = (90, 146, 140, 290)
    right_leg_box = (140, 146, 190, 290)

    new_waist, new_left, new_right = _expand_pants_target_boxes(
        waistband_box,
        left_leg_box,
        right_leg_box,
        image_w=320,
        flare_ratio=1.42,
    )

    assert new_waist[0] < waistband_box[0]
    assert new_waist[2] > waistband_box[2]
    assert new_left[0] < left_leg_box[0]
    assert new_left[2] > left_leg_box[2]
    assert new_right[0] < right_leg_box[0]
    assert new_right[2] > right_leg_box[2]
