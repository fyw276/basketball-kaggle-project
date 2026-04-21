from __future__ import annotations

from PIL import Image

from app.services.tryon_v2.warp_engine import tryon_pants_warp


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
