"""
测试 JWT Token 的有效性
"""

import sys

from jose import JWTError, jwt

from app.core.config import settings


def test_token(token: str):
    """测试 Token 是否有效"""
    print(f"\n{'='*60}")
    print("JWT Token 测试")
    print(f"{'='*60}\n")

    print(f"Token 长度: {len(token)}")
    print(f"Token 前 50 字符: {token[:50]}...")
    print("\nJWT 配置:")
    print(f"  SECRET_KEY: {settings.JWT_SECRET_KEY}")
    print(f"  ALGORITHM: {settings.JWT_ALGORITHM}")
    print(f"  EXPIRATION: {settings.JWT_EXPIRATION_HOURS} hours")

    print(f"\n{'='*60}")
    print("解码测试")
    print(f"{'='*60}\n")

    try:
        # 尝试解码
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        print("✅ Token 解码成功！")
        print("\nPayload 内容:")
        for key, value in payload.items():
            print(f"  {key}: {value}")

        # 检查必需字段
        if "sub" in payload:
            print(f"\n✅ 包含 'sub' 字段 (user_id): {payload['sub']}")
        else:
            print("\n❌ 缺少 'sub' 字段")

        if "exp" in payload:
            from datetime import datetime

            exp_time = datetime.fromtimestamp(payload["exp"])
            now = datetime.now()
            print("✅ 包含 'exp' 字段")
            print(f"  过期时间: {exp_time}")
            print(f"  当前时间: {now}")
            if exp_time > now:
                print("  ✅ Token 未过期")
            else:
                print("  ❌ Token 已过期")
        else:
            print("\n❌ 缺少 'exp' 字段")

    except JWTError as e:
        print("❌ Token 解码失败！")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")

        # 尝试不验证签名解码
        print("\n尝试不验证签名解码...")
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            print("✅ 不验证签名解码成功")
            print(f"Payload: {payload}")
            print("\n可能的问题:")
            print("  1. JWT_SECRET_KEY 不匹配")
            print("  2. JWT_ALGORITHM 不匹配")
        except Exception as e2:
            print(f"❌ 仍然失败: {e2}")
            print("\n可能的问题:")
            print("  1. Token 格式错误")
            print("  2. Token 被截断或损坏")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python test_token.py <your_token>")
        print("\n示例:")
        print('python test_token.py "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."')
        sys.exit(1)

    token = sys.argv[1]
    test_token(token)
