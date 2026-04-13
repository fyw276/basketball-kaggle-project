# Pre-Submit Self Check

Run this checklist locally before opening a pull request.

## 1) Backend lightweight tests

```bash
cd backend
python -m pytest tests_lite tests/test_release_and_observability.py -v --tb=short
```

## 2) Backend lint (fast path)

```bash
flake8 backend/app --max-line-length=100 --extend-ignore=E203,W503
```

## 3) Frontend build

```bash
cd frontend
npm ci
npm run build
```

## 4) Mobile analyze and test

```bash
cd mobile
flutter pub get
flutter analyze
flutter test
```

## 5) Optional: run all hooks

```bash
pre-commit run --all-files
```

## Pass Criteria

1. All commands complete without errors
2. No new lint or test failures
3. Build artifacts are generated successfully where applicable
