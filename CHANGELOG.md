# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Agent chat SSE endpoint** (`POST /api/v1/agent/chat-stream`): multi-round OpenAI-compatible tool loop with structured `step`, `skill_execution`, `tool_call`, `tool_result`, `answer`, `error`, and `done` events.
- **Agent tool registry** (`backend/app/agent/tools/`): single source of truth for wardrobe, weather, outfit, mood, memory, collection, and try-on tools used by the LLM tool loop.
- **Agent skills API** (`/api/v1/agent/skills`): list/create skills, capture skills from tool-call sequences, and preview keyword-triggered prompt injection.
- **Hybrid memory search** (`memory_search.py`, `embedding_client.py`): keyword Jaccard + embedding cosine retrieval with keyword-only fallback.
- **Prometheus metrics endpoint** (`GET /metrics`): exports dependency, try-on v2, and agent run/tool/failure metrics.
- **Flutter Agent UI** (`mobile/lib/features/agent/`): streaming chat page with visible pipeline/tool progress.
- **Chunk-safe SSE parser** (`mobile/lib/core/services/sse_parser.dart`): shared by smart-outfit streaming and Agent chat.
- **Wardrobe picker sheet** (`mobile/lib/core/widgets/wardrobe_picker_sheet.dart`): analysis and try-on screens can reuse existing wardrobe images.
- **`tryon_mask_utils.py`** (`backend/app/services/`): `expand_binary_mask_to_ratio()` — dilates a binary mask to a target area/width ratio with optional top guard, width cap, and max-area constraints. Used by CatVTON subprocess to produce properly-sized upper-body masks.
- **`fidelity_guard.py`** (`backend/app/services/tryon_v2/`): fidelity engine decision guard module providing `extract_engine_decision_features()`, `decide_color_fidelity_engine()` (with hysteresis guard band at pattern_score 0.38-0.45), `evaluate_cutout_alpha_qc()`, `score_input_anomaly()` (mirror-ghost + JPEG artifact detection), `detect_post_cf_artifacts()`, and `estimate_pattern_enhance_strength()`.
- **`test_tryon_fidelity_guard.py`** (`backend/tests/`): 8 unit tests covering the fidelity guard module (engine decision, QC gates, anomaly detection, artifact reporting, pattern strength estimation).
- **Expanded `test_tryon_debug_pattern_region.py`**: 10 new/updated tests covering light cartoon print detection, CatVTON garment region expansion beyond pose torso, width guard enforcement, spatial fidelity (no sticker background, no motif upscaling, no dark-shadow rectangle, shape preservation, face never restored, upper mask torso-only), debug stage image/bytes save, and relative debug dir resolution.

### Changed

- **`tryon_debug_utils.py`**: Added `resolve_debug_session_dir()` for consistent project-root-relative path resolution; added `save_debug_stage_bytes()` for exact byte payload storage with sidecar metadata.
- **`tryon_pattern_utils.py`**: `estimate_catvton_garment_region_from_change()` now enforces a width cap for upper-body garments (`max_top_w = min(62% canvas, max(210% pose_w, 38% canvas))`) to prevent overly wide garment regions from being accepted.
- **`warp_engine.py`**: `catvton_color_fidelity_spatial()` now computes `fidelity_allowed` mask from person-vs-CatVTON pixel difference, excluding near-white-background and skin-like pixels from fidelity application; added `motif_gate` to restrict fidelity to only small-color-distinct regions (motif-only fidelity); removed layer restoration on face-protection alpha degradation (keeps protected layer instead).
- **`catvton_runner.py`**: Replaced hard-coded dilation (kernel=5x5, iterations=3) with `expand_binary_mask_to_ratio(target_ratio=0.075, max_area_ratio=0.09, max_width_ratio=0.45, top_guard_y=22% height)` for upper-body masks.
- **`tryon_v2.py`**: CatVTON subprocess `debug_session_dir` now propagates to post-CatVTON backend stages (color fidelity, postprocess); added `12_after_color_fidelity.jpg` debug stage image save; added `99_backend_final_returned.jpg` debug stage bytes save.
- **Rate limiting**: `ENABLE_RATE_LIMIT` now defaults to true, and `RATE_LIMIT_TRYON_PER_MINUTE` applies independent limits to `/api/v1/tryon` and `/api/v2/tryon`.
- **CatVTON reproducibility**: `CATVTON_SEED` controls subprocess seed; default fixed seed is `42`, `-1` requests random behavior.
- **Hybrid mode default**: `TRYON_V2_HYBRID_WARP_OVERLAY_ENABLED=false` returns successful local CatVTON output directly; true restores legacy warp overlay behavior.
- **Docs**: Added `docs/AGENT_AND_TRYON_FIDELITY_SYNC_2026-05-24.md` and synchronized README, backend README, mobile README, project status, delivery status, and doc index.

