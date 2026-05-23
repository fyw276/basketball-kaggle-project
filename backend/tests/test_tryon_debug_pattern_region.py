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


def test_light_fidelity_filter_removes_off_center_white_blocks_only() -> None:
    from app.services.tryon_v2.warp_engine import _suppress_light_fidelity_artifact_candidates

    layer = np.full((100, 100, 3), (205, 198, 180), dtype=np.uint8)
    motif_candidate = np.zeros((100, 100), dtype=bool)
    motif_source = np.ones((100, 100), dtype=bool)

    # Simulates the pasted product-photo highlight block near a shoulder.
    layer[22:32, 22:32] = (246, 246, 246)
    motif_candidate[22:32, 22:32] = True

    # Simulates legitimate white details inside the chest print.
    layer[44:54, 46:56] = (246, 246, 246)
    motif_candidate[44:54, 46:56] = True

    filtered, removed_ratio = _suppress_light_fidelity_artifact_candidates(
        motif_candidate,
        layer,
        motif_source,
        gar_x0=20,
        gar_y0=20,
        gar_x1=80,
        gar_y1=80,
        body_cx=50,
        light_pattern_base=True,
    )

    assert removed_ratio > 0.0
    assert not filtered[24:30, 24:30].any()
    assert filtered[46:52, 48:54].all()


def test_light_block_repair_softens_shoulder_patch_preserves_center_print() -> None:
    from app.services.tryon_v2.warp_engine import _repair_light_garment_block_artifacts

    result = np.full((100, 100, 3), (198, 190, 176), dtype=np.float32)
    garment_mask = np.zeros((100, 100), dtype=bool)
    garment_mask[20:80, 20:80] = True
    motif_gate = np.zeros((100, 100), dtype=np.float32)

    result[24:36, 64:76] = (244, 244, 244)
    result[46:58, 46:58] = (244, 244, 244)
    motif_gate[46:58, 46:58] = 1.0

    repaired, ratio = _repair_light_garment_block_artifacts(
        result,
        garment_mask,
        motif_gate,
        gar_x0=20,
        gar_y0=20,
        gar_x1=80,
        gar_y1=80,
        body_cx=50,
        light_pattern_base=True,
    )

    assert ratio > 0.0
    assert float(repaired[28:34, 68:74].mean()) < 225.0
    assert float(repaired[48:56, 48:56].mean()) > 238.0


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
    assert x0 <= 170
    assert x1 >= 340
    assert y0 <= 185
    assert y1 >= 425


def test_light_print_change_region_does_not_expand_to_full_canvas_width() -> None:
    from app.services.tryon_pattern_utils import estimate_catvton_garment_region_from_change

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[165:610, 215:298] = (226, 184, 156)  # arms/body skin close to the log case
    person = Image.fromarray(person_arr, mode="RGB")

    result_arr = person_arr.copy()
    # Simulate CatVTON changing a very light top across almost the full canvas width.
    # The estimator must not accept the whole canvas as the garment overlay target.
    result_arr[153:432, 0:512] = (221, 216, 199)
    result_arr[178:420, 148:370] = (202, 198, 184)
    catvton_result = Image.fromarray(result_arr, mode="RGB")

    region = estimate_catvton_garment_region_from_change(
        catvton_result=catvton_result,
        person_image=person,
        pose_region={"x0": 181, "x1": 331, "neck_y": 174, "waist_y": 410},
        garment_category="top",
    )

    assert region is not None
    x0, _y0, x1, _y1 = region
    assert x0 > 0
    assert x1 < width
    assert (x1 - x0) <= int(width * 0.62)


