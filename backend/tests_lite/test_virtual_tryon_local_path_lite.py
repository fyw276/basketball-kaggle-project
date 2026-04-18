import builtins

import numpy as np
from PIL import Image

import app.services.virtual_tryon as vt


def test_resolve_tryon_model_source_prefers_local_path(monkeypatch, tmp_path):
    model_dir = tmp_path / "stable-diffusion-inpainting"
    model_dir.mkdir()
    monkeypatch.setattr(vt.settings, "TRYON_MODEL_LOCAL_PATH", str(model_dir))
    kind, value = vt._resolve_tryon_model_source()
    assert kind == "local"
    assert value == str(model_dir)


def test_resolve_tryon_model_source_falls_back_to_hf(monkeypatch):
    monkeypatch.setattr(vt.settings, "TRYON_MODEL_LOCAL_PATH", "")
    kind, value = vt._resolve_tryon_model_source()
    assert kind == "hf"
    assert value == vt.SD_VTON_MODEL_ID


def test_haarcascade_frontalface_xml_points_to_existing_file():
    p = vt._haarcascade_frontalface_xml()
    if p is None:
        import pytest

        pytest.skip("OpenCV Haar data not available in this environment")
    assert p.is_file()
    assert p.name == "haarcascade_frontalface_default.xml"


def test_garment_cutout_survives_rembg_system_exit(monkeypatch):
    service = vt.VirtualTryOnService(device="cpu")
    image = Image.new("RGB", (64, 64), color=(245, 245, 245))

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "rembg":
            raise SystemExit(1)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    out = service._garment_to_rgba_cutout(image)
    assert out.mode == "RGBA"
    assert out.size == image.size


def test_current_model_label_prefers_actual_loaded_source():
    service = vt.VirtualTryOnService(device="cpu")
    service._model_source = r"D:\models\stable-diffusion-inpainting"
    assert service._current_model_label() == r"D:\models\stable-diffusion-inpainting"


def test_ensure_model_loaded_skips_when_force_fallback_enabled(monkeypatch):
    service = vt.VirtualTryOnService(device="cpu")
    monkeypatch.setattr(vt.settings, "TRYON_FORCE_FALLBACK", True)
    assert service._ensure_model_loaded() is False
    assert service._model_source == "forced_fallback"


def test_garment_cutout_skips_rembg_when_force_fallback_enabled(monkeypatch):
    service = vt.VirtualTryOnService(device="cpu")
    image = Image.new("RGB", (64, 64), color=(245, 245, 245))
    monkeypatch.setattr(vt.settings, "TRYON_FORCE_FALLBACK", True)

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "rembg":
            raise AssertionError("rembg should not be imported in forced fallback mode")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    out = service._garment_to_rgba_cutout(image)
    assert out.mode == "RGBA"
    assert out.size == image.size


def test_infer_fallback_placement_dress_not_treated_as_bottom():
    assert vt._infer_fallback_placement("连衣裙") is None
    assert vt._infer_fallback_placement("下装(汉)") == "bottom"


def test_compute_fallback_overlay_box_prefers_lower_larger_box_for_long_garments():
    service = vt.VirtualTryOnService(device="cpu")
    long_box = service._compute_fallback_overlay_box((1000, 1600), (400, 800))
    short_box = service._compute_fallback_overlay_box((1000, 1600), (800, 600))

    _, long_y, long_w, long_h = long_box
    _, short_y, short_w, short_h = short_box

    assert long_y > short_y
    assert long_h > short_h
    assert long_w >= 48 and short_w >= 48


def test_compute_fallback_overlay_box_bottom_placement_lowers_wide_garment():
    """Category 'bottom' should anchor wide/squat crops lower than aspect-only heuristics."""
    service = vt.VirtualTryOnService(device="cpu")
    person = (1000, 1600)
    garment = (700, 500)  # squat crop; aspect-only would use top-heavy tier
    _, y_aspect, _, _ = service._compute_fallback_overlay_box(person, garment, None)
    _, y_bottom, _, _ = service._compute_fallback_overlay_box(person, garment, "bottom")
    assert y_bottom >= y_aspect


def test_paste_garment_on_person_returns_same_canvas_size():
    service = vt.VirtualTryOnService(device="cpu")
    person = Image.new("RGB", (720, 1280), color=(230, 230, 230))
    garment = Image.new("RGBA", (320, 480), color=(40, 40, 40, 220))

    out = service._paste_garment_on_person(person, garment)

    assert out.mode == "RGB"
    assert out.size == person.size


def test_crop_to_alpha_bbox_ignores_faint_alpha_haze():
    service = vt.VirtualTryOnService(device="cpu")
    im = Image.new("RGBA", (100, 80), color=(0, 0, 0, 1))
    # Solid center object
    for x in range(30, 70):
        for y in range(20, 60):
            im.putpixel((x, y), (10, 10, 10, 255))

    cropped = service._crop_to_alpha_bbox(im)
    assert cropped.size[0] < 100
    assert cropped.size[1] < 80


