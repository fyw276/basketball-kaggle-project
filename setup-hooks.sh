#!/bin/bash
# Git Hooks Setup Script for Smart Outfit Assistant
# Run this script from the project root directory

set -e

echo "=========================================="
echo "Git Hooks Setup - Smart Outfit Assistant"
echo "=========================================="
echo ""

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo "❌ Error: Not in a Git repository"
    echo "   Please run this script from the project root directory"
    echo "   Current: $(pwd)"
    exit 1
fi

echo "✓ Found Git repository"

# Check if Python is installed
if ! command -v python &> /dev/null; then
    echo "❌ Error: Python is not installed"
    echo "   Please install Python 3.11+ first"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Python version: $PYTHON_VERSION"

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Warning: Virtual environment is not activated"
    echo "   Recommended: activate your venv first"
    echo "   Command: source backend/venv/bin/activate"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install pre-commit
echo ""
echo "[1/4] Installing pre-commit and detect-secrets..."
pip install pre-commit==4.0.1 detect-secrets==1.5.0

# Install pre-commit hooks
echo ""
echo "[2/4] Installing Git hooks..."
pre-commit install --hook-type pre-commit
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push

echo "✓ Git hooks installed"

# Initialize secrets baseline
echo ""
echo "[3/4] Initializing secrets detection..."
if [ ! -f "backend/.secrets.baseline" ]; then
    detect-secrets scan > backend/.secrets.baseline
    echo "✓ Created backend/.secrets.baseline"
else
    echo "✓ backend/.secrets.baseline already exists"
fi

# Run hooks on all files
echo ""
echo "[4/4] Verifying hooks installation..."
echo "Running pre-commit on all files (this may take a few minutes)..."
echo ""

pre-commit run --all-files || true

echo ""
echo "=========================================="
echo "✓ Git hooks setup complete!"
echo "=========================================="
echo ""
echo "Installed hooks:"
echo "  • pre-commit: Runs linting, formatting, and checks on staged files"
echo "  • commit-msg: Enforces conventional commit messages"
echo "  • pre-push: Runs tests before pushing"
echo ""
echo "Usage:"
echo "  • Normal commit: git commit -m 'feat: add new feature'"
echo "  • Skip hooks: git commit --no-verify"
echo "  • Run manually: pre-commit run --all-files"
echo ""
echo "Commit message format:"
echo "  type(scope): description"
echo ""
echo "  Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build, revert"
echo "  Example: feat(api): add user authentication endpoint"
echo ""
echo "Documentation:"
echo "  • Full guide: backend/GIT_HOOKS.md"
echo "  • Commit convention: backend/COMMIT_CONVENTION.md"
echo "  • Manual install: backend/MANUAL_INSTALL.md"
echo ""
