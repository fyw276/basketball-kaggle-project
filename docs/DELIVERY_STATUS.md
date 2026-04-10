# Delivery Status

## Date

2026-04-10

## Scope

This release focused on smart-outfit API contract normalization, AI recommendation output stabilization, and the home/smart-outfit UX feedback loop.

## Completed

1. API response contract standardized
   - Added shared success/error envelope helpers in `backend/app/core/api_response.py`
   - Wrapped successful JSON responses in `ApiEnvelopeMiddleware`
   - Updated the error handlers to emit the same envelope shape

2. Smart-outfit contract expanded
   - Added structured `address` input/output support
   - Added `ai_recommendation` with fixed fields: `outfit`, `style`, `score`, `reasons`
   - Forced AI JSON parsing with fallback so the frontend always receives a stable schema
   - Changed empty-wardrobe generation to a clear 400 error instead of a virtual fallback

3. Weather/address diagnostics improved
   - Added optional AMap reverse-geocoding support
   - Added `geocode_source` and `geocode_error` to help diagnose partial address resolution

4. Flutter UX closed the loop
   - Home screen now shows city, weather, temperature, and a today-recommendation card
   - Home recommendation card shows score, style, reasons, preview thumbnail, and last-viewed outfit index
   - Smart-outfit screen adds one-tap generate, page indicators, current-card highlighting, and resume-to-index behavior
   - `PlatformImage` now has a consistent failed-image placeholder

5. Docs synchronized
   - Updated root README, mobile README, backend README, and project status pages
   - Added this release note for auditability

## Verification

- `pre-commit run --all-files` passed after auto-fixes were applied
- `cd mobile; flutter test --no-pub` passed
- `cd backend; python -m pytest tests_lite -v --tb=short -x` passed
- `git push` completed successfully and pre-push hooks passed

## Current Risks

1. The full backend test suite was not run in this release; only the documented pre-push lite suite was executed.
2. AI recommendation quality still depends on the configured external provider when `AI_RECOMMENDER_ENABLED=true`.

---

## Date

2026-04-07

## Scope

This status summarizes the engineering governance improvements delivered in the current iteration.

## Completed

1. CI baseline established with multi-job checks
   - Backend Smoke Checks
   - Backend Lite Tests
   - Frontend Build (Vite)
   - Mobile Test (Flutter)

2. Backend lightweight test suite created under `backend/tests_lite`
   - Auth/token behavior
   - Config/env behavior
   - Exception contract behavior
   - Error response shape
   - Error handler behavior

3. Backend lite tests reporting improved
   - JUnit XML export
   - Artifact upload in GitHub Actions
   - Step summary output for quick diagnosis

4. Hooks governance converged
   - Single root pre-commit config source
   - Legacy duplicate backend pre-commit config removed
   - Secrets baseline path unified to root `.secrets.baseline`

5. Documentation governance improved
   - Engineering baseline document
   - Branch protection baseline and checklist
   - Pre-submit self-check checklist
   - Root README governance entry section

6. Hybrid inference baseline delivered for `/predict`
   - Added hybrid settings and external enhancement client
   - Extended `/predict` response contract with source/metadata fields
   - Added lightweight tests for hybrid path and API contract
   - Synchronized docs with copy-ready request/response examples

## Current Risks

1. CI has not yet been validated on remote GitHub Actions after all latest edits
2. Branch protection still requires repository admin configuration in GitHub UI
3. Lite test suite is intentionally narrow and does not cover full router/database integration paths
4. External enhancement endpoint stability depends on downstream API availability

## Recommended Next Phase

1. Execute a remote CI validation run via push/PR and confirm all checks pass
2. Enable branch protection rules using documented checklist
3. Add a medium-weight backend CI tier for selected API contract tests without model downloads
4. Add periodic review to keep docs and scripts aligned with actual repository state

## Exit Criteria For This Governance Iteration

1. CI workflow exists and is parse-valid
2. Lite tests are in place and runnable in CI
3. Governance documents are discoverable from root README
4. Hooks configuration is no longer split across duplicate config files
