"""
Main FastAPI application entry point
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    analysis_router,
    auth_router,
    profile_router,
    recognition_router,
    users_router,
    wardrobe_router,
)
from app.api.mood import router as mood_router
from app.api.outfit_collections import router as outfit_collections_router
from app.api.tryon import router as tryon_router
from app.api.wardrobe_simple import router as wardrobe_simple_router
from app.core.config import settings
from app.core.error_handlers import (
    app_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.exceptions import AppException
from app.core.hf_hub_env import apply_hf_hub_env_defaults
from app.core.logging import setup_logging

# 须在首次下载 HF 模型前生效（CLIP 等）
apply_hf_hub_env_defaults()

# Setup logging
logger = setup_logging()

# Create FastAPI app
app = FastAPI(
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

# Configure CORS
# Flutter Web 端口随机；页面 Origin 为 http://localhost:<port>，API 常为 http://127.0.0.1:8000，属跨域。
# 请求带 Authorization 时，部分浏览器对 ACAO: * 与实际 Origin 组合较严，易报「无 ACAO」类 CORS 错误。
# 开发宽松模式改为 allow_origin_regex + 回显具体 Origin（Starlette fullmatch），避免通配符。
_localhost_origin_re = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
_env = (settings.ENVIRONMENT or "").lower()
_cors_permissive = (
    _env in ("development", "dev", "local") or settings.DEBUG or settings.CORS_ALLOW_ALL_LOCALHOST
)
if _cors_permissive:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_localhost_origin_re,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
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
        allow_headers=["*"],
    )

# Register exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(PydanticValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)


@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    # 旧版 SQLite 库缺少 ORM 新增列时，启动时补齐（避免 no such column）
    from app.db.session import engine
    from app.db.sqlite_schema import apply_sqlite_schema_patches

    apply_sqlite_schema_patches(engine)

    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(
        "CORS: {}",
        (
            "宽松（本机 localhost/127.0.0.1 任意端口，回显 Origin）"
            if _cors_permissive
            else "严格（仅 CORS_ORIGINS / 正则）"
        ),
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    logger.info(f"Shutting down {settings.APP_NAME}")


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
app.include_router(users_router, prefix="/api/v1")
app.include_router(profile_router, prefix="/api/v1")
app.include_router(wardrobe_router, prefix="/api/v1")
app.include_router(wardrobe_simple_router, prefix="/api/v1")  # Simplified API
app.include_router(recognition_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(tryon_router, prefix="/api/v1")  # Virtual Try-On
app.include_router(outfit_collections_router, prefix="/api/v1")  # Outfit Collections
app.include_router(mood_router, prefix="/api/v1")  # Mood Recommendation

# Mount static files for uploaded images
upload_dir = Path(settings.UPLOAD_DIR)
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
