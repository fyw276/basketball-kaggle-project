"""
检查用户状态
"""

from sqlalchemy import create_engine, text

from app.core.config import settings


def check_users():
    """检查所有用户的状态"""
    print("\n" + "=" * 60)
    print("用户状态检查")
    print("=" * 60 + "\n")

    # 创建数据库连接
    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        # 查询所有用户
        result = conn.execute(
            text(
                """
            SELECT user_id, username, email, is_active, created_at
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
            user_id, username, email, is_active, created_at = user
            status = "✅ 激活" if is_active else "❌ 未激活"

            print(f"用户名: {username}")
            print(f"邮箱: {email}")
            print(f"用户 ID: {user_id}")
            print(f"状态: {status} (is_active={is_active})")
            print(f"创建时间: {created_at}")
            print("-" * 60)

        # 统计
        active_count = sum(1 for u in users if u[3])
        inactive_count = len(users) - active_count

        print("\n统计:")
        print(f"  激活用户: {active_count}")
        print(f"  未激活用户: {inactive_count}")

        if inactive_count > 0:
            print(f"\n⚠️  发现 {inactive_count} 个未激活用户")
            print("这可能导致 403 Forbidden 错误")

            # 提供修复选项
            print("\n是否要激活所有用户? (y/n): ", end="")
            choice = input().strip().lower()

            if choice == "y":
                # 激活所有用户
                conn.execute(text("UPDATE users SET is_active = 1"))
                conn.commit()
                print("✅ 所有用户已激活")
            else:
                print("未进行修改")

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    check_users()
