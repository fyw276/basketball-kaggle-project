"""
完整功能测试脚本

测试所有 API 端点的功能
"""

import sys

import requests

# 配置
BASE_URL = "http://localhost:8000"
TEST_USERNAME = "test_all_features_user"
TEST_EMAIL = "test_all@example.com"
TEST_PASSWORD = "TestPassword123"

# 全局变量
access_token = None
user_id = None
profile_id = None
garment_id = None


def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_test(test_name, passed, details=""):
    """打印测试结果"""
    status = "✓" if passed else "✗"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{status}{reset} {test_name}")
    if details:
        print(f"  {details}")


def test_health_check():
    """测试健康检查端点"""
    print_section("1. 健康检查")

    try:
        response = requests.get(f"{BASE_URL}/health")
        passed = response.status_code == 200 and response.json().get("status") == "healthy"
        print_test(
            "GET /health",
            passed,
            f"状态码: {response.status_code}, 响应: {response.json()}",
        )
        return passed
    except Exception as e:
        print_test("GET /health", False, f"错误: {e}")
        return False


def test_root_endpoint():
    """测试根端点"""
    try:
        response = requests.get(f"{BASE_URL}/")
        passed = response.status_code == 200 and "Smart Outfit Assistant" in response.json().get(
            "name", ""
        )
        print_test(
            "GET /",
            passed,
            f"状态码: {response.status_code}, 应用: {response.json().get('name')}",
        )
        return passed
    except Exception as e:
        print_test("GET /", False, f"错误: {e}")
        return False


def test_register():
    """测试用户注册"""
    print_section("2. 用户注册")

    try:
        # 先尝试删除已存在的测试用户（如果有）
        payload = {"username": TEST_USERNAME, "email": TEST_EMAIL, "password": TEST_PASSWORD}

        response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=payload)

        if response.status_code == 201:
            global user_id
            user_id = response.json().get("user_id")
            print_test(
                "POST /api/v1/auth/register",
                True,
                f"用户创建成功, ID: {user_id}",
            )
            return True
        elif response.status_code == 400 and "already registered" in response.json().get(
            "detail", ""
        ):
            print_test(
                "POST /api/v1/auth/register",
                True,
                "用户已存在（这是正常的）",
            )
            return True
        else:
            print_test(
                "POST /api/v1/auth/register",
                False,
                f"状态码: {response.status_code}, 响应: {response.json()}",
            )
            return False
    except Exception as e:
        print_test("POST /api/v1/auth/register", False, f"错误: {e}")
        return False


def test_login():
    """测试用户登录"""
    print_section("3. 用户登录")

    try:
        payload = {"username": TEST_USERNAME, "password": TEST_PASSWORD}

        response = requests.post(f"{BASE_URL}/api/v1/auth/login", json=payload)

        if response.status_code == 200:
            global access_token
            access_token = response.json().get("access_token")
            print_test(
                "POST /api/v1/auth/login",
                True,
                f"登录成功, Token: {access_token[:20]}...",
            )
            return True
        else:
            print_test(
                "POST /api/v1/auth/login",
                False,
                f"状态码: {response.status_code}, 响应: {response.json()}",
            )
            return False
    except Exception as e:
        print_test("POST /api/v1/auth/login", False, f"错误: {e}")
        return False


def test_get_current_user():
    """测试获取当前用户信息"""
    print_section("4. 获取用户信息")

    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(f"{BASE_URL}/api/v1/users/me", headers=headers)

        if response.status_code == 200:
            user_data = response.json()
            print_test(
                "GET /api/v1/users/me",
                True,
                f"用户名: {user_data.get('username')}, 邮箱: {user_data.get('email')}",
            )
            return True
        else:
            print_test(
                "GET /api/v1/users/me",
                False,
                f"状态码: {response.status_code}",
            )
            return False
    except Exception as e:
        print_test("GET /api/v1/users/me", False, f"错误: {e}")
        return False


def test_create_profile():
    """测试创建用户画像"""
    print_section("5. 创建用户画像")

    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "height": 170,
            "body_type": "矩形",  # 修正：使用有效的体型值
            "skin_tone": "冷白",
            "style_preference": ["通勤", "简约"],
            "budget_range": "中等",
            "avoid_body_parts": ["肩"],  # 修正：使用有效的身体部位值
        }

        response = requests.post(f"{BASE_URL}/api/v1/profile", json=payload, headers=headers)

        if response.status_code == 201:
            global profile_id
            profile_id = response.json().get("profile_id")
            print_test(
                "POST /api/v1/profile",
                True,
                f"画像创建成功, ID: {profile_id}",
            )
            return True
        elif response.status_code == 400 and "already exists" in response.json().get("detail", ""):
            print_test(
                "POST /api/v1/profile",
                True,
                "画像已存在（这是正常的）",
            )
            return True
        else:
            print_test(
                "POST /api/v1/profile",
                False,
                f"状态码: {response.status_code}, 响应: {response.json()}",
            )
            return False
    except Exception as e:
        print_test("POST /api/v1/profile", False, f"错误: {e}")
        return False


