"""
Main FastAPI application entry point
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api import (
    analysis_router,
    auth_router,
    profile_router,
    recognition_router,
    users_router,
    wardrobe_router,
)
from app.api.agent_chat import router as agent_chat_router
from app.api.agent_intent import router as agent_intent_router
from app.api.agent_skills import router as agent_skills_router
from app.api.analytics import router as analytics_router
from app.api.feedback import router as feedback_router
from app.api.memory_rag import router as memory_rag_router
from app.api.mood import router as mood_router
from app.api.outfit_collections import router as outfit_collections_router
from app.api.predict_style import router as predict_style_router
from app.api.smart_outfit import router as smart_outfit_router
from app.api.subscription import router as subscription_router
from app.api.subscription import usage_router
from app.api.tryon import router as tryon_router
from app.api.tryon_v2 import router as tryon_v2_router
from app.api.wardrobe_simple import router as wardrobe_simple_router
from app.core.config import settings
from app.core.error_handlers import (
    app_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.exceptions import AppException
from app.core.hf_hub_env import apply_hf_hub_env_defaults, sync_hf_env_from_settings
from app.core.logging import setup_logging
from app.core.release_info import build_env_snapshot, build_release_ledger

# 须在首次下载 HF 模型前生效（CLIP / 虚拟试衣 diffusers）
sync_hf_env_from_settings(settings)
apply_hf_hub_env_defaults()

# Setup logging
logger = setup_logging()

# CORS 模式在启动日志中使用（ lifespan 内需访问）
_env = (settings.ENVIRONMENT or "").lower()
_cors_permissive = (
    _env in ("development", "dev", "local") or settings.DEBUG or settings.CORS_ALLOW_ALL_LOCALHOST
)


class ApiEnvelopeMiddleware(BaseHTTPMiddleware):
    """Wrap successful JSON responses in the standard envelope."""

    # Paths that must be returned as-is (binary or raw formats).
    _RAW_PREFIXES = ("/openapi.json", "/docs", "/redoc", "/uploads/")

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        # Keep OpenAPI schema/docs and static uploads raw so they are served correctly.
        if any(path.startswith(p) for p in self._RAW_PREFIXES):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        if not body:
            return JSONResponse(
                status_code=response.status_code,
                content={"success": True, "data": None, "error": None, "message": "ok"},
            )

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            # Non-JSON responses (e.g. binary images, plain text) cannot be parsed.
            # Return the raw response as-is to avoid corruption (JSONResponse would
            # try to JSON-encode bytes and break the response).
            from starlette.responses import Response as StarletteResponse

            return StarletteResponse(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type"),
            )

        if isinstance(payload, dict) and {"success", "data", "error"}.issubset(payload.keys()):
            return JSONResponse(status_code=response.status_code, content=payload)

        return JSONResponse(
            status_code=response.status_code,
            content={"success": True, "data": payload, "error": None, "message": "ok"},
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every API request for debugging."""

    async def dispatch(self, request: Request, call_next):
        import time

        path = request.url.path
        method = request.method

        # Skip logging for static files and docs
        if (
            path.startswith("/static")
            or path.startswith("/docs")
            or path.startswith("/redoc")
            or path == "/openapi.json"
        ):
            return await call_next(request)

        start_time = time.time()

        # Log request start
        logger.info(f"[REQUEST] {method} {path} - started")

        try:
            response = await call_next(request)
            elapsed_ms = (time.time() - start_time) * 1000

            # Log request completion
            if response.status_code >= 400:
                logger.warning(
                    f"[REQUEST] {method} {path} - completed "
                    f"{response.status_code} in {elapsed_ms:.1f}ms"
                )
            else:
                logger.info(
                    f"[REQUEST] {method} {path} - completed "
                    f"{response.status_code} in {elapsed_ms:.1f}ms"
                )

            return response
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"[REQUEST] {method} {path} - failed after {elapsed_ms:.1f}ms: {e}")
            raise


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    """应用启动/关闭：数据库补丁、日志（替代已弃用的 on_event）。"""
    from pathlib import Path

    from app.db.session import engine
    from app.db.sqlite_schema import apply_sqlite_schema_patches

    _env = (settings.ENVIRONMENT or "").strip().lower()
    if _env in ("production", "prod") and not Path(settings.UPLOAD_DIR).is_absolute():
        logger.warning(
            "生产环境 UPLOAD_DIR=%r 为相对路径，发布/改工作目录后易导致图片「消失」。"
            "请改为绝对路径（如 /var/lib/clothing-assistant/uploads），见 docs/PRODUCTION_DEPLOY.md",
            settings.UPLOAD_DIR,
        )
    if _env in ("production", "prod") and (settings.DATABASE_URL or "").lower().startswith(
        "sqlite"
    ):
        logger.warning(
            "生产环境正在使用 SQLite。请将 DATABASE_URL 指向部署目录之外的绝对路径"
            "（例如 sqlite:////var/lib/clothing-assistant/data/outfit.db），或改用 PostgreSQL；"
            "详见 docs/PRODUCTION_DEPLOY.md",
        )

    apply_sqlite_schema_patches(engine)

    try:
        import app.models  # noqa: F401  # register new tables (feedback, memory)
        from app.db.base import Base

        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning("create_all skipped or failed: %s", e)

    try:
        from app.services.outfit_style_predict import ensure_pipeline

        ensure_pipeline()
        logger.info("Outfit style predict model loaded (POST /predict)")
    except Exception as e:
        logger.warning(
            "Outfit style predict model unavailable — POST /predict will return 503: %s",
            e,
        )

    # 初始化本地推理服务（微调模型）
    try:
        from app.services import local_inference

        local_inference.init()
        logger.info(
            "Local fine-tuned inference service initialized (POST /recognition/category-v2)"
        )
    except Exception as e:
        logger.warning(
            "Local fine-tuned inference service initialization failed: %s",
            e,
        )

    try:
        from app.services.external_enhance_client import (
            get_external_enhance_status,
            probe_external_enhance,
        )

        ok, reason = probe_external_enhance(timeout_ms=settings.EXTERNAL_INFER_TIMEOUT_MS)
        if ok:
            logger.info("External enhancement ready: %s", reason)
        else:
            logger.warning("External enhancement degraded to local-only: %s", reason)
        status_ok, status_reason = get_external_enhance_status()
        logger.info(
            "External enhancement status: enabled=%s reason=%s",
            status_ok,
            status_reason,
        )
    except Exception as e:
        logger.warning("External enhancement probe skipped due to error: %s", e)

    # Log CatVTON status for debugging "realistic mode" issues
    try:
        from app.services.tryon_v2.catvton_engine_client import log_catvton_status

        catvton_summary = log_catvton_status("[CATVTON]")
        if "model=NOT_DOWNLOADED" in catvton_summary or "path=MISSING" in catvton_summary:
            logger.warning(
                "CatVTON realistic mode will NOT work: %s. "
                "Details: set CATVTON_ENABLED=true, ensure CATVTON_PATH exists, "
                "and run CatVTON once to download models from HuggingFace.",
                catvton_summary,
            )
        else:
            logger.info("CatVTON realistic mode is available: %s", catvton_summary)
    except Exception as e:
        logger.warning("Failed to check CatVTON status: %s", e)

    # Preload ImageRecognizer singleton at startup to avoid first-request blocking.
    # Without this, the first HTTP request to /api/v2/tryon/validate-input would block
    # for 20+ seconds while TensorFlow/MobileNetV2 models are loaded.
    try:
        from app.ml.image_recognizer import get_recognizer

        get_recognizer()  # Initialize singleton (don't store reference)
        logger.info("ImageRecognizer singleton preloaded at startup (no first-request blocking)")
    except Exception as e:
        logger.warning("Failed to preload ImageRecognizer at startup: %s", e)

    # Initialize Haar Cascade XML files in ASCII temp directory.
    # This solves the Windows + Chinese path issue where cv2.data.haarcascades
    # returns garbled paths, causing OpenCV FileStorage to fail.
    try:
        from app.services.cascade_manager import ensure_cascade_available, init_cascades

        init_cascades()
        if ensure_cascade_available():
            logger.info("Haar Cascades preloaded successfully (ASCII temp path)")
        else:
            logger.warning("Haar Cascades not available - face detection in try-on may fail")
    except Exception as e:
        logger.warning("Failed to initialize Haar Cascades at startup: %s", e)

    # Initialize embedding client for memory hybrid search
    if settings.AI_RECOMMENDER_API_BASE_URL and settings.AI_RECOMMENDER_API_KEY:
        from app.services.embedding_client import EmbeddingClient, init_embedding_client

        _emb_client = EmbeddingClient(
            api_base=settings.AI_RECOMMENDER_API_BASE_URL,
            api_key=settings.AI_RECOMMENDER_API_KEY,
            model=settings.EMBEDDING_MODEL,
            dim=settings.EMBEDDING_DIM,
            timeout_seconds=settings.EMBEDDING_TIMEOUT_SECONDS,
        )
        init_embedding_client(_emb_client)
        logger.info(
            "Embedding client initialized: model=%s dim=%d",
            settings.EMBEDDING_MODEL,
            settings.EMBEDDING_DIM,
        )
    else:
        logger.info("Embedding client skipped (AI_RECOMMENDER_API_BASE_URL / API_KEY not set)")

    # Warn if CatVTON is enabled but DISABLE_HOT_RELOAD is not set
    import os as _os

    if getattr(settings, "CATVTON_ENABLED", False) and not _os.environ.get("DISABLE_HOT_RELOAD"):
        logger.warning(
            "CatVTON is enabled (CATVTON_ENABLED=true). "
            "Do NOT use uvicorn --reload in production — hot reload causes "
            "CatVTON model to be reloaded/restarted on every code change, "
            "triggering CUDA context destruction and GPU memory fragmentation. "
            "Set DISABLE_HOT_RELOAD=true or run without --reload."
        )

    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(
        "CORS: %s",
        (
            "宽松（本机 localhost/127.0.0.1 任意端口，回显 Origin）"
            if _cors_permissive
            else "严格（仅 CORS_ORIGINS / 正则）"
        ),
    )

    _default_jwt = "your-secret-key-change-this-in-production"
    _env_name = (settings.ENVIRONMENT or "").lower()
    if _env_name in ("production", "prod") and not settings.DEBUG:
        secret = (settings.JWT_SECRET_KEY or "").strip()
        if secret == _default_jwt or len(secret) < 24:
            logger.critical(
                "JWT_SECRET_KEY is default or too short while ENVIRONMENT is production — "
                "rotate to a long random secret before accepting traffic."
            )
    elif len((settings.JWT_SECRET_KEY or "").strip()) < 16:
        logger.warning(
            "JWT_SECRET_KEY is short (%d chars); use >=32 random bytes for production.",
            len((settings.JWT_SECRET_KEY or "").strip()),
        )

    yield

    logger.info(f"Shutting down {settings.APP_NAME}")


