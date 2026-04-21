from __future__ import annotations

from PIL import Image

from app.services.tryon_v2.warp_engine import tryon_pants_warp, tryon_top_warp


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

    out, meta = tryon_top_warp(person_image=person, garment_image=garment)
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
