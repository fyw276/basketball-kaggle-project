# 智能穿搭助手 - 项目状态文档

**最后更新**: 2026-05-08
**项目版本**: v1.7.0
**状态**: 生产级可用；六模式虚拟试衣 v2（strict/balanced/replace/realistic/professional/hybrid），后端服务已完成高度模块化拆分。

---

## 本次更新（2026-05-08）

- **真实模式优化 (Realistic Mode)**: 移除后处理层的衣物纹理二次叠加机制（Overlay），完全信任 CatVTON inpainting 网络自身合成能力，解决“多层贴纸/鬼影”现象
- **引入 realistic_v2 变体**: API 层新增支持 `realistic_v2` 等模式，允许未来灵活测试新的混合渲染算法
- **模块化重构**: 拆分出了 `human_parsing`、`densepose_service`、`sam_mask`、`person_crop` 等原子级别服务，大幅降低了之前单模块的圈复杂度
- **文档同步**: 新增与更新了 `SERVICE_MODULES_GUIDE.md` 明确声明独立服务的输入输出契约及使用指南

---

## 上次更新（2026-05-01）

- 重写 `README.md`：更新技术栈为 FashionCLIP（非 TensorFlow/MobileNetV2），更新虚拟试衣 v2 为四模式架构（strict/balanced/replace/realistic/professional），新增 tryon_v2 14 个模块说明，新增极限 VRAM 优化与白盒调试文档

---

## 上次更新（2026-04-29）

- CatVTON 后处理尺寸不匹配修复：CatVTON 输出（768×1024）与原始图片尺寸不同时，使用 `quick_enhance()` 替代 `enhance_tryon_result()`
- 新增诊断脚本：`backend/scripts/analyze_debug.py`、`backend/scripts/test_path.py`（CatVTON 路径诊断）
- 极限 VRAM 优化：CATVTON_FORCE_FP16 / VAE slicing / xformers / 一键 LOW_VRAM_MODE，8GB VRAM 可正常运行
- 白盒调试工具：每个请求独立时间戳会话目录，输出 10 个中间产物文件（mask/pose/overlay 等）

---

## 上次更新（2026-04-27）

- CatVTON 集成修复：runner 脚本路径计算错误，子进程工作目录错误
- CatVTON 路径自动检测：自动检测 `D:\models\CatVTON_full` 或 `D:\models\CatVTON`
- 请求日志中间件：`RequestLoggingMiddleware` 显示每个 API 请求
- CatVTON 实时日志：使用线程流式传输子进程输出到终端
- 白盒调试工具：诊断脚本和调试中间产物保存

---

## 项目概览

智能穿搭助手是一个基于 AI 图像识别的智能穿搭决策系统，帮助用户：
- 避免重复购买相似服饰
- 获取个性化搭配推荐
- 评估服饰适合度
- 虚拟试衣（多引擎多模式）

---

## 已完成功能

### 后端服务 (FastAPI + Python)

#### 1. 用户认证模块 (100%)
- 用户注册（用户名、邮箱、密码）
- 用户登录（JWT Token）
- 密码加密（bcrypt）
- Token 验证中间件
- 账号删除（级联删除所有数据）

#### 2. 用户画像模块 (100%)
- 创建用户画像
- 查询用户画像
- 更新用户画像
- 字段验证（身高、体型、肤色、风格偏好、预算范围）
- 权限控制（用户只能访问自己的画像）

#### 3. 图像识别模块 (100%)
- FashionCLIP 零样本分类（`transformers` + `torch`，非 TensorFlow/MobileNetV2）
- 品类识别（top/bottom/skirt/outfit + 中文标签）
- 颜色识别（K-Means 聚类 + 10 种标准色系）
- 风格识别（12 个风格标签，含国风/汉服）
- 特征提取（CLIP 768 维向量，用于相似度计算）
- 完整识别流程（一次调用返回所有信息）

