# 服务模块实施检查表

**截止日期**: 2026/04/15 | **状态**: 🟢 已完成 | **版本**: 1.0

## ✅ 阶段 1: 核心模块创建 (已完成)

- [x] `batch_service.py` - 批量处理服务 (117 行)
- [x] `cache_service.py` - 识别结果缓存 (146 行)
- [x] `image_preprocessor.py` - 图像预处理 (132 行)
- [x] `data_augmenter.py` - 数据增强 (118 行)
- [x] `finetuned_inference.py` - 微调推断包装器 (75 行)
- [x] `qwen_client.py` - Qwen LLM 集成 (171 行)

**统计**: 759 行新增代码
**状态**: ✅ 所有模块已创建，预提交检查通过，16/16 钩子 ✓
**提交**: `c43537e` "feat(services): add batch, cache, preprocessing, augmentation, finetuned wrapper, and qwen client"

---

## ✅ 阶段 2: 集成测试 (已完成)

- [x] 所有 43 个单元测试通过
  ```
  ======================== 43 passed, 24 warnings in 1.29s ========================
  ```
- [x] Pre-commit 钩子通过
  - [x] trim-whitespace ✓
  - [x] fix-end-of-file ✓
  - [x] check-yaml ✓
  - [x] check-json ✓
  - [x] check-toml ✓
  - [x] check-large-files ✓
  - [x] check-merge-conflicts ✓
  - [x] debug-statements ✓
  - [x] check-case-conflicts ✓
  - [x] mixed-line-ending ✓
  - [x] detect-secrets ✓
  - [x] black ✓
  - [x] isort ✓
  - [x] flake8 ✓
  - [x] dart-format ✓ (N/A)
  - [x] dart-analyze ✓ (N/A)
- [x] 后端服务器启动成功 (端口 8010)
- [x] Git 提交成功

---

## 🟡 阶段 3: 功能集成 (待部署)

### 3.1 启用缓存服务

**在您的 API 端点中**:
```python
# 例如: backend/app/api/wardrobe_simple.py
from app.services.cache_service import get_cache
from app.services.image_preprocessor import get_preprocessor

@router.post("/upload-garment-optimized")
async def upload_with_cache(file: UploadFile, category: Optional[str] = None):
    """优化的上传端点，带缓存"""
    image_bytes = await file.read()

    # 1. 预处理
    preprocessor = get_preprocessor()
    processed, (w, h), fmt = preprocessor.preprocess(image_bytes)

    # 2. 缓存查询 (命中时非常快)
    cache = get_cache()
    if cached_result := cache.get(processed):
        return {"success": True, "data": cached_result, "_cached": True}

    # 3. 识别
    from app.ml.image_recognizer import ImageRecognizer
    recognizer = ImageRecognizer()
    result = recognizer.recognize(processed)

    # 4. 缓存结果
    cache.set(processed, result)

    return {"success": True, "data": result}
```

**配置** (backend/.env):
```bash
# 默认值已足够，但可自定义:
# CACHE_MAX_SIZE=1000
# CACHE_TTL_SEC=3600
```

**验证**:
```bash
# 首次请求 (无缓存命中): ~150ms
# 第二次请求 (缓存命中): ~1ms
curl -X POST http://localhost:8010/upload-garment-optimized \
  -F "file=@test.jpg" \
  -F "category=T恤"
```

---

### 3.2 启用微调推断服务

**配置** (backend/.env):
```bash
# 如果有微调模型 API 可用，启用此项:
FINETUNED_INFER_ENABLED=true
FINETUNED_INFER_API_BASE_URL=https://your-model-api.com
FINETUNED_INFER_API_PATH=/infer/fashion
FINETUNED_INFER_API_KEY=sk-xxxxx
FINETUNED_INFER_TIMEOUT_MS=3000  # 3 秒超时
```

