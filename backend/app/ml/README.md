# Machine Learning Module

This module provides image recognition capabilities using MobileNetV2 pretrained model.

## Components

### 1. ModelLoader

Manages loading and caching of the MobileNetV2 pretrained model.

```python
from app.ml.model_loader import ModelLoader

# Initialize loader
loader = ModelLoader()

# Load feature extractor (downloads ImageNet weights on first run)
model = loader.load_feature_extractor()

# Get model information
info = loader.get_model_info()
print(info)
# Output: {
#   'status': 'loaded',
#   'model_name': 'MobileNetV2',
#   'input_shape': (None, 224, 224, 3),
#   'output_shape': (None, 1280),
#   'trainable': False,
#   'total_params': 2257984
# }
```

### 2. ImagePreprocessor

Handles image preprocessing for MobileNetV2 inference.

```python
from app.ml.image_preprocessor import ImagePreprocessor
from PIL import Image

# Initialize preprocessor
preprocessor = ImagePreprocessor(target_size=(224, 224))

# Preprocess single image
image = Image.open("garment.jpg")
preprocessed = preprocessor.preprocess_single(image)
# Output shape: (1, 224, 224, 3), normalized to [-1, 1]

# Preprocess batch of images
images = [Image.open(f"garment_{i}.jpg") for i in range(5)]
batch = preprocessor.preprocess_batch(images)
# Output shape: (5, 224, 224, 3)

# Validate image
is_valid = preprocessor.validate_image("garment.jpg")
```

**Preprocessing Steps:**
1. Load image from file path, bytes, or PIL Image
2. Convert to RGB format
3. Resize to 224x224 pixels (BILINEAR resampling)
4. Convert to numpy array (float32)
5. Normalize to [-1, 1] range (MobileNetV2 preprocessing)
6. Add batch dimension

### 3. FeatureExtractor

Extracts 1280-dimensional feature vectors from images.

```python
from app.ml.feature_extractor import FeatureExtractor
from PIL import Image

# Initialize extractor
extractor = FeatureExtractor()

# Extract features from single image
image = Image.open("garment.jpg")
features = extractor.extract(image)
# Output shape: (1280,), L2-normalized

# Extract features from batch
images = [Image.open(f"garment_{i}.jpg") for i in range(5)]
batch_features = extractor.extract_batch(images)
# Output shape: (5, 1280)

# Get feature dimension
dim = extractor.get_feature_dimension()
# Output: 1280
```

**Feature Extraction:**
- Uses MobileNetV2 backbone (without top classification layer)
- Global average pooling produces 1280-dimensional vector
- L2 normalization ensures unit norm (useful for cosine similarity)

## Model Details

### MobileNetV2

- **Architecture**: Lightweight CNN optimized for mobile and edge devices
- **Pretrained Weights**: ImageNet (automatically downloaded on first use)
- **Input Size**: 224x224x3 (RGB images)
- **Feature Dimension**: 1280
- **Model Size**: ~14 MB
- **Inference Time**: < 100ms per image (CPU)

### Model Storage

Models are stored in the `models/` directory at the project root:
```
clothing-assistant/
├── models/
│   └── (MobileNetV2 weights cached here)
├── backend/
│   └── app/
│       └── ml/
```

## Usage Examples

### Complete Pipeline

```python
from app.ml import ModelLoader, ImagePreprocessor, FeatureExtractor
from PIL import Image
import numpy as np

# Initialize components
loader = ModelLoader()
preprocessor = ImagePreprocessor()
extractor = FeatureExtractor(model_loader=loader, preprocessor=preprocessor)

# Load and extract features
image = Image.open("garment.jpg")
features = extractor.extract(image)

# Features are L2-normalized, ready for similarity computation
print(f"Feature shape: {features.shape}")  # (1280,)
print(f"Feature norm: {np.linalg.norm(features):.4f}")  # ~1.0000
```

### Batch Processing

