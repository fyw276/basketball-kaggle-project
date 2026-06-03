"""CLIP zero-shot category classifier for garment product photos.

This module is the no-TensorFlow fallback for category recognition. It uses the
locally cached Hugging Face CLIP model through PyTorch/transformers and returns
the same Chinese category labels used by the wardrobe/evaluation pipeline.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.core.logging import setup_logging

logger = setup_logging()


CATEGORY_LABELS = {
    "top": "\u4e0a\u8863",
    "outer": "\u5916\u5957",
    "pants": "\u88e4\u5b50",
    "skirt": "\u88d9\u5b50",
    "dress": "\u8fde\u8863\u88d9",
    "shoes": "\u978b",
    "bag": "\u5305",
}


CATEGORY_PROMPTS = {
    "top": [
        "a product photo of a shirt",
        "a product photo of a blouse",
        "a product photo of a t-shirt",
        "a product photo of a pullover sweater",
        "a product photo of a hoodie",
        "a product photo of a shirt without outerwear",
    ],
    "outer": [
        "a product photo of a coat",
        "a product photo of a jacket",
        "a product photo of a blazer",
        "a product photo of a cardigan",
        "a product photo of a trench coat",
        "a product photo of a padded jacket",
        "a product photo of a down jacket",
        "a product photo of open front outerwear",
        "a product photo of layered outerwear worn over a shirt",
    ],
    "pants": [
        "a product photo of pants",
        "a product photo of jeans",
        "a product photo of trousers",
        "a product photo of shorts",
    ],
    "skirt": [
        "a product photo of a skirt",
        "a product photo of a pleated skirt",
        "a product photo of a mini skirt",
    ],
    "dress": [
        "a product photo of a dress",
        "a product photo of a one piece dress",
        "a product photo of a gown",
    ],
    "shoes": [
        "a product photo of shoes",
        "a product photo of sneakers",
        "a product photo of boots",
        "a product photo of high heels",
    ],
    "bag": [
        "a product photo of a bag",
        "a product photo of a handbag",
        "a product photo of a backpack",
        "a product photo of a tote bag",
    ],
}


class CLIPCategoryClassifier:
    """Small zero-shot CLIP wrapper focused only on garment categories."""

    def __init__(self, model_id: str = "openai/clip-vit-large-patch14", device: str = "cpu"):
        self.model_id = model_id
        self.device = device
        self._model: Any | None = None
        self._processor: Any | None = None
        self._text_features: Any | None = None
        self._prompt_owners: list[str] = []

    def _load_image(self, image_source: str | Path | bytes | Image.Image) -> Image.Image:
        if isinstance(image_source, Image.Image):
            return image_source.convert("RGB")
        if isinstance(image_source, bytes):
            return Image.open(BytesIO(image_source)).convert("RGB")
        return Image.open(Path(image_source)).convert("RGB")

    def _ensure_loaded(self) -> None:
        if (
            self._model is not None
            and self._processor is not None
            and self._text_features is not None
        ):
            return

        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

        import torch
        from transformers import CLIPModel, CLIPProcessor

        logger.info("Loading CLIP category classifier: %s", self.model_id)
        self._model = CLIPModel.from_pretrained(self.model_id, local_files_only=True)
        self._processor = CLIPProcessor.from_pretrained(self.model_id, local_files_only=True)
        self._model.to(self.device)
        self._model.eval()

        prompts: list[str] = []
        owners: list[str] = []
        for category, category_prompts in CATEGORY_PROMPTS.items():
            for prompt in category_prompts:
                prompts.append(prompt)
                owners.append(category)

        with torch.no_grad():
            text_inputs = self._processor(text=prompts, return_tensors="pt", padding=True)
            text_inputs = {k: v.to(self.device) for k, v in text_inputs.items()}
            text_features = self._model.get_text_features(**text_inputs)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        self._text_features = text_features
        self._prompt_owners = owners

    def classify_category(
        self, image_source: str | Path | bytes | Image.Image
    ) -> tuple[str, float]:
        self._ensure_loaded()

        import torch

        image = self._load_image(image_source)
        with torch.no_grad():
            image_inputs = self._processor(images=image, return_tensors="pt")
            image_inputs = {k: v.to(self.device) for k, v in image_inputs.items()}
            image_features = self._model.get_image_features(**image_inputs)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            similarities = (image_features @ self._text_features.T).squeeze(0).cpu().numpy()

        scores: dict[str, float] = {}
        for category in CATEGORY_PROMPTS:
            prompt_scores = [
                float(similarities[idx])
                for idx, owner in enumerate(self._prompt_owners)
                if owner == category
            ]
            scores[category] = max(prompt_scores)

        best = max(scores, key=scores.get)
        ordered_scores = np.array([scores[key] for key in CATEGORY_PROMPTS], dtype=np.float32)
        # Temperature-softmax turns CLIP cosine similarities into a relative confidence.
        scaled = ordered_scores * 20.0
        scaled = scaled - float(scaled.max())
        probs = np.exp(scaled)
        probs = probs / max(float(probs.sum()), 1e-12)
        best_idx = list(CATEGORY_PROMPTS).index(best)
        confidence = float(probs[best_idx])

        # 二阶段判断：如果第一阶段是 top-like，第二阶段再判断上衣 vs 外套
        if best == "top":
            # 检查 outer 的得分是否接近 top
            top_score = scores.get("top", 0.0)
            outer_score = scores.get("outer", 0.0)
            # 如果 outer 得分超过 top 得分的 88%，则认为是外套
            if outer_score > top_score * 0.88:
                # 重新计算 outer 的 confidence
                outer_idx = list(CATEGORY_PROMPTS).index("outer")
                confidence = float(probs[outer_idx])
                return CATEGORY_LABELS["outer"], confidence

        return CATEGORY_LABELS[best], confidence


_instance: CLIPCategoryClassifier | None = None


def get_clip_category_classifier() -> CLIPCategoryClassifier:
    global _instance
    if _instance is None:
        _instance = CLIPCategoryClassifier()
    return _instance
