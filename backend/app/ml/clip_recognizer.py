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
# Enhanced Chinese Fashion Prompt Engineering
# ──────────────────────────────────────────────────────────────────────────────

# Garment categories — Extended with Chinese-fashion specific categories
CATEGORY_CANDIDATES = [
    # Western fashion
    "上衣",  # Tops: T-shirt, 衬衫, 毛衣, 卫衣, 针织衫
    "裤子",  # Bottoms: 牛仔裤, 西裤, 休闲裤, 运动裤
    "裙子",  # Dresses/Skirts: 连衣裙, 半裙, 短裙
    "外套",  # Outerwear: 夹克, 西装, 风衣, 大衣, 羽绒服
    "鞋",  # Footwear: 运动鞋, 高跟鞋, 靴子, 休闲鞋
    "包",  # Bags: 手提包, 双肩包, 单肩包
    # Chinese-fashion specific
    "汉服",  # Hanfu整套
    "国风",  # 新中式（旗袍/唐装/禅意风）
    "马面裙",  # 马面裙
    "上衣(汉)",  # 汉服上衣
    "下装(汉)",  # 汉服下装
]

# Fashion styles — Extended with Chinese fashion styles
STYLE_CANDIDATES = [
    # Western styles
    "通勤", "休闲", "正式", "运动", "街头",
    "学院", "甜酷", "简约", "复古", "朋克",
    "民族", "优雅", "度假",
    # Chinese styles
    "国风", "汉服", "新中式", "禅意", "古风",
]

# Fit types
FIT_CANDIDATES = ["修身", "标准", "宽松", "oversized"]

# Occasions
OCCASION_CANDIDATES = [
    "通勤上班", "商务正式", "约会", "休闲日常", "运动健身",
    "校园", "聚会", "度假旅行", "街头潮流", "正式宴会",
]

# ──────────────────────────────────────────────────────────────────────────────
# Enhanced Chinese Fashion Prompt Templates
# ──────────────────────────────────────────────────────────────────────────────

# Category prompts — bilingual for better CLIP understanding
CATEGORY_PROMPTS = {
    "上衣": "a stylish Chinese top: T-shirt, dress shirt, sweater, hoodie, knitwear",
    "裤子": "classic pants or bottoms: jeans, trousers, casual pants, leggings",
    "裙子": "elegant dress or skirt: dress, skirt, miniskirt, gown",
    "外套": "fashionable outerwear: jacket, blazer, coat, windbreaker, down jacket",
    "鞋": "fashionable shoes: sneakers, high heels, boots, casual shoes",
    "包": "designer bag: handbag, backpack, shoulder bag, tote",
    "汉服": "traditional Chinese Hanfu complete outfit,曲裾直裾圆领袍 Han Chinese clothing",
    "国风": "Chinese fashion 新中式旗袍唐装 with traditional Chinese elements",
    "马面裙": "Chinese Mamian skirt 马面裙 with traditional pleated design",
    "上衣(汉)": "traditional Chinese top 汉服上襦衫袄 with Han style",
    "下装(汉)": "traditional Chinese bottom 汉服裙裤 with Han style",
}

# Style prompts — detailed descriptions in English for better CLIP matching
STYLE_PROMPTS = {
    "通勤": "professional office commute style, business work outfit",
    "休闲": "casual everyday comfortable style, relaxed leisure outfit",
    "正式": "formal business attire, elegant formal wear",
    "运动": "athletic sports fitness outfit, gym workout clothing",
    "街头": "street fashion urban style, trendy urban streetwear",
    "学院": "preppy academic college style, scholarly campus fashion",
    "甜酷": "sweet and cool mix style, girl crush outfit",
    "简约": "minimalist simple clean style, basic wardrobe pieces",
    "复古": "vintage retro old-fashioned style, classic vintage fashion",
    "朋克": "punk edgy rebellious style, alternative fashion",
    "民族": "ethnic cultural style, traditional folk fashion",
    "优雅": "elegant graceful feminine style, sophisticated chic outfit",
    "度假": "resort vacation tropical style, holiday travel outfit",
    "国风": "国潮 Chinese fashion, modern Chinese cultural style, 中国风",
    "汉服": "traditional Chinese Hanfu style, 汉服古典造型",
    "新中式": "neo-Chinese new Chinese style, modern Chinese chic, 新中式穿搭",
    "禅意": "zen minimalist Eastern aesthetic, 禅意素雅风格",
    "古风": "ancient classical Chinese style, 古风造型, traditional Chinese",
}