def test_spatial_fidelity_light_print_does_not_create_sticker_background() -> None:
    from app.services.tryon_v2.warp_engine import catvton_color_fidelity_spatial

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[120:170, 222:290] = (238, 200, 174)  # face
    person_arr[175:610, 208:306] = (226, 184, 156)  # body/arms
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    catvton_arr[175:430, 145:380] = (198, 194, 180)  # generated top, not full canvas
    catvton_result = Image.fromarray(catvton_arr, mode="RGB")

    garment = make_light_cartoon_garment((768, 768))
    result, meta = catvton_color_fidelity_spatial(
        catvton_result=catvton_result,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        fidelity_strength=0.75,
    )

    region = meta.get("garment_region") or {}
    assert region.get("x0", 0) > 0
    assert region.get("x1", width) < width
    assert region.get("x1", width) - region.get("x0", 0) <= int(width * 0.62)

    result_np = np.asarray(result.convert("RGB"), dtype=np.float32)
    catvton_np = catvton_arr.astype(np.float32)
    diff = np.abs(result_np - catvton_np).mean(axis=2)

    left_bg_changed = float((diff[153:432, :80] > 18).mean())
    right_bg_changed = float((diff[153:432, 432:] > 18).mean())
    arm_changed = float((diff[190:430, 208:236] > 18).mean())

    assert left_bg_changed < 0.08
    assert right_bg_changed < 0.08
    assert arm_changed < 0.20


def test_spatial_fidelity_does_not_upscale_small_existing_print() -> None:
    from app.services.tryon_v2.warp_engine import catvton_color_fidelity_spatial

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[120:170, 222:290] = (238, 200, 174)
    person_arr[175:610, 208:306] = (226, 184, 156)
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    catvton_arr[175:430, 145:380] = (208, 203, 190)
    # CatVTON already generated a small print. Color fidelity may recolor it,
    # but it must not turn it into a much larger product-photo print.
    catvton_arr[275:345, 228:284] = (125, 175, 210)
    catvton_result = Image.fromarray(catvton_arr, mode="RGB")

    garment = make_light_cartoon_garment((768, 768))
    result, _meta = catvton_color_fidelity_spatial(
        catvton_result=catvton_result,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        fidelity_strength=0.75,
    )

    result_np = np.asarray(result.convert("RGB"), dtype=np.float32)
    top = result_np[175:430, 145:380]
    motif_like = (
        (top[:, :, 2] > top[:, :, 0] + 18)
        | (top[:, :, 1] > top[:, :, 0] + 14)
        | (top[:, :, 0] > top[:, :, 1] + 18)
    )
    ys, xs = np.where(motif_like)

    assert xs.size > 0
    assert (xs.max() - xs.min() + 1) <= 90
    assert (ys.max() - ys.min() + 1) <= 110


def test_spatial_fidelity_dark_print_does_not_create_large_shadow_rectangle() -> None:
    from app.services.tryon_v2.warp_engine import catvton_color_fidelity_spatial

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[120:170, 222:290] = (238, 200, 174)
    person_arr[175:610, 208:306] = (226, 184, 156)
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    catvton_arr[175:430, 145:380] = (205, 200, 188)
    catvton_arr[265:350, 224:292] = (55, 48, 46)
    catvton_result = Image.fromarray(catvton_arr, mode="RGB")

    garment = Image.new("RGB", (768, 768), (248, 248, 248))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((96, 96, 672, 704), fill=(28, 22, 22))
    draw.ellipse((270, 250, 500, 520), fill=(145, 22, 28))
    draw.rectangle((305, 520, 465, 650), fill=(22, 18, 18))

    result, _meta = catvton_color_fidelity_spatial(
        catvton_result=catvton_result,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        fidelity_strength=0.75,
    )

    result_np = np.asarray(result.convert("RGB"), dtype=np.float32)
    top = result_np[175:430, 145:380]
    dark_or_red = ((top[:, :, 0] < 90) & (top[:, :, 1] < 80) & (top[:, :, 2] < 80)) | (
        (top[:, :, 0] > 110) & (top[:, :, 1] < 60) & (top[:, :, 2] < 70)
    )

    assert float(dark_or_red.mean()) < 0.22


