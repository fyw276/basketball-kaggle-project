"""
训练器注册表 - 统一管理所有训练任务
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Type

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import setup_logging

logger = setup_logging()


class TrainerRegistry:
    """训练器注册表"""

    _trainers: Dict[str, Type] = {}

    @classmethod
    def register(cls, name: str):
        """注册训练器"""
        def decorator(trainer_class: Type):
            cls._trainers[name] = trainer_class
            logger.info(f"Registered trainer: {name}")
            return trainer_class
        return decorator

    @classmethod
    def get(cls, name: str):
        """获取训练器"""
        if name not in cls._trainers:
            raise ValueError(f"Unknown trainer: {name}. Available: {list(cls._trainers.keys())}")
        return cls._trainers[name]

    @classmethod
    def list_trainers(cls) -> List[str]:
        """列出所有训练器"""
        return list(cls._trainers.keys())

    @classmethod
    def get_info(cls, name: str) -> Dict:
        """获取训练器信息"""
        trainer_class = cls.get(name)
        return {
            "name": name,
            "class": trainer_class.__name__,
            "description": trainer_class.__doc__ or "No description",
        }


def list_available_training_tasks() -> Dict:
    """列出所有可用的训练任务"""
    return {
        "available_trainers": TrainerRegistry.list_trainers(),
        "tasks": [
            {
                "id": "reextract_features",
                "name": "重新提取特征向量",
                "description": "从 CLIP 模型重新提取所有衣物的特征向量，修复零向量问题",
                "command": "python scripts/training/main_train.py --task reextract",
            },
            {
                "id": "finetune_clip",
                "name": "微调 CLIP 模型",
                "description": "使用已有标注数据微调 CLIP 模型，提高服装识别准确性",
                "command": "python scripts/training/main_train.py --task finetune_clip --data training_data.json",
            },
            {
                "id": "train_category",
                "name": "训练类别分类器",
                "description": "基于提取的特征训练衣物类别分类器",
                "command": "python scripts/training/main_train.py --task train_category",
            },
            {
                "id": "train_style",
                "name": "训练风格分类器",
                "description": "基于提取的特征训练风格标签分类器",
                "command": "python scripts/training/main_train.py --task train_style",
            },
            {
                "id": "export_data",
                "name": "导出训练数据",
                "description": "从数据库导出已标注的训练数据",
                "command": "python scripts/training/main_train.py --task export --output training_data.json",
            },
            {
                "id": "analyze_data",
                "name": "分析数据质量",
                "description": "分析数据库中数据的质量",
                "command": "python scripts/training/main_train.py --task analyze",
            },
        ],
        "gpu_info": {
            "cuda_available": False,
            "device": "CPU",
        },
    }
