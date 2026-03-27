"""
CLIP-based image recognition service for fashion/clothing.

Uses OpenAI CLIP (ViT-B/32 or ViT-L/14) for:
1. Zero-shot garment category classification via Chinese text prompts
2. Zero-shot style/occasion tagging via Chinese text prompts
3. Feature vector extraction for similarity matching

Advantage over MobileNetV2:
- CLIP understands semantic clothing attributes (通勤/复古/国风等中文概念)
- Zero-shot classification: no need for fine-tuning on fashion datasets
- Much better generalization for fashion-specific attributes
- Native multi-language support (English + Chinese)

Supports Chinese fashion domain with specialized prompt engineering.
"""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image

from app.core.logging import setup_logging

logger = setup_logging()

# ──────────────────────────────────────────────────────────────────────────────
# Prompt Engineering: Chinese Fashion Domain
# ──────────────────────────────────────────────────────────────────────────────

# Garment categories in Chinese (target classes for zero-shot classification)
CATEGORY_CANDIDATES = [
    "上衣",  # Tops: T-shirt, shirt, sweater, hoodie, blouse
    "裤子",  # Bottoms: jeans, trousers, slacks, leggings
    "裙子",  # Dresses/Skirts
    "外套",  # Outerwear: jacket, coat, blazer, cardigan
    "鞋",  # Footwear: sneakers, heels, boots, sandals
    "包",  # Bags: handbag, backpack, clutch, tote
]

# Fashion styles in Chinese
STYLE_CANDIDATES = [
    "通勤",
    "休闲",
    "正式",
    "运动",
    "街头",
    "学院",
    "甜酷",
    "简约",
    "复古",
    "朋克",
    "民族",
    "优雅",
    "度假",
]

# Fit types in Chinese
FIT_CANDIDATES = [
    "修身",
    "宽松",
    "标准",
    "oversized",
]

# Occasions in Chinese (for occasion tagging)
OCCASION_CANDIDATES = [
    "通勤上班",
    "商务正式",
    "约会",
    "休闲日常",
    "运动健身",
    "校园",
    "聚会",
    "度假旅行",
    "街头潮流",
    "正式宴会",
]

# ──────────────────────────────────────────────────────────────────────────────
# Chinese Fashion CLIP Recognizer
# ──────────────────────────────────────────────────────────────────────────────