def test_spatial_fidelity_keeps_catvton_shape_and_transfers_only_small_motif() -> None:
    from app.services.tryon_v2.warp_engine import catvton_color_fidelity_spatial

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[120:170, 222:290] = (238, 200, 174)
    person_arr[175:610, 208:306] = (226, 184, 156)
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    # CatVTON has already generated a natural shirt shape. The fidelity pass
    # should not repaint this whole generated shirt with product-photo pixels.
    catvton_arr[175:430, 135:390] = (196, 193, 185)
    catvton_arr[190:260, 120:150] = (196, 193, 185)  # sleeve extension
    catvton_arr[190:260, 375:405] = (196, 193, 185)
    catvton_result = Image.fromarray(catvton_arr, mode="RGB")

    garment = Image.new("RGB", (768, 768), (248, 248, 248))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((96, 96, 672, 704), fill=(35, 32, 30))
    draw.ellipse((410, 255, 455, 300), fill=(210, 52, 48))
    draw.rectangle((424, 300, 442, 340), fill=(250, 235, 180))

    result, _meta = catvton_color_fidelity_spatial(
        catvton_result=catvton_result,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        fidelity_strength=0.75,
    )

    result_np = np.asarray(result.convert("RGB"), dtype=np.float32)
    catvton_np = catvton_arr.astype(np.float32)
    diff = np.abs(result_np - catvton_np).mean(axis=2)

    left_shirt_body_change = float(diff[210:380, 145:220].mean())
    right_shirt_body_change = float(diff[210:380, 310:380].mean())
    changed_ratio = float((diff[175:430, 135:390] > 18).mean())

    assert left_shirt_body_change < 8.0
    assert right_shirt_body_change < 8.0
    assert changed_ratio < 0.12


def test_spatial_fidelity_restores_low_contrast_upper_chest_prints() -> None:
    from app.services.tryon_v2.warp_engine import catvton_color_fidelity_spatial

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[95:170, 220:292] = (238, 200, 174)
    person_arr[175:610, 208:306] = (226, 184, 156)
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    catvton_arr[160:400, 95:410] = (205, 200, 188)
    catvton_result = Image.fromarray(catvton_arr, mode="RGB")

    garment = Image.new("RGB", (768, 768), (248, 248, 248))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((40, 80, 728, 710), fill=(236, 230, 214))
    for x, y, color in [
        (260, 170, (180, 202, 218)),
        (380, 190, (245, 218, 122)),
        (500, 175, (190, 218, 198)),
        (310, 430, (180, 202, 218)),
        (440, 455, (245, 218, 122)),
        (540, 420, (190, 218, 198)),
    ]:
        draw.ellipse((x - 20, y - 20, x + 20, y + 20), fill=color, outline=(120, 130, 135), width=2)

    result, _meta = catvton_color_fidelity_spatial(
        catvton_result=catvton_result,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        fidelity_strength=0.75,
    )

    result_np = np.asarray(result.convert("RGB"), dtype=np.float32)
    catvton_np = catvton_arr.astype(np.float32)
    diff = np.abs(result_np - catvton_np).mean(axis=2)

    upper_changed = float((diff[165:275, 110:400] > 8.0).mean())
    lower_changed = float((diff[300:395, 110:400] > 8.0).mean())

    assert upper_changed > 0.008
    assert lower_changed > 0.008


def test_spatial_fidelity_dark_logo_garment_keeps_dark_base_color() -> None:
    from app.services.tryon_v2.warp_engine import catvton_color_fidelity_spatial

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[95:170, 220:292] = (238, 200, 174)
    person_arr[175:610, 208:306] = (226, 184, 156)
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    catvton_arr[160:400, 95:410] = (88, 90, 88)
    catvton_arr[205:245, 322:370] = (124, 126, 124)  # localized gray mismatch
    catvton_result = Image.fromarray(catvton_arr, mode="RGB")

    garment = Image.new("RGB", (768, 768), (248, 248, 248))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((40, 80, 728, 710), fill=(48, 52, 54))
    draw.ellipse((520, 180, 568, 228), fill=(218, 58, 44))
    draw.rectangle((535, 228, 555, 268), fill=(245, 224, 128))

    result, _meta = catvton_color_fidelity_spatial(
        catvton_result=catvton_result,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        fidelity_strength=0.75,
    )

    result_np = np.asarray(result.convert("RGB"), dtype=np.float32)
    gray_patch = result_np[205:245, 322:370]
    patch_mean = float(gray_patch.mean())

    assert patch_mean < 112.0


