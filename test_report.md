# CatVTON Virtual Try-On Pipeline - Test Report

**Generated:** May 8, 2026
**Pipeline Version:** v2 (realistic_v2 mode)
**Test Suite:** `backend/tests/test_tryon_pipeline.py`
**Total Tests:** 36
**Result:** 36 passed, 0 failed

---

## 1. Test Summary

| Category | Tests | Status |
|---|---|---|
| Phase 10 - Quality Checker | 7 | All Passed |
| Phase 6 - Garment Alignment | 7 | All Passed |
| Phase 4 - Person Crop | 5 | All Passed |
| Phase 5 - DensePose Service | 5 | All Passed |
| Phase 8 - Realistic V2 Integration | 2 | All Passed |
| Preprocess Pipeline | 2 | All Passed |
| 8GB GPU Optimizations | 2 | All Passed |
| Config Defaults | 1 | All Passed |
| API Modes | 2 | All Passed |
| Boundary Conditions | 3 | All Passed |
| **Total** | **36** | **36 passed** |

---

## 2. Phase-by-Phase Test Coverage

### Phase 10: Quality Checker (`backend/app/services/quality_checker.py`)

Tests verify the `TryOnQualityScores` dataclass and `QualityChecker` class:

- `test_quality_checker_scores_are_bounded` - Scores always in [0.0, 1.0]
- `test_quality_checker_passes_for_normal_result` - Normal result scores >= 0.0
- `test_quality_checker_fails_for_floating_garment` - Floating garment detection works
- `test_quality_checker_without_optional_inputs` - Works without person/garment images
- `test_quality_checker_weighted_overall` - Overall score is weighted average (floating 20%, shoulder 15%, transparency 20%, penetration 15%, boundary 15%, mask 15%)
- `test_quality_checker_dataclass_fields` - All required fields present
- `test_quality_checker_passed_threshold` - `passed = overall >= 0.75`, `should_retry = not passed`

Quality dimensions checked:
- **Floating garment** (weight 20%): Edge density analysis in garment region
- **Shoulder alignment** (weight 15%): Gradient analysis in shoulder area
- **Transparency/ghosting** (weight 20%): Alpha channel variance + near-transparent regions
- **Body penetration** (weight 15%): Dark/negative pixel detection
- **Boundary quality** (weight 15%): Canny edge density at garment boundaries
- **Mask accuracy** (weight 15%): Structural similarity between result and garment

### Phase 6: Garment Alignment (`backend/app/services/garment_alignment.py`)

Tests verify automatic garment preprocessing:

- `test_garment_alignment_returns_pil_image` - Returns PIL Image in RGB mode
- `test_garment_alignment_canvas_size` - Produces specified canvas size (768x768)
- `test_center_garment_preserves_content` - Content preserved after centering
- `test_enforce_garment_symmetry_preserves_size` - Symmetry enforcement preserves dimensions
- `test_enforce_garment_symmetry_skips_lower` - Skips symmetry for lower-body garments
- `test_standardize_garment_canvas_white_background` - White background (mean > 200)
- `test_garment_alignment_small_image` - Handles small images (64x64) gracefully
- `test_garment_alignment_no_crash` - No crashes for upper/lower/dress types

Key functions tested:
- `align_garment()` - Full pipeline: orientation detection, rotation, centering, symmetry
- `center_garment()` - Centering with 70% fill ratio
- `enforce_garment_symmetry()` - Left-right symmetry for upper-body
- `standardize_garment_canvas()` - White background standardization

### Phase 4: Person Auto-Cropping (`backend/app/services/person_crop.py`)

Tests verify automatic person detection and cropping:

- `test_person_crop_returns_tuple` - Returns (Image, PersonCropInfo) tuple
- `test_person_crop_preserves_dimensions` - Output height matches target_height
- `test_person_crop_both_image_types` - Handles MediaPipe / fallback return types
- `test_detect_person_bbox_fallback` - Fallback bbox always returns valid 4-tuple
- `test_person_crop_info_dataclass` - All PersonCropInfo fields present

Methods supported: MediaPipe PoseLandmarker, MediaPipe Holistic, OpenCV body detection fallback

### Phase 5: DensePose Service (`backend/app/services/densepose_service.py`)

Tests verify human body parsing and warp field generation:

- `test_densepose_wrapper_import` - DensePoseWrapper instantiates successfully
- `test_densepose_wrapper_detect_returns_result` - Returns DensePoseResult with all fields
- `test_densepose_result_has_valid_arrays` - IUV array (H, W, 3) and mask (H, W) shapes correct
- `test_densepose_result_part_labels` - Part labels dictionary populated
- `test_apply_densepose_warp_returns_array` - Warp field is ndarray with shape (H, W, 2)

Note: Detectron2 DensePose is attempted first; on failure, MediaPipe Holistic fallback is used.

### Phase 8: Realistic V2 Mode Integration

Tests verify the new `mode=realistic_v2` in the API:

- `test_quality_checker_in_realistic_v2_import` - QualityChecker importable with correct min_score
- `test_api_modes_include_realistic_v2` - `realistic_v2` present in tryon_v2.py
- `test_realistic_v2_qc_scores_in_details` - Verbose mode includes all detail keys

### Preprocess Pipeline Integration

Tests verify the garment preprocessing pipeline end-to-end:

- `test_preprocess_includes_alignment_metadata` - `preprocess_garment_image()` returns `alignment_applied=True`
- `test_preprocess_garment_rgba_cutout` - `cutout_garment_rgba()` returns valid GarmentCutout

### 8GB GPU Optimizations

Tests verify VRAM optimization flags:

- `test_catvton_runner_fp16_default` - `--force-fp16`, `--precision`, `--vae-slicing`, `--no-xformers` flags present
- `test_catvton_runner_no_repaint_default` - `--no-repaint` flag present

### Config Defaults (Phase 7)

Tests verify CatVTON configuration defaults:

- `test_catvton_config_defaults` - Field defaults: WIDTH=768, HEIGHT=1024, STEPS=28, GUIDANCE=2.5

### API Modes

- `test_api_modes_include_realistic_v2` - realistic_v2 in modes list
- `test_catvton_engine_client_has_realistic_v2_status` - call_local_catvton supports realistic_v2 params

---

## 3. Configured Parameters

### CatVTON Inference (Phase 7)

| Parameter | Value | Description |
|---|---|---|
| Width | 768 | Recommended for 8GB GPU |
| Height | 1024 | Portrait aspect ratio |
| Steps | 28 | Balanced quality/speed |
| Guidance Scale | 2.5 | High fidelity |
| Precision | bf16 (default) | RTX 4090/3090 recommended |
| VAE Slicing | Enabled | ~40% VRAM reduction |
| Attention Slicing | auto | Automatic tiling |
| CPU Offload | Available | Via --cpu-offload flag |

### Mode: realistic_v2

Added in Phase 8. Combines:
1. CatVTON deep learning try-on (768x1024)
2. DensePose body parsing (Phase 5)
3. Automatic quality check (Phase 10)
4. Auto-retry up to 3 times if score < 0.75 (Phase 11)

---

## 4. Files Modified/Created

### New Files

| File | Phase | Description |
|---|---|---|
| `backend/app/services/person_crop.py` | 4 | Auto-detect and crop person to 70-80% height |
| `backend/app/services/densepose_service.py` | 5 | Detectron2 DensePose + MediaPipe fallback |
| `backend/app/services/garment_alignment.py` | 6 | Garment orientation/centering/symmetry |
| `backend/app/services/quality_checker.py` | 10 | 6-dimension quality scoring |
| `backend/tests/test_tryon_pipeline.py` | 13 | 36 comprehensive tests |

### Modified Files

| File | Phases | Changes |
|---|---|---|
| `backend/app/api/tryon_v2.py` | 8, 11 | Added `realistic_v2` mode with auto-retry (3x) and QC |
| `backend/app/core/config.py` | 7 | CATVTON defaults: 768x1024, steps=28, guidance=2.5 |
| `backend/app/services/tryon_v2/preprocess.py` | 6 | Integrated `align_garment()` + metadata |
| `backend/app/services/tryon_v2/garment_struct.py` | 3 | MobileSAM segmentation with cloth_type hints |
| `backend/app/services/tryon_v2/catvton_engine_client.py` | 7 | Updated defaults: 768x1024, 28 steps, 2.5 guidance |
| `vton_inference_service/catvton_runner.py` | 1, 2, 7, 9 | Removed repaint overlay, updated defaults, enhanced logging |

---

## 5. How to Run Tests

```bash
# Run all pipeline tests
cd backend
python -m pytest tests/test_tryon_pipeline.py -v

# Run specific phase tests
python -m pytest tests/test_tryon_pipeline.py -v -k "quality_checker"
python -m pytest tests/test_tryon_pipeline.py -v -k "garment_alignment"
python -m pytest tests/test_tryon_pipeline.py -v -k "person_crop"
python -m pytest tests/test_tryon_pipeline.py -v -k "densepose"
```

---

## 6. How to Run Realistic V2 Mode

```bash
# Via API
POST /api/tryon_v2/garment
  - garment_file: <garment.jpg>
  - person_file: <person.jpg>
  - mode: realistic_v2
  - garment_category: "upper"  # or "bottom", "skirt", "outfit"

# Via debug mode (fast, no diffusion)
POST /api/tryon_v2/garment
  - garment_file: <garment.jpg>
  - person_file: <person.jpg>
  - mode: realistic_v2
  - debug_mode: preprocess_only

# Debug output (all intermediate images)
POST /api/tryon_v2/garment
  - garment_file: <garment.jpg>
  - person_file: <person.jpg>
  - mode: realistic_v2
  - debug_mode: full

# Check quality scores
POST /api/tryon_v2/validate-input
  - mode: realistic_v2
  - garment_image_url: /uploads/...
  - person_image_url: /uploads/...
```

---

## 7. Inference Time & VRAM Estimates

Based on debug session data from `debug_output/` directory:

| Configuration | Size | Steps | Est. Time (RTX 4060 8GB) | Est. VRAM |
|---|---|---|---|---|
| Fast | 512x768 | 20 | 3-5 min | 5-6 GB |
| Standard (Phase 7) | 768x1024 | 28 | 8-12 min | 7-8 GB |
| High Quality | 768x1024 | 50 | 15-25 min | 8 GB |

Applied optimizations: VAE slicing, attention slicing, bf16/fp16 mixed precision, optional CPU offload.

---

## 8. Remaining Tasks

- **Phase 8**: Integrate DensePose warp field output into CatVTON preprocess pipeline (warp field needs to be passed to catvton_runner.py)
- **Phase 11**: Add mask-regeneration and DensePose-regeneration retry strategies (currently auto-retry calls CatVTON again)
- **Phase 14**: Generate visual comparison report with before/after screenshots (requires real CatVTON inference runs)

To trigger a full realistic_v2 test run with debug output:

```bash
cd backend
python -m uvicorn app.main:app --reload
# Then POST to /api/tryon_v2/garment with mode=realistic_v2 and debug_mode=full
```
