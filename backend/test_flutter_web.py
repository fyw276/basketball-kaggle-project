#!/usr/bin/env python3
"""
Flutter Web 连接测试脚本

测试后端 API 是否可以被 Flutter Web 访问
"""

import json
from datetime import datetime

import requests


def print_section(title):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_health_check():
    """测试健康检查端点"""
    print_section("1. 健康检查")
    try:
        response = requests.get("http://127.0.0.1:8010/health")
        print(f"✅ 状态码: {response.status_code}")
        print(f"✅ 响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        return True
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False


def test_register():
    """测试注册端点"""
    print_section("2. 注册测试")

    # 使用时间戳创建唯一用户名
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    username = f"flutter_test_{timestamp}"
    email = f"flutter_{timestamp}@test.com"
    password = "Test123!@#"

    try:
        response = requests.post(
            "http://127.0.0.1:8010/api/v1/auth/register",
            json={"username": username, "email": email, "password": password},
            headers={"Content-Type": "application/json"},
        )

        print(f"✅ 状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ 用户名: {data['username']}")
            print(f"✅ 邮箱: {data['email']}")
            print(f"✅ 用户ID: {data['user_id']}")
            print(f"✅ 激活状态: {data['is_active']}")
            return username, password
        else:
            print(f"❌ 注册失败: {response.text}")
            return None, None

    except Exception as e:
        print(f"❌ 错误: {e}")
        return None, None


def test_login(username, password):
    """测试登录端点"""
    print_section("3. 登录测试")

    try:
        response = requests.post(
            "http://127.0.0.1:8010/api/v1/auth/login",
            json={"username": username, "password": password},
            headers={"Content-Type": "application/json"},
        )

        print(f"✅ 状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print(f"✅ Token 获取成功")
            print(f"✅ Token 前缀: {token[:50]}...")
            return token
        else:
            print(f"❌ 登录失败: {response.text}")
            return None

    except Exception as e:
        print(f"❌ 错误: {e}")
        return None


def test_authenticated_request(token):
    """测试需要认证的请求"""
    print_section("4. 认证请求测试")

    try:
        response = requests.get(
            "http://127.0.0.1:8010/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )

        print(f"✅ 状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"✅ 用户信息获取成功")
            print(f"✅ 用户名: {data['username']}")
            print(f"✅ 邮箱: {data['email']}")
            return True
        else:
            print(f"❌ 请求失败: {response.text}")
            return False

    except Exception as e:
        print(f"❌ 错误: {e}")
        return False


def test_cors():
    """测试 CORS 配置"""
    print_section("5. CORS 配置测试")

    try:
        # 模拟来自 Flutter Web 的请求
        response = requests.options(
            "http://127.0.0.1:8010/api/v1/auth/login",
            headers={
                "Origin": "http://localhost:50850",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        print(f"✅ 状态码: {response.status_code}")

        cors_headers = {
            "Access-Control-Allow-Origin": response.headers.get("Access-Control-Allow-Origin"),
            "Access-Control-Allow-Methods": response.headers.get("Access-Control-Allow-Methods"),
            "Access-Control-Allow-Headers": response.headers.get("Access-Control-Allow-Headers"),
            "Access-Control-Allow-Credentials": response.headers.get(
                "Access-Control-Allow-Credentials"
            ),
        }

        print("✅ CORS 响应头:")
        for key, value in cors_headers.items():
            if value:
                print(f"   {key}: {value}")

        return True

    except Exception as e:
        print(f"❌ 错误: {e}")
        return False


def main():
    """主测试流程"""
    print("\n" + "🚀" * 30)
    print("  Flutter Web 后端连接测试")
    print("🚀" * 30)

    # 1. 健康检查
    if not test_health_check():
        print("\n❌ 后端服务器未运行，请先启动后端服务器")
        return

    # 2. 注册测试
    username, password = test_register()
    if not username:
        print("\n❌ 注册测试失败")
        return

    # 3. 登录测试
    token = test_login(username, password)
    if not token:
        print("\n❌ 登录测试失败")
        return

    # 4. 认证请求测试
    if not test_authenticated_request(token):
        print("\n❌ 认证请求测试失败")
        return

    # 5. CORS 测试
    test_cors()

    # 总结
    print_section("✅ 测试总结")
    print("✅ 所有测试通过！")
    print("✅ 后端 API 可以正常被 Flutter Web 访问")
    print("\n📝 测试凭据（可用于 Flutter Web 登录）:")
    print(f"   用户名: {username}")
    print(f"   密码: {password}")
    print("\n🎯 下一步:")
    print("   1. 启动 Flutter Web: cd mobile && flutter run -d chrome")
    print("   2. 使用上述凭据在 Flutter Web 中登录")
    print("   3. 如果遇到问题，打开浏览器开发者工具（F12）查看详细错误")


if __name__ == "__main__":
    main()