def test_spatial_fidelity_keeps_scattered_prints_off_shoulders() -> None:
    from app.services.tryon_v2.warp_engine import catvton_color_fidelity_spatial

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[95:170, 220:292] = (238, 200, 174)
    person_arr[175:610, 208:306] = (226, 184, 156)
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    # Natural generated shirt shape: broad bbox, but shoulders are still mostly
    # plain fabric. Fidelity should not scatter product-photo stars across them.
    catvton_arr[175:430, 145:380] = (205, 200, 188)
    catvton_arr[195:260, 115:155] = (205, 200, 188)
    catvton_arr[195:260, 370:410] = (205, 200, 188)
    catvton_result = Image.fromarray(catvton_arr, mode="RGB")

    garment = Image.new("RGB", (768, 768), (248, 248, 248))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((40, 80, 728, 710), fill=(236, 230, 214))
    # Main chest motif.
    draw.ellipse((315, 275, 453, 430), fill=(245, 220, 180), outline=(70, 85, 95), width=4)
    draw.polygon((384, 160, 315, 275, 453, 275), fill=(170, 205, 230), outline=(70, 85, 95))
    draw.rectangle((350, 430, 418, 540), fill=(145, 195, 220), outline=(70, 85, 95), width=3)
    # Scattered small stars/dots in the product photo should not dominate the worn result.
    for x, y, color in [
        (150, 150, (120, 170, 210)),
        (610, 155, (120, 170, 210)),
        (150, 280, (210, 120, 160)),
        (615, 300, (210, 120, 160)),
        (185, 510, (170, 220, 185)),
        (590, 540, (170, 220, 185)),
    ]:
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=color, outline=(70, 85, 95), width=2)

    result, _meta = catvton_color_fidelity_spatial(
        catvton_result=catvton_result,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        fidelity_strength=0.75,
    )

    result_np = np.asarray(result.convert("RGB"), dtype=np.float32)
    catvton_np = catvton_arr.astype(np.float32)
    diff = np.abs(result_np - catvton_np).mean(axis=2)

    chest_changed = float((diff[170:430, 130:390] > 10.0).mean())
    left_shoulder_changed = float((diff[185:285, 115:175] > 10.0).mean())
    right_shoulder_changed = float((diff[185:285, 350:410] > 10.0).mean())
    chest_max_delta = float(diff[170:430, 130:390].max())

    assert chest_changed > 0.005
    assert chest_max_delta > 50.0
    assert left_shoulder_changed < 0.06
    assert right_shoulder_changed < 0.06


def test_spatial_fidelity_constrains_high_coverage_motif_even_with_existing_color() -> None:
    from app.services.tryon_v2.warp_engine import catvton_color_fidelity_spatial

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[95:170, 220:292] = (238, 200, 174)
    person_arr[175:610, 208:306] = (226, 184, 156)
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    catvton_arr[175:430, 145:380] = (204, 200, 188)
    catvton_arr[195:260, 115:155] = (204, 200, 188)
    catvton_arr[195:260, 370:410] = (204, 200, 188)
    # Slight existing color/noise used to trick the old branch into bypassing
    # motif constraining, as happened in the real white debug samples.
    catvton_arr[205:245, 158:210] = (198, 188, 160)
    catvton_arr[205:245, 318:370] = (198, 188, 160)
    catvton_result = Image.fromarray(catvton_arr, mode="RGB")

    garment = Image.new("RGB", (768, 768), (248, 248, 248))
    draw = ImageDraw.Draw(garment)
    draw.rectangle((40, 80, 728, 710), fill=(236, 230, 214))
    draw.ellipse((315, 275, 453, 430), fill=(245, 220, 180), outline=(70, 85, 95), width=4)
    draw.polygon((384, 160, 315, 275, 453, 275), fill=(170, 205, 230), outline=(70, 85, 95))
    draw.rectangle((350, 430, 418, 540), fill=(145, 195, 220), outline=(70, 85, 95), width=3)
    for x, y, color in [
        (150, 150, (120, 170, 210)),
        (610, 155, (120, 170, 210)),
        (150, 280, (210, 120, 160)),
        (615, 300, (210, 120, 160)),
        (185, 510, (170, 220, 185)),
        (590, 540, (170, 220, 185)),
    ]:
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=color, outline=(70, 85, 95), width=2)

    result, _meta = catvton_color_fidelity_spatial(
        catvton_result=catvton_result,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        fidelity_strength=0.75,
    )

    result_np = np.asarray(result.convert("RGB"), dtype=np.float32)
    catvton_np = catvton_arr.astype(np.float32)
    diff = np.abs(result_np - catvton_np).mean(axis=2)

    left_shoulder_changed = float((diff[185:285, 115:175] > 10.0).mean())
    right_shoulder_changed = float((diff[185:285, 350:410] > 10.0).mean())

    assert left_shoulder_changed < 0.06
    assert right_shoulder_changed < 0.06


