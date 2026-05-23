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
    # 实况天气（可选）：高德天气查询 API weatherInfo（需与 AMAP_WEB_KEY 同属 Web 服务 Key）
    AMAP_WEATHER_ENABLED: bool = Field(
        default=False,
        description="为 true 且配置了 AMAP_WEB_KEY 时，实况温度/天气文案优先用高德，失败回退 Open-Meteo",
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
    AI_RECOMMENDER_STRICT_JSON: bool = Field(
        default=True,
        description="为 true 时请求 response_format=json_object；若上游不支持会自动回退",
    )

    # Agent Loop（统一工具调用循环）
    AGENT_MODEL: str = Field(
        default="",
        description="Agent loop LLM model name; empty falls back to AI_RECOMMENDER_MODEL",
    )
    AGENT_MAX_ROUNDS: int = Field(
        default=5,
        description="Maximum LLM call rounds per agent request (tool call + response cycles)",
    )
    AGENT_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        description="Total wall-clock timeout for a single agent request in seconds",
    )
    AGENT_TOTAL_TOKEN_BUDGET: int = Field(
        default=50000,
        description="Maximum total tokens (prompt + completion) across all rounds",
    )
    AGENT_MAX_TOOL_CALLS: int = Field(
        default=15,
        description="Maximum number of tool executions per agent request",
    )

    # Memory embedding
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-v3",
        description="Text embedding model name (OpenAI-compatible /embeddings endpoint)",
    )
    EMBEDDING_DIM: int = Field(default=1024, description="Embedding vector dimension")
    EMBEDDING_TIMEOUT_SECONDS: float = Field(
        default=10.0, description="Embedding API timeout in seconds"
    )
    MEMORY_KEYWORD_WEIGHT: float = Field(
        default=0.3, description="Keyword search weight in hybrid scoring"
    )
    MEMORY_EMBEDDING_WEIGHT: float = Field(
        default=0.7, description="Embedding search weight in hybrid scoring"
    )
    MEMORY_PRELOAD_TOP_K: int = Field(
        default=3, description="Number of memory snippets to preload in agent loop"
    )

    # Fine-tuned model inference
    FINETUNED_INFER_ENABLED: bool = Field(
        default=False,
        description="Enable fine-tuned model inference fallback for image classification",
    )
    FINETUNED_INFER_API_BASE_URL: str = Field(
        default="",
        description="Base URL for fine-tuned model inference service",
    )
    FINETUNED_INFER_API_PATH: str = Field(
        default="/infer/fashion",
        description="API endpoint path on the fine-tuned service",
    )
    FINETUNED_INFER_API_KEY: str = Field(
        default="",
        description="API key for fine-tuned model service (if required)",
    )
    FINETUNED_INFER_TIMEOUT_MS: int = Field(
        default=5000,
        description="Timeout in milliseconds for fine-tuned inference calls",
    )

    # Try-on resilience
    TRYON_MAX_RETRIES: int = Field(
        default=1,
        description="虚拟试衣错误重试次数（仅对可重试错误生效）",
    )
    TRYON_BOTTOM_FORCE_FALLBACK: bool = Field(
        default=True,
        description="下装/裙装默认走身份保护模式（本地 fallback 粘贴，避免生成式换人）",
    )
    TRYON_V2_ENABLED: bool = Field(
        default=True,
        description="启用虚拟试衣 v2 接口（/api/v2/tryon/*）",
    )
    TRYON_V2_STRICT_IDENTITY: bool = Field(
        default=True,
        description="v2 默认是否开启严格身份保护（优先贴合而非生成）",
    )
    TRYON_V2_MIN_FULL_BODY_SCORE: float = Field(
        default=0.55,
        description="v2 输入门禁：全身可见最低分",
    )
    TRYON_V2_MIN_LEG_VISIBILITY_SCORE: float = Field(
        default=0.45,
        description="v2 输入门禁：腿部可见最低分",
    )
    TRYON_V2_MIN_FRONT_POSE_SCORE: float = Field(
        default=0.35,
        description="v2 输入门禁：正面姿态最低分",
    )
    TRYON_V2_MIN_GARMENT_FRONT_SCORE: float = Field(
        default=0.45,
        description="v2 输入门禁：商品图正面度最低分",
    )
    TRYON_V2_QC_THRESHOLD: float = Field(
        default=0.6,
        description="v2 质量门槛预留字段（后续阶段使用）",
    )
    TRYON_V2_TIMEOUT_MS: int = Field(
        default=12000,
        description="v2 接口超时预算（毫秒，预留）",
    )
    TRYON_V2_AUTO_PREPROCESS: bool = Field(
        default=True,
        description="v2 试衣在 garment_category=auto 时自动预处理（去背景白底+自动品类）",
    )
    TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION: bool = Field(
        default=False,
        description=(
            "v2 mode=replace 是否允许在百炼/远程VTON都不可用或失败时回退到本机 diffusers inpainting。"
            "默认关闭：本地权重不完整时容易生成无关图像（幻觉）。"
        ),
    )
    TRYON_V2_REPLACE_ENGINE_PRIORITY: str = Field(
        default="warp,bailian,remote,catvton,diffusion",
        description=(
            "v2 replace 模式引擎优先级（逗号分隔）。可选项: "
            "warp(几何贴合), bailian(百炼), remote(远程VTON), "
            "catvton(本地CatVTON), diffusion(本地diffusion)"
        ),
    )
    TRYON_V2_REPLACE_SKIP_WARP: bool = Field(
        default=False,
        description="v2 replace 模式跳过几何贴合，直接使用AI生成",
    )

    # Try-on engine switches
    TRYON_V2_HYBRID_WARP_OVERLAY_ENABLED: bool = Field(
        default=False,
        description=(
            "v2 hybrid mode legacy warp overlay switch. False returns CatVTON diffusion output "
            "directly after a successful local CatVTON run; True restores the old "
            "warp_preserve + CatVTON + overlay_draping path."
        ),
    )

    # DashScope / Bailian (阿里云百炼) for virtual try-on
    DASHSCOPE_TRYON_ENABLED: bool = Field(
        default=False,
        description="启用阿里云百炼（DashScope）虚拟试衣服务",
    )
    DASHSCOPE_API_KEY: str = Field(
        default="",
        description="阿里云百炼 API Key",
    )
    DASHSCOPE_TRYON_MODEL: str = Field(
        default="wanx2.1-imageedit",
        description="百炼试衣默认模型",
    )
    DASHSCOPE_TRYON_MODEL_TOP: str = Field(
        default="",
        description="上装专用模型（空则使用 DASHSCOPE_TRYON_MODEL）",
    )
    DASHSCOPE_TRYON_MODEL_BOTTOM: str = Field(
        default="",
        description="下装专用模型（空则使用 DASHSCOPE_TRYON_MODEL）",
    )
    DASHSCOPE_TRYON_MODEL_SKIRT: str = Field(
        default="",
        description="裙装专用模型（空则使用 DASHSCOPE_TRYON_MODEL）",
    )
    DASHSCOPE_TRYON_FUNCTION: str = Field(
        default="",
        description="百炼试衣功能名（空则自动选择 description_edit_with_mask 或 stylization_all）",
    )
    DASHSCOPE_TRYON_DOWNLOAD_TIMEOUT_SECONDS: int = Field(
        default=120,
        description="百炼结果图下载超时（秒）",
    )
    DASHSCOPE_TRYON_FALLBACK_LOCAL: bool = Field(
        default=True,
        description="百炼失败时是否降级到远程VTON或本地试衣",
    )
    DASHSCOPE_TRYON_STRENGTH: float = Field(
        default=0.25,
        description=(
            "百炼 diffusion 强度 0.0-1.0。值越低越忠实于原图（服装变形小，人脸不变），"
            "值越高生成质量越好但变化越大。建议 0.2-0.35，真实贴身模式推荐 0.25"
        ),
    )

    # Remote VTON service (专用虚拟试衣服务)
    VTON_INFERENCE_URL: str = Field(
        default="",
        description="远程VTON服务URL（如 http://127.0.0.1:8011/v1/tryon）",
    )
    VTON_INFERENCE_TIMEOUT_SECONDS: int = Field(
        default=2400,
        description="远程VTON服务超时（秒）",
    )
    VTON_INFERENCE_API_KEY: str = Field(
        default="",
        description="远程VTON服务API Key（可选）",
    )

    # CatVTON (本地高质量试衣引擎)
    # 推荐用于 product→person 场景，支持自动遮罩生成，8GB VRAM (fp16) 可运行
    CATVTON_ENABLED: bool = Field(
        default=False,
        description="启用 CatVTON 作为本地试衣引擎（需安装 CatVTON 并配置 CATVTON_PATH）",
    )
    CATVTON_PATH: str = Field(
        default="",
        description="CatVTON 仓库路径，如 D:\\models\\CatVTON",
    )
    CATVTON_WIDTH: int = Field(
        default=768,
        description="CatVTON 输入图像宽度（512 低显存 / 768 标准 / 1024 高质量）",
    )
    CATVTON_HEIGHT: int = Field(
        default=1024,
        description="CatVTON 输入图像高度（768 低显存 / 1024 标准 / 1280 高质量）",
    )
    CATVTON_STEPS: int = Field(
        default=28,
        description="CatVTON 推理步数（20=快速3-7min / 28=标准28步 / 50=高质量29min）",
    )
    CATVTON_GUIDANCE: float = Field(
        default=2.5,
        description="CatVTON CFG 强度（1.5 低显存快速 / 2.0 标准 / 2.5 高保真）",
    )
    CATVTON_SEED: int = Field(
        default=42,
        description="CatVTON random seed. -1 for random; fixed values make runs reproducible.",
    )
    CATVTON_REPAINT: bool = Field(
        default=True,
        description="CatVTON 是否使用背景重绘（repaint 模式恢复原始背景）",
    )
    CATVTON_MIXED_PRECISION: str = Field(
        default="fp16",
        description="CatVTON 混合精度：fp16（推荐，~4-6GB VRAM）/ bf16（高质量，~8GB VRAM）/ no（fp32）",
    )
    CATVTON_TIMEOUT_SECONDS: int = Field(
        default=900,
        description="CatVTON 单次推理超时（秒，20步约需 3-7 分钟，50步约需 25-30 分钟）",
    )
    CATVTON_DEBUG_DIR: str = Field(
        default="",
        description="保存 CatVTON 调试中间产物（mask、骨架图等）的目录，为空则不保存",
    )
    CATVTON_CPU_OFFLOAD: bool = Field(
        default=True,
        description="启用 CPU Offload 以减少 VRAM 占用（更慢但支持更小显存）",
    )
    # ─── 极限 VRAM 优化配置（8GB 及以下显存推荐全部开启）─────────────────
    CATVTON_FORCE_FP16: bool = Field(
        default=True,
        description="强制使用 fp16 替代 bf16（8GB VRAM 建议开启，节省约 2GB）",
    )
    CATVTON_ENABLE_VAE_SLICING: bool = Field(
        default=True,
        description="启用 VAE 分片推理（将 VAE 的编码/解码切分为小块，显著降低峰值显存）",
    )
    CATVTON_ENABLE_XFORMERS: bool = Field(
        default=True,
        description="启用 xformers 高效注意力（需要 xformers 库；若无则自动降级到 PyTorch 2.0 FlashAttention）",
    )
    CATVTON_LOW_VRAM_MODE: bool = Field(
        default=False,
        description="一键开启低显存模式（等于 force_fp16 + vae_slicing + cpu_offload，推理速度最慢但兼容性最好）",
    )
    CATVTON_ENABLE_GC_AFTER_INFER: bool = Field(
        default=True,
        description="每次推理后强制调用 torch.cuda.empty_cache() 和 gc.collect() 释放显存",
    )
    TRYON_V2_COLOR_FIDELITY_ENABLED: bool = Field(
        default=True,
        description="启用衣服颜色保真（彩色/图案衣服调用 catvton_color_fidelity_spatial）",
    )
    TRYON_V2_COLOR_FIDELITY_STRENGTH: float = Field(
        default=0.75,
        description="衣服颜色保真强度 0.0-1.0（0.75=75% 原衣服 + 25% CatVTON，适合图案衣服）",
    )
    CATVTON_GARMENT_RESIZE_MODE: str = Field(
        default="letterbox",
        description=(
            "CatVTON 衣服预处理缩放模式："
            "letterbox（默认，白边填充保留完整衣服，不变形）；"
            "crop（等比裁剪，无白边但可能丢失衣服边缘；推荐高显存用户）；"
            "fill（填满画布，不留白边但会裁切边缘）"
        ),
    )
    TRYON_V2_PATTERN_DETAIL_BOOST: bool = Field(
        default=True,
        description="启用频率分离增强保护图案细节（unsharp mask + 高频叠加，图案衣服专用）",
    )

    TRYON_V2_PREFLIGHT_QC_ENABLED: bool = Field(
        default=True,
        description="Enable preflight hard-gate QC before color fidelity injection",
    )
    TRYON_V2_FIDELITY_GUARD_BAND_MIN: float = Field(
        default=0.38,
        description="Lower bound for hysteresis guard band in engine selection",
    )
    TRYON_V2_FIDELITY_GUARD_BAND_MAX: float = Field(
        default=0.45,
        description="Upper bound for hysteresis guard band in engine selection",
    )
    TRYON_V2_ADAPTIVE_PATTERN_ENHANCE_ENABLED: bool = Field(
        default=True,
        description="Enable adaptive pattern enhance strength and artifact-triggered disable",
    )

    # Subscription & quota
    USAGE_QUOTA_ENABLED: bool = Field(default=False, description="启用后执行功能额度扣减")
    FREE_QUOTA_SMART_OUTFIT: int = Field(default=60, description="免费用户每月智能穿搭次数")
    FREE_QUOTA_TRYON: int = Field(default=30, description="免费用户每月试衣次数")
    FREE_QUOTA_ANALYSIS: int = Field(default=200, description="免费用户每月分析次数")
    PRO_QUOTA_SMART_OUTFIT: int = Field(default=9999, description="Pro 用户每月智能穿搭次数")
    PRO_QUOTA_TRYON: int = Field(default=9999, description="Pro 用户每月试衣次数")
    PRO_QUOTA_ANALYSIS: int = Field(default=9999, description="Pro 用户每月分析次数")

    SUBSCRIPTION_CURRENCY: str = Field(default="CNY", description="订阅币种")
    SUBSCRIPTION_PRO_MONTHLY_PRICE_CENTS: int = Field(default=1900, description="Pro 月费，分")
    SUBSCRIPTION_PRO_DURATION_DAYS: int = Field(default=30, description="Pro 有效天数")

    PAYMENT_PROVIDER_NAME: str = Field(default="local_hmac", description="支付提供方标识")
    PAYMENT_SIGNING_SECRET: str = Field(default="dev-secret", description="支付验签密钥")
    PAYMENT_REQUIRE_SIGNATURE: bool = Field(default=True, description="是否强制签名校验")

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

    # Rate Limiting（默认开启；pytest 通过环境变量 ENABLE_RATE_LIMIT=false 关闭）
    ENABLE_RATE_LIMIT: bool = Field(
        default=True,
        description="启用后按 IP 滑动窗口限制请求（RATE_LIMIT_PER_MINUTE 次/分钟）",
    )
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=60,
        description="每分钟上限；仅当 ENABLE_RATE_LIMIT=true 时启用",
    )
    RATE_LIMIT_TRYON_PER_MINUTE: int = Field(
        default=10,
        description="试衣接口每分钟上限（/api/v1/tryon, /api/v2/tryon），0 则使用全局限制",
    )

    # Release ledger（CD/部署脚本写入 manifest 或下列环境变量；供 /release 台账）
    RELEASE_MANIFEST_PATH: str = Field(
        default="",
        description="可选 JSON 路径：frontend_index_sha256、backend_git_commit、deploy_time_utc",
    )
    RELEASE_FRONTEND_INDEX_SHA256: str = ""
    RELEASE_BACKEND_GIT_COMMIT: str = ""
    RELEASE_DEPLOY_TIME_UTC: str = ""

    # 内网 HTML 看板：仅展示聚合指标 + 台账摘要，不含密钥
    OPS_DASHBOARD_ENABLED: bool = Field(
        default=False,
        description="为 true 时开放 /ops/dependency-board（须在网关后限制访问）",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Create global settings instance
settings = Settings()