#### 4. 衣橱管理模块 (100%)
- 添加服饰（图片上传 + CLIP 自动识别）
- 查询衣橱（分页、按品类/颜色/风格筛选）
- 删除服饰
- 更新服饰信息
- 简化 API（自动识别并添加，一步完成）
- 静态文件服务（图片访问）

#### 5. 相似度分析模块 (100%)
- CLIP 语义向量余弦相似度计算
- 相似度分级（高/中/低）
- 重复购买预警
- 批量对比优化

#### 6. 搭配推荐模块 (100%)
- 颜色搭配规则（同色系/邻近色/互补色）
- 风格一致性规则
- 品类搭配规则
- 生成多套搭配方案（1-5 套）
- 搭配评分和排序
- 场景搭配历史重排（反馈驱动）

#### 7. 适合度评分模块 (100%)
- 颜色适合度（基于肤色）
- 版型适合度（基于体型和避免强调部位）
- 风格适合度（基于风格偏好）
- 综合评分（加权平均）
- 场合推荐
- 改进建议
- **三维原因说明**：`scene_match_reason` / `body_fit_reason` / `style_coordination_reason`

#### 8. 性别表达指数系统 (100%)
- 性别表达指数滑块（0.0 = 柔粉，1.0 = 深蓝）
- 全局动态主题配色（AppTheme 根据指数变化）
- 性别表达指数存储与同步（API + 本地 SharedPreferences）
- 影响搭配推荐算法（跨性别中性穿搭支持）

#### 9. 虚拟试衣 v2 模块 (100%)

##### 核心管线（`backend/app/services/tryon_v2/`，14 个模块）

| 模块 | 状态 | 说明 |
|------|------|------|
| `pipeline_a.py` | ✅ | 方案 A 主管道：门禁 QC → 贴合 → 后处理 |
| `input_gate.py` | ✅ | 输入门禁：全人体/腿部可见/前姿态/衣服正面评分 |
| `warp_engine.py` | ✅ | Warp 几何引擎：上装/下装/裙装/套装多段贴合，阴影生成 |
| `catvton_engine_client.py` | ✅ | CatVTON 本地引擎客户端（子进程调用） |
| `catvton_client.py` | ✅ | CatVTON HTTP 远程推理客户端 |
| `postprocess.py` | ✅ | 后处理：`quick_enhance()` + `enhance_tryon_result()` |
| `qc.py` | ✅ | 质量评分：身份保真度 / 边缘伪影检测 |
| `preprocess.py` | ✅ | 衣物预处理：自动品类检测 + 标准化 |
| `pose_utils.py` | ✅ | 姿态关键点工具 |
| `realism_engine.py` | ✅ | 真实感引擎 |
| `occlusion_blend.py` | ✅ | 遮挡区域混合 |
| `professional_tryon.py` | ✅ | Professional 模式 6 步流水线 |
| `garment_struct.py` | ✅ | 衣物结构化数据 |

##### API 层（`backend/app/api/tryon_v2.py`）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v2/tryon/garment` | POST | 多模式试衣（strict/balanced/replace/realistic/professional） |
| `/api/v2/tryon/validate-input` | POST | 输入门禁评估（不生成图片） |
| `/api/v2/tryon/preprocess` | POST | 衣物预处理（自动品类检测） |
| `/api/v2/tryon/preprocess-batch` | POST | 批量预处理 |
| `/api/v2/tryon/capabilities` | GET | 能力开关、默认模式、支持品类 |
| `/api/v2/tryon/model-status` | GET | CatVTON 等引擎就绪状态诊断 |

##### 引擎客户端

| 引擎 | 状态 | 配置 |
|------|------|------|
| **CatVTON**（本地子进程） | ✅ | `CATVTON_ENABLED=true`，`CATVTON_PATH`，MediaPipe PoseLandmarker 自动掩码 |
| **百炼（DashScope）** | ✅ | `DASHSCOPE_TRYON_ENABLED=true`，`DASHSCOPE_API_KEY` |
| **Remote VTON** | ✅ | `VTON_INFERENCE_URL`，`VTON_INFERENCE_API_KEY` |
| **Warp 几何引擎** | ✅ | 始终可用，纯 CPU，几何贴合保真 |
| **diffusers SD Inpainting** | ✅ | GPU + `diffusers`（fallback） |