def test_resized_upper_mask_stays_on_torso_without_reaching_shoulders_or_face() -> None:
    from app.services.tryon_mask_utils import expand_binary_mask_to_ratio

    width, height = 512, 768
    mask = np.zeros((height, width), dtype=np.uint8)
    # Mirrors the latest failing white-box step 08 bbox: x=159..356, y=185..367.
    mask[185:368, 159:357] = 255

    expanded = expand_binary_mask_to_ratio(
        mask,
        target_ratio=0.075,
        kernel_size=5,
        max_iterations=8,
        max_width_ratio=0.45,
        max_area_ratio=0.09,
        top_guard_y=170,
    )

    ys, xs = np.where(expanded > 127)
    assert xs.size > 0
    assert 0.070 <= float((expanded > 127).mean()) <= 0.090
    assert (xs.max() - xs.min() + 1) <= int(width * 0.45)
    assert ys.min() >= 170


def test_garment_preprocess_removes_border_connected_black_background() -> None:
    from app.services.garment_preprocess import (
        _remove_border_background,
        _remove_dark_edge_contamination,
    )

    arr = np.zeros((160, 160, 3), dtype=np.uint8)
    arr[35:135, 30:130] = (235, 226, 205)
    arr[35:135, 30:33] = (8, 8, 8)
    arr[35:38, 30:130] = (8, 8, 8)
    arr[70:88, 72:92] = (5, 5, 5)  # inner label/print must survive
    alpha = np.full((160, 160), 255, dtype=np.uint8)

    rgb_clean, alpha_clean = _remove_border_background(arr, alpha)
    rgb_clean, alpha_clean = _remove_dark_edge_contamination(rgb_clean, alpha_clean)

    assert alpha_clean[0, 0] == 0
    assert alpha_clean[36, 31] == 0
    assert alpha_clean[80, 80] == 255
    assert tuple(rgb_clean[80, 80]) == (5, 5, 5)


def test_garment_struct_cutout_cleanup_preserves_inner_dark_prints() -> None:
    from app.services.tryon_v2.garment_struct import (
        _remove_border_background_from_rgba,
        _remove_dark_edge_contamination_from_rgba,
    )

    rgb_arr = np.zeros((160, 160, 3), dtype=np.uint8)
    rgb_arr[35:135, 30:130] = (238, 228, 207)
    rgb_arr[35:135, 30:33] = (8, 8, 8)
    rgb_arr[35:38, 30:130] = (8, 8, 8)
    rgb_arr[70:88, 72:92] = (5, 5, 5)
    rgb = Image.fromarray(rgb_arr, mode="RGB")

    rgba_arr = np.dstack([rgb_arr, np.full((160, 160), 255, dtype=np.uint8)])
    rgba = Image.fromarray(rgba_arr, mode="RGBA")

    cleaned = _remove_border_background_from_rgba(rgba, rgb)
    cleaned = _remove_dark_edge_contamination_from_rgba(cleaned)
    cleaned_arr = np.asarray(cleaned, dtype=np.uint8)

    assert cleaned_arr[0, 0, 3] == 0
    assert cleaned_arr[36, 31, 3] == 0
    assert cleaned_arr[80, 80, 3] == 255
    assert tuple(cleaned_arr[80, 80, :3]) == (5, 5, 5)


