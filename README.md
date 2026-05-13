# 智能穿搭助手 (Smart Outfit Assistant)

**最后更新**: 2026-05-13
**状态**: 生产级可用（FastAPI 后端 + Flutter Web/移动端 + CLI + MCP Agent 工具面）

## 项目简介

智能穿搭助手是一个多端协同的智能穿搭决策系统，通过图像理解（CLIP/FashionCLIP）与多维度推荐算法，为用户提供：

- 相似度分析与重复预警：找出相似单品，避免重复购买
- 智能搭配推荐：基于衣橱与画像生成场景穿搭方案
- 适合度评分：颜色 / 风格 / 体型友好度建议（含三维原因说明）
- 情绪穿搭：根据心情给出配色与风格方向，并匹配衣橱单品
- 虚拟试衣 v2：多引擎多模式虚拟试穿（CatVTON 深度学习 / 百炼 / Warp 几何粘贴 / Stable Diffusion），支持白盒调试与极限低显存优化
- 首页天气与今日推荐卡：展示城市/天气/温度、AI 评分/风格/理由
- 性别表达指数系统：动态全局配色（柔粉 ↔ 深蓝）

## 核心功能

### 1. 重复购买预警
- 优先使用 CLIP/FashionCLIP 提取服饰特征向量（`transformers` + `torch`），弱网/离线可回退轻量方案
- 基于余弦相似度计算与衣橱中服饰的相似度
- 高/中/低三级相似度分级，自动标记重复购买风险

### 2. 搭配推荐
- 基于品类搭配规则生成搭配方案（颜色和谐 + 风格一致）
- 支持场景指定（正式/休闲/约会/运动）
- 支持 **多张服饰图** 同次请求（最多 5 张）：服务端合并特征与标签后以第一张为主图预览
- 考虑用户性别表达指数，智能推荐中性风或跨性别穿搭

### 3. 适合度评分
- 颜色适合度：基于肤色与服饰颜色的匹配度
- 版型适合度：基于体型和不希望强化的身体部位
- 风格适合度：基于用户风格偏好
- 综合评分并提供个性化改进建议
- 返回三维原因说明：`scene_match_reason` / `body_fit_reason` / `style_coordination_reason`

### 4. 情绪穿搭（Mood → Outfit）
- 快捷心情选择（例如「心情不好 · 想暖一点」）
- 后端输出：风格建议、适用场景、配色倾向（权重）、衣橱单品匹配列表

### 5. 虚拟试衣 v2（多引擎多模式）

#### 七种试衣模式

| 模式 | 说明 | 推荐场景 |
|------|------|---------|
| `strict`（默认） | 方案 A 几何贴合 + QC 门禁，平衡速度与质量 | 日常使用 |
| `balanced` | 宽松 QC，更易通过验证 | 快速预览 |
| `replace` | AI 生成式合成，引擎优先级：warp → bailian → remote → catvton → diffusion（warp 先运行提供 100% 衣服像素保真；`TRYON_V2_REPLACE_SKIP_WARP=true` 可跳过 warp；可通过 `TRYON_V2_REPLACE_ENGINE_PRIORITY` 配置，默认 `warp,bailian,remote,catvton,diffusion`） | 需要真实感时 |
| `realistic` | CatVTON 深度学习 + 颜色保真增强，100% 保留商品细节 | 商品展示 |
| `realistic_v2` | CatVTON v2 增强版 + 饱和度感知颜色保真 + 面部/手部保护 | 高保真应用 |
| `professional` | CatVTON + 后处理 + 质量评分 | 专业应用 |
| `hybrid` | Warp 保真 + CatVTON 真实感，智能饱和度感知 alpha 调节 | 彩色高饱和度衣物 |

#### 引擎架构（`backend/app/services/tryon_v2/`）

