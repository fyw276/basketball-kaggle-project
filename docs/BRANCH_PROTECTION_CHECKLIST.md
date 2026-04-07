# Branch Protection Checklist

Use this checklist when configuring branch protection in GitHub.

## Target Branches

- [ ] main
- [ ] master (if still used)
- [ ] develop (if used)

## Pull Request Rules

- [ ] Require a pull request before merging
- [ ] Require approvals: at least 1
- [ ] Dismiss stale pull request approvals when new commits are pushed
- [ ] Require conversation resolution before merging

## Status Checks

- [ ] Require status checks to pass before merging
- [ ] Require branches to be up to date before merging (recommended)
- [ ] Add required checks:
  - [ ] Backend Smoke Checks
  - [ ] Backend Lite Tests
  - [ ] Frontend Build (Vite)
  - [ ] Mobile Test (Flutter)

## History and Push Safety

- [ ] Do not allow force pushes
- [ ] Do not allow deletions

## Optional Hardening

- [ ] Require signed commits
- [ ] Restrict who can push to matching branches
- [ ] Restrict who can dismiss pull request reviews

## Final Verification

- [ ] Open a test PR and verify all required checks are enforced
- [ ] Verify merge button is blocked when one required check fails
- [ ] Verify merge is allowed when all required checks pass

## Troubleshooting

- [ ] If a required check is missing in GitHub UI, confirm the same job name exists in `.github/workflows/ci.yml`
- [ ] If checks never appear on PRs, verify workflow trigger includes `pull_request`
- [ ] If only some checks run, confirm branch name matches workflow trigger branches
- [ ] If backend lite tests fail on imports, review the dependency list in `backend-lite-tests` job
- [ ] After changing workflow job names, update required checks in branch protection rules