```python
from app.ml import FeatureExtractor
from pathlib import Path

extractor = FeatureExtractor()

# Process all images in a directory
image_dir = Path("uploads/garments")
image_paths = list(image_dir.glob("*.jpg"))

# Extract features in batch (more efficient)
features = extractor.extract_batch(image_paths)

# Store features in database
for path, feature_vector in zip(image_paths, features):
    # Save to database
    save_garment_features(path.stem, feature_vector.tolist())
```

## Testing

Run the test script to verify model loading and feature extraction:

```bash
cd backend
python scripts/test_model_loading.py
```

Expected output:
```
============================================================
MobileNetV2 Model Loading and Feature Extraction Test
============================================================

=== Testing ModelLoader ===
✓ ModelLoader initialized
✓ MobileNetV2 loaded
✓ Model info: {...}

=== Testing ImagePreprocessor ===
✓ ImagePreprocessor initialized
✓ Created test image: (300, 400)
✓ Preprocessed shape: (1, 224, 224, 3)
✓ Value range: [-1.00, 1.00]
✓ Shape verification passed
✓ Normalization verification passed
✓ Batch preprocessed shape: (3, 224, 224, 3)
✓ Batch shape verification passed

=== Testing FeatureExtractor ===
✓ FeatureExtractor initialized
✓ Feature dimension: 1280
✓ Extracted features shape: (1280,)
✓ Feature vector norm: 1.0000
✓ Feature shape verification passed
✓ L2 normalization verification passed
✓ Batch features shape: (2, 1280)
✓ Batch feature shape verification passed

============================================================
✓ ALL TESTS PASSED!
============================================================
```

## Requirements

The following dependencies are required (already in requirements.txt):

```
tensorflow==2.18.0
numpy>=1.26.0,<2.1.0
Pillow==11.1.0
```

## Performance Considerations

### Memory Usage
- Model size: ~14 MB
- Single image preprocessing: ~0.6 MB
- Feature vector: ~5 KB (1280 floats)

### Optimization Tips
1. **Batch Processing**: Process multiple images together for better throughput
2. **Model Caching**: ModelLoader caches the model in memory (reuse instances)
3. **Async Processing**: Use ThreadPoolExecutor for I/O-bound operations
4. **Feature Caching**: Cache extracted features in Redis to avoid recomputation

### Example: Async Feature Extraction

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.ml import FeatureExtractor

async def extract_features_async(image_path: str) -> np.ndarray:
    """Extract features asynchronously"""
    loop = asyncio.get_event_loop()
    extractor = FeatureExtractor()

    with ThreadPoolExecutor() as executor:
        features = await loop.run_in_executor(
            executor,
            extractor.extract,
            image_path
        )
    return features

# Usage
features = await extract_features_async("garment.jpg")
```

### 4. CategoryClassifier

Classifies garment images into 6 categories using MobileNetV2.

```python
from app.ml.category_classifier import CategoryClassifier
from PIL import Image

# Initialize classifier
classifier = CategoryClassifier()

# Classify single image
image = Image.open("garment.jpg")
result = classifier.classify(image)
print(result)
# Output: {
#   'category': '上衣',
#   'confidence': 0.95,
#   'all_probabilities': {
#     '上衣': 0.95,
#     '裤子': 0.02,
#     '裙子': 0.01,
#     '外套': 0.01,
#     '鞋': 0.005,
#     '包': 0.005
#   }
# }

# Classify batch
images = [Image.open(f"garment_{i}.jpg") for i in range(5)]
results = classifier.classify_batch(images)
```

**Categories:**
- 上衣 (Top): T-shirts, shirts, sweaters, hoodies
- 裤子 (Pants): Jeans, trousers, casual pants
- 裙子 (Skirt): Dresses, skirts
- 外套 (Outerwear): Jackets, coats, windbreakers
- 鞋 (Shoes): Sneakers, leather shoes, boots
- 包 (Bag): Handbags, backpacks, crossbody bags

### 5. ColorExtractor

Extracts dominant colors from garment images using K-Means clustering.

```python
from app.ml.color_extractor import ColorExtractor
from PIL import Image

# Initialize extractor
extractor = ColorExtractor(n_colors=3)

# Extract colors from image
image = Image.open("garment.jpg")
colors = extractor.extract_colors(image)