| 模块 | 说明 |
|------|------|
| `pipeline_a.py` | 方案 A 主管道：输入门禁 QC → 几何贴合 → 后处理增强 |
| `input_gate.py` | 输入门禁：全人体评分 / 腿部可见度 / 前姿态评分 / 衣服正面评分 |
| `warp_engine.py` | Warp 几何引擎：上装 / 下装 / 裙装 / 套装多段贴合，含阴影生成 |
| `catvton_engine_client.py` | CatVTON 本地引擎客户端（子进程调用） |
| `catvton_client.py` | CatVTON HTTP 远程推理客户端 |
| `postprocess.py` | 后处理增强：`quick_enhance()` + 完整 `enhance_tryon_result()` |
| `qc.py` | 质量评分：身份保真度 / 边缘伪影检测 |
| `preprocess.py` | 衣物预处理：自动品类检测（top/bottom/skirt/outfit）+ 标准化 |
| `pose_utils.py` | 姿态关键点工具 |
| `realism_engine.py` | 真实感引擎 |
| `occlusion_blend.py` | 遮挡区域混合 |
| `professional_tryon.py` | Professional 模式管道（6 步流水线） |
| `garment_struct.py` | 衣物结构化数据 |

#### 极限 VRAM 优化（8GB 及以下显存）

全部开启可在 8GB VRAM 正常运行：

```env
CATVTON_FORCE_FP16=true
CATVTON_ENABLE_VAE_SLICING=true
CATVTON_ENABLE_XFORMERS=true
CATVTON_LOW_VRAM_MODE=true
```

RTX 4060 Laptop 推荐开启 `CATVTON_FORCE_FP16=true` 节省约 2GB。

#### 白盒调试模式

```bash
# 仅运行预处理（极快，验证 mask 质量）
debug_mode=preprocess_only

# 完整运行（含扩散，耗时最长）
debug_mode=full
# 输出目录：CATVTON_DEBUG_DIR 中每个请求一个独立时间戳会话目录
# 中间产物：01_input_person.jpg, 02_input_garment.jpg, 03_mask.png, 04_pose_keypoints.jpg, 05_mask_overlay.png ...
```

### 6. AI 穿搭风格分（`POST /predict`）

- **sklearn** 风格分 + Top3 推荐与中文解释；与 Flutter / Vite 共用同一契约
- 独立服务默认端口 **8765**；主应用 `app.main` 亦提供 `POST /predict`（无 `/api/v1` 前缀）

### 7. 智能穿搭（Flutter Web 行为、CORS、认证顺序、响应式）

详见 [`docs/SMART_OUTFIT_FLUTTER_WEB.md`](docs/SMART_OUTFIT_FLUTTER_WEB.md)。

## 技术架构

### 后端服务
- **框架**: FastAPI（推荐 Python 3.12+，支持 3.14）
- **数据库**: PostgreSQL + Redis
- **AI**:
  - CLIP/FashionCLIP（`transformers` + `torch`）用于零样本品类/风格/场景识别与相似检索
  - 虚拟试衣：**CatVTON**（本地子进程深度学习）/ **百炼（DashScope）** / **Warp 几何引擎** / **diffusers** SD Inpainting（fallback）
- **独立推理服务**: `vton_inference_service/` 最小 HTTP 服务，支持 CatVTON 子进程 / HTTP 上游 / Stub 三种模式

### 移动端 (Flutter)
- **框架**: Flutter 3.x + Dart（iOS / Android / Web）
- **状态管理**: Provider
- **HTTP 客户端**: `package:http`（自定义 `ApiClient`）

### 设计系统
- **Material Design 3** 全局统一主题
- **性别表达指数** 动态配色（0.0 柔粉 ↔ 1.0 深蓝）
- **大圆角** 统一样式（BorderRadius 统一为 22px）

### CLI 工具
- **实现**: Python **argparse** + **httpx**，默认 **JSON** 输出
- **入口**: `cli/outfit_cli.py`（`python cli/outfit_cli.py --help`）
- **能力**: 注册/登录、衣橱、相似度/场景搭配/适合度、按城市天气、智能穿搭上传+生成、情绪列表/推荐、虚拟试衣、套装收藏列表

