# Windows：PyTorch CUDA 与 `pip install -r requirements.txt`

## 你刚才遇到了什么

1. **`torch>=2.6.0` 无上限时**，pip 可能安装 **最新 2.11.x（默认 CPU 轮）**，覆盖你之前手动安装的 **`2.6.0+cu124`**，导致 **CUDA 不可用**；若本机还装了 **`torchaudio 2.6.0+cu124`**，会报 **与当前 torch 版本不一致**。
2. **可选包 `rembg`**（文档里写的「更强抠图」）若已安装，其 **numpy / Pillow** 要求与当前仓库为 **TensorFlow 2.18** 保留的 **`numpy<2.1`** 常见 **冲突**——这不是百炼 DashScope 的问题，而是 **同一 venv 里多栈并存** 的典型现象。
3. **`WARNING: Failed to remove contents in a temporary directory ... ~qlalchemy`**：多为 **文件被占用**（杀毒/索引/仍在运行的 Python）。可 **关掉 uvicorn / IDE 后再装**，或 **退出 venv 后删除** `.venv\Lib\site-packages` 下以 `~` 开头的残留目录。

## 接下来怎么做（推荐顺序）

### 0. 激活虚拟环境（路径别搞错）

本仓库的 **`.venv` 在仓库根目录**，不在 `backend` 里。

- 当前目录是 **仓库根** `clothing-assistant` 时：

  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```

- 当前目录是 **`backend`** 时：

  ```powershell
  ..\.venv\Scripts\Activate.ps1
  ```

### 1. 恢复与本项目约束一致的 PyTorch（CUDA 12.4）

在 **已激活的 `.venv`** 下执行（与 [`backend/requirements.txt`](../backend/requirements.txt) 中 `torch>=2.6.0,<2.7.0` 一致）：

```powershell
pip install "torch==2.6.0+cu124" "torchvision==0.21.0+cu124" --index-url https://download.pytorch.org/whl/cu124
```

若你使用 **torchaudio**，请装 **同系列**（示例）：

```powershell
pip install "torchaudio==2.6.0+cu124" --index-url https://download.pytorch.org/whl/cu124
```

验证：

```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

应看到 **`2.6.0+cu124`** 与 **`True`**（驱动与 CUDA 正常时）。

### 2. 处理 `rembg` 与 numpy 冲突

- **不需要 rembg**：可直接卸载，避免 pip 持续告警：

  ```powershell
  pip uninstall rembg -y
  ```

- **需要 rembg**：建议 **单独虚拟环境** 安装 rembg，或接受与 **TensorFlow + 本仓库 numpy 上界** 的取舍（需自行升级/替换 TF 并全面回归测试，本仓库未默认支持）。

### 3. 以后安装依赖的习惯

- 优先：**只补装缺的包**（例如 `pip install dashscope`），避免反复 **全量** `pip install -r requirements.txt` 覆盖已手工对齐的 CUDA 栈。
- 若必须全量重装：装完后 **再执行一遍** 上面第 1 步的 **PyTorch 官方 cu124 索引** 命令。

## 与阿里云百炼试衣的关系

百炼试衣走 **HTTP API + `dashscope`**，**不依赖本机 GPU**。恢复 PyTorch 是为了 **本机 diffusers 虚拟试衣 / CLIP** 等路径仍可用；若你 **只跑百炼**，只要 **`dashscope` 与后端能启动** 即可，但 **仍建议** 把 torch 版本理顺，避免与其它功能混用时报错。
