#!/usr/bin/env python3
"""
调试 Flutter Web 请求

模拟 Flutter Web 发送的请求，查看详细错误信息
"""

import json

import requests


def test_register_with_details():
    """测试注册并显示详细错误"""
    print("=" * 60)
    print("测试注册 API")
    print("=" * 60)

    url = "http://127.0.0.1:8010/api/v1/auth/register"

    # 测试 1: 正常请求
    print("\n1. 正常请求:")
    data = {"username": "test_user_debug", "email": "debug@test.com", "password": "Test123!@#"}

    try:
        response = requests.post(url, json=data, headers={"Content-Type": "application/json"})

        print(f"   状态码: {response.status_code}")
        print(f"   响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    except Exception as e:
        print(f"   错误: {e}")

    # 测试 2: 密码太短
    print("\n2. 密码太短 (应该返回 422):")
    data = {
        "username": "test_short",
        "email": "short@test.com",
        "password": "Test1",  # 只有 5 个字符
    }

    try:
        response = requests.post(url, json=data, headers={"Content-Type": "application/json"})

        print(f"   状态码: {response.status_code}")
        print(f"   响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    except Exception as e:
        print(f"   错误: {e}")

    # 测试 3: 缺少必填字段
    print("\n3. 缺少 email 字段 (应该返回 422):")
    data = {"username": "test_missing", "password": "Test123!@#"}

    try:
        response = requests.post(url, json=data, headers={"Content-Type": "application/json"})

        print(f"   状态码: {response.status_code}")
        print(f"   响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    except Exception as e:
        print(f"   错误: {e}")

    # 测试 4: 用户名太短
    print("\n4. 用户名太短 (应该返回 422):")
    data = {
        "username": "ab",  # 只有 2 个字符，最少需要 3 个
        "email": "short_username@test.com",
        "password": "Test123!@#",
    }

    try:
        response = requests.post(url, json=data, headers={"Content-Type": "application/json"})

        print(f"   状态码: {response.status_code}")
        print(f"   响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    except Exception as e:
        print(f"   错误: {e}")


def test_login_with_details():
    """测试登录并显示详细错误"""
    print("\n" + "=" * 60)
    print("测试登录 API")
    print("=" * 60)

    url = "http://127.0.0.1:8010/api/v1/auth/login"

    # 测试 1: 用户不存在
    print("\n1. 用户不存在 (应该返回 401):")
    data = {"username": "nonexistent_user", "password": "Test123!@#"}

    try:
        response = requests.post(url, json=data, headers={"Content-Type": "application/json"})

        print(f"   状态码: {response.status_code}")
        print(f"   响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    except Exception as e:
        print(f"   错误: {e}")

    # 测试 2: 密码错误
    print("\n2. 密码错误 (应该返回 401):")
    data = {"username": "test_user_debug", "password": "WrongPassword123!@#"}

    try:
        response = requests.post(url, json=data, headers={"Content-Type": "application/json"})

        print(f"   状态码: {response.status_code}")
        print(f"   响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    except Exception as e:
        print(f"   错误: {e}")

    # 测试 3: 正确的凭据
    print("\n3. 正确的凭据 (应该返回 200):")
    data = {"username": "test_user_debug", "password": "Test123!@#"}

    try:
        response = requests.post(url, json=data, headers={"Content-Type": "application/json"})

        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"   Token 前缀: {result['access_token'][:50]}...")
        else:
            print(f"   响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")

    except Exception as e:
        print(f"   错误: {e}")


def main():
    print("\n🔍 Flutter Web 请求调试工具\n")

    test_register_with_details()
    test_login_with_details()

    print("\n" + "=" * 60)
    print("✅ 调试完成")
    print("=" * 60)
    print("\n💡 提示:")
    print("   - 400 错误通常表示用户名或邮箱已存在")
    print("   - 401 错误表示用户名或密码不正确")
    print("   - 422 错误表示请求数据格式不正确")
    print("\n📝 如果 Flutter Web 遇到这些错误:")
    print("   1. 检查浏览器 Network 标签页中的 Request Payload")
    print("   2. 确认发送的数据格式是否正确")
    print("   3. 查看 Response 中的详细错误信息")


if __name__ == "__main__":
    main()
