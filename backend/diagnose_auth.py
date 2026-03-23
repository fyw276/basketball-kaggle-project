"""
诊断认证问题
"""

import requests

BASE_URL = "http://localhost:8000"


def test_auth_flow():
    """测试完整的认证流程"""
    print("\n" + "=" * 60)
    print("认证流程诊断")
    print("=" * 60 + "\n")

    # 步骤 1: 注册
    print("步骤 1: 注册用户")
    print("-" * 60)

    register_data = {
        "username": "diagnose_user",
        "email": "diagnose@test.com",
        "password": "Test123456",
    }

    try:
        response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=register_data)
        print(f"状态码: {response.status_code}")

        if response.status_code == 201:
            print("✅ 注册成功")
            user_data = response.json()
            print(f"用户 ID: {user_data.get('user_id')}")
        elif response.status_code == 400:
            print("⚠️  用户已存在（继续测试）")
        else:
            print(f"❌ 注册失败: {response.text}")
            return
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        print("请确保后端服务正在运行: python run.py")
        return

    # 步骤 2: 登录
    print("\n步骤 2: 登录获取 Token")
    print("-" * 60)

    login_data = {"username": "diagnose_user", "password": "Test123456"}

    try:
        response = requests.post(f"{BASE_URL}/api/v1/auth/login", json=login_data)
        print(f"状态码: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ 登录失败: {response.text}")
            return

        login_response = response.json()
        token = login_response.get("access_token")

        print("✅ 登录成功")
        print(f"Token 类型: {login_response.get('token_type')}")
        print(f"Token 长度: {len(token)}")
        print(f"Token 前 50 字符: {token[:50]}...")

    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return

    # 步骤 3: 测试认证端点
    print("\n步骤 3: 测试认证端点 (GET /api/v1/users/me)")
    print("-" * 60)

    # 测试正确的 Authorization header
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(f"{BASE_URL}/api/v1/users/me", headers=headers)
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            print("✅ 认证成功")
            user_data = response.json()
            print(f"用户名: {user_data.get('username')}")
            print(f"邮箱: {user_data.get('email')}")
        else:
            print(f"❌ 认证失败: {response.text}")
            print("\n可能的原因:")
            print("  1. Token 格式错误")
            print("  2. Token 已过期")
            print("  3. JWT_SECRET_KEY 不匹配")
            return
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return

    # 步骤 4: 测试创建用户画像
    print("\n步骤 4: 测试创建用户画像 (POST /api/v1/profile)")
    print("-" * 60)

    profile_data = {
        "height": 170,
        "body_type": "矩形",
        "skin_tone": "冷白",
        "style_preference": ["通勤", "简约"],
        "budget_range": "中等",
        "avoid_body_parts": ["肩"],
    }

    try:
        response = requests.post(f"{BASE_URL}/api/v1/profile", json=profile_data, headers=headers)
        print(f"状态码: {response.status_code}")

        if response.status_code == 201:
            print("✅ 创建画像成功")
            profile = response.json()
            print(f"画像 ID: {profile.get('profile_id')}")
            print(f"身高: {profile.get('height')} cm")
            print(f"体型: {profile.get('body_type')}")
        elif response.status_code == 400:
            print("⚠️  画像已存在")
            # 尝试获取现有画像
            response = requests.get(f"{BASE_URL}/api/v1/profile", headers=headers)
            if response.status_code == 200:
                print("✅ 获取现有画像成功")
                profile = response.json()
                print(f"画像 ID: {profile.get('profile_id')}")
        elif response.status_code == 401:
            print("❌ 认证失败 (401 Unauthorized)")
            print(f"响应: {response.text}")
            print("\n这是你遇到的问题！")
            print("\n可能的原因:")
            print("  1. 在 Swagger UI 中，Authorize 时包含了 'Bearer' 前缀")
            print("     ❌ 错误: Bearer eyJhbGci...")
            print("     ✅ 正确: eyJhbGci...")
            print("  2. Token 被截断或复制不完整")
            print("  3. Token 已过期（24 小时有效期）")
            print("\n解决方案:")
            print("  1. 重新登录获取新 Token")
            print("  2. 在 Swagger UI 的 Authorize 对话框中:")
            print("     - 只粘贴 Token 本身")
            print("     - 不要包含 'Bearer' 前缀")
            print("     - 确保 Token 完整（没有被截断）")
        else:
            print(f"❌ 创建画像失败: {response.text}")
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60 + "\n")

    print("如果所有步骤都成功，说明后端认证功能正常。")
    print("如果在 Swagger UI 中仍然遇到 401 错误，请检查:")
    print("  1. Authorize 对话框中是否只输入了 Token（不含 'Bearer'）")
    print("  2. Token 是否完整（没有被截断）")
    print("  3. 是否点击了 'Authorize' 按钮并看到锁图标变为已锁定状态")
    print("\n")


if __name__ == "__main__":
    test_auth_flow()