def test_get_profile():
    """测试获取用户画像"""
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(f"{BASE_URL}/api/v1/profile", headers=headers)

        if response.status_code == 200:
            profile_data = response.json()
            print_test(
                "GET /api/v1/profile",
                True,
                f"身高: {profile_data.get('height')}cm, 体型: {profile_data.get('body_type')}",
            )
            return True
        else:
            print_test(
                "GET /api/v1/profile",
                False,
                f"状态码: {response.status_code}",
            )
            return False
    except Exception as e:
        print_test("GET /api/v1/profile", False, f"错误: {e}")
        return False


def test_update_profile():
    """测试更新用户画像"""
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {"height": 175, "budget_range": "高端"}

        response = requests.put(f"{BASE_URL}/api/v1/profile", json=payload, headers=headers)

        if response.status_code == 200:
            print_test(
                "PUT /api/v1/profile",
                True,
                "画像更新成功",
            )
            return True
        else:
            print_test(
                "PUT /api/v1/profile",
                False,
                f"状态码: {response.status_code}",
            )
            return False
    except Exception as e:
        print_test("PUT /api/v1/profile", False, f"错误: {e}")
        return False


def test_recognition_categories():
    """测试获取品类列表"""
    print_section("6. 图像识别功能")

    try:
        response = requests.get(f"{BASE_URL}/api/v1/recognition/categories")

        if response.status_code == 200:
            categories = response.json().get("categories", [])
            print_test(
                "GET /api/v1/recognition/categories",
                True,
                f"可用品类: {', '.join(categories)}",
            )
            return True
        else:
            print_test(
                "GET /api/v1/recognition/categories",
                False,
                f"状态码: {response.status_code}",
            )
            return False
    except Exception as e:
        print_test("GET /api/v1/recognition/categories", False, f"错误: {e}")
        return False


def test_wardrobe_list():
    """测试查询衣橱"""
    print_section("7. 衣橱管理功能")

    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(f"{BASE_URL}/api/v1/wardrobe/garments", headers=headers)

        if response.status_code == 200:
            garments = response.json().get("garments", [])
            print_test(
                "GET /api/v1/wardrobe/garments",
                True,
                f"衣橱中有 {len(garments)} 件服饰",
            )
            return True
        else:
            print_test(
                "GET /api/v1/wardrobe/garments",
                False,
                f"状态码: {response.status_code}",
            )
            return False
    except Exception as e:
        print_test("GET /api/v1/wardrobe/garments", False, f"错误: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  智能穿搭助手 - 完整功能测试")
    print("=" * 60)
    print(f"\n测试服务器: {BASE_URL}")
    print(f"测试用户: {TEST_USERNAME}")
    print()

    results = []

    # 基础测试
    results.append(("健康检查", test_health_check()))
    results.append(("根端点", test_root_endpoint()))

    # 认证测试
    results.append(("用户注册", test_register()))
    results.append(("用户登录", test_login()))

    if not access_token:
        print("\n⚠️  登录失败，无法继续测试需要认证的端点")
        print_summary(results)
        return

    # 用户信息测试
    results.append(("获取用户信息", test_get_current_user()))

    # 用户画像测试
    results.append(("创建用户画像", test_create_profile()))
    results.append(("获取用户画像", test_get_profile()))
    results.append(("更新用户画像", test_update_profile()))

    # 图像识别测试
    results.append(("获取品类列表", test_recognition_categories()))

    # 衣橱管理测试
    results.append(("查询衣橱", test_wardrobe_list()))

    # 打印总结
    print_summary(results)


def print_summary(results):
    """打印测试总结"""
    print("\n" + "=" * 60)
    print("  测试总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print(f"\n通过: {passed}/{total} 项测试")
    print()

    if passed == total:
        print("✅ 所有测试通过！后端功能正常。")
    else:
        print(f"⚠️  {total - passed} 项测试失败")
        print("\n失败的测试:")
        for name, result in results:
            if not result:
                print(f"  ✗ {name}")

    print()
    print("注意:")
    print("- 图像识别、相似度分析、搭配推荐、适合度评分需要上传图片")
    print("- 这些功能请在 Swagger UI 中手动测试")
    print("- 访问: http://localhost:8000/docs")
    print()


if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