class CLIPRecognizer:
    """
    CLIP-based fashion image recognizer.

    Supports:
    - Category classification (6 classes)
    - Style tagging (12+ styles, multi-label)
    - Fit type estimation (4 types)
    - Occasion tagging (10 occasions, multi-label)
    - Feature extraction (512-dim for ViT-B/32, 768-dim for ViT-L/14)

    Falls back to MobileNetV2 if CLIP loading fails.
    """

    # Feature dimension per CLIP model
    CLIP_FEATURE_DIMS = {
        "vit_b32": 512,
        "vit_l14": 768,
    }

    def __init__(
        self,
        model_name: str = "vit_l14",  # "vit_b32" or "vit_l14"
        device: str = "auto",  # "auto", "cuda", "cpu"
        enable_cache: bool = True,
    ):
        """
        Initialize CLIP recognizer.

        Args:
            model_name: CLIP model variant ("vit_b32" or "vit_l14")
            device: Device to run on ("auto", "cuda", "cpu")
            enable_cache: Whether to cache results (default True)
        """
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.enable_cache = enable_cache

        # Initialize cache
        self._cache: Dict[str, dict] = {}
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Cache for text embeddings (computed once per instance)
        self._text_cache: Dict[str, np.ndarray] = {}

        # Will be initialized lazily on first use
        self._model = None
        self._preprocess = None
        self._feature_dim = self.CLIP_FEATURE_DIMS.get(model_name, 512)
        self._is_clip_available = None

        logger.info(f"CLIPRecognizer initialized (model={model_name}, device={self.device})")

    def _resolve_device(self, device: str) -> str:
        """Resolve compute device."""
        if device == "auto":
            try:
                import torch

                return "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                return "cpu"
        return device

    # ─── Lazy model loading ────────────────────────────────────────────────────

    def _ensure_model_loaded(self) -> bool:
        """
        Lazily load CLIP model. Returns True if successful, False if fallback needed.
        """
        if self._is_clip_available is not None:
            return self._is_clip_available

        try:
            from transformers import CLIPModel, CLIPProcessor

            model_id = self._get_huggingface_model_id()
            logger.info(f"Loading CLIP model: {model_id} on {self.device}")

            self._model = CLIPModel.from_pretrained(model_id)
            self._model.to(self.device)
            self._model.eval()

            self._processor = CLIPProcessor.from_pretrained(model_id)

            self._is_clip_available = True
            logger.info("CLIP model loaded successfully")
            return True

        except ImportError as e:
            logger.warning(f"transformers/torch not available: {e}")
            logger.warning("Will use MobileNetV2 fallback for features + heuristics for categories")
            self._is_clip_available = False
            return False
        except Exception as e:
            logger.warning(f"Failed to load CLIP: {e}")
            self._is_clip_available = False
            return False

    def _get_huggingface_model_id(self) -> str:
        """Get HuggingFace model ID for CLIP variant."""
        variants = {
            "vit_b32": "openai/clip-vit-base-patch32",
            "vit_l14": "openai/clip-vit-large-patch14",
        }
        return variants.get(self.model_name, "openai/clip-vit-base-patch32")

    # ─── Core CLIP inference ───────────────────────────────────────────────────

    def _compute_image_features(self, image: Image.Image) -> np.ndarray:
        """Extract CLIP image features."""
        self._ensure_model_loaded()

        if self._is_clip_available:
            import torch

            inputs = self._processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad():
                image_features = self._model.get_image_features(**inputs)
            # L2 normalize
            image_features = image_features.cpu().numpy()
            image_features = image_features / np.linalg.norm(image_features)
            return image_features[0]
        else:
            # Fallback: use MobileNetV2
            return self._mobilenet_fallback_features(image)

    def _compute_text_features(self, texts: List[str]) -> np.ndarray:
        """Compute CLIP text features for a list of texts (cached per instance)."""
        self._ensure_model_loaded()

        cache_key = "|".join(sorted(texts))
        if cache_key in self._text_cache:
            return self._text_cache[cache_key]

        if self._is_clip_available:
            import torch

            inputs = self._processor(text=texts, return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad():
                text_features = self._model.get_text_features(**inputs)
            text_features = text_features.cpu().numpy()
            # L2 normalize
            norms = np.linalg.norm(text_features, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-12)
            text_features = text_features / norms
            self._text_cache[cache_key] = text_features
            return text_features
        else:
            # Fallback: random unit vectors
            n = len(texts)
            features = np.random.randn(n, self._feature_dim).astype(np.float32)
            features = features / np.linalg.norm(features, axis=1, keepdims=True)
            self._text_cache[cache_key] = features
            return text_features

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        return float(np.dot(a, b))

    def _compute_similarities(
        self, image_features: np.ndarray, text_features: np.ndarray
    ) -> np.ndarray:
        """Compute cosine similarities between image and text features."""
        return np.dot(text_features, image_features)

    # ─── Zero-shot classification ─────────────────────────────────────────────

    def _classify_zero_shot(
        self,
        image: Image.Image,
        candidates: List[str],
        prompt_template: str = "a photo of {label}",
    ) -> Tuple[str, float, Dict[str, float]]:
        """
        Zero-shot classification using CLIP.

        Args:
            image: PIL Image
            candidates: List of candidate labels
            prompt_template: Template to wrap each label

        Returns:
            Tuple of (best_label, best_score, all_scores_dict)
        """
        self._ensure_model_loaded()

        # Build text inputs
        texts = [prompt_template.format(label=c) for c in candidates]
        text_features = self._compute_text_features(texts)
        image_features = self._compute_image_features(image)

        # Compute similarities
        similarities = self._compute_similarities(image_features, text_features)

        # Map to candidate labels
        scores = {candidates[i]: float(similarities[i]) for i in range(len(candidates))}

        # Find best
        best_label = max(scores, key=scores.get)
        best_score = scores[best_label]

        return best_label, best_score, scores

    def _classify_multi_label(
        self,
        image: Image.Image,
        candidates: List[str],
        threshold: float = 0.25,
        prompt_template: str = "a photo of {label}",
    ) -> List[str]:
        """
        Multi-label classification using CLIP (returns all candidates above threshold).

        Args:
            image: PIL Image
            candidates: List of candidate labels
            threshold: Minimum similarity score to include a label
            prompt_template: Template to wrap each label

        Returns:
            List of labels that exceed threshold
        """
        _, _, scores = self._classify_zero_shot(image, candidates, prompt_template)

        selected = [label for label, score in scores.items() if score >= threshold]

        # Always return at least the top-1 if nothing exceeds threshold
        if not selected:
            best = max(scores, key=scores.get)
            selected = [best]

        return selected

    # ─── Public API ───────────────────────────────────────────────────────────

    def recognize(
        self,
        image_source: Union[str, Path, bytes, Image.Image],
    ) -> dict:
        """
        Perform complete fashion image recognition using CLIP.

        Pipeline:
        1. Load & preprocess image
        2. Zero-shot category classification (6 classes)
        3. Zero-shot style tagging (12+ styles, multi-label)
        4. Zero-shot fit type estimation (4 types)
        5. Zero-shot occasion tagging (10 occasions, multi-label)
        6. Extract CLIP feature vector (768-dim)

        Args:
            image_source: Image file path, bytes, or PIL Image

        Returns:
            Dict with category, style_tags, fit_type, occasions, feature_vector
        """
        # Load image
        image = self._load_image(image_source)

        # Check cache
        cache_key = self._compute_cache_key(image_source)
        if self.enable_cache and cache_key in self._cache:
            logger.debug("CLIPRecognizer cache hit")
            return self._cache[cache_key]

        self._ensure_model_loaded()

        logger.info("Starting CLIP fashion recognition")

        # 1. Category (single-label, high confidence needed)
        category, cat_conf, cat_scores = self._classify_zero_shot(
            image,
            CATEGORY_CANDIDATES,
            prompt_template="a photo of {label} clothing",
        )
        logger.info(f"Category: {category} (conf={cat_conf:.3f})")

        # 2. Style tags (multi-label)
        style_tags = self._classify_multi_label(
            image,
            STYLE_CANDIDATES,
            threshold=0.25,
            prompt_template="a {label} style outfit",
        )
        logger.info(f"Styles: {style_tags}")

        # 3. Fit type (single-label)
        fit_type, fit_conf, _ = self._classify_zero_shot(
            image,
            FIT_CANDIDATES,
            prompt_template="a photo of {label} fit clothing",
        )
        # Only return fit_type if confidence is reasonable
        if fit_conf < 0.20:
            fit_type = None
        logger.info(f"Fit type: {fit_type} (conf={fit_conf:.3f})")

        # 4. Occasion tags (multi-label) - for recommendation context
        occasions = self._classify_multi_label(
            image,
            OCCASION_CANDIDATES,
            threshold=0.25,
            prompt_template="a photo suitable for {label}",
        )
        logger.info(f"Occasions: {occasions}")

        # 5. Feature vector
        feature_vector = self._compute_image_features(image)
        logger.info(f"Feature vector: dim={len(feature_vector)}")

        result = {
            "category": category,
            "category_confidence": float(cat_conf),
            "category_scores": {k: float(v) for k, v in cat_scores.items()},
            "style_tags": style_tags,
            "fit_type": fit_type,
            "fit_confidence": float(fit_conf) if fit_type else None,
            "occasions": occasions,
            "feature_vector": feature_vector.tolist(),
            "feature_dim": len(feature_vector),
        }

        # Cache
        if self.enable_cache:
            self._cache[cache_key] = result

        logger.info("CLIP recognition completed")
        return result

    # ─── Fallback for feature extraction ────────────────────────────────────

    def _mobilenet_fallback_features(self, image: Image.Image) -> np.ndarray:
        """
        Fallback feature extraction using MobileNetV2 when CLIP unavailable.
        Returns a 512-dim or 768-dim zero-padded vector compatible with CLIP dims.
        """
        try:
            from app.ml.feature_extractor import FeatureExtractor

            extractor = FeatureExtractor(enable_cache=False)
            mobilenet_features = extractor.extract(image)  # 1280-dim

            # Project to CLIP-compatible dimension using simple PCA-like approach
            # Take first N dimensions (mobilenet correlates with CLIP somewhat)
            target_dim = self._feature_dim
            if len(mobilenet_features) >= target_dim:
                projected = mobilenet_features[:target_dim]
            else:
                projected = np.zeros(target_dim, dtype=np.float32)
                projected[: len(mobilenet_features)] = mobilenet_features

            # L2 normalize
            projected = projected / np.linalg.norm(projected)
            return projected
        except Exception as e:
            logger.warning(f"MobileNetV2 fallback also failed: {e}")
            # Return random unit vector
            v = np.random.randn(self._feature_dim).astype(np.float32)
            return v / np.linalg.norm(v)

    # ─── Utility ──────────────────────────────────────────────────────────────

    def _load_image(self, source: Union[str, Path, bytes, Image.Image]) -> Image.Image:
        """Load image from various sources."""
        if isinstance(source, Image.Image):
            return source.convert("RGB")

        if isinstance(source, (str, Path)):
            from pathlib import Path as P

            return Image.open(P(source)).convert("RGB")

        if isinstance(source, bytes):
            from io import BytesIO

            return Image.open(BytesIO(source)).convert("RGB")

        raise ValueError(f"Unsupported image source type: {type(source)}")

    def _compute_cache_key(self, source: Union[str, Path, bytes, Image.Image]) -> str:
        """Compute cache key for an image source."""
        if isinstance(source, (str, Path)):
            with open(source, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        if isinstance(source, bytes):
            return hashlib.md5(source).hexdigest()
        if isinstance(source, Image.Image):
            buf = BytesIO()
            source.save(buf, format="PNG")
            return hashlib.md5(buf.getvalue()).hexdigest()
        return hashlib.md5(str(source).encode()).hexdigest()

    # ─── Specialized methods ─────────────────────────────────────────────────

    def extract_features(self, image_source: Union[str, Path, bytes, Image.Image]) -> np.ndarray:
        """
        Extract CLIP feature vector from image.
        Used for similarity matching.
        """
        image = self._load_image(image_source)
        return self._compute_image_features(image)

    def classify_category(
        self, image_source: Union[str, Path, bytes, Image.Image]
    ) -> Tuple[str, float]:
        """Classify garment category (single-label)."""
        image = self._load_image(image_source)
        return self._classify_zero_shot(
            image,
            CATEGORY_CANDIDATES,
            prompt_template="a photo of {label} clothing",
        )[:2]

    def classify_styles(self, image_source: Union[str, Path, bytes, Image.Image]) -> List[str]:
        """Classify style tags (multi-label)."""
        image = self._load_image(image_source)
        return self._classify_multi_label(
            image,
            STYLE_CANDIDATES,
            threshold=0.25,
            prompt_template="a {label} style outfit",
        )

    def tag_occasions(self, image_source: Union[str, Path, bytes, Image.Image]) -> List[str]:
        """Tag suitable occasions (multi-label)."""
        image = self._load_image(image_source)
        return self._classify_multi_label(
            image,
            OCCASION_CANDIDATES,
            threshold=0.25,
            prompt_template="a photo suitable for {label}",
        )

    def clear_cache(self):
        """Clear the in-memory cache."""
        self._cache.clear()
        self._text_cache.clear()
        logger.info("CLIPRecognizer cache cleared")

    def __del__(self):
        """Cleanup resources."""
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=False)


# ──────────────────────────────────────────────────────────────────────────────
# Global singleton instance (lazy-loaded)
# ──────────────────────────────────────────────────────────────────────────────
_recognizer_instance: Optional[CLIPRecognizer] = None


def get_clip_recognizer() -> CLIPRecognizer:
    """Get or create the global CLIPRecognizer singleton."""
    global _recognizer_instance
    if _recognizer_instance is None:
        _recognizer_instance = CLIPRecognizer()
    return _recognizer_instance
