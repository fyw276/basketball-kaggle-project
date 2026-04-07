# Branch Protection Baseline

## Goal

Ensure that pull requests are merged only after core quality checks pass.

## Recommended Protected Branches

1. main
2. master (if still used)
3. develop (if used as integration branch)

## Required Status Checks

Require these checks to pass before merge:

1. Backend Smoke Checks
2. Backend Lite Tests
3. Frontend Build (Vite)
4. Mobile Test (Flutter)

These check names must match the job names in:

- .github/workflows/ci.yml

## Required Pull Request Rules

1. Require a pull request before merging
2. Require at least 1 approving review
3. Dismiss stale approvals when new commits are pushed
4. Require conversation resolution before merging
5. Do not allow force pushes
6. Do not allow branch deletion

## Optional Hardening

1. Require branches to be up to date before merging
2. Require signed commits
3. Restrict who can push to protected branches

## Setup Steps (GitHub UI)

1. Open repository Settings
2. Open Branches
3. Add branch protection rule for each protected branch
4. Enable the rules above
5. Add required status checks from CI

For an operator-friendly checklist, see:

- docs/BRANCH_PROTECTION_CHECKLIST.md
