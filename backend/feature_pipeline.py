"""
特征工程与回归管线：分类特征 One-Hot + XGBoost 回归（搭配风格分）。
"""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

# 与 data/final_dataset.csv 列名一致（目标列除外）
CATEGORICAL_FEATURES = [
    "top",
    "bottom",
    "color_top",
    "color_bottom",
    "season",
    "occasion",
]


def build_pipeline(
    n_estimators: int = 100,
    max_depth: int = 4,
    learning_rate: float = 0.1,
    random_state: int = 42,
) -> Pipeline:
    """
    构建 sklearn Pipeline：
    - ColumnTransformer + OneHotEncoder 处理分类特征
    - XGBRegressor 回归预测 style_score
    """
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )

    regressor = XGBRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        random_state=random_state,
        n_jobs=-1,
    )

    return Pipeline(
        steps=[
            ("preprocess", preprocessor),
            ("regressor", regressor),
        ]
    )
