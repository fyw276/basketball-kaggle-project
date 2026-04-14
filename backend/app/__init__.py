"""
Smart Outfit Assistant - Backend Application
"""

import os

# Force transformers to avoid TensorFlow backend in this project.
# Some local environments have a broken tensorflow namespace package
# (missing attributes like Tensor), which causes wardrobe upload recognition to fail.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TORCH", "1")

__version__ = "1.0.0"