# Get main color
main_color = extractor.get_main_color(image)
print(main_color)
# Output: ColorSchema(
#   name='蓝',
#   rgb=(52, 120, 180),
#   hsv=(210.0, 71.1, 70.6),
#   hex_code='#3478b4'
# )

# Get secondary colors
secondary_colors = extractor.get_secondary_colors(image)
```

**Standard Color Categories (10 colors):**
- 红 (Red): H: 0-15° or 345-360°, S: ≥50%, V: ≥50%
- 橙 (Orange): H: 16-30°, S: ≥50%, V: ≥50%
- 黄 (Yellow): H: 31-60°, S: ≥50%, V: ≥50%
- 绿 (Green): H: 61-150°, S: ≥50%, V: ≥50%
- 蓝 (Blue): H: 151-240°, S: ≥50%, V: ≥50%
- 紫 (Purple): H: 241-300°, S: ≥50%, V: ≥50%
- 黑 (Black): S: ≤30%, V: ≤30%
- 白 (White): S: ≤30%, V: ≥70%
- 灰 (Gray): S: ≤30%, V: 31-69%
- 棕 (Brown): H: 16-30°, S: ≥30%, V: ≤60%

**Color Extraction Process:**
1. Resize image to 150x150 for faster processing
2. Apply K-Means clustering (default: 3 clusters)
3. Extract cluster centers as dominant RGB colors
4. Calculate color percentages
5. Sort by dominance (percentage)
6. Convert RGB to HSV and hex
7. Map to standard color categories

### 6. StyleClassifier

Classifies garment style tags using multi-label classification with MobileNetV2.

```python
from app.ml.style_classifier import StyleClassifier
from PIL import Image

# Initialize classifier
classifier = StyleClassifier(threshold=0.3)

# Classify style tags (multi-label)
image = Image.open("garment.jpg")
style_tags = classifier.classify_style(image)
print(style_tags)
# Output: ['通勤', '简约', '正式']

# Get style scores
style_scores = classifier.classify_style_with_scores(image)
print(style_scores)
# Output: {
#   '通勤': 0.85,
#   '简约': 0.72,
#   '正式': 0.68,
#   '休闲': 0.45,
#   ...
# }

# Adjust threshold
classifier.set_threshold(0.5)
style_tags = classifier.classify_style(image)
# Returns fewer tags with higher confidence

# Get available style tags
all_styles = classifier.get_style_tags()
```

**Style Tags (12 styles):**
- 通勤 (Commute): Office wear, business casual
- 休闲 (Casual): Everyday casual wear
- 正式 (Formal): Formal occasions, business formal
- 运动 (Sports): Athletic, sportswear
- 街头 (Street): Street style, urban fashion
- 学院 (School): Preppy, collegiate style
- 甜美 (Sweet): Cute, feminine style
- 简约 (Minimalist): Simple, clean lines
- 复古 (Vintage): Retro, vintage style
- 朋克 (Punk): Punk, edgy style
- 民族 (Ethnic): Ethnic patterns, traditional
- 优雅 (Elegant): Elegant, sophisticated

**Multi-Label Classification:**
- Uses sigmoid activation (not softmax) to allow multiple style tags
- Threshold filtering: Only tags with confidence ≥ threshold are returned
- If no tags exceed threshold, returns the highest scoring tag
- Default threshold: 0.3 (adjustable via `set_threshold()`)

**Threshold Guidelines:**
- 0.2-0.3: More tags, broader classification
- 0.4-0.5: Balanced, moderate number of tags
- 0.6-0.8: Fewer tags, higher confidence

## Next Steps

This module provides the foundation for:
- **Task 7**: ✅ Category classification (上衣/裤子/裙子/外套/鞋/包)
- **Task 8**: ✅ Color recognition and clustering
- **Task 9**: ✅ Style tag classification (通勤/休闲/正式/运动/街头等)
- **Task 14**: Similarity analysis using feature vectors (TODO)

The feature extraction, color recognition, and style classification capabilities are now ready for integration with the wardrobe management and similarity analysis modules.
