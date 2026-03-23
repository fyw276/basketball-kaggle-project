"""
注册错误诊断脚本

检查注册失败的可能原因
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def diagnose_registration():
    """诊断注册问题"""
    print("=" * 60)
    print("注册错误诊断")
    print("=" * 60)
    print()

    issues = []
    suggestions = []

    # 1. 检查数据库连接
    print("[1/5] 检查数据库连接...")
    try:
        from app.db.session import engine

        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            print("  ✓ 数据库连接成功")
    except Exception as e:
        print(f"  ✗ 数据库连接失败: {e}")
        issues.append("数据库连接失败")
        suggestions.append("检查 PostgreSQL 是否运行")
        suggestions.append("检查 .env 文件中的 DATABASE_URL 配置")
        suggestions.append("运行: python scripts/test_db_connection.py")

    print()

    # 2. 检查数据库表
    print("[2/5] 检查数据库表...")
    try:
        from sqlalchemy import inspect

        from app.db.session import engine

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        required_tables = ["users", "user_profiles", "garments"]
        missing_tables = [t for t in required_tables if t not in tables]

        if missing_tables:
            print(f"  ✗ 缺少表: {', '.join(missing_tables)}")
            issues.append(f"缺少数据库表: {', '.join(missing_tables)}")
            suggestions.append("运行数据库迁移: alembic upgrade head")
            suggestions.append("或运行初始化脚本: python scripts/init_db.py")
        else:
            print(f"  ✓ 所有必需的表都存在: {', '.join(required_tables)}")
    except Exception as e:
        print(f"  ✗ 无法检查表: {e}")
        issues.append("无法检查数据库表")

    print()

    # 3. 检查用户服务
    print("[3/5] 检查用户服务...")
    try:
        from app.services.user import create_user

        print("  ✓ 用户服务模块可以导入")
    except Exception as e:
        print(f"  ✗ 用户服务导入失败: {e}")
        issues.append(f"用户服务导入失败: {e}")

    print()

    # 4. 检查密码加密
    print("[4/5] 检查密码加密...")
    try:
        from app.services.auth import hash_password, verify_password

        test_password = "TestPassword123"
        hashed = hash_password(test_password)
        verified = verify_password(test_password, hashed)

        if verified:
            print("  ✓ 密码加密和验证正常")
        else:
            print("  ✗ 密码验证失败")
            issues.append("密码加密验证失败")
    except Exception as e:
        print(f"  ✗ 密码加密测试失败: {e}")
        issues.append(f"密码加密失败: {e}")

    print()

    # 5. 测试用户创建
    print("[5/5] 测试用户创建...")
    try:
        from app.db.session import SessionLocal
        from app.schemas.user import UserCreate
        from app.services.user import create_user, get_user_by_username

        db = SessionLocal()

        # 创建测试用户
        test_user = UserCreate(
            username="test_diagnostic_user",
            email="test_diagnostic@example.com",
            password="TestPassword123",
        )

        # 检查用户是否已存在
        existing = get_user_by_username(db, test_user.username)
        if existing:
            print("  ℹ 测试用户已存在（这是正常的）")
        else:
            # 尝试创建用户
            user = create_user(db, test_user)
            print(f"  ✓ 成功创建测试用户: {user.username}")
            print("  ℹ 注册功能应该正常工作")

        db.close()

    except Exception as e:
        print(f"  ✗ 用户创建测试失败: {e}")
        issues.append(f"用户创建失败: {e}")
        import traceback

        print("\n  详细错误:")
        traceback.print_exc()

    print()

    # 总结
    print("=" * 60)
    print("诊断总结")
    print("=" * 60)
    print()

    if not issues:
        print("✅ 未发现问题，注册功能应该正常工作")
        print()
        print("如果仍然出错，请：")
        print("1. 查看后端服务器日志")
        print("2. 检查浏览器控制台错误")
        print("3. 确认请求数据格式正确")
    else:
        print(f"⚠️  发现 {len(issues)} 个问题：")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")

    print()

    if suggestions:
        print("💡 建议操作：")
        for i, suggestion in enumerate(suggestions, 1):
            print(f"  {i}. {suggestion}")

    print()


if __name__ == "__main__":
    try:
        diagnose_registration()
    except Exception as e:
        print(f"✗ 诊断失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