### Fixed

- **Docs: try-on v2 mode count**: Fixed README, VTON_INTEGRATION.md, SERVICE_MODULES_GUIDE.md, TRYON_TECH_BLUEPRINT_AB.md to reflect **7 modes** (not 6), adding `realistic_v2` mode
- **Docs: replace engine priority**: Corrected replace mode engine priority in README, VTON_INTEGRATION.md, SERVICE_MODULES_GUIDE.md, TRYON_TECH_BLUEPRINT_AB.md to **warp first** (not CatVTON first) — default `warp,bailian,remote,catvton,diffusion`; warp runs before AI engines to provide 100% garment pixel fidelity; `TRYON_V2_REPLACE_SKIP_WARP=true` skips warp
- **Backend: similarity analysis**: Fixed `SimilarityDecision` attribute error (`target_decision.group` not `.category`), added logger import, added `image_url` validation with path-derivation fallback
- **Backend: try-on v2 quality**: Fixed `cv2` import scope to prevent `UnboundLocalError`, improved garment preprocessing (CLOSE+dilate morphology, auto bbox expansion for small masks), fixed postprocess face protection cascade, fixed `haar` cascade path for Windows Chinese usernames
- **Flutter: similarity screen**: Fixed image URL construction to strip `/api/v1` suffix before prepending to relative upload URLs

## [1.6.0] - 2026-05-02

### Added

- **`hybrid` mode for try-on v2**: Warp + CatVTON two-stage blending with saturation-aware alpha
- **Knee-aware warp for pants**: Two-stage warp preserving pattern symmetry at knee-bend vs single-taper warp
- **torch.compile integration**: Optional GPU acceleration for CatVTON engine
- **Replace mode engine priority chain**: Configurable via `TRYON_V2_REPLACE_ENGINE_PRIORITY` (default: `warp,bailian,remote,catvton,diffusion`)
- **Replace mode warp-first strategy**: For AI engines (catvton/bailian/remote), warp is run first to guarantee 100% garment pixel fidelity before AI enhancement
- **CatVTON subprocess with MediaPipe PoseLandmarker**: No SCHP/DensePose dependency required
- **Whitebox debug mode**: `CATVTON_DEBUG_DIR` saves intermediate artifacts (01_input_person.jpg, 03_mask.png, 04_pose_keypoints.jpg, etc.)

### Changed

- **Try-on v2 modes**: Seven modes now available: `strict` (default, pipeline A geometric warp + QC gate), `balanced` (looser QC), `replace` (AI generative with configurable engine priority, warp runs first for garment fidelity), `realistic` (CatVTON deep learning + color fidelity), `realistic_v2` (CatVTON v2 + saturation-aware fidelity), `professional` (CatVTON + postprocessing), `hybrid` (Warp + CatVTON blending)
- **Replace mode default priority**: `warp,bailian,remote,catvton,diffusion` — warp runs first to guarantee 100% garment pixel fidelity before AI enhancement; `TRYON_V2_REPLACE_SKIP_WARP=true` skips warp
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
