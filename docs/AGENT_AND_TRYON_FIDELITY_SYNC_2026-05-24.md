# Agent and Try-On Fidelity Sync (2026-05-24)

## Scope

This sync documents the current branch work across three surfaces:

1. Agent chat and reusable skills.
2. CatVTON / try-on v2 fidelity fixes.
3. Flutter client support for streaming and wardrobe-based image reuse.

## Backend Agent

- Added `POST /api/v1/agent/chat-stream`, an SSE endpoint that runs a bounded multi-round tool loop.
- SSE events use a structured envelope with `run_id`, `step_id`, `event`, `tool_name`, `elapsed_ms`, `status`, and optional `data`.
- Event types currently include `step`, `skill_execution`, `tool_call`, `tool_result`, `answer`, `error`, and `done`.
- Agent runs persist to `agent_runs`, including outcome, rounds, tool calls, token count, latency, failure reason, and matched skill.
- Tool definitions now come from a single registry under `backend/app/agent/tools/`, so OpenAI tool schemas, execution, UI cards, and tests share one source.
- The tool set covers wardrobe lookup/search, weather, outfit recommendation, mood recommendation, memory add/search, collections, and try-on helpers.

## Skills And Memory

- Added `/api/v1/agent/skills` CRUD-style creation and listing for user-owned skills.
- Added `/api/v1/agent/skills/capture` to turn a successful tool-call sequence into a reusable skill prompt addon.
- Added `/api/v1/agent/skills/{skill_id}/execute-preview` for dry-run keyword matching and prompt injection preview.
- Memory search now supports hybrid scoring: keyword Jaccard plus embedding cosine similarity.
- If the embedding client is not configured, memory search degrades to keyword-only results.
- Agent startup initializes the embedding client when `AI_RECOMMENDER_API_BASE_URL` and `AI_RECOMMENDER_API_KEY` are configured.

## Observability And Limits

- Added `backend/app/observability/agent_metrics.py` and Prometheus rendering in `prometheus_exporter.py`.
- Added `GET /metrics` for Prometheus exposition text covering dependency, try-on v2, and agent metrics.
- `ENABLE_RATE_LIMIT` now defaults to true for runtime.
- Added `RATE_LIMIT_TRYON_PER_MINUTE` to cap `/api/v1/tryon` and `/api/v2/tryon` separately from global request limits.

## Try-On Fidelity

- Added `backend/app/services/tryon_v2/fidelity_guard.py` for color-fidelity engine selection, preflight QC, anomaly scoring, post-fidelity artifact detection, and adaptive pattern strength.
- Added `backend/app/services/tryon_mask_utils.py` for target-ratio binary mask expansion with top guard, width cap, and max-area guard.
- CatVTON upper-body mask generation now uses target-ratio expansion rather than a fixed dilation kernel.
- `catvton_color_fidelity_spatial()` now limits fidelity to person-vs-CatVTON changed pixels and excludes near-white background and skin-like pixels.
- Motif-gated fidelity restricts strong texture restoration to small, color-distinct regions.
- Lower-body fidelity now uses narrower clip masks and structured lower overlays to avoid full-width dark blocks, waist halos, shoe contamination, and upper-body spill.
- Debug sessions now carry through post-CatVTON backend stages and save `12_after_color_fidelity.jpg` plus `99_backend_final_returned.jpg`.
- `CATVTON_SEED` makes subprocess inference reproducible by default; set `-1` for random.
- `TRYON_V2_HYBRID_WARP_OVERLAY_ENABLED=false` now keeps successful local CatVTON hybrid output direct by default; true restores the legacy warp overlay path.

## Flutter Client

- Added `mobile/lib/core/services/sse_parser.dart`, a chunk-safe SSE parser shared by smart-outfit streaming and Agent chat.
- Added `mobile/lib/features/agent/` with an Agent chat screen and pipeline widget for visible step/tool progress.
- Added `/agent` route in `mobile/lib/main.dart`.
- Added `WardrobePickerSheet` so analysis and try-on screens can reuse existing wardrobe items instead of forcing a new upload.
- `ApiClient.agentChatStream()` posts to `/api/v1/agent/chat-stream` and yields parsed event payloads.

## Test Coverage

- Agent: metrics, Prometheus exporter, skills API, tool registry, prompt guard, LLM cache, and hybrid memory tests.
- Try-on fidelity: fidelity guard, lower-body spatial fidelity, hybrid lower whitebox, preprocess category fallback, dark garment background removal, and detail-fidelity lower tests.
- Flutter/Dart: analyzer coverage is expected through the pre-commit hook; the pre-push hook runs `flutter test --no-pub`.

## Corrected Documentation

- Replaced stale five/six-mode try-on wording with the current seven-mode set:
  `strict`, `balanced`, `replace`, `realistic`, `realistic_v2`, `professional`, `hybrid`.
- Updated backend and mobile docs to include Agent chat, skills, SSE streaming, Prometheus metrics, hybrid memory search, and try-on-specific rate limiting.
