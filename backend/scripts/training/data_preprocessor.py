"""
数据预处理器：从数据库提取数据、检查特征向量、重新提取特征
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import setup_logging
from app.ml.clip_recognizer import CLIPRecognizer
from app.ml.feature_extractor import FeatureExtractor

logger = setup_logging()


class DataPreprocessor:
    """数据库衣物数据预处理器"""

    def __init__(self, db_path: str = "./outfit_assistant.db"):
        """
        初始化预处理器

        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = db_path
        self.db_url = f"sqlite:///{db_path}" if not db_path.startswith("sqlite:///") else db_path
        self.engine = create_engine(self.db_url)

        # 初始化特征提取器
        self.clip_recognizer = CLIPRecognizer()
        self.feature_extractor = FeatureExtractor()

        logger.info(f"DataPreprocessor initialized with db: {db_path}")

    def get_all_garments(self) -> List[Dict]:
        """
        从数据库获取所有衣物数据

        Returns:
            List[Dict]: 衣物数据列表
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT
                        garment_id, user_id, category, main_color,
                        secondary_colors, style_tags, fit_type,
                        image_path, image_url, feature_vector,
                        name, gender_label, neutral_score
                    FROM garments
                    ORDER BY created_at DESC
                """
                )
            )

            garments = []
            for row in result:
                garment = {
                    "garment_id": row[0],
                    "user_id": row[1],
                    "category": row[2],
                    "main_color": json.loads(row[3]) if row[3] else {},
                    "secondary_colors": json.loads(row[4]) if row[4] else [],
                    "style_tags": json.loads(row[5]) if row[5] else [],
                    "fit_type": row[6],
                    "image_path": row[7],
                    "image_url": row[8],
                    "feature_vector": self._parse_feature_vector(row[9]),
                    "name": row[10],
                    "gender_label": row[11],
                    "neutral_score": row[12],
                }
                garments.append(garment)

            logger.info(f"Loaded {len(garments)} garments from database")
            return garments

    def _parse_feature_vector(self, vector_str: str) -> np.ndarray:
        """解析特征向量字符串"""
        if not vector_str:
            return np.zeros(1280)
        try:
            vector_list = json.loads(vector_str)
            return np.array(vector_list)
        except (json.JSONDecodeError, TypeError):
            return np.zeros(1280)

    def analyze_data_quality(self) -> Dict:
        """
        分析数据质量

        Returns:
            Dict: 数据质量报告
        """
        garments = self.get_all_garments()

        report = {
            "total": len(garments),
            "valid_features": 0,
            "zero_features": 0,
            "valid_categories": {},
            "invalid_categories": 0,
            "valid_styles": {},
            "images_found": 0,
            "images_missing": 0,
        }

        project_root = Path(__file__).parent.parent.parent

        for g in garments:
            # 检查特征向量
            if np.any(g["feature_vector"] != 0):
                report["valid_features"] += 1
            else:
                report["zero_features"] += 1

            # 统计类别
            cat = g.get("category", "")
            if cat:
                report["valid_categories"][cat] = report["valid_categories"].get(cat, 0) + 1
            else:
                report["invalid_categories"] += 1

            # 统计风格
            for style in g.get("style_tags", []):
                report["valid_styles"][style] = report["valid_styles"].get(style, 0) + 1

            # 检查图片是否存在
            img_path = g.get("image_path", "")
            if img_path:
                full_path = project_root / img_path.replace("\\", "/")
                if full_path.exists():
                    report["images_found"] += 1
                else:
                    report["images_missing"] += 1

        logger.info(f"Data quality report: {report}")
        return report

    def extract_features_for_garment(self, garment: Dict, use_cache: bool = False) -> np.ndarray:
        """
        为单个衣物提取特征向量

        Args:
            garment: 衣物数据字典
            use_cache: 是否使用缓存

        Returns:
            np.ndarray: 特征向量
        """
        project_root = Path(__file__).parent.parent.parent
        img_path = garment.get("image_path", "")

        if not img_path:
            logger.warning(f"No image path for garment {garment['garment_id']}")
            return np.zeros(1280)

        full_path = project_root / img_path.replace("\\", "/")

        if not full_path.exists():
            logger.warning(f"Image not found: {full_path}")
            return np.zeros(1280)

        try:
            # 使用 CLIP 提取特征
            features = self.clip_recognizer.extract_features(str(full_path))
            logger.debug(f"Extracted features for {garment['garment_id']}: shape={features.shape}")
            return features
        except Exception as e:
            logger.error(f"Failed to extract features for {garment['garment_id']}: {e}")
            return np.zeros(1280)

    def update_feature_vector(self, garment_id: str, feature_vector: np.ndarray) -> bool:
        """
        更新数据库中的特征向量

        Args:
            garment_id: 衣物 ID
            feature_vector: 新的特征向量

        Returns:
            bool: 是否成功
        """
        try:
            vector_json = json.dumps(feature_vector.tolist())

            with self.engine.connect() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE garments
                        SET feature_vector = :vector,
                            updated_at = datetime('now')
                        WHERE garment_id = :garment_id
                    """
                    ),
                    {"vector": vector_json, "garment_id": garment_id},
                )
                conn.commit()

            logger.info(f"Updated feature vector for {garment_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update feature vector for {garment_id}: {e}")
            return False

    def reextract_all_features(self, batch_size: int = 4) -> Dict:
        """
        重新提取所有衣物的特征向量

        Args:
            batch_size: 批处理大小

        Returns:
            Dict: 更新报告
        """
        garments = self.get_all_garments()

        report = {
            "total": len(garments),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "zero_vectors": 0,
        }

        for i, garment in enumerate(garments):
            logger.info(f"Processing {i+1}/{len(garments)}: {garment['garment_id']}")

            # 检查是否已有有效特征
            if np.any(garment["feature_vector"] != 0):
                report["skipped"] += 1
                logger.info(f"Skipping {garment['garment_id']} - has valid features")
                continue

            # 提取特征
            features = self.extract_features_for_garment(garment)

            if np.any(features != 0):
                self.update_feature_vector(garment["garment_id"], features)
                report["success"] += 1
            else:
                report["failed"] += 1

        report["zero_vectors"] = report["failed"]
        logger.info(f"Reextraction complete: {report}")
        return report

    def export_for_training(self, output_path: str = "./training_data.json") -> str:
        """
        导出训练数据（图片路径 + 标签）

        Args:
            output_path: 输出文件路径

        Returns:
            str: 输出文件路径
        """
        garments = self.get_all_garments()
        project_root = Path(__file__).parent.parent.parent

        training_data = []
        for g in garments:
            img_path = g.get("image_path", "")
            if not img_path:
                continue

            full_path = project_root / img_path.replace("\\", "/")
            if not full_path.exists():
                continue

            # 只导出有有效标签的数据
            if not g.get("category"):
                continue

            entry = {
                "image_path": str(full_path),
                "category": g["category"],
                "style_tags": g.get("style_tags", []),
                "fit_type": g.get("fit_type"),
                "main_color": g.get("main_color", {}).get("name"),
                "gender_label": g.get("gender_label"),
            }
            training_data.append(entry)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(training_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported {len(training_data)} training samples to {output_path}")
        return output_path

    def get_statistics(self) -> Dict:
        """获取数据统计信息"""
        report = self.analyze_data_quality()

        return {
            "total_garments": report["total"],
            "images_available": report["images_found"],
            "images_missing": report["images_missing"],
            "valid_features": report["valid_features"],
            "zero_features": report["zero_features"],
            "categories": report["valid_categories"],
            "styles": report["valid_styles"],
            "needs_extraction": report["zero_features"],
        }


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="数据预处理工具")
    parser.add_argument("--analyze", action="store_true", help="分析数据质量")
    parser.add_argument("--reextract", action="store_true", help="重新提取所有特征")
    parser.add_argument("--export", action="store_true", help="导出训练数据")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    parser.add_argument("--output", default="./training_data.json", help="导出文件路径")

    args = parser.parse_args()

    preprocessor = DataPreprocessor()

    if args.analyze:
        report = preprocessor.analyze_data_quality()
        print("\n=== 数据质量报告 ===")
        print(f"总数据量: {report['total']}")
        print(f"有效特征: {report['valid_features']}")
        print(f"零特征: {report['zero_features']}")
        print(f"图片存在: {report['images_found']}")
        print(f"图片缺失: {report['images_missing']}")
        print(f"\n类别分布: {report['valid_categories']}")
        print(f"风格分布: {report['valid_styles']}")

    elif args.reextract:
        print("开始重新提取特征向量...")
        report = preprocessor.reextract_all_features()
        print(f"\n=== 提取完成 ===")
        print(f"成功: {report['success']}")
        print(f"失败: {report['failed']}")
        print(f"跳过: {report['skipped']}")

    elif args.export:
        output_path = preprocessor.export_for_training(args.output)
        print(f"已导出训练数据到: {output_path}")

    elif args.stats:
        stats = preprocessor.get_statistics()
        print("\n=== 统计信息 ===")
        print(f"总衣物数: {stats['total_garments']}")
        print(f"可用图片: {stats['images_available']}")
        print(f"有效特征: {stats['valid_features']}")
        print(f"需提取: {stats['needs_extraction']}")
        print(f"\n类别: {stats['categories']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