### MCP 服务
- **实现**: **FastMCP**（`mcp` PyPI），工具通过 HTTP 转发后端 `/api/v1`
- **入口**: `mcp/server.py`
- **环境变量**: `OUTFIT_API_BASE_URL`（默认 `http://127.0.0.1:8010/api/v1`）、`OUTFIT_API_TOKEN`

## 项目结构

```
clothing-assistant/
├── backend/
│   ├── app/
│   │   ├── api/                   # 20 个路由模块（含 tryon_v2）
│   │   ├── core/                  # 配置、错误处理、日志、超参
│   │   ├── db/                    # 数据库会话 + SQLite schema patches
│   │   ├── ml/                    # 模型加载（CLIP）
│   │   ├── models/                # ORM 模型（含 FeedbackEvent、MemorySnippet 等）
│   │   ├── observability/          # 指标收集（tryon_v2_metrics, dependency_metrics）
│   │   ├── schemas/               # Pydantic schemas
│   │   └── services/              # 50 个服务模块
│   │       └── tryon_v2/           # 14 个 v2 管线模块（pipeline_a / warp_engine 等）
│   ├── scripts/                    # 诊断与测试脚本
│   ├── tests/                     # pytest 套件
│   └── uploads/                   # 上传的图片
├── mobile/                         # Flutter 前端（Provider + GoRouter）
│   └── lib/
│       ├── core/                  # API 客户端、主题、性别表达系统
│       └── features/              # auth / home / profile / wardrobe / analysis
├── vton_inference_service/         # 独立最小 HTTP 推理服务
│   ├── catvton_runner.py          # CatVTON 子进程推理（含 MediaPipe PoseLandmarker）
│   ├── catvton_engine.py          # CatVTON 引擎封装
│   ├── ootd_engine.py             # OOTDiffusion 引擎（待接入）
│   └── main.py                    # FastAPI 入口
├── cli/                           # outfit_cli.py
├── mcp/                           # server.py（FastMCP 工具桥接）
├── docs/                          # 技术文档（40+ 篇）
├── deploy/ecs/                    # ECS 部署脚本与清单
└── .kiro/specs/                   # 需求与设计规格
```

## 快速开始

### 1. 启动后端

```bash
# Windows PowerShell
cd backend
# 激活 .venv
..\.venv\Scripts\Activate.ps1

# 启动服务（默认端口 8010）
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010

# API 文档
# http://127.0.0.1:8010/docs
```

### 2. 启动前端

```bash
cd mobile
flutter run -d chrome
```

### 3. CatVTON 虚拟试衣（如需 realistic/professional 模式）

```bash
# 环境变量（在 backend/.env 中配置）
CATVTON_ENABLED=true
CATVTON_PATH=D:\models\CatVTON_full
CATVTON_WIDTH=768
CATVTON_HEIGHT=1024
CATVTON_STEPS=50
CATVTON_FORCE_FP16=true
CATVTON_ENABLE_VAE_SLICING=true
CATVTON_ENABLE_XFORMERS=true
CATVTON_LOW_VRAM_MODE=true
```

### 4. CLI / MCP

```bash
python cli/outfit_cli.py --help
# 或
python -m mcp.server  # 需要先设置 OUTFIT_API_BASE_URL / OUTFIT_API_TOKEN
```

## 虚拟试衣 v2 API

虚拟试衣 v2 接口统一挂在 `http://<host>/api/v2` 下：

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v2/tryon/garment` | 多模式试衣（`mode`: strict/balanced/replace/realistic/realistic_v2/professional/hybrid） |
| `POST` | `/api/v2/tryon/validate-input` | 输入门禁评估（不生成图片） |
| `POST` | `/api/v2/tryon/preprocess` | 衣物预处理（自动品类检测） |
| `POST` | `/api/v2/tryon/preprocess-batch` | 批量预处理 |
| `GET` | `/api/v2/tryon/capabilities` | 能力开关、默认模式、支持品类 |
| `GET` | `/api/v2/tryon/model-status` | CatVTON 等引擎就绪状态诊断 |

### CLI 调用示例

```bash
# 仅做 v2 预检
python cli/outfit_cli.py tryon --v2 --precheck-only \
  --garment ./samples/garment.jpg \
  --person ./samples/person.jpg \
  --garment-category bottom \
  --mode strict

