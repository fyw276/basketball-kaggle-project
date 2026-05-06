# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`hybrid` mode for try-on v2**: Warp + CatVTON two-stage blending with saturation-aware alpha
- **Knee-aware warp for pants**: Two-stage warp preserving pattern symmetry at knee-bend vs single-taper warp
- **torch.compile integration**: Optional GPU acceleration for CatVTON engine
- **Replace mode engine priority chain**: Configurable via `TRYON_V2_REPLACE_ENGINE_PRIORITY` (default: `warp,bailian,remote,catvton,diffusion`)
- **Replace mode warp-first strategy**: For AI engines (catvton/bailian/remote), warp is run first to guarantee 100% garment pixel fidelity before AI enhancement
- **CatVTON subprocess with MediaPipe PoseLandmarker**: No SCHP/DensePose dependency required
- **Whitebox debug mode**: `CATVTON_DEBUG_DIR` saves intermediate artifacts (01_input_person.jpg, 03_mask.png, 04_pose_keypoints.jpg, etc.)

### Changed

- **Try-on v2 modes**: Six modes now available: `strict` (default, pipeline A geometric warp + QC gate), `balanced` (looser QC), `replace` (AI generative with configurable engine priority), `realistic` (CatVTON deep learning), `professional` (CatVTON + postprocessing), `hybrid` (Warp + CatVTON blending)
- **Replace mode default priority**: Changed from `[catvton,bailian,remote,warp,diffusion]` to `[warp,bailian,remote,catvton,diffusion]` — warp runs first to guarantee garment fidelity
- **CatVTON subprocess runner**: Lives in `vton_inference_service/catvton_runner.py`; called by `backend/app/services/tryon_v2/catvton_engine_client.py` as subprocess to avoid dependency conflicts

### Fixed

- **Hybrid mode docstring**: Corrected function reference from `tryon_top_warp` to `tryon_top_warp_preserve` in hybrid try-on docstring
- **Test documentation**: Updated test docstring to reflect actual replace mode engine priority chain
- **Tech blueprint accuracy**: Removed reference to non-existent `tryon_engine_selector.py`, updated to reflect actual engine routing in `tryon_v2.py`
- **Overlay garment fidelity**: Fixed `overlay_top_onto_ai_result` returning `ai_warp_hybrid` with near-zero alpha when rembg fails on solid-color images (added Step 3b guard to return `ai_only` with reason)
- **VTON integration docs**: Corrected replace mode engine priority from `catvton→bailian→remote→warp→diffusion` to `warp→bailian→remote→catvton→diffusion`
- **Try-on v2 API tests**: Fixed mock paths for warp engine functions (`tryon_top_warp` → `tryon_top_warp_preserve`) and CatVTON config isolation
- **Overlay fidelity tests**: Rewrote to gracefully handle synthetic images where rembg produces near-zero alpha, avoiding false failures

---

## [2026-05-02] - Recent Commits Summary

### commit 3b6e239 - feat(tryon-v2): add hybrid mode, knee-aware warp, saturation alpha, and torch.compile

- Added `hybrid` mode combining warp + CatVTON with saturation-aware drape_alpha
- Added knee-aware pants warp for better pattern symmetry
- Added torch.compile integration option for GPU acceleration
- Updated CatVTON subprocess runner with improved diagnostics

### commit 80498c0 - docs: comprehensive documentation overhaul and accuracy fixes

- Fixed inaccurate documentation references
- Added hybrid mode documentation
- Updated tech blueprint to reflect actual implementation
- Added CatVTON VRAM optimization documentation

### commit 7e1d87c - feat(tryon-v2): CatVTON subprocess runner, whitebox debug, VRAM optimization

- Added CatVTON subprocess runner for backend integration
- Added whitebox debug mode with intermediate artifact saving
- Added VRAM optimization options (FP16, VAE slicing, xformers)
- Added diagnostic tools for CatVTON troubleshooting

### commit 61ea974 - fix(tryon-v2): complete replace-mode bailian diagnostics + add comprehensive test suite

- Fixed replace mode engine priority chain
- Added bailian diagnostics for production debugging
- Added comprehensive preservation tests for replace mode
- Added test suite for all engine fallback scenarios

---

## [2026-04-30] - VTON Delivery

### commit 43703f4 - fix(tryon-v2): CatVTON inference compatibility, MediaPipe 0.10 API, terminal log noise

- Fixed CatVTON inference compatibility issues
- Updated to MediaPipe 0.10 PoseLandmarker API
- Reduced terminal log noise from subprocess

### commit d4ce026 - fix(tryon-v2): debug pipeline save intermediate masks skeleton add FP16 CPU offload single-worker mode

- Added debug pipeline with intermediate mask saving
- Added FP16 CPU offload for low VRAM systems
- Added single-worker mode for stability

---

## [2026-04-21] - Try-on v2 Implementation Sync

### commit 87f9994 - feat(tryon-v2): add realistic and professional modes, CatVTON integration, and postprocessing pipeline

- Added `realistic` mode using CatVTON deep learning
- Added `professional` mode with postprocessing pipeline
- Added CatVTON integration with local subprocess execution
- Added postprocessing: edge blending, color matching, detail enhancement

### commit 6a01b7f - feat(tryon-v2): best-effort preprocess for posters and models

- Added best-effort garment preprocessing
- Auto-detect garment category (top/bottom/skirt/outfit)
- Handle poster and model images gracefully

### commit da26704 - feat(mobile): auto preprocess and auto category for try-on

- Added auto preprocess support in Flutter mobile app
- Added auto category detection in mobile try-on screen

---

## [2026-04-10] - Smart Outfit Release

### commit d7a8f5e - feat(smart-outfit): weather-aware + mood-aware outfit generation

- Added weather-aware smart outfit generation
- Added mood-based outfit recommendations
- Added Flutter home screen with weather display and today-recommendation card