# Scene prompts — detailed descriptions
SCENE_PROMPTS = {
    "通勤上班": "suitable for daily commute office work, professional business setting",
    "商务正式": "appropriate for formal business meeting conference negotiation",
    "约会": "romantic date dinner outfit, couple dating, love atmosphere",
    "休闲日常": "casual daily life shopping outing, comfortable home relaxed",
    "运动健身": "gym fitness exercise running outdoor sports activity",
    "校园": "campus school life classroom learning student activities",
    "聚会": "friend party social gathering birthday celebration",
    "度假旅行": "vacation travel beach resort tropical holiday trip",
    "街头潮流": "street trend fashion show edgy avant-garde urban style",
    "正式宴会": "gala dinner red carpet formal banquet high-end event",
}

# ──────────────────────────────────────────────────────────────────────────────
# Chinese Fashion CLIP Recognizer
# ──────────────────────────────────────────────────────────────────────────────


class CLIPRecognizer:
    """
    Enhanced CLIP-based fashion image recognizer.

    Supports:
    - Category classification (11 classes including Chinese fashion)
    - Style tagging (18+ styles, multi-label)
    - Fit type estimation (4 types)
    - Occasion tagging (10 occasions, multi-label)
    - Feature extraction (512-dim for ViT-B/32, 768-dim for ViT-L/14)

    Falls back to MobileNetV2 if CLIP loading fails.
    """

    CLIP_FEATURE_DIMS = {
        "vit_b32": 512,
        "vit_l14": 768,
    }

    def __init__(
        self,
        model_name: str = "vit_l14",
        device: str = "auto",
        enable_cache: bool = True,
    ):
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.enable_cache = enable_cache

        self._cache: Dict[str, dict] = {}
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._text_cache: Dict[str, np.ndarray] = {}

        self._model = None
        self._processor = None
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
        """Lazily load CLIP model. Returns True if successful, False if fallback needed."""
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
            image_features = image_features.cpu().numpy()[0]
            image_features = image_features / np.linalg.norm(image_features)
            return image_features
        else:
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
            norms = np.linalg.norm(text_features, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-12)
            text_features = text_features / norms
            self._text_cache[cache_key] = text_features
            return text_features
        else:
            n = len(texts)
            features = np.random.randn(n, self._feature_dim).astype(np.float32)
            features = features / np.linalg.norm(features, axis=1, keepdims=True)
            self._text_cache[cache_key] = features
            return features

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        return float(np.dot(a, b))

    def _compute_similarities(
        self, image_features: np.ndarray, text_features: np.ndarray
    ) -> np.ndarray:
        """Compute cosine similarities between image and text features."""
        return np.dot(text_features, image_features)

    # ─── Zero-shot classification with enhanced prompts ─────────────────────────

    def _classify_zero_shot(
        self,
        image: Image.Image,
        candidates: List[str],
        prompt_dict: Dict[str, str],
        default_template: str = "a photo of {label} clothing",
    ) -> Tuple[str, float, Dict[str, float]]:
        """Zero-shot classification using enhanced bilingual prompts."""
        self._ensure_model_loaded()

        # Build text inputs using enhanced prompts
        texts = [prompt_dict.get(c, default_template.format(label=c)) for c in candidates]
        text_features = self._compute_text_features(texts)
        image_features = self._compute_image_features(image)

        similarities = self._compute_similarities(image_features, text_features)
        scores = {candidates[i]: float(similarities[i]) for i in range(len(candidates))}

        best_label = max(scores, key=scores.get)
        best_score = scores[best_label]

        return best_label, best_score, scores

    def _classify_multi_label(
        self,
        image: Image.Image,
        candidates: List[str],
        prompt_dict: Dict[str, str],
        threshold: float = 0.25,
        default_template: str = "a {label} style outfit",
    ) -> List[str]:
        """Multi-label classification using enhanced prompts."""
        _, _, scores = self._classify_zero_shot(
            image, candidates, prompt_dict, default_template
        )

        selected = [label for label, score in scores.items() if score >= threshold]

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
        2. Category classification (11 classes including Chinese fashion)
        3. Style tagging (18+ styles, multi-label)
        4. Fit type estimation (4 types)
        5. Occasion tagging (10 occasions, multi-label)
        6. Extract CLIP feature vector (768-dim)
        """
        image = self._load_image(image_source)

        cache_key = self._compute_cache_key(image_source)
        if self.enable_cache and cache_key in self._cache:
            logger.debug("CLIPRecognizer cache hit")
            return self._cache[cache_key]

        self._ensure_model_loaded()
        logger.info("Starting CLIP fashion recognition")

        # 1. Category (single-label)
        category, cat_conf, cat_scores = self._classify_zero_shot(
            image,
            CATEGORY_CANDIDATES,
            CATEGORY_PROMPTS,
            default_template="a photo of {label} clothing",
        )
        logger.info(f"Category: {category} (conf={cat_conf:.3f})")

        # 2. Style tags (multi-label)
        style_tags = self._classify_multi_label(
            image,
            STYLE_CANDIDATES,
            STYLE_PROMPTS,
            threshold=0.25,
            default_template="a {label} style outfit",
        )
        logger.info(f"Styles: {style_tags}")

        # 3. Fit type (single-label)
        fit_type, fit_conf, _ = self._classify_zero_shot(
            image,
            FIT_CANDIDATES,
            {},
            default_template="a photo of {label} fit clothing",
        )
        if fit_conf < 0.20:
            fit_type = None
        logger.info(f"Fit type: {fit_type} (conf={fit_conf:.3f})")

        # 4. Occasion tags (multi-label)
        occasions = self._classify_multi_label(
            image,
            OCCASION_CANDIDATES,
            SCENE_PROMPTS,
            threshold=0.25,
            default_template="a photo suitable for {label}",
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

        if self.enable_cache:
            self._cache[cache_key] = result

        logger.info("CLIP recognition completed")
        return result

    # ─── Fallback for feature extraction ────────────────────────────────────

    def _mobilenet_fallback_features(self, image: Image.Image) -> np.ndarray:
        """
        Fallback feature extraction using MobileNetV2 when CLIP unavailable.
        Returns CLIP-compatible dimension zero-padded vector.
        """
        try:
            from app.ml.feature_extractor import FeatureExtractor
            extractor = FeatureExtractor(enable_cache=False)
            mobilenet_features = extractor.extract(image)  # 1280-dim

            # Project to CLIP-compatible dimension
            target_dim = self._feature_dim
            if len(mobilenet_features) >= target_dim:
                projected = mobilenet_features[:target_dim]
            else:
                projected = np.zeros(target_dim, dtype=np.float32)
                projected[: len(mobilenet_features)] = mobilenet_features

            projected = projected / np.linalg.norm(projected)
            return projected
        except Exception as e:
            logger.warning(f"MobileNetV2 fallback also failed: {e}")
            v = np.random.randn(self._feature_dim).astype(np.float32)
            return v / np.linalg.norm(v)

    # ─── Utility ─────────────────────────────────────────────────────────────

    def _load_image(self, source: Union[str, Path, bytes, Image.Image]) -> Image.Image:
        """Load image from various sources."""
        if isinstance(source, Image.Image):
            return source.convert("RGB")

        if isinstance(source, (str, Path)):
            return Image.open(Path(source)).convert("RGB")

        if isinstance(source, bytes):
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
        """Extract CLIP feature vector from image. Used for similarity matching."""
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
            CATEGORY_PROMPTS,
            default_template="a photo of {label} clothing",
        )[:2]

    def classify_styles(self, image_source: Union[str, Path, bytes, Image.Image]) -> List[str]:
        """Classify style tags (multi-label)."""
        image = self._load_image(image_source)
        return self._classify_multi_label(
            image,
            STYLE_CANDIDATES,
            STYLE_PROMPTS,
            threshold=0.25,
            default_template="a {label} style outfit",
        )

    def tag_occasions(self, image_source: Union[str, Path, bytes, Image.Image]) -> List[str]:
        """Tag suitable occasions (multi-label)."""
        image = self._load_image(image_source)
        return self._classify_multi_label(
            image,
            OCCASION_CANDIDATES,
            SCENE_PROMPTS,
            threshold=0.25,
            default_template="a photo suitable for {label}",
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
