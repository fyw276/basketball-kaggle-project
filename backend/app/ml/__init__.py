"""
Machine Learning module for image recognition
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "CategoryClassifier",
    "ColorExtractor",
    "FeatureExtractor",
    "ImagePreprocessor",
    "ModelLoader",
]


def __getattr__(name: str):
    module_map = {
        "CategoryClassifier": "app.ml.category_classifier",
        "ColorExtractor": "app.ml.color_extractor",
        "FeatureExtractor": "app.ml.feature_extractor",
        "ImagePreprocessor": "app.ml.image_preprocessor",
        "ModelLoader": "app.ml.model_loader",
    }
    module_name = module_map.get(name)
    if module_name is None:
        raise AttributeError(f"module 'app.ml' has no attribute '{name}'")
    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value
