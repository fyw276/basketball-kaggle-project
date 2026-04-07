# Engineering Baseline

## Purpose

This document defines the minimum engineering baseline for day-to-day collaboration.
It is intentionally lightweight and focuses on fast feedback.

## CI Pipeline

The repository uses GitHub Actions workflow:

- .github/workflows/ci.yml
- docs/BRANCH_PROTECTION_BASELINE.md
- docs/BRANCH_PROTECTION_CHECKLIST.md
- docs/PRE_SUBMIT_SELF_CHECK.md
- docs/DELIVERY_STATUS.md

Current jobs:

1. Backend Smoke Checks
2. Backend Lite Tests
3. Frontend Build (Vite)
4. Mobile Test (Flutter)

Backend Lite Tests also exports a junit report artifact for easier failure diagnosis.

## Why Backend Uses Smoke Checks First

The backend currently includes heavyweight AI dependencies (for example Torch, TensorFlow, Diffusers).
To keep PR feedback fast and stable, CI first enforces:

1. Python syntax compilation
2. Flake8 checks for backend/app
3. Lightweight pytest subset for auth/security and config/env behavior without heavyweight model dependencies

After dependency layers are split (core vs ai), backend CI should be upgraded to run targeted pytest suites in pull requests.

## Local Quality Gate

Before push, run:

1. Backend lint/format via pre-commit hooks
2. Frontend build check
3. Flutter analyze and test

## Backend Lite Test Boundary

Included in `backend/tests_lite`:

1. Auth and token utility behavior
2. Config parsing and environment variable sync behavior
3. Exception contract behavior (status_code/message/details)

Excluded from lite tests:

1. Tests that import `backend/tests/conftest.py`
2. Database/session integration tests
3. Router tests requiring full app startup and heavyweight model/runtime dependencies

## Lite Test Contribution Rules

When adding new tests to `backend/tests_lite`, follow all rules below:

1. Keep tests deterministic and side-effect free (no network, no filesystem writes, no external services)
2. Avoid importing modules that trigger heavyweight model loading paths
3. Do not depend on `backend/tests/conftest.py` fixtures
4. Prefer unit-level contract checks over end-to-end behavior
5. Keep runtime fast enough for PR feedback (target: seconds, not minutes)

## Next Hardening Steps

1. Expand lightweight pytest subset to cover routing and config behaviors
2. Add branch protection requiring CI green
3. Add artifact upload for build/test reports