def test_fallback_paste_protects_head_region_from_overlay():
    service = vt.VirtualTryOnService(device="cpu")
    pw, ph = 600, 1000
    person = Image.new("RGB", (pw, ph), color=(250, 250, 250))

    # A big opaque overlay that would normally cover everything.
    garment = Image.new("RGBA", (900, 1200), color=(10, 10, 10, 255))
    out = service._paste_garment_on_person(person, garment)

    hx0, hy0, hx1, hy1 = service._protected_head_box((pw, ph))
    # Sample a point inside protected region; must remain close to original.
    sx = (hx0 + hx1) // 2
    sy = (hy0 + hy1) // 2
    r, g, b = out.getpixel((sx, sy))
    assert r > 200 and g > 200 and b > 200


def test_paste_bottom_category_clears_alpha_in_upper_band():
    service = vt.VirtualTryOnService(device="cpu")
    pw, ph = 400, 600
    person = Image.new("RGB", (pw, ph), color=(250, 250, 250))
    garment = Image.new("RGBA", (200, 400), color=(20, 20, 20, 255))
    out = service._paste_garment_on_person(person, garment, garment_category="长裤")
    # Upper chest band should stay background after bottom cutoff + head guard.
    sx, sy = pw // 2, int(ph * 0.20)
    r, g, b = out.getpixel((sx, sy))
    assert r > 200 and g > 200 and b > 200


def test_largest_connected_component_mask_keeps_main_blob():
    service = vt.VirtualTryOnService(device="cpu")
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[1:6, 1:6] = 1
    mask[8, 8] = 1

    out = service._largest_connected_component_mask(mask)

    assert int(out.sum()) == 25
    assert out[8, 8] == 0


def test_refined_cutout_produces_nonzero_alpha_in_forced_fallback(monkeypatch):
    service = vt.VirtualTryOnService(device="cpu")
    monkeypatch.setattr(vt.settings, "TRYON_FORCE_FALLBACK", True)

    garment = Image.new("RGB", (120, 160), color=(245, 245, 245))
    for x in range(30, 90):
        for y in range(20, 140):
            garment.putpixel((x, y), (30, 30, 80))

    out = service._garment_to_rgba_cutout(garment)
    alpha = np.array(out.getchannel("A"))

    assert out.mode == "RGBA"
    assert alpha.max() > 0
    assert alpha[80, 60] > alpha[5, 5]


def test_classify_garment_photo_type_detects_white_bg():
    service = vt.VirtualTryOnService(device="cpu")
    garment = Image.new("RGB", (120, 160), color=(248, 248, 248))
    for x in range(35, 85):
        for y in range(25, 140):
            garment.putpixel((x, y), (80, 80, 120))

    assert service._classify_garment_photo_type(garment) == "white_bg"


def test_classify_garment_photo_type_detects_real_photo():
    service = vt.VirtualTryOnService(device="cpu")
    garment = Image.new("RGB", (120, 160), color=(50, 40, 30))
    for x in range(25, 95):
        for y in range(20, 145):
            garment.putpixel((x, y), (220, 220, 225))

    assert service._classify_garment_photo_type(garment) == "real_photo"


def test_generate_mask_by_photo_type_keeps_center_object():
    service = vt.VirtualTryOnService(device="cpu")
    garment = Image.new("RGB", (120, 160), color=(245, 245, 245))
    for x in range(30, 90):
        for y in range(20, 140):
            garment.putpixel((x, y), (40, 60, 120))

    mask = service._generate_garment_mask_by_photo_type(garment, "white_bg")
    arr = np.array(mask)

    assert arr[80, 60] > 0
    assert arr[5, 5] < arr[80, 60]


def test_real_photo_mask_removes_border_skin_like_region():
    service = vt.VirtualTryOnService(device="cpu")
    # Dark-ish background + garment in center.
    garment = Image.new("RGB", (180, 220), color=(60, 50, 45))
    for x in range(50, 140):
        for y in range(30, 200):
            garment.putpixel((x, y), (20, 20, 80))

    # Add a "hand-like" skin patch entering from the left border.
    skin = (225, 175, 145)
    for x in range(0, 35):
        for y in range(80, 170):
            garment.putpixel((x, y), skin)

    mask = service._generate_garment_mask_by_photo_type(garment, "real_photo")
    arr = np.array(mask)

    # Skin border area should be mostly background in coarse mask.
    assert int(arr[120, 10]) < int(arr[120, 90])


def test_real_photo_mask_does_not_keep_whole_background_slab():
    service = vt.VirtualTryOnService(device="cpu")
    # Border background color (wall-like).
    bg = (230, 228, 224)
    garment = Image.new("RGB", (220, 220), color=bg)
    # Add a garment region with strong contrast.
    for x in range(60, 160):
        for y in range(40, 200):
            garment.putpixel((x, y), (20, 40, 120))

    mask = service._generate_garment_mask_by_photo_type(garment, "real_photo")
    arr = np.array(mask)

    # Corner should be background-ish, center should be foreground-ish.
    assert int(arr[10, 10]) < int(arr[120, 110])
    # Not everything should be foreground.
    ratio = float((arr > 128).mean())
    assert ratio < 0.85


def test_fill_binary_mask_holes_fills_inner_gap():
    service = vt.VirtualTryOnService(device="cpu")
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[8:32, 8:32] = 255
    mask[18:22, 18:22] = 0

    filled = service._fill_binary_mask_holes(mask)

    assert filled[20, 20] > 0