##### 极限 VRAM 优化（8GB 及以下）
- `CATVTON_FORCE_FP16=true` — 节省约 2GB（RTX 4060 Laptop 推荐）
- `CATVTON_ENABLE_VAE_SLICING=true`
- `CATVTON_ENABLE_XFORMERS=true`
- `CATVTON_LOW_VRAM_MODE=true` — 一键开启

##### 白盒调试模式
- `debug_mode=preprocess_only` — 仅运行预处理（极快，验证 mask 质量）
- `debug_mode=full` — 完整管线（含扩散，输出 10 个中间产物）

##### 独立推理服务（`vton_inference_service/`）
- CatVTON 子进程推理（推荐，无需独立 GPU 服务进程）
- HTTP 上游模式（另一进程或 Docker `--gpus all`）
- Stub 演示模式（`VTON_STUB_MODE=true`）

#### 10. 智能穿搭（天气 + 情绪 + AI 推荐）

- `GET /api/v1/smart-outfit/weather` — 经纬度查询城市与天气
- `GET /api/v1/smart-outfit/weather-by-city` — 按城市名查询天气
- `POST /api/v1/smart-outfit/upload-reference` — 上传参考衣物图
- `POST /api/v1/smart-outfit/generate` — 生成多套搭配（含 `ai_recommendation`）
- 天气道路名过滤（详见 [`docs/WEATHER_DISPLAY_AND_HF_ENV.md`](docs/WEATHER_DISPLAY_AND_HF_ENV.md)）

#### 11. 情绪穿搭 (100%)
- 快捷心情选择（`/api/v1/mood/quick-recall`）
- 风格建议 + 配色权重 + 衣橱单品匹配
- 14 种情绪 + 8 种配色方案

#### 12. 套装收藏 (100%)
- 保存和管理用户精选搭配
- 记录穿搭采纳次数

#### 13. 反馈与数据飞轮 (100%)
- `POST /api/v1/feedback/events` — like/dislike/adopt/view 事件收集
- `GET /api/v1/analytics/summary` — 正向反馈率、收藏率
- 场景搭配推荐历史重排

#### 14. 意图路由 + 轻量记忆 RAG (100%)
- `POST /api/v1/agent/intent` — 自然语言 → 建议 MCP 工具名
- `POST/GET/DELETE /api/v1/memory/snippets` — 记忆片段写入/检索

#### 15. 生产就绪能力 (100%)
- `GET /health/ready` — 数据库探活就绪探针
- 可选滑动窗口限流（`ENABLE_RATE_LIMIT`）
- JWT 弱密钥 CRITICAL 日志提示
- 依赖可观测性：`GET /api/v1/analytics/dependency-observability`

#### 16. CLI 工具 (100%)
- `cli/outfit_cli.py`：认证/衣橱/分析/天气/智能穿搭/情绪/试衣/收藏

#### 17. MCP 服务 (100%)
- `mcp/server.py`：FastMCP 工具桥接后端 API

---

## 前端应用 (Flutter Web)

### 已实现功能
- 用户认证（注册/登录/JWT/自动路由跳转）
- 用户画像（完整表单 + 验证 + 自动加载）
- **衣橱页** 左右分栏（固定分类边栏 + 虚拟滚动网格，每行 4 张 1:1 正方形）
- **批量上传**（`pickMultiImage`，一次选多张，逐张上传，实时进度条）
- 相似度分析 / 搭配推荐 / 适合度评分 / 情绪穿搭 — 统一设计模式
- 性别表达指数滑块（全局大圆角样式）
- 智能穿搭（天气自动查询 + 手动输入 + 多套生成）
- 虚拟试衣（多视角人物照 + 服饰上传 + 全屏预览）
- Flutter Web 完全兼容

