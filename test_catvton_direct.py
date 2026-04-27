"""直接测试 CatVTON - 显示所有日志步骤"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_catvton_direct():
    """直接测试 CatVTON 推理流程"""
    import io
    import time
    from PIL import Image
    from app.services.tryon_v2.catvton_engine_client import _run_catvton_sync, _catvton_configured

    print("=" * 60)
    print("CatVTON 直接测试")
    print("=" * 60)

    # 检查配置
    print(f"\n[1] 检查 CatVTON 配置...")
    configured = _catvton_configured()
    print(f"    配置状态: {configured}")

    if not configured:
        print("    错误: CatVTON 未配置！请检查 CATVTON_ENABLED 和 CATVTON_PATH")
        return False

    # 查找测试图片
    test_person = "data/test_person.jpg"
    test_garment = "data/test_garment.jpg"

    if not os.path.exists(test_person):
        print(f"\n[错误] 找不到人物图片: {test_person}")
        # 尝试创建测试图片
        print("    创建测试人物图片...")
        img = Image.new('RGB', (400, 600), color=(200, 180, 160))
        img.save(test_person)

    if not os.path.exists(test_garment):
        print(f"\n[错误] 找不到衣服图片: {test_garment}")
        # 尝试创建测试图片
        print("    创建测试衣服图片...")
        img = Image.new('RGB', (300, 400), color=(100, 50, 50))
        img.save(test_garment)

    # 读取图片
    print(f"\n[2] 读取测试图片...")
    with open(test_person, 'rb') as f:
        person_bytes = f.read()
    print(f"    人物图片大小: {len(person_bytes)} bytes")

    with open(test_garment, 'rb') as f:
        garment_bytes = f.read()
    print(f"    衣服图片大小: {len(garment_bytes)} bytes")

    # 运行 CatVTON
    print(f"\n[3] 开始 CatVTON 推理...")
    print("    (这可能需要 30-60 秒，请耐心等待)")
    print("    如果看到 [CATVTON-RUNNER] 日志，说明正在执行")
    print("-" * 60)

    start_time = time.time()

    result = _run_catvton_sync(
        person_bytes=person_bytes,
        garment_bytes=garment_bytes,
        cloth_type="upper",  # 上装
        timeout=300,  # 5 分钟超时
    )

    elapsed = time.time() - start_time
    print("-" * 60)
    print(f"\n[4] 推理完成，耗时: {elapsed:.1f} 秒")

    # 检查结果
    if result.get("status") == "success":
        print("\n[成功] CatVTON 推理成功！")
        print(f"    消息: {result.get('message')}")
        print(f"    元数据: {result.get('metadata', {}).get('engine', 'N/A')}")

        # 保存结果图片
        result_img = result.get("result_image")
        if result_img:
            output_path = "data/test_result_catvton.jpg"
            result_img.save(output_path)
            print(f"    结果图片已保存到: {output_path}")
        return True
    else:
        print("\n[失败] CatVTON 推理失败！")
        print(f"    状态: {result.get('status')}")
        print(f"    消息: {result.get('message')}")
        print(f"    元数据: {result.get('metadata', {})}")
        return False


if __name__ == "__main__":
    success = test_catvton_direct()
    sys.exit(0 if success else 1)
