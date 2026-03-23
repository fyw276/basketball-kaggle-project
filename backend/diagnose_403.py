"""
诊断 403 Forbidden 错误
"""

import sys

from jose import jwt
from sqlalchemy import create_engine, text

from app.core.config import settings


def diagnose_403(token: str = None):
    """诊断 403 错误"""
    print("\n" + "=" * 60)
    print("403 Forbidden 错误诊断")
    print("=" * 60 + "\n")

    # 创建数据库连接
    engine = create_engine(settings.DATABASE_URL)

    # 步骤 1: 检查所有用户的 is_active 状态
    print("步骤 1: 检查数据库中的用户状态")
    print("-" * 60)

    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
            SELECT user_id, username, email, is_active,
                   CASE
                       WHEN is_active = 1 THEN '激活'
                       WHEN is_active = 0 THEN '未激活'
                       WHEN is_active IS NULL THEN 'NULL'
                       ELSE '未知'
                   END as status_text,
                   typeof(is_active) as type
            FROM users
            ORDER BY created_at DESC
        """
            )
        )

        users = result.fetchall()

        if not users:
            print("❌ 数据库中没有用户")
            return

        print(f"找到 {len(users)} 个用户:\n")

        for user in users:
            user_id, username, email, is_active, status_text, type_name = user

            print(f"用户名: {username}")
            print(f"邮箱: {email}")
            print(f"用户 ID: {user_id}")
            print(f"is_active 值: {is_active}")
            print(f"is_active 类型: {type_name}")
            print(f"状态: {status_text}")

            # Python 布尔值检查
            if is_active:
                print("Python 布尔检查: ✅ True (用户应该可以访问)")
            else:
                print("Python 布尔检查: ❌ False (会导致 403 错误)")

            print("-" * 60)

    # 步骤 2: 如果提供了 Token，解码并检查
    if token:
        print("\n步骤 2: 解码 Token 并检查用户")
        print("-" * 60)

        try:
            payload = jwt.decode(
                token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )

            user_id = payload.get("sub")
            username = payload.get("username")

            print(f"Token 中的用户 ID: {user_id}")
            print(f"Token 中的用户名: {username}")

            # 查询这个用户
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT username, email, is_active FROM users WHERE user_id = :user_id"),
                    {"user_id": user_id},
                )

                user = result.fetchone()

                if user:
                    username_db, email, is_active = user
                    print("\n数据库中的用户信息:")
                    print(f"  用户名: {username_db}")
                    print(f"  邮箱: {email}")
                    print(f"  is_active: {is_active}")
                    print(f"  is_active 类型: {type(is_active).__name__}")

                    if is_active:
                        print("\n✅ 用户已激活，不应该出现 403 错误")
                        print("可能的原因:")
                        print("  1. Token 已过期，请重新登录")
                        print("  2. 缓存问题，请清除浏览器缓存")
                        print("  3. 使用了旧的 Token")
                    else:
                        print("\n❌ 用户未激活，这就是 403 错误的原因")
                        print("\n修复方法:")
                        print("  运行: python fix_user_activation.py")
                else:
                    print(f"\n❌ 数据库中找不到用户 ID: {user_id}")

        except Exception as e:
            print(f"❌ Token 解码失败: {e}")

    # 步骤 3: 提供解决方案
    print("\n" + "=" * 60)
    print("解决方案")
    print("=" * 60 + "\n")

    print("如果用户显示为'未激活':")
    print("  1. 运行: python fix_user_activation.py")
    print("  2. 重新登录获取新 Token")
    print("  3. 在 Swagger UI 中重新授权")
    print()
    print("如果用户显示为'激活'但仍然 403:")
    print("  1. 重新登录获取新 Token")
    print("  2. 确保使用最新的 Token")
    print("  3. 检查 Token 是否过期（24 小时有效期）")
    print()
    print("如果 is_active 值为 0 而不是 1:")
    print("  这是 SQLite 布尔值问题")
    print("  运行: python fix_user_activation.py")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        token = sys.argv[1]
        diagnose_403(token)
    else:
        print("用法: python diagnose_403.py [token]")
        print("\n不带 Token 参数运行，只检查数据库状态:")
        diagnose_403()
