# 专用 VTON 本地 PoC 跑通记录（OOTDiffusion / IDM-VTON）

在**独立虚拟环境**中操作，避免与主应用 [`backend/requirements.txt`](../../backend/requirements.txt) 的 PyTorch / TensorFlow 版本冲突。GPU 驱动与 CUDA 需与所选仓库 README 一致。

## 1. 选型（推荐首 PoC：OOTDiffusion）

| 项目 | 克隆命令 | 备注 |
|------|----------|------|
| OOTDiffusion | `git clone https://github.com/levihsu/OOTDiffusion.git` | 品类：full-body 常为 upper=0 / lower=1 / dress=2，见官方 README |
| IDM-VTON | `git clone https://github.com/yisol/IDM-VTON.git` | VITON-HD 与 DressCode 两套推理脚本；`--category` 因脚本而异 |

**许可证**：两者常见为 **CC BY-NC-SA 4.0**，商用前需自行评估。

## 2. 环境

```text
python -m venv .venv-vton
.\.venv-vton\Scripts\activate   # Windows
pip install -U pip
# 按官方 README 安装 PyTorch（CUDA）后再安装仓库依赖
pip install -r requirements.txt
```

## 3. 权重与单次推理

- 按官方说明从 [Hugging Face](https://huggingface.co/) 拉取 checkpoint（可配置 `HF_ENDPOINT` 镜像）。
- 使用官方提供的 `run` / `inference` 命令对 **1 张人物 + 1 张商品** 跑通，记录下面表格。

## 4. 结果记录表（主观 + 客观）

| 样例 ID | 品类（上装/下装/裙） | 人物图分辨率 | 商品图 | 峰值显存 (GB) | 耗时 (s) | 主观（1–5：身份/商品一致） | 备注 |
|---------|----------------------|--------------|--------|----------------|----------|-----------------------------|------|
| S1 | | | | | | | |
| S2 | | | | | | | |
| S3 | | | | | | | |

**建议样例**：人物 **全身正面**；商品 **无模特白底**；避免「连衣裙人物 + 裤子商品」等互斥组合。

## 5. 接入主应用

推理稳定后，用 **HTTP 封装**（可使用仓库 [`vton_inference_service`](../../vton_inference_service/) 作为起点，将 Stub 替换为真实调用），主应用 `.env` 设置：

```env
VTON_INFERENCE_URL=http://127.0.0.1:8011/v1/tryon
```

并关闭百炼或按需调整优先级，见 [`docs/VTON_INTEGRATION.md`](../../docs/VTON_INTEGRATION.md)。

## 6. 参考

- Windows CUDA 与 PyTorch 版本勿与主 venv 混装：[`docs/PYTORCH_CUDA_WINDOWS.md`](../../docs/PYTORCH_CUDA_WINDOWS.md)。
