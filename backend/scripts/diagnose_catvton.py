"""
CatVTON 诊断脚本 - 验证 CatVTON 是否正常工作

使用方法：
1. 确保后端已启动
2. 运行此脚本查看 CatVTON 诊断信息
3. 或者直接调用 API 并检查返回的 metadata.engine 字段
"""

import json
import os
import sys

import requests

API_BASE = "http://localhost:8010"


def check_model_status():
    """检查所有试衣引擎的状态"""
    print("=" * 60)
    print("检查试衣引擎状态")
    print("=" * 60)

    try:
        # 获取 token (需要先登录)
        # 这里假设你已经有 token，或者直接测试公开端点
        response = requests.get(f"{API_BASE}/api/tryon/v2/model-status")
        print(f"\n[1] Model Status API 响应:")
        print(f"    状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"\n    数据: {json.dumps(data, indent=4, ensure_ascii=False)}")

            # 检查 CatVTON 配置
            if "engines" in data and "catvton_local" in data["engines"]:
                catvton = data["engines"]["catvton_local"]
                print(f"\n[2] CatVTON 详细状态:")
                print(f"    enabled: {catvton.get('enabled')}")
                print(f"    configured: {catvton.get('configured')}")
                print(f"    path: {catvton.get('path')}")
                print(f"    path_exists: {catvton.get('path_exists')}")
                print(f"    model_exists: {catvton.get('model_exists')}")
                print(f"    runner_exists: {catvton.get('runner_exists')}")

                if not catvton.get("model_exists"):
                    print("\n    [!] 警告: CatVTON 模型文件不存在！")
                    print("    这意味着 CatVTON 可能无法正常工作")
        else:
            print(f"    错误: {response.text}")

    except Exception as e:
        print(f"    请求失败: {e}")


def check_log_analysis():
    """分析后端日志中的 CatVTON 调用情况"""
    print("\n" + "=" * 60)
    print("CatVTON 调用分析")
    print("=" * 60)

    print(
        """
要确定 CatVTON 是否被正确调用，请检查后端终端日志：

1. 应该有 "[CATVTON]" 或 "[CATVTON-RUNNER]" 前缀的日志
2. 应该看到类似以下的步骤日志：
   - [CATVTON-STEP] 开始生成衣服遮罩
   - [CATVTON-STEP] 正在加载 CatVTON Pipeline
   - [CATVTON-STEP] 正在缩放图片
   - [CATVTON-STEP] 开始 CatVTON 扩散推理
   - [CATVTON-STEP] 推理完成，耗时 X秒

3. API 返回的 metadata 中应该包含：
   - "engine": "catvton"
   - 而不是 "engine": "warp_preserve"

如果只看到 warp 日志，说明 CatVTON 失败了或未被调用
    """
    )


def suggest_fixes():
    """建议的修复方案"""
    print("\n" + "=" * 60)
    print("可能的修复方案")
    print("=" * 60)

    print(
        """
根据你的情况（结果不符合 CatVTON 预期），可能的原因：

1. CatVTON 模型未正确下载
   - 检查 D:\\models\\CatVTON_full 目录
   - 应该有 mix-48k-1024/attention/model.safetensors 文件
   - 如果没有，运行: python -m huggingface_hub.commands.huggingface_hub download zhengchong/CatVTON

2. CatVTON 返回了错误的结果
   - 可能是因为模型权重损坏
   - 尝试重新下载模型

3. 后处理步骤可能改变了 CatVTON 输出
   - 检查 enhance_tryon_result 函数
   - 尝试禁用后处理

4. 使用 debug_mode=preprocess_only 查看中间产物
   - 这会显示 mask、pose 等是否正确
   - 如果 mask 错误，CatVTON 输出也会错误

建议的测试步骤：
1. 启用 debug_mode=preprocess_only 查看中间产物
2. 检查 03_mask.png 是否覆盖了正确的衣服区域
3. 检查 04_pose_keypoints.jpg 关键点是否准确
    """
    )


if __name__ == "__main__":
    print("CatVTON 诊断工具\n")

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        check_model_status()
    else:
        suggest_fixes()

    check_log_analysis()
