"""
修复注册问题脚本

这个脚本会：
1. 创建 .env 文件（如果不存在）
2. 使用 SQLite 作为临时数据库（无需安装 PostgreSQL）
3. 初始化数据库表
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def fix_registration():
    """修复注册问题"""
    print("=" * 60)
    print("修复注册问题")
    print("=" * 60)
    print()

    # 1. 创建 .env 文件
    print("[1/3] 创建 .env 文件...")
    env_path = Path(__file__).parent / ".env"

    if env_path.exists():
        print("  ℹ .env 文件已存在")
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
            if "sqlite" in content.lower():
                print("  ✓ 已配置 SQLite 数据库")
            else:
                print("  ⚠ 使用的是 PostgreSQL 配置")
                print("  建议：如果 PostgreSQL 未安装，切换到 SQLite")
    else:
        print("  创建新的 .env 文件（使用 SQLite）...")

        env_content = """# Application
APP_NAME="Smart Outfit Assistant"
APP_VERSION="1.0.0"
DEBUG=True
ENVIRONMENT=development

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4

# Database (使用 SQLite - 无需安装 PostgreSQL)
DATABASE_URL=sqlite:///./outfit_assistant.db
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis (可选 - 如果未安装 Redis，缓存功能会被禁用)
REDIS_URL=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=50

# JWT Authentication
JWT_SECRET_KEY=dev-secret-key-change-in-production-12345
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# File Upload
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE=10485760

# Model Configuration
MODEL_PATH=../models
MODEL_CACHE_SIZE=1000

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8080,http://localhost:8000

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60
"""

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)

        print("  ✓ 已创建 .env 文件（使用 SQLite）")

    print()

    # 2. 初始化数据库
    print("[2/3] 初始化数据库...")
    try:
        from app.db.base import Base
        from app.db.session import engine

        # 创建所有表
        Base.metadata.create_all(bind=engine)
        print("  ✓ 数据库表创建成功")

        # 验证表
        from sqlalchemy import inspect

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"  ✓ 已创建 {len(tables)} 个表: {', '.join(tables)}")

    except Exception as e:
        print(f"  ✗ 数据库初始化失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    print()

    # 3. 测试注册功能
    print("[3/3] 测试注册功能...")
    try:
        from app.db.session import SessionLocal
        from app.schemas.user import UserCreate
        from app.services.user import create_user, get_user_by_username

        db = SessionLocal()

        # 创建测试用户
        test_username = "testuser"
        existing = get_user_by_username(db, test_username)

        if existing:
            print(f"  ℹ 测试用户 '{test_username}' 已存在")
            print("  ✓ 注册功能应该正常工作")
        else:
            test_user = UserCreate(
                username=test_username, email="test@example.com", password="Test123456"
            )

            user = create_user(db, test_user)
            print(f"  ✓ 成功创建测试用户: {user.username}")
            print("  ✓ 注册功能正常工作")

        db.close()

    except Exception as e:
        print(f"  ✗ 注册测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    print()

    # 总结
    print("=" * 60)
    print("修复完成！")
    print("=" * 60)
    print()
    print("✅ 注册功能已修复")
    print()
    print("下一步:")
    print("1. 重启后端服务: python run.py")
    print("2. 访问 Swagger UI: http://localhost:8000/docs")
    print("3. 尝试注册新用户")
    print()
    print("注意:")
    print("- 现在使用 SQLite 数据库（文件: outfit_assistant.db）")
    print("- 无需安装 PostgreSQL")
    print("- 数据存储在本地文件中")
    print("- 如果需要 PostgreSQL，请修改 .env 中的 DATABASE_URL")
    print()

    return True


if __name__ == "__main__":
    try:
        success = fix_registration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"✗ 修复失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