**在您的代码中使用**:
```python
from app.services.finetuned_inference import get_wrapper

wrapper = get_wrapper()
result = wrapper.infer(image_bytes, prefer_finetuned=True)
# 自动降级到 CLIP if:
#   - FINETUNED_INFER_ENABLED=false
#   - API 超时或不可用
#   - 返回无效响应
```

**验证**:
```python
# 禁用时 (推荐初期)
FINETUNED_INFER_ENABLED=false
# 会降级到 CLIP，和之前行为一致

# 启用时 (有 API)
FINETUNED_INFER_ENABLED=true
# 尝试微调模型 (~80ms)，失败时降级到 CLIP (~250ms)
```

---

### 3.3 启用批量处理服务

**用于衣物导入**:
```python
# backend/app/api/wardrobe_bulk_import.py (新建)
from fastapi import APIRouter, File, UploadFile
from app.services.batch_service import get_batch_processor

router = APIRouter(prefix="/wardrobe", tags=["wardrobe"])

@router.post("/bulk-import")
async def bulk_import(files: List[UploadFile]):
    """导入多张衣服图像，支持并发处理"""

    # 读取所有文件
    image_list = [await f.read() for f in files]

    # 批量处理 (4 个并发线程)
    processor = get_batch_processor(max_workers=4)
    try:
        results = processor.process_batch(
            image_list,
            timeout_sec=30.0  # 总超时时间
        )

        # 处理结果
        success_count = sum(1 for r in results if r is not None)

        return {
            "success": True,
            "data": {
                "total": len(image_list),
                "successful": success_count,
                "failed": len(image_list) - success_count,
                "results": [
                    {"category": r.category, "confidence": r.category_confidence}
                    if r else {"error": "Processing failed"}
                    for r in results
                ]
            }
        }
    finally:
        processor.close()  # 释放线程资源

# 使用示例:
# curl -X POST http://localhost:8010/wardrobe/bulk-import \
#   -F "files=@img1.jpg" \
#   -F "files=@img2.jpg" \
#   -F "files=@img3.jpg"
```

---

### 3.4 启用 Qwen LLM 集成

**配置** (backend/.env):
```bash
# Qwen API 配置
AI_RECOMMENDER_API_BASE_URL=https://api.qwen.com/v1  # 或本地 LLM URL
AI_RECOMMENDER_API_KEY=sk-xxxxx
```

**在推荐端点使用**:
```python
from app.services.qwen_client import get_qwen_client

@router.post("/smart-outfit-recommendation")
async def recommend_outfit(user_message: str):
    """智能服装推荐，基于用户意图"""

    # 分类用户意图
    with get_qwen_client() as client:
        intent = client.classify_intent(user_message)
        # 可能值: "outfit_recommendation", "outfit_search", "style_advice", "other"

    if intent == "outfit_recommendation":
        return search_recommended_outfits(user_message)
    elif intent == "outfit_search":
        return search_similar_items(user_message)
    else:
        return provide_style_advice(user_message)
```

---

## 🟡 阶段 4: 性能验证 (待执行)

### 4.1 基准测试

```bash
# 测试单张图像处理时间
cd backend
time python -c "
from app.ml.image_recognizer import ImageRecognizer
from app.services.cache_service import get_cache
recognizer = ImageRecognizer()
cache = get_cache()
with open('test_image.jpg', 'rb') as f:
    img = f.read()
    result = recognizer.recognize(img)
    print(f'Result: {result.category} ({result.category_confidence:.2f})')
"
# 预期: ~150-200ms

# 缓存命中测试
python -c "
from app.services.cache_service import get_cache
cache = get_cache()
# 第一次: 缓存未命中
# 第二次: 缓存命中 (~1ms)
"
```

### 4.2 并发测试

```bash
# 使用 ab (Apache Bench) 进行负载测试
ab -n 100 -c 10 http://localhost:8010/api/health

# 使用 wrk 进行高并发测试
wrk -t4 -c100 -d30s http://localhost:8010/api/health
```

### 4.3 监控指标

