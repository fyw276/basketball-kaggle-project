# AI 穿搭推荐（Vite + React）

本目录为可选的 **演示前端**，用于调用后端的 **`POST /predict`**（穿搭风格分 + Top3 推荐 + 中文解释）。主产品客户端为仓库根目录下的 **`mobile/`**（Flutter）。

## 前置条件

- 已训练并放置 **`model/model.pkl`**（仓库根目录，与 `backend` 训练脚本一致）。
- 已启动 predict 服务之一：
  - **独立进程**（默认端口 **8765**）：在仓库根目录执行
    `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765`
    或使用 `scripts/run_predict_api.ps1`。
  - 或启动 **`app.main`**，其同样提供 **`POST /predict`**（端口见 `backend/.env` 的 `PORT`，常为 8010）。

## 配置

复制 `frontend/.env.example` 为 `frontend/.env`（可选）：

- `VITE_API_BASE`：predict 服务根 URL，**无尾斜杠**，例如 `http://127.0.0.1:8765`。
  未设置时默认 `http://127.0.0.1:8765`。

## 运行

```bash
cd frontend
npm install
npm run dev
```

浏览器访问终端输出的本地地址（通常为 `http://127.0.0.1:5173`）。

## 与 Flutter / 后端的统一说明

完整契约、端口与虚拟试衣相关说明见仓库 **[docs/AI_OUTFIT_PREDICT_AND_TRYON.md](../docs/AI_OUTFIT_PREDICT_AND_TRYON.md)**。
