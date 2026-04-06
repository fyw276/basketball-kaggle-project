"""
本地搭配风格分预测 API（独立 FastAPI 应用，与 app.main 并存）。

与 app.main 共用同一模型与响应：`POST /predict` 返回 score、recommendations、explanation。

启动（必须在仓库根目录执行，Swagger: http://127.0.0.1:8765/docs）::

  python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8765

若出现 WinError 10013：换端口、去掉 --reload、或检查 netsh 排除端口范围（见 scripts/run_predict_api.ps1 注释）。
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# 与 `python -m uvicorn app.main:app`（cwd=backend）一致，使 `app` 包可导入
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.outfit_style_predict import (  # noqa: E402
    PredictRequest,
    PredictResponse,
    ensure_pipeline,
    predict_impl,
)

_logger = logging.getLogger("outfit_predict_api")
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "app.log"


def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO)
    _logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    try:
        ensure_pipeline()
    except FileNotFoundError as e:
        _logger.error("模型文件不存在: %s — 请先运行 python backend/train_model.py", e)
        raise RuntimeError(str(e)) from e
    yield


app = FastAPI(title="Outfit Style Score API", lifespan=lifespan)

# 本地前端（Vite / Flutter Web 任意端口）跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "outfit-style-predict",
        "docs": "/docs",
        "predict": "POST /predict",
    }


@app.post("/predict", response_model=PredictResponse)
def predict(body: PredictRequest) -> PredictResponse:
    try:
        return predict_impl(body)
    except Exception as e:
        _logger.exception("predict failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
