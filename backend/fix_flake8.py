#!/usr/bin/env python3
"""
Quick script to fix common flake8 errors
"""

import re
from pathlib import Path


def fix_file(filepath):
    """Fix common flake8 errors in a file"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # Fix unused imports
    fixes = [
        # Remove unused imports
        (r"^from typing import Optional\n", "", "backend/app/api/analysis.py"),
        (r"^import tensorflow as tf\n", "", "backend/app/ml/feature_extractor.py"),
        (r"^import numpy as np\n", "", "backend/app/ml/image_recognizer.py"),
        (r"^import os\n", "", "backend/app/ml/model_loader.py"),
        (r"^from typing import Tuple\n", "", "backend/app/ml/style_classifier.py"),
        (r"^from typing import Optional\n", "", "backend/app/services/outfit_recommender.py"),
        (r"^from typing import Dict\n", "", "backend/app/services/outfit_rules.py"),
        (r"^import json\n", "", "backend/diagnose_auth.py"),
        (r"^import json\n", "", "backend/test_all_features.py"),
        (r"^from pathlib import Path\n", "", "backend/test_all_features.py"),
        # Fix f-strings without placeholders
        (r'print\(f"([^{]*?)"\)', r'print("\1")', None),
        (r'logger\.info\(f"([^{]*?)"\)', r'logger.info("\1")', None),
        (r'logger\.error\(f"([^{]*?)"\)', r'logger.error("\1")', None),
        (r'logger\.warning\(f"([^{]*?)"\)', r'logger.warning("\1")', None),
        # Fix SuitabilityResult type hint
        (r'-> "SuitabilityResult":', r"-> dict:", "backend/app/services/suitability_scorer.py"),
    ]

    for pattern, replacement, target_file in fixes:
        if target_file is None or str(filepath).endswith(target_file):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Fixed: {filepath}")
        return True
    return False


def main():
    backend_dir = Path(__file__).parent
    python_files = list(backend_dir.rglob("*.py"))

    fixed_count = 0
    for filepath in python_files:
        if "venv" in str(filepath) or "__pycache__" in str(filepath):
            continue
        if fix_file(filepath):
            fixed_count += 1

    print(f"\nFixed {fixed_count} files")


if __name__ == "__main__":
    main()
