import numpy as np
from PIL import Image

import app.services.virtual_tryon as vt


def test_sanitize_tryon_prompt_removes_controls_and_trims():
    raw = "  hello\x00\x01\nworld\t \n "
    cleaned = vt.sanitize_tryon_prompt(raw)
    assert cleaned == "hello world"


def test_sanitize_tryon_prompt_caps_length():
    long_text = "x" * 700
    cleaned = vt.sanitize_tryon_prompt(long_text)
    assert len(cleaned) == 500


def test_generate_garment_mask_keeps_center_object():
    service = vt.VirtualTryOnService(device="cpu")
    garment = Image.new("RGB", (120, 160), color=(245, 245, 245))
    for x in range(30, 90):
        for y in range(20, 140):
            garment.putpixel((x, y), (40, 60, 120))

    mask = service._generate_garment_mask(garment)
    arr = np.array(mask)

    assert int(arr[80, 60]) > int(arr[5, 5])


def test_garment_cutout_outputs_rgba_with_alpha_signal():
    service = vt.VirtualTryOnService(device="cpu")
    garment = Image.new("RGB", (120, 160), color=(245, 245, 245))
    for x in range(30, 90):
        for y in range(20, 140):
            garment.putpixel((x, y), (30, 30, 80))

    out = service._garment_to_rgba_cutout(garment)
    alpha = np.array(out.getchannel("A"))

    assert out.mode == "RGBA"
    assert out.size == garment.size
    assert alpha.max() > 0


def test_crop_to_alpha_bbox_reduces_size_for_sparse_alpha():
    service = vt.VirtualTryOnService(device="cpu")
    im = Image.new("RGBA", (100, 80), color=(0, 0, 0, 0))
    for x in range(30, 70):
        for y in range(20, 60):
            im.putpixel((x, y), (10, 10, 10, 255))

    cropped = service._crop_to_alpha_bbox(im)
    assert cropped.size[0] < 100
    assert cropped.size[1] < 80


def test_paste_garment_on_person_returns_same_canvas_size():
    service = vt.VirtualTryOnService(device="cpu")
    person = Image.new("RGB", (720, 1280), color=(230, 230, 230))
    garment = Image.new("RGBA", (320, 480), color=(40, 40, 40, 220))

    out = service._paste_garment_on_person(person, garment)

    assert out.mode == "RGB"
    assert out.size == person.size


def test_compute_cache_key_changes_with_prompt_and_gender():
    service = vt.VirtualTryOnService(device="cpu")
    garment = Image.new("RGB", (64, 64), color=(10, 10, 10))
    person = Image.new("RGB", (64, 64), color=(200, 200, 200))

    k1 = service._compute_cache_key(garment, person, "p1", "neutral")
    k2 = service._compute_cache_key(garment, person, "p2", "neutral")
    k3 = service._compute_cache_key(garment, person, "p1", "male")

    assert k1 != k2
    assert k1 != k3


def test_tryon_garment_force_fallback_sets_identity_reason(monkeypatch):
    service = vt.VirtualTryOnService(device="cpu")
    garment = Image.new("RGB", (64, 64), color=(20, 20, 20))
    person = Image.new("RGB", (64, 64), color=(240, 240, 240))

    monkeypatch.setattr(service, "_garment_has_face", lambda *_args, **_kwargs: False)

    def _stub_tryon_fallback(*_args, **_kwargs):
        return {
            "status": "fallback",
            "message": "ok",
            "result_image": Image.new("RGB", (64, 64), color=(1, 2, 3)),
            "metadata": {"reason": "model_unavailable"},
        }

    monkeypatch.setattr(service, "_tryon_fallback", _stub_tryon_fallback)

    out = service.tryon_garment(
        garment_image=garment,
        person_image=person,
        force_fallback=True,
    )
    assert out["status"] == "fallback"
    assert out.get("metadata", {}).get("reason") == "forced_identity_preservation"


def test_check_tryon_garment_has_face_handles_service_error(monkeypatch):
    monkeypatch.setattr(
        vt, "get_tryon_service", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert vt.check_tryon_garment_has_face(Image.new("RGB", (8, 8), color=(255, 255, 255))) is False
