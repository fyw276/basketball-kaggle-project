# 服务模块架构与实现指南

**最后更新**: 2026/05/07 | **版本**: 1.1

## 目录

1. [架构概览](#架构概览)
2. [核心服务模块](#核心服务模块)
3. [集成指南](#集成指南)
4. [性能考量](#性能考量)
5. [最佳实践](#最佳实践)

## 架构概览

clothing-assistant 后端采用**分层服务架构**，将复杂的图像识别和推荐逻辑拆分为独立的功能模块。所有服务都遵循 **单一职责原则** 和 **依赖注入模式**。

### 服务层次结构

```
FastAPI Application (main.py)
├── API Routes (api/)
├── Service Layer (services/)
│   ├── 图像处理服务
│   │   ├── image_preprocessor.py (图像规范化)
│   │   ├── data_augmenter.py (数据增强)
│   │   └── batch_service.py (批量处理)
│   ├── 识别与推断服务
│   │   ├── finetuned_infer_client.py (微调模型)
│   │   ├── finetuned_inference.py (智能推断)
│   │   └── similarity_category.py (相似度匹配)
│   ├── 缓存与优化服务
│   │   └── cache_service.py (识别结果缓存)
│   ├── 外源服务集成
│   │   └── qwen_client.py (LLM 意图分类)
│   ├── 虚拟试衣 v2 服务 (tryon_v2/)
│   │   ├── pipeline_a.py         (方案 A 主管道)
│   │   ├── input_gate.py        (输入门禁 QC)
│   │   ├── warp_engine.py       (几何贴合引擎)
│   │   ├── qc.py               (质量评分)
│   │   ├── postprocess.py      (后处理增强)
│   │   ├── preprocess.py       (衣物预处理)
│   │   ├── pose_utils.py      (姿态关键点)
│   │   ├── garment_struct.py   (衣物结构化)
│   │   ├── catvton_engine_client.py (CatVTON 客户端)
│   │   ├── occlusion_blend.py  (遮挡混合)
│   │   ├── realism_engine.py   (真实感引擎)
│   │   └── professional_tryon.py (专业模式)
│   └── 其他服务 (auth, storage, etc.)
└── Database & Models
```

## 核心服务模块

### 1. 图像预处理服务 (`image_preprocessor.py`)

**职责**: 将用户上传的图像标准化，确保一致的输入质量。

```python
from app.services.image_preprocessor import get_preprocessor

preprocessor = get_preprocessor(max_width=1024, max_height=1024, quality=85)
processed_bytes, (width, height), format_used = preprocessor.preprocess(image_bytes)
```

**关键功能**:
- ✅ 自适应调整大小（保持宽高比）
- ✅ 格式转换 (RGBA → JPEG)
- ✅ 压缩优化 (质量/大小平衡)
- ✅ 色空间规范化

**性能指标**:
- 平均处理时间: 50-150ms (取决于原始大小)
- 压缩率: 原始→85% JPEG 通常可节省 60-75% 空间

### 2. 数据增强服务 (`data_augmenter.py`)

**职责**: 为训练生成图像变体，增加训练数据多样性。

```python
from app.services.data_augmenter import get_augmenter

augmenter = get_augmenter()
variants = augmenter.augment(image_bytes, num_variants=3, seed=42)
# 返回 [原始, 变体1, 变体2, 变体3]
```

**支持的变换**:
- 旋转 (-15° ~ +15°)
- 亮度调整 (0.8x ~ 1.2x)
- 对比度调整 (0.8x ~ 1.2x)
- 随机裁剪 (10-20%)

**使用场景**:
- 训练专业模型时扩展数据集
- 在线数据增强提高泛化能力

### 3. 批量处理服务 (`batch_service.py`)

**职责**: 使用 ThreadPoolExecutor 并发处理多张图像。

```python
from app.services.batch_service import get_batch_processor

processor = get_batch_processor(max_workers=4)
results = processor.process_batch(
    image_bytes_list=[img1, img2, img3],
    timeout_sec=30.0
)
processor.close()  # 清理资源
```

**功能**:
- ✅ 并发处理（最多 4 个 workers）
- ✅ 单张图像超时隔离
- ✅ 部分失败容错 (返回 None)
- ✅ 最大批大小限制 (100 张)

**性能提升**:
- 单线程: 10 张图像 = ~1.5 秒
- 4 线程: 10 张图像 = ~500ms (3 倍加速)

### 4. 识别缓存服务 (`cache_service.py`)

**职责**: LRU 缓存识别结果，避免重复处理相同图像。

```python
from app.services.cache_service import get_cache

cache = get_cache(max_size=1000, ttl_sec=3600)

# 查询缓存
cached = cache.get(image_bytes)
if not cached:
    result = recognizer.recognize(image_bytes)
    cache.set(image_bytes, result)
```

**缓存策略**:
- **键**: SHA256(image_bytes)
- **数据结构**: {hash → (RecognitionResult, 过期时间)}
- **容量**: 可配置 (默认 1000 条)
- **TTL**: 1 小时 (可配置)
- **淘汰**: LRU (最近最少使用)

**性能影响**:
- 缓存命中: ~1ms
- 缓存未命中: 走完整识别流程

### 5. 微调推断服务 (`finetuned_infer_client.py`)

**职责**: 调用外部微调模型 API，优雅降级到基础 CLIP 模型。

```python
from app.services.finetuned_infer_client import try_finetuned_infer

result = try_finetuned_infer(
    image_bytes,
    feature="wardrobe_upload"
)
# 返回 dict 或 None (若禁用或出错)
```

**智能降级**:
1. 检查 `FINETUNED_INFER_ENABLED` 标志
2. 尝试调用外部 API (5 秒超时)
3. 解析响应并归一化到标准格式
4. 失败时返回 None (不抛异常)

**必需配置**:
```python
# backend/app/core/config.py
FINETUNED_INFER_ENABLED=true
FINETUNED_INFER_API_BASE_URL=https://your-api.com
FINETUNED_INFER_API_PATH=/infer/fashion
FINETUNED_INFER_API_KEY=sk-xxxxx
FINETUNED_INFER_TIMEOUT_MS=5000
```

### 6. 推断包装器 (`finetuned_inference.py`)

**职责**: 统一接口，自动选择最优推断方案。

```python
from app.services.finetuned_inference import get_wrapper

wrapper = get_wrapper()
result = wrapper.infer(
    image_bytes,
    prefer_finetuned=True  # 优先尝试微调模型
)
```

**策略**:
1. 如果 `prefer_finetuned=True` 且 API 可用 → 使用微调模型
2. 微调模型失败或禁用 → 自动降级到 CLIP
3. 返回 `RecognitionResult` (始终成功)

### 7. 相似度分类服务 (`similarity_category.py`)

**职责**: 类别感知的相似度匹配和分组决策。

```python
from app.services.similarity_category import (
    normalize_similarity_category,
    is_similarity_category_compatible,
    detect_similarity_category
)

# 规范化类别到组别
group = normalize_similarity_category("T恤")  # → "上衣"

# 检查兼容性
can_match = is_similarity_category_compatible("上衣", "下装")  # → False

# 做出相似度决策
decision = detect_similarity_category(
    image_bytes,
    clip_category="衬衫",
    clip_confidence=0.92
)
# → SimilarityDecision(group="上衣", confidence=0.92)
```

**类别映射**:
- `上衣` → [T 恤, 衬衫, 毛衣, 卫衣, ...]
- `下装` → [牛仔裤, 运动裤, 短裤, ...]
- `外套` → [夹克, 风衣, 羽绒服, ...]
- `连衣裙` → [日常裙, 优雅裙, 运动裙, ...]
- `其他` → (未分类或新类别)

### 8. Qwen LLM 客户端 (`qwen_client.py`)

**职责**: 集成 Qwen LLM，用于意图分类和描述生成。

```python
from app.services.qwen_client import get_qwen_client

with get_qwen_client() as client:
    # 分类用户意图
    intent = client.classify_intent("我想找一件蓝色的衬衫")
    # → "outfit_search" | "outfit_recommendation" | "style_advice" | "other"

    # 生成服装描述
    description = client.generate_description({
        "category": "衬衫",
        "colors": ["蓝色", "白色"],
        "style_tags": ["商务", "简洁"],
        "occasion": "工作"
    })
    # → "一件优雅的蓝白相间衬衫，完美适配商务场景。"
```

**必需配置**:
```python
AI_RECOMMENDER_API_BASE_URL=https://api.qwen.com/v1
AI_RECOMMENDER_API_KEY=sk-xxxxx
```

### 9. 虚拟试衣 v2 服务 (`tryon_v2/`)

`backend/app/services/tryon_v2/` 是虚拟试衣 v2 的核心引擎包，提供七种试衣模式（strict/balanced/replace/realistic/realistic_v2/professional/hybrid）。

#### 9.1 `pipeline_a.py` — 方案 A 主管道

```python
from app.services.tryon_v2 import run_pipeline_a

result = run_pipeline_a(
    person_image=person_img,
    garment_image=garment_img,
    garment_category="top",
    strict_identity=True,
)
# result: {"status": "success"|"error", "result_image": PIL.Image, ...}
```

方案 A（strict/balanced 模式）：几何贴合 + QC 门禁，平衡速度与质量。
路由到 `warp_engine.py` 的 `tryon_top_warp` / `tryon_skirt_warp` / `tryon_pants_warp`。

#### 9.2 `input_gate.py` — 输入门禁评估

```python
from app.services.tryon_v2.input_gate import evaluate_input_gate

gate = evaluate_input_gate(
    person_image=person_img,
    garment_image=garment_img,
    garment_category="top",
    strict=True,
    thresholds={"full_body": 0.55, "leg_visibility": 0.45, ...},
)
# gate.passed: bool, gate.scores: dict, gate.error_code: str
```

评估全身可见度 / 腿部可见度 / 正面姿态 / 商品正面度，分数低于阈值则拒绝试衣请求。

#### 9.3 `warp_engine.py` — 几何贴合引擎

```python
from app.services.tryon_v2.warp_engine import (
    tryon_top_warp,           # 上装贴合（带 LAB 亮度转移 + 褶皱 + 边缘暗化）
    tryon_top_warp_preserve,  # 上装贴合（无 realism pass，纯像素保真）
    tryon_skirt_warp,         # 裙装贴合
    tryon_pants_warp,         # 下装贴合（双阶段膝关节感知变形）
    tryon_hybrid_warp_catvton, # Warp + CatVTON 两阶段混合
    overlay_draping_from_ai,   # AI 光影叠加（衣服像素 100% 保留）
    overlay_top_onto_ai_result, # CatVTON 结果注入原始衣服像素
)
```

关键特性：
- MediaPipe 关键点优先路径（肩膀/臀部/膝盖/踝关节）
- 梯度能量 fallback（无 MediaPipe 时）
- 双阶段膝关节感知下装变形（保持裤腿图案对称）
- 透视梯形变形（肩宽 → 腰宽，模拟 3D 贴合感）
- LAB 亮度转移 + 折痕线 + 边缘暗化（solid-color 衣服）
- 图案强度检测（`_detect_pattern_strength`）：格子/条纹衣服跳过亮度转移

#### 9.4 `qc.py` — 质量评分

```python
from app.services.tryon_v2.qc import evaluate_qc

qc = evaluate_qc(person, result, threshold=0.6)
# qc.passed: bool
# qc.scores: {identity_preserve_score, boundary_artifact_score, occlusion_validity_score, qc_aggregate_score}
```

通过 SSIM 类指标检测身份保真度 / 边缘伪影 / 遮挡有效性。

#### 9.5 `preprocess.py` — 衣物预处理

```python
from app.services.tryon_v2.preprocess import preprocess_garment_image

r = preprocess_garment_image(garment_img)
# r.image: PIL.Image (白底标准化图)
# r.tryon_category: "top"|"bottom"|"skirt"|"unknown"
# r.confidence: float
```

自动去背景（rembg） + 白底合成 + 自动品类识别 + 围巾/accessory 形状检测。

#### 9.6 `postprocess.py` — 后处理增强

```python
from app.services.tryon_v2.postprocess import enhance_tryon_result, quick_enhance

enhanced = enhance_tryon_result(result, person, original_garment, strength="medium")
```

`quick_enhance` 用于 CatVTON 输出（尺寸可能与输入不同）；`enhance_tryon_result` 用于 warp 输出。

#### 9.7 `catvton_engine_client.py` — CatVTON 本地引擎客户端

```python
from app.services.tryon_v2.catvton_engine_client import call_local_catvton

upstream = await call_local_catvton(
    garment_bytes=garment_jpg,
    person_bytes=person_jpg,
    garment_category="upper",
    debug_dir=debug_session_dir,
    preprocess_only=False,
)
```

通过子进程调用 `vton_inference_service/catvton_runner.py`，支持白盒调试（`--debug-dir`）和预处理模式（`--preprocess-only`）。

#### 9.8 `garment_struct.py` — 衣物结构化数据

```python
from app.services.tryon_v2.garment_struct import cutout_garment_rgba

cutout = cutout_garment_rgba(garment_img)
# cutout.cropped: PIL.Image (去背景 RGBA)
```

使用 rembg 或 MobileSAM 进行精准去背景。

#### 9.9 `pose_utils.py` — 姿态关键点工具

```python
from app.services.tryon_v2.pose_utils import detect_pose_keypoints, get_body_bounds_from_keypoints

kpts = detect_pose_keypoints(person_img)
# kpts: {"left_shoulder": (x_norm, y_norm), ...} 或 None

bounds = get_body_bounds_from_keypoints(kpts, w, h, "top")
# bounds: {"valid": bool, "x0", "x1", "neck_y", "waist_y", ...}
```

使用 MediaPipe PoseLandmarker，fallback 到 rembg 衣服分割 + 关键点映射。

#### 9.10 `occlusion_blend.py` — 遮挡区域混合

```python
from app.services.tryon_v2.occlusion_blend import build_change_mask, occlusion_validity_score

mask = build_change_mask(person, result)
score = occlusion_validity_score(person, result)
```

用于 QC 模块：检测试穿后图像的变化区域，评估遮挡合理性。

#### 9.11 七种试衣模式总结

| 模式 | 引擎 | 特点 | 适用场景 |
|------|------|------|---------|
| `strict` | Warp + QC | 几何贴合 + 门禁，身份保护 | 日常快速预览 |
| `balanced` | Warp + QC | 宽松 QC | 快速预览 |
| `replace` | AI 生成（warp → bailian → remote → catvton → diffusion；warp 先运行保衣服像素，`TRYON_V2_REPLACE_SKIP_WARP=true` 可跳过；默认 `warp,bailian,remote`） | 像素级衣服保真 + AI 真实感 | 需要真实感时 |
| `realistic` | CatVTON | 深度学习，真实褶皱光照，颜色保真增强 | 商品展示 |
| `realistic_v2` | CatVTON v2 | 饱和度感知颜色保真 + 面部/手部保护 | 高保真应用 |
| `professional` | CatVTON + 后处理 | CatVTON + 质量评分，图案保护注入 (alpha=0.92) | 专业应用 |
| `hybrid` | Warp + CatVTON + overlay_draping | 饱和度感知 drape_alpha，warp 保颜色 CatVTON 提供真实感 | 彩色高饱和度衣物 |

## 集成指南

### 在 API 端点中使用服务

```python
from fastapi import APIRouter, UploadFile
from app.services.image_preprocessor import get_preprocessor
from app.services.cache_service import get_cache
from app.services.finetuned_inference import get_wrapper
from app.ml.color_extractor import ColorExtractor

router = APIRouter()

@router.post("/predict")
async def predict(file: UploadFile):
    """示例: 集成所有服务的预测端点"""

    # 1. 读取并预处理图像
    image_bytes = await file.read()
    preprocessor = get_preprocessor()
    processed, (w, h), fmt = preprocessor.preprocess(image_bytes)

    # 2. 检查缓存
    cache = get_cache()
    cached_result = cache.get(processed)
    if cached_result:
        return {"success": True, "data": cached_result}

    # 3. 运行推断 (微调 → 降级到 CLIP)
    wrapper = get_wrapper()
    recognition_result = wrapper.infer(processed, prefer_finetuned=True)

    # 4. 提取颜色
    color_extractor = ColorExtractor()
    colors = color_extractor.extract(processed, top_n=3)

    # 5. 缓存结果
    cache.set(processed, recognition_result)

    return {
        "success": True,
        "data": {
            "category": recognition_result.category,
            "confidence": recognition_result.category_confidence,
            "colors": colors,
            "style_tags": recognition_result.style_tags,
            "image_size": {"width": w, "height": h}
        }
    }
```

### 批量处理示例

```python
from app.services.batch_service import get_batch_processor
from app.services.cache_service import get_cache

@router.post("/batch-upload")
async def batch_upload(files: List[UploadFile]):
    """上传多张衣物图像"""

    image_list = [await f.read() for f in files]

    # 进行批量处理
    processor = get_batch_processor(max_workers=4)
    results = processor.process_batch(image_list, timeout_sec=30.0)

    # 缓存所有结果
    cache = get_cache()
    processed_data = []
    for img, result in zip(image_list, results):
        if result:
            cache.set(img, result)
            processed_data.append({
                "category": result.category,
                "confidence": result.category_confidence
            })
        else:
            processed_data.append({"error": "Processing failed"})

    processor.close()
    return {"success": True, "data": processed_data}
```

## 性能考量

### 缓存命中率优化

**问题**: 相同的衣物图像可能多次上传（如用户编辑后重新提交）。

**解决方案**:
```python
# 在 wardrobe_simple.py 中
cache = get_cache()

# 预处理 + 缓存查询
preprocessor = get_preprocessor()
processed_bytes, _, _ = preprocessor.preprocess(image_bytes)

cached = cache.get(processed_bytes)
if cached:
    return {
        "success": True,
        "data": cached,
        "_cache_hit": True  # 记录缓存命中
    }
```

**预期效果**:
- 频繁上传场景: 70-80% 缓存命中率
- 缓存节省时间: 每张 100-200ms

### 并发处理优化

**场景**: 用户导入大量衣物库。

```python
# 配置并发度 (取决于 CPU 核心数)
processor = get_batch_processor(max_workers=4)  # 推荐 4-8

# 分批处理超大列表
from itertools import islice

def batch_iter(iterable, batch_size):
    it = iter(iterable)
    while True:
        batch = list(islice(it, batch_size))
        if not batch:
            break
        yield batch

all_results = []
for batch in batch_iter(image_list, batch_size=20):
    results = processor.process_batch(batch)
    all_results.extend(results)
```

### 内存管理

**关键点**:
1. **缓存大小限制**: `max_size=1000` 对应 ~1GB 内存 (取决于图像大小)
2. **TTL 过期**: 1 小时后自动清理
3. **线程池清理**: 明确调用 `processor.close()`

```python
# 定期清理旧缓存
from datetime import datetime, timedelta
import time

cache = get_cache()
# TTL 在 set() 时自动处理
# get() 会检查过期并自动删除条目
```

## 最佳实践

### 1. 错误处理

```python
from app.services.finetuned_infer_client import try_finetuned_infer

# ✅ 正确: 返回 None 而非抛异常
result = try_finetuned_infer(image_bytes)
if result:
    use_finetuned(result)
else:
    use_base_model()

# ❌ 错误: 不应在服务内抛异常
# 留给调用者选择如何处理
```

### 2. 资源生命周期

```python
# ✅ ThreadPool 使用
processor = get_batch_processor()
try:
    results = processor.process_batch(images)
finally:
    processor.close()  # 总是清理

# ✅ Qwen 客户端使用
with get_qwen_client() as client:
    intent = client.classify_intent(text)
# httpx.Client 自动关闭
```

### 3. 单元测试

```python
def test_image_preprocessor():
    from app.services.image_preprocessor import ImagePreprocessor

    preprocessor = ImagePreprocessor(max_width=512, max_height=512)
    processed, size, fmt = preprocessor.preprocess(dummy_image_bytes)

    assert size[0] <= 512
    assert size[1] <= 512
    assert len(processed) < len(dummy_image_bytes)

def test_cache_ttl():
    from app.services.cache_service import RecognitionCache
    import time

    cache = RecognitionCache(ttl_sec=1)
    cache.set(b"img", mock_result)

    assert cache.get(b"img") is not None
    time.sleep(1.1)
    assert cache.get(b"img") is None  # TTL 过期
```

### 4. 配置管理

所有服务都从 `app.core.config.Settings` 读取配置：

```python
# backend/.env
FINETUNED_INFER_ENABLED=true
FINETUNED_INFER_API_BASE_URL=https://...
AI_RECOMMENDER_API_BASE_URL=https://...
```

### 5. 监控和日志

```python
import logging

logger = logging.getLogger(__name__)

# 在服务中记录关键事件
logger.debug(f"Preprocessed image: {len(image_bytes)} → {len(processed_bytes)} bytes")
logger.warning(f"Fine-tuned API unavailable, falling back to CLIP")
logger.error(f"Batch processing failed: {e}")
```

## 总结

这个服务层架构提供了：

| 特性 | 益处 |
|------|------|
| **模块化** | 独立开发、测试、维护每个服务 |
| **可复用性** | 跨多个 API 端点使用相同服务 |
| **容错性** | 智能降级（微调 → 基础模型） |
| **性能** | 缓存 + 批处理 + 并发 |
| **可扩展性** | 易于添加新服务或升级现有服务 |

---

**相关文档**:
- [API 合约](API_CONTRACT_v1.0.md)
- [后端就绪](BACKEND_READY.md)
- [配置指南](../backend/README.md)
- [VTON 集成](VTON_INTEGRATION.md)
- [CatVTON 后处理修复](CATVTON_POSTPROCESS_FIX_2026-04-29.md)
- [VTON 交付说明](VTON_DELIVERY_2026-04.md)
