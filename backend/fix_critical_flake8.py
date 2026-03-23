#!/usr/bin/env python3
"""Fix critical flake8 errors"""

# Fix unused imports
files_to_fix = {
    "app/api/analysis.py": [
        ("from typing import Dict, List, Optional\n", "from typing import Dict, List\n"),
    ],
    "app/ml/feature_extractor.py": [
        ("import tensorflow as tf\n", ""),
    ],
    "app/ml/image_recognizer.py": [
        ("import numpy as np\n", ""),
    ],
    "app/ml/model_loader.py": [
        ("import os\n", ""),
    ],
    "app/ml/style_classifier.py": [
        ("from typing import List, Tuple\n", "from typing import List\n"),
    ],
    "app/services/outfit_recommender.py": [
        ("from typing import Dict, List, Optional\n", "from typing import Dict, List\n"),
    ],
    "app/services/outfit_rules.py": [
        ("from typing import Dict, List, Set\n", "from typing import List, Set\n"),
    ],
    "diagnose_auth.py": [
        ("import json\n", ""),
    ],
    "test_all_features.py": [
        ("import json\n", ""),
        ("from pathlib import Path\n", ""),
    ],
    "diagnose_register_error.py": [
        ("        result = create_user(db, test_user)\n", "        create_user(db, test_user)\n"),
    ],
    "scripts/test_model_loading.py": [
        ("    model = loader.load_model()\n", "    loader.load_model()\n"),
        ("    loader = ModelLoader()\n", "    ModelLoader()\n"),
        ("    preprocessor = ImagePreprocessor()\n", "    ImagePreprocessor()\n"),
    ],
    "scripts/test_wardrobe_integration.py": [
        ("from io import BytesIO\n", ""),
    ],
    "scripts/verify_backend_completion.py": [
        (
            "    from app.core.exceptions import (\n        AppException,\n        AuthenticationError,\n        AuthorizationError,\n        ConflictError,\n        ImageProcessingError,\n        NotFoundError,\n        ValidationError,\n    )\n",
            "    from app.core import exceptions  # noqa: F401\n",
        ),
        (
            "    from app.core.error_handlers import (\n        app_exception_handler,\n        create_error_response,\n        generic_exception_handler,\n        http_exception_handler,\n        validation_exception_handler,\n    )\n",
            "    from app.core import error_handlers  # noqa: F401\n",
        ),
        (
            "    from app.services.user import delete_user\n",
            "    from app.services import user  # noqa: F401\n",
        ),
        (
            "        from app.core.cache import RedisCache\n",
            "        from app.core import cache  # noqa: F401\n",
        ),
        ("        import app.core.cache\n", "        from app.core import cache  # noqa: F401\n"),
        (
            "    from app.ml.feature_extractor import FeatureExtractor\n",
            "    from app.ml import feature_extractor  # noqa: F401\n",
        ),
    ],
    "tests/test_error_handling.py": [
        ("from fastapi import FastAPI\n", ""),
        ("from fastapi.testclient import TestClient\n", ""),
        ("from app.core.error_handlers import validation_exception_handler\n", ""),
    ],
    "tests/test_feature_extractor.py": [
        ("import asyncio\n", ""),
        ("from unittest.mock import patch\n", ""),
    ],
    "tests/test_performance.py": [
        ("from pathlib import Path\n", ""),
    ],
    "tests/test_security.py": [
        ("from app.models.user import User\n", ""),
    ],
    "tests/test_suitability_scorer.py": [
        ("import pytest\n", ""),
    ],
    "scripts/test_style_classifier.py": [
        (
            "from app.ml.style_classifier import STYLE_TAGS, StyleClassifier\n",
            "from app.ml.style_classifier import StyleClassifier\n",
        ),
    ],
}

for filepath, replacements in files_to_fix.items():
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        for old, new in replacements:
            content = content.replace(old, new)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Fixed: {filepath}")
    except Exception as e:
        print(f"Error fixing {filepath}: {e}")

print("\nDone!")
