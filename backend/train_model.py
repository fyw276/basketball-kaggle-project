"""
读取 data/final_dataset.csv，训练搭配风格分回归模型并保存到 model/model.pkl。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import joblib
import pandas as pd

# 保证可从 backend 目录直接运行
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from feature_pipeline import CATEGORICAL_FEATURES, build_pipeline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "final_dataset.csv"
MODEL_PATH = ROOT / "model" / "model.pkl"
LOG_PATH = ROOT / "logs" / "train.log"
TARGET_COL = "style_score"


def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> None:
    _setup_logging()
    log = logging.getLogger(__name__)

    if not DATA_PATH.is_file():
        log.error("数据文件不存在: %s", DATA_PATH)
        sys.exit(1)

    df = pd.read_csv(DATA_PATH)
    missing = [c for c in CATEGORICAL_FEATURES + [TARGET_COL] if c not in df.columns]
    if missing:
        log.error("CSV 缺少列: %s", missing)
        sys.exit(1)

    X = df[CATEGORICAL_FEATURES]
    y = df[TARGET_COL]

    log.info("样本数: %d, 特征: %s", len(df), CATEGORICAL_FEATURES)

    pipeline = build_pipeline()
    pipeline.fit(X, y)
    log.info("训练完成。")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    log.info("模型已保存: %s", MODEL_PATH)


if __name__ == "__main__":
    main()