# Create FastAPI app
app = FastAPI(
    lifespan=_app_lifespan,
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    ## 智能穿搭助手 API

    基于多模态推荐与轻量化推理的穿搭决策系统

    ### 核心功能

    * **用户认证**: 注册、登录、JWT Token 管理
    * **用户画像**: 创建和管理个人画像信息（身高、体型、肤色、风格偏好等）
    * **图像识别**: FashionCLIP 零样本分类 — 品类、颜色、风格标签识别（含国风/汉服）
    * **衣橱管理**: 添加、查询、搜索、编辑、删除服饰单品（支持 CLIP 自动识别）
    * **相似度分析**: CLIP 语义向量相似度计算，提供重复购买预警
    * **穿搭推荐**: 场景-品类-风格 三维匹配推荐（基于 Polyvore 风格规则）
    * **适合度评分**: 场景-体型-风格 三维评分引擎
    * **套装收藏**: 保存和管理用户精选搭配，记录穿搭次数
    * **虚拟试穿**: SD-VTON/Stable Diffusion 虚拟试穿（GPU 推荐）

    ### 技术栈

    * FastAPI + Python 3.9+
    * PostgreSQL + Redis
    * **FashionCLIP** 零样本图文分类（transformers + PyTorch）
    * **Stable Diffusion Inpainting** 虚拟试穿（diffusers）
    * MobileNetV2 特征提取（备用）
    * JWT 认证
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Smart Outfit Assistant Team",
        "email": "support@smartoutfit.example.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)


# ── 中间件注册顺序 ────────────────────────────────────────────────
# add_middleware 的注册顺序决定 ASGI 洋葱模型：
#   先注册 = 最外层（最先处理请求，最后处理响应）
#   后注册 = 最内层（最后处理请求，最先处理响应）
#
# CORSMiddleware 是原生 ASGI 中间件，通过包裹 send 在 http.response.start
# 消息中注入 CORS 头。它必须在所有 BaseHTTPMiddleware 之内（即后注册），
# 这样 BaseHTTPMiddleware 创建新 response 时，CORS 包裹的 send 仍在链中。
# ─────────────────────────────────────────────────────────────────

# 最外层：日志（BaseHTTPMiddleware）
app.add_middleware(RequestLoggingMiddleware)

# 中间层：API envelope 包裹（BaseHTTPMiddleware）
app.add_middleware(ApiEnvelopeMiddleware)

# 最内层：CORS + PNA（原生 ASGI，包裹 send）
# 确保 BaseHTTPMiddleware 创建新 response 后 send 仍经过 CORS 包裹。
_CORS_ALLOW_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Accept-Language",
    "Origin",
    "X-Requested-With",
    "Access-Control-Request-Private-Network",
]
_localhost_origin_re = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
if _cors_permissive:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_localhost_origin_re,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=_CORS_ALLOW_HEADERS,
    )
