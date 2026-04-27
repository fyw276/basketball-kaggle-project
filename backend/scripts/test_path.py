"""测试 CatVTON runner 路径"""

import sys
from pathlib import Path

# 模拟 __file__ 的路径
test_file = Path(
    "D:/Users/omen/OneDrive/桌面/clothing-assistant/backend/app/services/tryon_v2/catvton_engine_client.py"
)
print(f"__file__ = {test_file}")

backend_dir = test_file.parent.parent.parent  # backend/app/
print(f"backend_dir = {backend_dir}")

workspace_root = test_file
for _ in range(5):
    workspace_root = workspace_root.parent
print(f"workspace_root = {workspace_root}")

runner_path = workspace_root / "vton_inference_service" / "catvton_runner.py"
print(f"runner_path = {runner_path}")
print(f"exists = {runner_path.exists()}")