def test_spatial_fidelity_never_restores_overlay_over_face() -> None:
    from app.services.tryon_v2.warp_engine import catvton_color_fidelity_spatial

    width, height = 512, 768
    person_arr = np.full((height, width, 3), 245, dtype=np.uint8)
    person_arr[95:170, 220:292] = (238, 200, 174)
    person_arr[95:120, 215:297] = (38, 32, 30)  # hair
    person_arr[138:170, 215:297] = (42, 35, 32)  # dark jaw/neck edge inside protect band
    person_arr[122:132, 235:246] = (35, 25, 20)
    person_arr[122:132, 265:276] = (35, 25, 20)
    person_arr[175:610, 208:306] = (226, 184, 156)
    person = Image.fromarray(person_arr, mode="RGB")

    catvton_arr = person_arr.copy()
    # Simulate an over-tall light garment change that reaches the face-protection band.
    catvton_arr[135:430, 145:380] = (205, 200, 188)
    catvton_arr[138:170, 215:297] = (44, 36, 34)
    catvton_result = Image.fromarray(catvton_arr, mode="RGB")

    garment = make_light_cartoon_garment((768, 768))
    result, _meta = catvton_color_fidelity_spatial(
        catvton_result=catvton_result,
        original_garment=garment,
        person_image=person,
        garment_category="top",
        fidelity_strength=0.75,
    )

    result_np = np.asarray(result.convert("RGB"), dtype=np.float32)
    catvton_np = catvton_arr.astype(np.float32)
    face_diff = np.abs(result_np[95:170, 220:292] - catvton_np[95:170, 220:292]).mean(axis=2)
    dark_edge_diff = np.abs(result_np[138:170, 220:292] - catvton_np[138:170, 220:292]).mean(axis=2)

    assert float((face_diff > 10).mean()) < 0.02
    assert float(face_diff.mean()) < 3.0
    assert float((dark_edge_diff > 10).mean()) < 0.02


def test_debug_stage_image_saves_image_and_metadata() -> None:
    from app.services.tryon_debug_utils import resolve_debug_session_dir, save_debug_stage_image

    debug_dir = Path("debug_output") / f"test_debug_stage_image_{uuid.uuid4().hex}"

    img = Image.new("RGB", (32, 24), (200, 210, 220))
    save_debug_stage_image(
        debug_session_dir=str(debug_dir),
        filename="12_after_color_fidelity.jpg",
        image=img,
        metadata={"stage": "after_color_fidelity", "pattern_score": 0.51},
    )

    resolved_debug_dir = resolve_debug_session_dir(debug_dir)
    assert resolved_debug_dir is not None
    assert (resolved_debug_dir / "12_after_color_fidelity.jpg").exists()
    meta_path = resolved_debug_dir / "12_after_color_fidelity.json"
    assert meta_path.exists()
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    assert metadata["stage"] == "after_color_fidelity"
    assert metadata["pattern_score"] == 0.51


def test_relative_catvton_debug_dir_resolves_from_project_root(monkeypatch) -> None:
    from app.services.tryon_debug_utils import resolve_debug_session_dir

    project_root = Path(__file__).resolve().parents[2]
    backend_cwd = project_root / "backend"
    monkeypatch.chdir(backend_cwd)

    resolved = resolve_debug_session_dir(
        "debug_output/tryon_case",
        project_root=project_root,
    )

    assert resolved == project_root / "debug_output" / "tryon_case"


def test_debug_stage_bytes_saves_exact_payload() -> None:
    from app.services.tryon_debug_utils import resolve_debug_session_dir, save_debug_stage_bytes

    debug_dir = Path("debug_output") / f"test_debug_stage_bytes_{uuid.uuid4().hex}"
    payload = b"jpeg-bytes-used-for-upload"

    save_debug_stage_bytes(
        debug_session_dir=str(debug_dir),
        filename="99_backend_final_returned.jpg",
        data=payload,
        metadata={"stage": "backend_final_returned"},
    )

    resolved_debug_dir = resolve_debug_session_dir(debug_dir)
    assert resolved_debug_dir is not None
    assert (resolved_debug_dir / "99_backend_final_returned.jpg").read_bytes() == payload
    metadata = json.loads(
        (resolved_debug_dir / "99_backend_final_returned.json").read_text(encoding="utf-8")
    )
    assert metadata["stage"] == "backend_final_returned"