else:
    _localhost_re = _localhost_origin_re
    _pattern = (settings.CORS_ALLOW_PATTERN or "").strip()
    _allow_regex: str | None = None
    if _pattern and settings.CORS_ALLOW_ALL_LOCALHOST:
        _allow_regex = f"(?:{_pattern})|(?:{_localhost_re})"
    elif _pattern:
        _allow_regex = _pattern
    elif settings.CORS_ALLOW_ALL_LOCALHOST:
        _allow_regex = _localhost_re

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=_allow_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=_CORS_ALLOW_HEADERS,
    )


# Chrome Private Network Access: Starlette CORSMiddleware 不处理此头，
# 但 Chrome 从 localhost → 127.0.0.1 时要求 Access-Control-Allow-Private-Network: true。
# 此原生 ASGI 中间件在最内层包裹 send，给所有带 CORS-Allow-Origin 的响应补上 PNA 头。
class _PrivateNetworkAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_pna(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                if b"access-control-allow-origin" in headers:
                    headers[b"access-control-allow-privatenetwork"] = b"true"
                    message["headers"] = list(headers.items())
            await send(message)

        await self.app(scope, receive, send_with_pna)


app.add_middleware(_PrivateNetworkAccessMiddleware)

if settings.ENABLE_RATE_LIMIT and settings.RATE_LIMIT_PER_MINUTE > 0:
    from app.middleware.rate_limit import SlidingWindowRateLimitMiddleware

    _prefix_limits = {}
    if settings.RATE_LIMIT_TRYON_PER_MINUTE > 0:
        _prefix_limits["/api/v1/tryon"] = settings.RATE_LIMIT_TRYON_PER_MINUTE
        _prefix_limits["/api/v2/tryon"] = settings.RATE_LIMIT_TRYON_PER_MINUTE

    app.add_middleware(
        SlidingWindowRateLimitMiddleware,
        limit=settings.RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
        prefix_limits=_prefix_limits,
    )

# Register exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(PydanticValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "version": settings.APP_VERSION,
        },
    )


