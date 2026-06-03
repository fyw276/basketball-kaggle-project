"""
Unit tests for image recognition module (Tasks 6.3, 7.3, 8.3, 9.2, 11.3)
"""

import io

import numpy as np
from PIL import Image

from app.ml.category_classifier import CategoryClassifier
from app.ml.color_extractor import ColorExtractor
from app.ml.feature_extractor import FeatureExtractor
from app.ml.image_preprocessor import ImagePreprocessor
from app.ml.image_recognizer import ImageRecognizer
from app.ml.style_classifier import StyleClassifier


def create_test_image(color="blue", size=(224, 224)):
    """Create a test PIL image"""
    return Image.new("RGB", size, color=color)


def create_test_image_bytes(color="blue", size=(224, 224)):
    """Create test image as bytes"""
    img = create_test_image(color, size)
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    return img_bytes.getvalue()


class TestImagePreprocessor:
    """Test image preprocessing"""

    def test_preprocessor_initialization(self):
        """Test preprocessor initializes correctly"""
        preprocessor = ImagePreprocessor(target_size=(224, 224))
        assert preprocessor is not None

    def test_preprocess_pil_image(self):
        """Test preprocessing PIL image"""
        preprocessor = ImagePreprocessor(target_size=(224, 224))
        img = create_test_image()

        processed = preprocessor.preprocess_single(img)

        assert processed is not None
        assert processed.shape == (1, 224, 224, 3)

    def test_preprocess_bytes(self):
        """Test preprocessing image bytes"""
        preprocessor = ImagePreprocessor(target_size=(224, 224))
        img_bytes = create_test_image_bytes()

        processed = preprocessor.preprocess_single(img_bytes)

        assert processed is not None
        assert processed.shape == (1, 224, 224, 3)


