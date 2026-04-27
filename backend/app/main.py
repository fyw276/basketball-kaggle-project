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
from app.api.agent_intent import router as agent_intent_router
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

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        # Keep OpenAPI schema/docs raw so Swagger/Redoc can parse correctly.
        if path == "/openapi.json" or path.startswith("/docs") or path.startswith("/redoc"):
            return response
        content_type = response.headers.get("content-type", "")
        if response.status_code >= 400 or "application/json" not in content_type.lower():
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
            return JSONResponse(status_code=response.status_code, content=body.decode("utf-8"))

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
            log_msg = (
                f"[REQUEST] {method} {path} - completed {response.status_code} "
                f"in {elapsed_ms:.1f}ms"
            )
            if response.status_code >= 400:
                logger.warning(log_msg)
            else:
                logger.info(log_msg)

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


class PrivateNetworkAccessMiddleware(BaseHTTPMiddleware):
    """为预检/跨站请求补充 Chrome 私有网络访问 (PNA) 所需响应头。"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response


# 最内层先统一包裹 JSON 响应，让外层 CORS / PNA 仍能补齐响应头
app.add_middleware(ApiEnvelopeMiddleware)

# 添加请求日志中间件（显示每个 API 请求）
app.add_middleware(RequestLoggingMiddleware)

# 再补充 PNA 头，供外层 CORS 最终返回给浏览器
app.add_middleware(PrivateNetworkAccessMiddleware)

# 最外层 CORS 必须最后注册，这样它才能给最终响应补上 ACAO 等头
# Flutter Web 端口随机；页面 Origin 为 http://localhost:<port>，API 常为 http://127.0.0.1:<后端端口>，属跨域。
# 请求带 Authorization 时，部分浏览器对 ACAO: * 与实际 Origin 组合较严，易报「无 ACAO」类 CORS 错误。
# 开发宽松模式改为 allow_origin_regex + 回显具体 Origin（Starlette fullmatch），避免通配符。
# 预检请求若仅返回 Allow-Headers: *，部分浏览器不把 Authorization 视为已允许，导致带 Bearer 的 POST 失败
# （XHR onError）；须显式列出 Authorization、Content-Type 等。
_CORS_ALLOW_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "Accept-Language",
    "Origin",
    "X-Requested-With",
    # Chrome 从 http://localhost:<flutter> 访问本机 API 时，预检可能携带
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
    # 生产等环境：显式域名 + 可选正则；localhost/127.0.0.1 任意端口可与 CORS_ALLOW_PATTERN 同时生效
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

if settings.ENABLE_RATE_LIMIT and settings.RATE_LIMIT_PER_MINUTE > 0:
    from app.middleware.rate_limit import SlidingWindowRateLimitMiddleware

    app.add_middleware(
        SlidingWindowRateLimitMiddleware,
        limit=settings.RATE_LIMIT_PER_MINUTE,
        window_seconds=60,
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