@app.get("/release")
async def release_ledger():
    """
    发布工件版本台账：前端 index指纹、后端 commit、环境快照（无密钥）。
    CD 可向 RELEASE_* 环境变量或 RELEASE_MANIFEST_PATH 指向的 JSON 注入字段。
    """
    return JSONResponse(
        status_code=200,
        content={
            "ledger": build_release_ledger(settings),
            "env_snapshot": build_env_snapshot(settings),
        },
    )


@app.get("/ops/dependency-board", include_in_schema=False)
async def ops_dependency_board():
    """HTML 看板：天气 / 试衣 / AI / 外部增强 依赖的成功率、失败率、超时率、降级率（进程内累计）。"""
    if not settings.OPS_DASHBOARD_ENABLED:
        raise HTTPException(status_code=404, detail="not found")
    from fastapi.responses import HTMLResponse

    from app.observability.dependency_metrics import render_dependency_board_html

    rel = json.dumps(
        {
            "ledger": build_release_ledger(settings),
            "env_snapshot": build_env_snapshot(settings),
        },
        ensure_ascii=False,
    )
    return HTMLResponse(render_dependency_board_html(rel))


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus exposition-format metrics endpoint (零依赖纯文本）。"""
    from fastapi.responses import PlainTextResponse

    from app.observability.prometheus_exporter import render_prometheus_metrics

    return PlainTextResponse(
        render_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/health/ready")
async def health_ready():
    """Readiness: verifies DB connectivity (orchestrators should use this for traffic)."""
    from sqlalchemy import text

    from app.db.session import SessionLocal

    issues = []
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as e:
        issues.append(f"database: {e}")

    if issues:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "data": None,
                "error": {
                    "type": "ServiceUnavailable",
                    "message": "; ".join(issues),
                    "status_code": 503,
                },
                "message": "not ready",
            },
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "checks": {"database": "ok"}},
    )


@app.get("/redoc-alt", include_in_schema=False)
async def redoc_alternative():
    """
    Alternative ReDoc endpoint with multiple CDN fallbacks

    Use this if the default /redoc endpoint shows a blank page.
    This version tries multiple CDN sources to ensure ReDoc loads.
    """
    from fastapi.responses import HTMLResponse

    return HTMLResponse(
        content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Smart Outfit Assistant - API Documentation</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                margin: 0;
                padding: 0;
            }
            #loading {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-family: Arial, sans-serif;
                text-align: center;
            }
            #loading h2 {
                color: #333;
                margin-bottom: 20px;
            }
            #loading p {
                color: #666;
                font-size: 14px;
            }
            .spinner {
                border: 4px solid #f3f3f3;
                border-top: 4px solid #3498db;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div id="loading">
            <h2>正在加载 API 文档...</h2>
            <div class="spinner"></div>
            <p>如果长时间未加载，请尝试 <a href="/docs">Swagger UI</a></p>
        </div>
        <redoc spec-url="/openapi.json"></redoc>

        <script>
            // Try multiple CDN sources with fallback
            const cdnSources = [
                'https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js',
                'https://unpkg.com/redoc@latest/bundles/redoc.standalone.js',
                'https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js'
            ];

            function loadScript(src) {
                return new Promise((resolve, reject) => {
                    const script = document.createElement('script');
                    script.src = src;
                    script.onload = () => {
                        console.log('✓ Loaded ReDoc from:', src);
                        resolve();
                    };
                    script.onerror = () => {
                        console.warn('✗ Failed to load from:', src);
                        reject();
                    };
                    document.body.appendChild(script);
                });
            }

            async function tryLoadRedoc() {
                for (let i = 0; i < cdnSources.length; i++) {
                    try {
                        await loadScript(cdnSources[i]);
                        document.getElementById('loading').style.display = 'none';
                        return;
                    } catch (error) {
                        if (i === cdnSources.length - 1) {
                            document.getElementById('loading').innerHTML =
                                '<h2>无法加载 API 文档</h2>' +
                                '<p>所有 CDN 源都无法访问</p>' +
                                '<p>请尝试：</p>' +
                                '<ul style="text-align: left; display: inline-block;">' +
                                '<li>检查网络连接</li>' +
                                '<li>使用 <a href="/docs">Swagger UI</a> 代替</li>' +
                                '<li>清除浏览器缓存后重试</li>' +
                                '<li>检查防火墙或代理设置</li>' +
                                '</ul>';
                        }
                    }
                }
            }

            tryLoadRedoc();
        </script>
    </body>
    </html>
    """
    )


