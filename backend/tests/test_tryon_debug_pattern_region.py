from __future__ import annotations

import json
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def make_light_cartoon_garment(size: tuple[int, int] = (768, 768)) -> Image.Image:
    """Synthetic version of a light T-shirt with small pastel cartoon prints."""
    img = Image.new("RGB", size, (250, 250, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle((96, 96, size[0] - 96, size[1] - 64), fill=(236, 232, 214))

    for x, y, color in [
        (250, 260, (160, 200, 230)),
        (360, 240, (245, 210, 90)),
        (480, 270, (170, 220, 190)),
        (310, 390, (250, 190, 210)),
        (520, 430, (120, 180, 220)),
        (230, 520, (180, 220, 190)),
        (575, 560, (245, 210, 90)),
    ]:
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=color, outline=(90, 90, 90), width=2)

    draw.ellipse((330, 330, 438, 438), fill=(245, 215, 180), outline=(90, 90, 90), width=3)
    draw.rectangle((355, 438, 413, 500), fill=(160, 205, 230), outline=(90, 90, 90), width=2)
    return img


def test_light_cartoon_print_is_detected_as_patterned() -> None:
    from app.services.tryon_pattern_utils import detect_pattern_strength

    score = detect_pattern_strength(make_light_cartoon_garment())

    assert score > 0.40


def test_changed_catvton_garment_region_expands_beyond_pose_torso() -> None:
    from app.services.tryon_pattern_utils import estimate_catvton_garment_region_from_change

    person_arr = np.full((768, 512, 3), 245, dtype=np.uint8)
    person_arr[160:650, 220:300] = (226, 184, 156)
    person = Image.fromarray(person_arr, mode="RGB")

    result_arr = person_arr.copy()
    result_arr[180:430, 145:385] = (145, 145, 135)
    catvton_result = Image.fromarray(result_arr, mode="RGB")

    narrow_pose_region = {"x0": 220, "x1": 300, "neck_y": 180, "waist_y": 410}
    region = estimate_catvton_garment_region_from_change(
        catvton_result=catvton_result,
        person_image=person,
        pose_region=narrow_pose_region,
        garment_category="top",
    )

    assert region is not None
    x0, y0, x1, y1 = region
    assert x0 <= 150
    assert x1 >= 380
    assert y0 <= 185
    assert y1 >= 425


def test_debug_stage_image_saves_image_and_metadata() -> None:
    from app.services.tryon_debug_utils import save_debug_stage_image

    debug_dir = Path("debug_output") / f"test_debug_stage_image_{uuid.uuid4().hex}"

    img = Image.new("RGB", (32, 24), (200, 210, 220))
    save_debug_stage_image(
        debug_session_dir=str(debug_dir),
        filename="12_after_color_fidelity.jpg",
        image=img,
        metadata={"stage": "after_color_fidelity", "pattern_score": 0.51},
    )

    assert (debug_dir / "12_after_color_fidelity.jpg").exists()
    meta_path = debug_dir / "12_after_color_fidelity.json"
    assert meta_path.exists()
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    assert metadata["stage"] == "after_color_fidelity"
    assert metadata["pattern_score"] == 0.51
