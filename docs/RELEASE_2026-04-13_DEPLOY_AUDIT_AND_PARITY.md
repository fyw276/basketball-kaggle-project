# Release Note: 2026-04-13 Deploy Audit And Parity

## Scope

This release closes the gap between local IDE behavior and Alibaba Cloud public deployment for smart-outfit workflows.

Focus areas:

1. Smart-outfit result rendering parity (no large blank preview area)
2. Legacy garment image URL repair (shoe image load failures)
3. Camera vs gallery behavior parity across upload entries
4. Deployment + audit automation for Windows local operator and Linux ECS host

## What Changed

### Backend

1. Smart-outfit upload content-type fallback
   - File: `backend/app/api/smart_outfit.py`
   - Supports `application/octet-stream` uploads by validating image bytes via PIL.

2. Garment image URL repair capability
   - Files:
     - `backend/app/services/garment.py`
     - `backend/app/api/wardrobe_simple.py`
   - Added auto-repair helper: normalize legacy `image_url` and derive from `image_path` when needed.
   - Added manual endpoint: `POST /api/v1/wardrobe/simple/garments/repair-image-urls`.
   - `GET /api/v1/wardrobe/simple/garments` now performs lightweight auto-repair before returning items.

3. Outfit image URL normalization and preview selection improvements
   - Files:
     - `backend/app/services/outfit_recommender_3d.py`
     - `backend/app/services/smart_outfit_generator.py`
   - Improved URL canonicalization under `/uploads/`.
   - Preview now prefers major garment categories over shoes/accessories to reduce blank/failed cover previews.

### Mobile (Flutter)

1. Camera/gallery behavior fixed across analysis flows
   - Files:
     - `mobile/lib/core/widgets/image_picker_section.dart`
     - `mobile/lib/features/analysis/screens/outfit_screen.dart`
     - `mobile/lib/features/analysis/screens/similarity_screen.dart`
     - `mobile/lib/features/analysis/screens/suitability_screen.dart`
     - `mobile/lib/features/analysis/screens/smart_outfit_screen.dart`
     - `mobile/lib/features/analysis/screens/virtual_tryon_screen.dart`
   - Camera now uses `ImageSource.camera` path directly.
   - Gallery path remains separate and explicit.

2. Smart-outfit preview fallback and credential-expiry UX
   - Files:
     - `mobile/lib/features/analysis/screens/smart_outfit_screen.dart`
     - `mobile/lib/core/services/api_client.dart`
     - `mobile/lib/core/utils/app_snackbar.dart`
   - Added clear fallback text for missing/failed preview image.
   - Unified 401 handling (`Could not validate credentials`) with friendly relogin prompt.

3. Wardrobe manual repair UI with stats
   - File: `mobile/lib/features/wardrobe/screens/wardrobe_screen.dart`
   - Added repair action and summary output: scanned / changed / skipped.

### Ops Scripts

1. One-step full deployment script
   - File: `scripts/deploy_full_to_ecs.ps1`
   - Supports full web+backend publish, service restart, health checks, and hotfix marker verification.

2. Local consistency audit script (Windows)
   - File: `scripts/full_chain_consistency_audit.ps1`
   - Checks local build/env/health and optional remote parity via SSH.

3. Remote-host consistency audit script (Linux)
   - File: `scripts/full_chain_consistency_audit.sh`
   - Runs directly on ECS host for runtime checks.

4. Push-and-run helper (Windows)
   - File: `scripts/push_and_run_remote_audit.ps1`
   - Uploads Linux audit script to ECS and executes it remotely.
   - Handles warning-only exit code (`1`) as non-fatal.

## How To Run

### A. Windows local operator (recommended)

1. Remote audit:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\push_and_run_remote_audit.ps1 -ServerHost 101.200.127.179 -User root
```

2. Full deployment:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_full_to_ecs.ps1
```

3. Deploy without rebuilding web (if `mobile/build/web` already verified):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_full_to_ecs.ps1 -SkipWebBuild
```

If your current terminal is not at repo root (for example `C:\Windows\System32`), use an absolute script path:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Users\omen\OneDrive\桌面\clothing-assistant\scripts\push_and_run_remote_audit.ps1" -ServerHost 101.200.127.179 -User root
```

### B. Linux ECS host (direct run)

```bash
cd /opt/clothing-assistant/clothing-assistant-main
bash scripts/full_chain_consistency_audit.sh
```

Note:
- Do not run `.ps1` on Linux shell.
- If remote folder is not a git repo, `code.remote.commit` can be warning-only.

## Troubleshooting

1. `powershell: command not found` on ECS
   - Cause: running Windows `.ps1` in Linux shell.
   - Fix: run `.ps1` on Windows; run `.sh` on ECS.

2. `.\scripts\push_and_run_remote_audit.ps1 not found` on Windows
   - Cause: current directory is not project root.
   - Fix: `cd` to repo root or use absolute `-File` path.

3. Remote audit returns `fail=0 warn=1`
   - Meaning: warning-only status; currently non-fatal in push runner.
   - Typical warning: ECS deploy directory is not a git checkout (`no .git`).

4. Deploy task appears to "hang"
   - Most common reason: waiting for interactive SSH password prompt during `scp` / `ssh`.
   - Fix: input password in the running terminal, or configure SSH key login.

## Acceptance Criteria Mapping

1. Smart-outfit feature parity
   - Weather/location/generate flows stay aligned.
   - Preview rendering no longer leaves unexplained large blank block on missing top image.

2. No broken image regressions for legacy wardrobe records
   - Auto and manual repair paths available.

3. Camera/gallery parity
   - Camera action invokes camera path.
   - Gallery action invokes gallery path.

4. Runtime checks
   - Health endpoint, nginx active state, env coverage checks included in audit scripts.

## Known Warning Semantics

Audit exit codes:

1. `0` = pass with no warnings
2. `1` = warnings only (non-fatal for push runner)
3. `2` = hard failure

Current common warning:
- `code.remote.commit :: no .git under /opt/clothing-assistant/clothing-assistant-main`
- This indicates deployment dir is not a git checkout; runtime parity can still be valid.