# v2 realistic 模式（需 CatVTON）
python cli/outfit_cli.py tryon --v2 \
  --garment ./samples/garment.jpg \
  --person ./samples/person.jpg \
  --mode realistic

# v2 professional 模式
python cli/outfit_cli.py tryon --v2 \
  --garment ./samples/garment.jpg \
  --person ./samples/person.jpg \
  --mode professional
```

### 诊断脚本

```bash
python backend/scripts/diagnose_catvton.py
python backend/scripts/analyze_debug.py
```

## 环境要求

- Python 3.11+（推荐 3.12；支持 3.14，使用 `requirements-py314.txt`）
- PostgreSQL 14+（开发环境可使用 SQLite：`DATABASE_URL=sqlite:///./outfit_local.db`）
- Redis 7+（可选，用于缓存）
- Flutter 3.x（前端开发）
- NVIDIA GPU + CUDA（如使用 CatVTON realistic 模式，8GB VRAM 可正常运行）

> 使用 NVIDIA GPU + 本机 PyTorch CUDA 时：全量 `pip install -r requirements.txt` 可能把 `torch` 换成 CPU 新版；恢复方式见 [`docs/PYTORCH_CUDA_WINDOWS.md`](docs/PYTORCH_CUDA_WINDOWS.md)。

## 工程治理

- **Pre-commit**: Black + isort + flake8 + dart-format + dart-analyze + detect-secrets + Conventional Commits
- **测试**: pytest（`backend/tests/`）；pre-push 跑 `tests_lite`（轻量门禁）
- **Flutter**: `flutter test`（pre-push）
- **安装 Hooks**: `powershell -NoProfile -ExecutionPolicy Bypass -File setup-hooks.ps1`

详见 [docs/ENGINEERING_BASELINE.md](docs/ENGINEERING_BASELINE.md)。

## 文档清单

- [`QUICK_START.md`](QUICK_START.md) — 5 分钟快速启动
- [`docs/AI_OUTFIT_PREDICT_AND_TRYON.md`](docs/AI_OUTFIT_PREDICT_AND_TRYON.md) — AI 预测与虚拟试衣配置
- [`docs/VTON_INTEGRATION.md`](docs/VTON_INTEGRATION.md) — 专用 VTON 选型与集成
- [`docs/VTON_DELIVERY_2026-04.md`](docs/VTON_DELIVERY_2026-04.md) — 2026-04 试衣交付说明
- [`vton_inference_service/README.md`](vton_inference_service/README.md) — 独立推理服务说明
- [`docs/SMART_OUTFIT_FLUTTER_WEB.md`](docs/SMART_OUTFIT_FLUTTER_WEB.md) — Flutter Web 行为与 CORS
- [`docs/CLI_MCP_QUICKSTART.md`](docs/CLI_MCP_QUICKSTART.md) — CLI + MCP 快速入门
- [`docs/PRODUCTION_DEPLOY.md`](docs/PRODUCTION_DEPLOY.md) — 生产部署清单
- [`docs/ENGINEERING_BASELINE.md`](docs/ENGINEERING_BASELINE.md) — 工程基线
- [`docs/COMPETITION_EXTENSIONS.md`](docs/COMPETITION_EXTENSIONS.md) — 竞赛/课题扩展清单
- [`backend/API_EXAMPLES.md`](backend/API_EXAMPLES.md) — curl 示例
- [`docs/DELIVERY_STATUS.md`](docs/DELIVERY_STATUS.md) — 本轮治理交付状态

## 许可证

MIT License — 详见 [LICENSE](LICENSE)

---

**项目类型**: 毕业设计/课题研究
**年级**: 2024级
**学号**: 202452320220
**班级**: 智能科学与技术2班