class TestColorExtractor:
    """Test color extraction"""

    def test_color_extractor_initialization(self):
        """Test color extractor initializes"""
        extractor = ColorExtractor(n_colors=3)
        assert extractor is not None

    def test_extract_colors_from_image(self):
        """Test extracting colors from image"""
        extractor = ColorExtractor(n_colors=3)
        img = create_test_image(color="blue")

        colors = extractor.extract_colors(img)

        assert colors is not None
        assert len(colors) > 0
        assert hasattr(colors[0], "name")
        assert hasattr(colors[0], "rgb")
        assert hasattr(colors[0], "hex_code")
        assert colors[0].confidence is not None
        assert 0.0 <= colors[0].confidence <= 1.0

    def test_extract_color_ignores_white_product_background(self):
        extractor = ColorExtractor(n_colors=3)
        img = Image.new("RGB", (240, 240), "white")
        for x in range(80, 160):
            for y in range(40, 220):
                img.putpixel((x, y), (245, 168, 190))

        colors = extractor.extract_colors(img)

        assert colors[0].name == "粉"

    def test_extract_multicolor_black_white_garment(self):
        extractor = ColorExtractor(n_colors=3)
        img = Image.new("RGB", (240, 240), "white")
        for x in range(50, 190):
            for y in range(40, 220):
                is_black = ((x // 24) + (y // 24)) % 2 == 0
                img.putpixel((x, y), (15, 15, 15) if is_black else (240, 240, 240))

        colors = extractor.extract_colors(img)
        names = {c.name for c in colors}

        assert {"黑", "白"}.issubset(names)

    def test_extract_silver_white_shoe_does_not_promote_shadow_to_black(self):
        extractor = ColorExtractor(n_colors=3)
        img = Image.new("RGB", (240, 240), "white")
        for x in range(46, 194):
            for y in range(94, 174):
                img.putpixel((x, y), (226, 228, 226))
        for x in range(76, 176):
            for y in range(126, 156):
                img.putpixel((x, y), (248, 248, 246))
        for x in range(72, 184):
            for y in range(166, 178):
                img.putpixel((x, y), (44, 44, 44))

        colors = extractor.extract_colors(img)
        names = [c.name for c in colors]

        assert names[0] in {"白", "灰"}
        assert "黑" not in names

    def test_extract_black_white_pants_keeps_real_black_and_white(self):
        extractor = ColorExtractor(n_colors=3)
        img = Image.new("RGB", (260, 260), "white")
        for x in range(74, 122):
            for y in range(36, 232):
                img.putpixel((x, y), (16, 16, 16))
        for x in range(138, 186):
            for y in range(36, 232):
                img.putpixel((x, y), (238, 238, 236))

        colors = extractor.extract_colors(img)
        names = {c.name for c in colors}

        assert {"黑", "白"}.issubset(names)

    def test_extract_green_skirt_over_mixed_background_keeps_green_main(self):
        extractor = ColorExtractor(n_colors=3)
        img = Image.new("RGB", (260, 260), (245, 245, 245))
        for x in range(40, 96):
            for y in range(40, 235):
                img.putpixel((x, y), (226, 177, 139))
        for x in range(88, 212):
            for y in range(82, 228):
                if abs(x - 150) + y < 330:
                    img.putpixel((x, y), (38, 142, 72))
        for x in range(110, 204):
            for y in range(214, 230):
                img.putpixel((x, y), (34, 34, 34))

        colors = extractor.extract_colors(img)

        assert colors[0].name == "绿"

    def test_extract_chromatic_color_over_dark_shadow(self):
        extractor = ColorExtractor(n_colors=3)
        img = Image.new("RGB", (240, 240), (18, 18, 18))
        for x in range(70, 170):
            for y in range(70, 205):
                img.putpixel((x, y), (45, 145, 75))

        colors = extractor.extract_colors(img)

        assert colors[0].name == "绿"


class TestCategoryClassifier:
    """Test category classification"""

    def test_classifier_initialization(self):
        """Test classifier initializes"""
        classifier = CategoryClassifier()
        assert classifier is not None

    def test_classify_category(self):
        """Test classifying garment category"""
        classifier = CategoryClassifier()
        img = create_test_image()

        category, confidence = classifier.classify_category(img)

        assert category is not None
        assert isinstance(category, str)
        assert 0 <= confidence <= 1

    def test_low_confidence_keeps_best_category(self):
        """Low confidence predictions should not collapse to 上衣."""
        classifier = CategoryClassifier.__new__(CategoryClassifier)
        classifier.confidence_threshold = 0.5

        predictions = np.zeros(1000, dtype=float)
        predictions[788] = 0.05  # shoes mapping, intentionally below threshold

        category, confidence = classifier._map_to_garment_category(predictions)

        assert category == "鞋"
        assert confidence == 0.05


class TestStyleClassifier:
    """Test style classification"""

    def test_style_classifier_initialization(self):
        """Test style classifier initializes"""
        classifier = StyleClassifier()
        assert classifier is not None

    def test_classify_style(self):
        """Test classifying style tags"""
        classifier = StyleClassifier()
        img = create_test_image()

        style_tags = classifier.classify_style(img)

        assert style_tags is not None
        assert isinstance(style_tags, list)


class TestFeatureExtractor:
    """Test feature extraction"""

    def test_feature_extractor_initialization(self):
        """Test feature extractor initializes"""
        extractor = FeatureExtractor()
        assert extractor is not None

    def test_extract_features(self):
        """Test extracting feature vector"""
        extractor = FeatureExtractor()
        img = create_test_image()

        features = extractor.extract(img)

        assert features is not None
        assert isinstance(features, np.ndarray)
        assert features.shape == (1280,)


class TestImageRecognizer:
    """Test complete image recognition pipeline"""

    def test_recognizer_initialization(self):
        """Test recognizer initializes with all modules"""
        recognizer = ImageRecognizer()
        assert recognizer is not None
        assert recognizer.category_classifier is not None
        assert recognizer.color_extractor is not None
        assert recognizer.style_classifier is not None
        assert recognizer.feature_extractor is not None

    def test_recognize_complete_pipeline(self):
        """Test complete recognition pipeline"""
        recognizer = ImageRecognizer()
        img = create_test_image()

        result = recognizer.recognize(img)

        assert result is not None
        assert hasattr(result, "category")
        assert hasattr(result, "category_confidence")
        assert hasattr(result, "main_color")
        assert hasattr(result, "style_tags")
        assert hasattr(result, "feature_vector")
        assert len(result.feature_vector) == 1280

    def test_recognize_from_bytes(self):
        """Test recognition from image bytes"""
        recognizer = ImageRecognizer()
        img_bytes = create_test_image_bytes()

        result = recognizer.recognize(img_bytes)

        assert result is not None
        assert result.category is not None

    def test_recognize_batch(self):
        """Test batch recognition"""
        recognizer = ImageRecognizer()
        images = [create_test_image() for _ in range(3)]

        results = recognizer.recognize_batch(images)

        assert results is not None
        assert len(results) == 3
        assert all(hasattr(r, "category") for r in results)