---

## 测试状态

### 后端测试
- `backend/tests/` 全量 pytest 套件（成功响应经 `ApiEnvelopeMiddleware` 统一为 `{success,data}`）
- `tests_lite` 轻量套件供 pre-push（35 例量级）
- pytest 可用 tempfile 解决 Windows 文件锁问题

### Flutter 测试
- `flutter test`（pre-push hook）

---

## 技术栈

### 后端
- **框架**: FastAPI 0.115+（支持 Python 3.14）
- **数据库**: PostgreSQL（开发环境 SQLite）
- **缓存**: Redis（可选）
- **AI 模型**: FashionCLIP 零样本分类（`transformers` + `torch`）
- **虚拟试衣**: CatVTON / 百炼 / Warp / diffusers SD Inpainting
- **认证**: JWT（PyJWT）
- **图像处理**: Pillow, OpenCV, scikit-learn
- **测试**: pytest, pytest-asyncio, Hypothesis

### 前端
- **框架**: Flutter 3.x（iOS / Android / Web）
- **状态管理**: Provider
- **路由**: GoRouter
- **HTTP**: `package:http`（自定义 ApiClient）

---

## 已修复问题

1. CatVTON 后处理尺寸不匹配（768×1024 输出与原始图片混合错误）→ `quick_enhance()` 快速路径
2. CatVTON 路径计算错误（runner 子进程工作目录）
3. 预训练模型准确度有限（FashionCLIP 零样本，非 MobileNetV2）
4. Flutter Web TextPainter 渲染断言 → 移除 TextScaler 覆盖
5. 适合度分析场景缺失显示 → 三阶段回退链
6. pre-commit mixed-line-ending / black / isort 格式冲突
7. pytest Windows 文件锁问题（改用 `tempfile.mkstemp`）
8. 性能测试零时间比较 bug（`max(times[1], 0.001)`）

---

## 已知限制

- FashionCLIP 零样本分类（非专用服装模型），准确度有限；可通过手动编辑或换用专用模型改善
- CatVTON realistic 模式依赖 NVIDIA GPU（8GB VRAM 可用，RTX 4060 Laptop 推荐开启 FP16）

---

## 项目结构

```
clothing-assistant/
├── backend/
│   ├── app/
│   │   ├── api/                   # 20 个路由（含 tryon_v2）
│   │   ├── core/                  # 配置、错误处理、日志、HuggingFace 环境
│   │   ├── db/                    # 数据库会话
│   │   ├── ml/                    # 模型加载
│   │   ├── models/                # ORM 模型
│   │   ├── observability/          # 指标收集
│   │   ├── schemas/               # Pydantic schemas
│   │   └── services/              # 50 个服务模块
│   │       └── tryon_v2/          # 14 个 v2 管线模块
│   ├── scripts/                    # 诊断与测试脚本
│   ├── tests/                     # pytest 套件
│   └── uploads/                   # 上传图片
├── mobile/                         # Flutter 前端
│   └── lib/
│       ├── core/                  # API 客户端、主题、性别表达系统
│       └── features/              # auth / home / profile / wardrobe / analysis
├── vton_inference_service/         # 独立最小 HTTP 推理服务
├── cli/                           # outfit_cli.py
├── mcp/                           # server.py（FastMCP）
├── docs/                          # 40+ 篇技术文档
├── deploy/ecs/                    # ECS 部署脚本
└── .kiro/specs/                  # 需求与设计规格
```

---

## 快速开始

### 后端
```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
# http://127.0.0.1:8010/docs
```

### 前端
```bash
cd mobile
flutter run -d chrome
```

### CatVTON（如需 realistic 模式）
在 `backend/.env` 中配置 `CATVTON_ENABLED=true`、`CATVTON_PATH=D:\models\CatVTON_full` 等。

---

**创建日期**: 2026-03-26
**最后更新**: 2026-05-01
**项目负责人**: 智能科学与技术2班 202452320220
**项目类型**: 毕业设计/课题研究
