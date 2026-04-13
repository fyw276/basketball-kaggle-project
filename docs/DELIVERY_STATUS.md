# Delivery Status

## Date

2026-04-13

## Scope

This release focused on public-deployment parity with local IDE behavior, with emphasis on smart-outfit rendering, image-link recovery, camera/gallery behavior, and deployment/audit automation.

## Completed

1. Smart-outfit rendering parity fixes
   - Avoided large blank preview block when top image is missing/broken
   - Added explicit fallback messages in UI for preview load failures

2. Legacy wardrobe image URL repair delivered
   - Added backend repair helper and manual endpoint
   - Added wardrobe UI action to trigger repair and show `scanned/changed/skipped`

3. Camera and gallery paths separated across upload flows
   - Ensured camera action invokes camera capture path
   - Ensured gallery action stays in gallery picker path

4. Deployment and audit scripts synchronized
   - Added full publish script for web+backend (`deploy_full_to_ecs.ps1`)
   - Added Windows local full-chain audit script (`full_chain_consistency_audit.ps1`)
   - Added Linux ECS audit script (`full_chain_consistency_audit.sh`)
   - Added push-and-run helper (`push_and_run_remote_audit.ps1`)

5. Operational edge cases fixed
   - Fixed CRLF-sensitive remote command behavior
   - Treated warning-only audit exit code as non-fatal in push runner

## Verification

1. `cd backend; python -m pytest tests_lite -v --tb=short -x` passed
2. `cd mobile; flutter test --no-pub` passed
3. `cd mobile; flutter build web --release` passed after null-safety compile fix
4. Remote audit summary observed: `fail=0 warn=1`
   - Warning reason: deployment directory on ECS is not a git checkout (`no .git`)

## Current Risks

1. ECS deployment directory not being a git checkout reduces direct commit parity observability.
2. Remote audit still relies on interactive SSH password unless key-based auth is configured.

## Recommended Next Phase

1. Convert ECS auth to key-based SSH to remove repeated password prompts in automation.
2. Keep `full_chain_consistency_audit.sh` on server image baseline for direct host-side checks.
3. Add a lightweight post-deploy smoke task that validates smart-outfit weather/generate endpoints with token.

## Date

2026-04-11

## Scope

This release focused on authentication reliability and UX alignment across backend, Flutter client, and operational verification docs.

## Completed

1. Multi-identifier login support completed
   - Backend login now accepts username, email, or phone number in a single credential field
   - Added phone-number user lookup path in auth service

2. User schema/model updated for phone number
   - Added optional `phone_number` to user model and request schema
   - Added SQLite `users` table patch for backward-compatible column rollout

3. Flutter auth flow corrected for production behavior
   - Removed demo fallback path that previously allowed pseudo-login without token
   - Updated login prompt to "用户名 / 邮箱 / 手机号"
   - Registration now supports optional phone number

4. Registration UX and validation aligned with backend policy
   - Password minimum length aligned to 8 characters on frontend
   - Added explicit password requirement hint on registration form
   - Registration success now returns user to login tab (no auto-login)

5. Docs synchronized
   - Corrected outdated docs that still described auto-login after registration
   - Added current ECS restart and login verification command sequence for fast operational checks

## Verification

- Backend and Flutter changed files pass static error checks in editor tools
- Runtime verification command set prepared for ECS:
  - backend service restart and health check
  - register test account
  - login via username/email/phone_number
  - tail backend logs for diagnosis

## Current Risks

1. Historical docs may still include older routing screenshots/wording that reference legacy login flow.
2. Full backend integration suite is still not part of the lightweight default pre-push gate.

---

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
