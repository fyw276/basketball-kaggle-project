"""
训练脚本包

包含以下模块：
- data_preprocessor: 数据预处理和特征提取
- feature_extractor_trainer: CLIP 特征提取器微调
- category_trainer: 类别分类器训练
- style_trainer: 风格分类器训练
- color_trainer: 颜色分类器训练
- data_annotator: 数据标注工具
"""

from .clip_finetuner import CLIPFineTuner
from .data_preprocessor import DataPreprocessor
from .trainer_registry import TrainerRegistry

__all__ = [
    "DataPreprocessor",
    "CLIPFineTuner",
    "TrainerRegistry",
]
