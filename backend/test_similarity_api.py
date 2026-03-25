"""
测试相似度分析 API 的脚本

使用方法:
python test_similarity_api.py
"""

from pathlib import Path

import requests

# API 基础 URL
BASE_URL = "http://localhost:8000/api/v1"

# 测试用户凭据
USERNAME = "testuser"
PASSWORD = "Test123!@#"
EMAIL = "test@example.com"


def register_user():
    """注册测试用户"""
    print("1. 注册测试用户...")
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={"username": USERNAME, "email": EMAIL, "password": PASSWORD},
    )

    if response.status_code == 201:
        print("✓ 用户注册成功")
        return True
    elif response.status_code == 400:
        print("✓ 用户已存在，跳过注册")
        return True
    else:
        print(f"✗ 注册失败: {response.status_code}")
        print(response.json())
        return False


def login_user():
    """登录并获取 token"""
    print("\n2. 登录获取 token...")
    response = requests.post(
        f"{BASE_URL}/auth/login", json={"username": USERNAME, "password": PASSWORD}
    )

    if response.status_code == 200:
        token = response.json()["access_token"]
        print(f"✓ 登录成功，token: {token[:20]}...")
        return token
    else:
        print(f"✗ 登录失败: {response.status_code}")
        print(response.json())
        return None


def test_similarity_api(token, image_path=None):
    """测试相似度分析 API"""
    print("\n3. 测试相似度分析 API...")

    # 如果没有提供图片，创建一个测试图片
    if not image_path:
        import io

        from PIL import Image

        # 创建测试图片
        img = Image.new("RGB", (224, 224), color=(100, 150, 200))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        files = {"file": ("test.jpg", img_bytes, "image/jpeg")}
    else:
        files = {"file": open(image_path, "rb")}

    headers = {"Authorization": f"Bearer {token}"}

    response = requests.post(f"{BASE_URL}/analysis/similarity", headers=headers, files=files)

    if response.status_code == 200:
        print("✓ 相似度分析成功")
        result = response.json()
        print(f"  - 目标服饰品类: {result['target_garment']['category']}")
        print(f"  - 相似服饰数量: {len(result['similar_garments'])}")
        print(f"  - 重复预警: {result['has_duplicate_warning']}")
        print(f"  - 推荐信息: {result['recommendation']}")
        return True
    else:
        print(f"✗ 相似度分析失败: {response.status_code}")
        print(response.json())
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("相似度分析 API 测试")
    print("=" * 60)

    # 1. 注册用户
    if not register_user():
        return

    # 2. 登录获取 token
    token = login_user()
    if not token:
        return

    # 3. 测试相似度分析 API
    test_similarity_api(token)

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n如何在 Swagger UI 中使用:")
    print("1. 访问 http://localhost:8000/docs")
    print("2. 点击右上角的 'Authorize' 按钮")
    print(f"3. 输入: Bearer {token}")
    print("4. 点击 'Authorize' 然后 'Close'")
    print("5. 现在可以测试需要认证的 API 了")


if __name__ == "__main__":
    main()
