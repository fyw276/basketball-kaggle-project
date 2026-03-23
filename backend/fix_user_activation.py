"""
修复用户激活状态
"""

from sqlalchemy import create_engine, text

from app.core.config import settings


def fix_user_activation():
    """激活所有用户"""
    print("\n" + "=" * 60)
    print("修复用户激活状态")
    print("=" * 60 + "\n")

    # 创建数据库连接
    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        # 查询未激活的用户
        result = conn.execute(
            text(
                """
            SELECT user_id, username, email, is_active
            FROM users
            WHERE is_active = 0 OR is_active IS NULL
        """
            )
        )

        inactive_users = result.fetchall()

        if not inactive_users:
            print("✅ 所有用户都已激活，无需修复")
            return

        print(f"发现 {len(inactive_users)} 个未激活用户:\n")

        for user in inactive_users:
            user_id, username, email, is_active = user
            print(f"  - {username} ({email}) - is_active={is_active}")

        print("\n正在激活这些用户...")

        # 激活所有用户
        result = conn.execute(
            text(
                """
            UPDATE users
            SET is_active = 1
            WHERE is_active = 0 OR is_active IS NULL
        """
            )
        )

        conn.commit()

        print(f"✅ 成功激活 {result.rowcount} 个用户")

        # 验证
        result = conn.execute(
            text(
                """
            SELECT COUNT(*)
            FROM users
            WHERE is_active = 0 OR is_active IS NULL
        """
            )
        )

        remaining = result.fetchone()[0]

        if remaining == 0:
            print("✅ 验证通过：所有用户都已激活")
        else:
            print(f"⚠️  仍有 {remaining} 个用户未激活")

    print("\n" + "=" * 60)
    print("修复完成")
    print("=" * 60 + "\n")

    print("现在可以重新测试 API 端点了")
    print("如果仍然遇到 403 错误，请重新登录获取新 Token")
    print("\n")


if __name__ == "__main__":
    fix_user_activation()