启用日志中的性能追踪:
```python
# backend/app/main.py
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 在关键路径添加计时
@app.post("/predict")
async def predict(file: UploadFile):
    start = time.perf_counter()
    # ... 处理 ...
    elapsed = time.perf_counter() - start
    logger.info(f"predict took {elapsed*1000:.1f}ms")
    return result
```

---

## 🟡 阶段 5: 监控和维护 (待执行)

### 5.1 定期检查

**每周**:
- [ ] 检查缓存命中率 (预期 70-80% 高频场景)
- [ ] 监控内存占用 (缓存应 <500MB)
- [ ] 查看错误日志 (微调 API 失败)

**每月**:
- [ ] 运行性能基准测试
- [ ] 调整缓存大小和 TTL
- [ ] 评估需要优化的新瓶颈

### 5.2 健康检查

```python
# 新增健康检查端点
@app.get("/api/health/services")
async def service_health():
    """检查所有服务的健康状态"""
    cache = get_cache()
    processor = get_batch_processor()

    return {
        "success": True,
        "data": {
            "cache": {
                "enabled": True,
                "size": len(cache.cache),
                "max_size": cache.max_size,
                "hit_rate_pct": "N/A (实现后可追踪)"
            },
            "batch_processor": {
                "enabled": True,
                "max_workers": processor.max_workers
            },
            "finetuned_inference": {
                "enabled": settings.FINETUNED_INFER_ENABLED,
                "api_url": settings.FINETUNED_INFER_API_BASE_URL or "disabled"
            }
        }
    }
```

---

## 📊 关键指标追踪

### 性能基准 (目标值)

| 操作 | 响应时间 | 阈值 |
|------|---------|------|
| 缓存查询 | <2 ms | ✓ |
| 单张图像 (无缓存) | <200 ms | ✓ |
| 批处理 (10 张, 4 线程) | <1000 ms | ✓ |
| API 响应 (P95) | <500 ms | ✓ |
| 吞吐量 | >5 req/s @ 4 CPU | ✓ |

### 资源使用 (目标值)

| 资源 | 目标 | 当前 |
|------|-----|------|
| 缓存内存 | <500 MB | - |
| 线程池线程数 | ≤4 | - |
| CPU 占用 | <70% @ 10 req/s | - |
| 错误率 | <0.5% | - |

---

## 🚀 快速开始指南

### 最小化部署 (5 分钟)

1. **启用缓存** (最高影响，最低成本)
   ```bash
   # 不需要.env 修改，使用默认值
   # 预期改进: 热路径 10x
   ```

2. **验证**
   ```bash
   cd backend
   python -m pytest tests_lite -v
   # 预期: 43/43 通过 ✓
   ```

3. **部署**
   ```bash
   git add -A
   git commit -m "feat(deploy): enable service modules"
   git push
   ```

### 标准部署 (1 小时)

1. 启用缓存 (见上)
2. 在关键端点集成 (参考实施清单)
3. 复制 Qwen 配置示例
4. 运行性能验证
5. 部署到生产

### 完整部署 (2-3 小时)

1. 完成标准部署
2. 迁移现有端点到新服务
3. 设置性能监控
4. 进行负载测试
5. 优化缓存参数

---

## ⚠️ 已知限制

1. **缓存**: 单进程限制
   - 多进程/多服务器需要 Redis
   - 计划: 长期优化

2. **微调推断**: 需要外部 API
   - 可选功能，禁用时自动降级
   - 配置驱动

3. **QWen LLM**: API 依赖
   - 离线使用需要本地 LLM
   - 可配置 API_BASE_URL

---

## 📝 最后检查

在部署到生产前，请确认:

- [ ] 所有单元测试通过 (43/43)
- [ ] Pre-commit 钩子通过 (16/16)
- [ ] 后端服务器启动成功
- [ ] 文档已更新 (SERVICE_MODULES_GUIDE.md)
- [ ] 性能基准已验证
- [ ] Git 提交消息清晰
- [ ] 无未提交的文件

---

**完成日期**: 2026/04/15 ✅
**下一步**: 根据需要部署阶段 3-5 的功能