@app.get("/test-html", include_in_schema=False)
async def test_html():
    """Test HTML response"""
    from fastapi.responses import HTMLResponse

    return HTMLResponse(
        content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Page</title>
    </head>
    <body>
        <h1>HTML Response Test</h1>
        <p>If you can see this, HTML responses are working correctly.</p>
        <p><a href="/docs">Go to Swagger UI</a></p>
        <p><a href="/redoc">Go to ReDoc</a></p>
    </body>
    </html>
    """
    )


# Include routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(agent_intent_router, prefix="/api/v1")
app.include_router(agent_chat_router, prefix="/api/v1")
app.include_router(agent_skills_router, prefix="/api/v1")
app.include_router(memory_rag_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(wardrobe_router, prefix="/api/v1")
app.include_router(wardrobe_simple_router, prefix="/api/v1")  # Simplified API
app.include_router(recognition_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(tryon_router, prefix="/api/v1")  # Virtual Try-On
app.include_router(tryon_v2_router, prefix="/api/v2")  # Virtual Try-On v2 (pipeline A)
app.include_router(outfit_collections_router, prefix="/api/v1")  # Outfit Collections
app.include_router(mood_router, prefix="/api/v1")  # Mood Recommendation
app.include_router(smart_outfit_router, prefix="/api/v1")  # Smart outfit (weather + mood)
app.include_router(subscription_router, prefix="/api/v1")  # Subscription & payment
app.include_router(usage_router, prefix="/api/v1")  # Usage quota

# 与 backend.main 相同：sklearn 穿搭风格分 + 推荐列表（无 /api/v1 前缀，便于与独立 8765 服务对齐）
app.include_router(predict_style_router)

# Mount static files for uploaded images
upload_dir = Path(settings.UPLOAD_DIR)
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")


if __name__ == "__main__":
    import uvicorn

    # ─────────────────────────────────────────────────────────────────
    # 强制单进程模式（调试阶段）。
    # 多进程模式（workers > 1）在 Windows 上会与 Loguru 的 rotation 文件锁冲突，
    # 导致 PermissionError: [WinError 32]，服务崩溃。
    # 同样，单进程避免了 CatVTON GPU 模型被多进程重复加载的问题。
    # 生产部署如需多进程，请使用 Gunicorn + uvicorn.workers 方案，
    # 并确保 Loguru 的 enqueue=True 已开启（已在本文件 logging.py 中配置）。
    # ─────────────────────────────────────────────────────────────────
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
        workers=1,  # 强制单进程，避免 Windows 日志文件锁死 + CatVTON GPU 冲突
    )
