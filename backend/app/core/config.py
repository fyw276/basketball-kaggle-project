"""
Application configuration using Pydantic Settings
"""

from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Smart Outfit Assistant"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Server（默认 8010，减少与本机其它占用 8000 的进程冲突；可用环境变量 PORT 覆盖）
    HOST: str = "0.0.0.0"
    PORT: int = 8010
    WORKERS: int = 4

    # Database
    DATABASE_URL: str = Field(
        default="postgresql://user:password@localhost:5432/outfit_db",
        description="PostgreSQL database URL",
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    REDIS_MAX_CONNECTIONS: int = 50

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(
        default="your-secret-key-change-this-in-production",
        description="Secret key for JWT token generation",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    # File Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 10485760  # 10 MB

    # Model Configuration
    MODEL_PATH: str = "../models"
    MODEL_CACHE_SIZE: int = 1000

    # Hybrid Inference (local primary + external enhancement)
    HYBRID_INFERENCE_ENABLED: bool = True
    EXTERNAL_ENHANCE_ENABLED: bool = False
    LOW_CONF_THRESHOLD: float = 0.62
    HIGH_CONF_THRESHOLD: float = 0.78
    MARGIN_THRESHOLD: float = 0.08
    LOCAL_WEIGHT: float = 0.65
    EXTERNAL_WEIGHT: float = 0.35
    LOCAL_INFER_TIMEOUT_MS: int = 1200
    EXTERNAL_INFER_TIMEOUT_MS: int = 1800
    EXTERNAL_API_BASE_URL: str = ""
    EXTERNAL_API_KEY: str = ""
    EXTERNAL_API_PATH: str = "/infer"
    EXTERNAL_HEALTHCHECK_ENABLED: bool = True
    EXTERNAL_API_HEALTH_PATH: str = "/health"

    # Hugging Face（写入 os.environ，供 huggingface_hub / diffusers 使用；仅配 .env 即可）
    HF_ENDPOINT: str = Field(
        default="",
        description="镜像基址，国内可填 https://hf-mirror.com",
    )
    HF_HOME: str = Field(default="", description="HF 缓存根目录，如 D:\\model-cache\\hf")
    HF_TOKEN: str = Field(default="", description="gated 模型令牌")
    TRANSFORMERS_CACHE: str = Field(default="", description="transformers 缓存目录")
    HF_HUB_DOWNLOAD_TIMEOUT: str = Field(
        default="",
        description="下载超时秒数；空则由 hf_hub_env 默认 120",
    )

    # 逆地理（可选）：高德 Web 服务 Key；国内部署时填写可提升「省市区街道」解析成功率（经纬度接口在 Open-Meteo 之后、Nominatim 之前尝试）
    AMAP_WEB_KEY: str = Field(
        default="", description="高德逆地理 key，空则仅用 Open-Meteo + Nominatim"
    )

    # AI 推荐解释层（OpenAI 兼容接口）
    AI_RECOMMENDER_ENABLED: bool = False
    AI_RECOMMENDER_API_BASE_URL: str = Field(
        default="",
        description="OpenAI 兼容接口基址，如 https://api.openai.com/v1",
    )
    AI_RECOMMENDER_API_KEY: str = Field(default="", description="AI 推荐接口密钥")
    AI_RECOMMENDER_MODEL: str = Field(default="gpt-4o-mini", description="AI 推荐模型名")
    AI_RECOMMENDER_TIMEOUT_MS: int = Field(default=8000, description="AI 推荐超时时间（毫秒）")

    # CORS
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8080",
        description="Allowed CORS origins (comma-separated)",
    )
    CORS_ALLOW_ALL_LOCALHOST: bool = Field(
        default=True,
        description="Allow all localhost ports (useful for Flutter Web development)",
    )
    CORS_ALLOW_PATTERN: str = Field(
        default="",
        description=(
            "Regex pattern for allowed origins "
            "(e.g., https://.*\\.your-domain\\.com). "
            "Overrides CORS_ORIGINS when set."
        ),
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        """Allow DEBUG env values like release/dev/true/false/0/1."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "t", "yes", "y", "on", "debug", "dev", "development"}:
            return True
        if text in {
            "0",
            "false",
            "f",
            "no",
            "n",
            "off",
            "release",
            "prod",
            "production",
        }:
            return False
        return value

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"

    # Rate Limiting（需 ENABLE_RATE_LIMIT=true 才生效；pytest 默认关闭）
    ENABLE_RATE_LIMIT: bool = Field(
        default=False,
        description="启用后按 IP 滑动窗口限制请求（RATE_LIMIT_PER_MINUTE 次/分钟）",
    )
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=60,
        description="每分钟上限；仅当 ENABLE_RATE_LIMIT=true 时启用",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Create global settings instance
settings = Settings()
