"""
Main FastAPI application entry point
"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from app.core.config import settings
from app.core.error_handlers import (
    app_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.exceptions import AppException
from app.core.logging import setup_logging

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
    * **图像识别**: 识别服饰品类、颜色、风格标签
    * **衣橱管理**: 添加、查询、编辑、删除服饰单品
    * **相似度分析**: 计算服饰相似度，提供重复购买预警
    * **搭配推荐**: 生成个性化搭配方案
    * **适合度评分**: 基于用户画像评估服饰适合度

    ### 技术栈

    * FastAPI + Python 3.9+
    * PostgreSQL + Redis
    * MobileNetV2 图像识别模型
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
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
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")


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
app.include_router(recognition_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
