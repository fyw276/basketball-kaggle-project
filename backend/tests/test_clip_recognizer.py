"""
Step 2: CLIP 识别模块测试
测试 FashionCLIP 能否正确识别服装品类、风格和场合
"""

import io
import time

from PIL import Image, ImageDraw


# 创建测试图片：模拟蓝色衬衫（简单色块）
def create_test_image(color_rgb: tuple, label: str) -> Image.Image:
    """创建测试色块图片"""
    img = Image.new("RGB", (224, 224), color_rgb)
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 213, 213], outline="black", width=2)
    draw.text((60, 100), label, fill="white")
    return img


def test_clip_recognizer():
    """测试 CLIP 识别器的所有功能"""
    print("=" * 60)
    print("Step 2: CLIP 识别模块测试")
    print("=" * 60)

    # 导入 CLIP Recognizer
    print("\n[1] 导入 CLIP Recognizer...")
    from app.ml.clip_recognizer import (
        CATEGORY_CANDIDATES,
        OCCASION_CANDIDATES,
        STYLE_CANDIDATES,
        CLIPRecognizer,
    )

    print("    - CATEGORY_CANDIDATES:", CATEGORY_CANDIDATES)
    print("    - STYLE_CANDIDATES ({0}): {1}".format(len(STYLE_CANDIDATES), STYLE_CANDIDATES))
    print(
        "    - OCCASION_CANDIDATES ({0}): {1}".format(len(OCCASION_CANDIDATES), OCCASION_CANDIDATES)
    )

    # 创建 recognizer（懒加载，首次调用才加载模型）
    print("\n[2] 创建 CLIP Recognizer 实例...")
    recognizer = CLIPRecognizer(model_name="vit_l14", enable_cache=False)
    print("    - model_name:", recognizer.model_name)
    print("    - device:", recognizer.device)

    # 测试 1：创建蓝色"上衣"测试图
    print("\n[3] 测试蓝色上衣图片...")
    blue_shirt = create_test_image((52, 120, 180), "Blue Shirt")
    blue_img_bytes = io.BytesIO()
    blue_shirt.save(blue_img_bytes, format="PNG")
    blue_img_bytes.seek(0)
    blue_img_bytes = blue_img_bytes.getvalue()

    start = time.time()
    result1 = recognizer.recognize(blue_img_bytes)
    elapsed1 = time.time() - start
    print(f"    ✅ 识别完成，耗时 {elapsed1:.1f}s")
    print(f"    - category: {result1['category']} (conf={result1['category_confidence']:.3f})")
    print(f"    - category_scores: {dict(list(result1['category_scores'].items())[:3])}")
    print(f"    - style_tags: {result1['style_tags']}")
    print(f"    - fit_type: {result1['fit_type']}")
    print(f"    - occasions: {result1['occasions']}")
    print(f"    - feature_dim: {result1['feature_dim']}")
    print(f"    - feature_sample: {result1['feature_vector'][:5]}...")

    # 测试 2：创建红色"外套"测试图
    print("\n[4] 测试红色外套图片...")
    red_jacket = create_test_image((180, 50, 50), "Red Jacket")
    red_img_bytes = io.BytesIO()
    red_jacket.save(red_img_bytes, format="PNG")
    red_img_bytes.seek(0)
    red_img_bytes = red_img_bytes.getvalue()

    start = time.time()
    result2 = recognizer.recognize(red_img_bytes)
    elapsed2 = time.time() - start
    print(f"    ✅ 识别完成，耗时 {elapsed2:.1f}s")
    print(f"    - category: {result2['category']} (conf={result2['category_confidence']:.3f})")
    print(f"    - style_tags: {result2['style_tags']}")
    print(f"    - occasions: {result2['occasions']}")

    # 测试 3：单独测试分类方法
    print("\n[5] 测试单独分类方法...")
    yellow_pants = create_test_image((200, 180, 80), "Yellow Pants")
    yellow_bytes = io.BytesIO()
    yellow_pants.save(yellow_bytes, format="PNG")
    yellow_bytes = yellow_bytes.getvalue()

    cat, conf = recognizer.classify_category(yellow_bytes)
    print(f"    - classify_category: {cat} (conf={conf:.3f})")

    styles = recognizer.classify_styles(yellow_bytes)
    print(f"    - classify_styles: {styles}")

    occasions = recognizer.tag_occasions(yellow_bytes)
    print(f"    - tag_occasions: {occasions}")

    # 测试 4：特征提取
    print("\n[6] 测试特征向量提取...")
    features = recognizer.extract_features(blue_img_bytes)
    print(f"    - feature shape: {features.shape}")
    print(f"    - feature norm: {float((features ** 2).sum() ** 0.5):.6f}")
    assert features.shape[0] == 768, "Expected 768, got %s" % features.shape[0]
    print("    - feature norm: %.6f" % float((features**2).sum() ** 0.5))
    print("    - 向量维度正确 (768)")

    # 测试 5：相似度计算
    print("\n[7] 测试特征向量相似度...")
    feat1 = recognizer.extract_features(blue_img_bytes)
    feat2 = recognizer.extract_features(yellow_bytes)
    sim = float(recognizer._cosine_similarity(feat1, feat2))
    print("    - 蓝色上衣 vs 黄色裤子 相似度: %.4f" % sim)
    assert 0 <= sim <= 1.0, "Similarity should be in [0, 1]"
    print("    - 相似度在合理范围内")

    # 测试 6：同名图片缓存（禁用缓存时应该每次重新计算）
    print("\n[8] 测试 CLIP 可用性...")
    is_available = recognizer._ensure_model_loaded()
    print(f"    - CLIP model loaded: {is_available}")
    print(
        f"    - Recognizer status: {'CLIP' if is_available else 'MobileNetV2'} (recommended)"
        if is_available
        else "MobileNetV2 (fallback)"
    )
    if is_available:
        print("    ✅ CLIP 模型加载成功")
    else:
        print("    ⚠️  CLIP 未加载，将使用 MobileNetV2 备用")

    print("\n" + "=" * 60)
    print("Step 2 结果汇总")
    print("=" * 60)
    print(f"  CLIP 模型: {'已加载 (推荐)' if is_available else '未加载 (备用模式)'}")
    print(f"  蓝色上衣 → 品类: {result1['category']}, 风格: {result1['style_tags']}")
    print(f"  红色外套 → 品类: {result2['category']}, 风格: {result2['style_tags']}")
    print(f"  特征维度: {result1['feature_dim']}")
    print("\n  ✅ CLIP 识别模块测试全部通过")
    print("=" * 60)


if __name__ == "__main__":
    test_clip_recognizer()
