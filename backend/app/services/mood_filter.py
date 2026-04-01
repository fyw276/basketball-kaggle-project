"""
情绪筛选器 - 根据情绪推荐筛选衣橱单品
"""

from typing import Dict, List, Tuple

from app.core.logging import setup_logging
from app.services.mood_recommender import MoodRecommendation

logger = setup_logging()


class MoodFilter:
    """
    根据情绪筛选衣橱单品

    匹配逻辑：
    1. 匹配推荐的颜色
    2. 匹配推荐的风格
    3. 计算综合匹配分数
    """

    # 颜色到基础分的映射
    COLOR_MATCH_WEIGHTS = {
        1.0: 1.0,  # 完全匹配
        0.8: 0.8,  # 高权重
        0.6: 0.6,  # 中等
        0.5: 0.4,  # 较低
        0.4: 0.2,  # 最低
    }

    def __init__(self):
        """初始化筛选器"""
        logger.info("MoodFilter initialized")

    def filter_by_mood(
        self,
        garments: List,
        mood_recommendation: MoodRecommendation,
        top_k: int = 10,
    ) -> List[Tuple]:
        """
        根据情绪推荐筛选衣橱单品

        Args:
            garments: 衣橱单品列表
            mood_recommendation: 情绪推荐结果
            top_k: 返回前 k 个最匹配的单品

        Returns:
            List[Tuple[Garment, Dict]]: (单品, 匹配详情) 的列表
        """
        if not garments:
            return []

        scored_garments = []

        for garment in garments:
            score_info = self._calculate_match_score(garment, mood_recommendation)
            if score_info["total_score"] > 0:
                scored_garments.append((garment, score_info))

        # 按总分排序
        scored_garments.sort(key=lambda x: x[1]["total_score"], reverse=True)

        return scored_garments[:top_k]

    def _calculate_match_score(self, garment, mood_recommendation: MoodRecommendation) -> Dict:
        """
        计算单品与情绪推荐的匹配分数

        Args:
            garment: 衣物单品
            mood_recommendation: 情绪推荐

        Returns:
            Dict: 分数详情
        """
        scores = {
            "color_score": 0.0,
            "style_score": 0.0,
            "total_score": 0.0,
            "matched_colors": [],
            "matched_styles": [],
        }

        # 1. 颜色匹配
        garment_color = None
        if garment.main_color and isinstance(garment.main_color, dict):
            garment_color = garment.main_color.get("name")

        if garment_color:
            recommended_colors = mood_recommendation.recommended_colors
            if garment_color in recommended_colors:
                color_weight = recommended_colors[garment_color]
                scores["color_score"] = color_weight
                scores["matched_colors"].append(garment_color)

        # 2. 风格匹配
        garment_styles = garment.style_tags or []
        recommended_styles = mood_recommendation.recommended_styles

        matched_styles = []
        for style in garment_styles:
            if style in recommended_styles:
                # 推荐列表中的位置越靠前，分数越高
                position = recommended_styles.index(style)
                position_score = 1.0 - (position * 0.15)  # 每个位置递减 0.15
                matched_styles.append((style, position_score))

        if matched_styles:
            # 平均分
            scores["style_score"] = sum(s[1] for s in matched_styles) / len(matched_styles)
            scores["matched_styles"] = [s[0] for s in matched_styles]

        # 3. 计算总分（颜色权重 0.6，风格权重 0.4）
        scores["total_score"] = scores["color_score"] * 0.6 + scores["style_score"] * 0.4

        return scores

    def get_mood_based_suggestions(
        self,
        garments: List,
        mood_recommendation: MoodRecommendation,
    ) -> Dict:
        """
        获取情绪驱动的穿搭建议

        Args:
            garments: 衣橱单品
            mood_recommendation: 情绪推荐

        Returns:
            Dict: 建议详情
        """
        # 筛选匹配单品
        matching = self.filter_by_mood(garments, mood_recommendation, top_k=20)

        # 按类别分组
        by_category = {}
        for garment, score_info in matching:
            cat = garment.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(
                {
                    "garment_id": str(garment.garment_id),
                    "category": cat,
                    "main_color": garment.main_color,
                    "style_tags": garment.style_tags,
                    "image_url": garment.image_url,
                    "match_score": score_info["total_score"],
                    "color_score": score_info["color_score"],
                    "style_score": score_info["style_score"],
                }
            )

        # 生成建议
        suggestions = {
            "top_picks": matching[:5] if len(matching) >= 5 else matching,
            "by_category": by_category,
            "outfit_ideas": self._generate_outfit_ideas(matching, mood_recommendation),
        }

        return suggestions

    def _generate_outfit_ideas(
        self,
        matching: List[Tuple],
        mood_recommendation: MoodRecommendation,
    ) -> List[Dict]:
        """生成穿搭创意"""
        ideas = []

        # 按类别组织单品
        by_category = {}
        for garment, score_info in matching:
            cat = garment.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((garment, score_info))

        # 生成 3 种穿搭方案
        for i in range(3):
            outfit = {
                "name": f"方案 {i + 1}",
                "mood": mood_recommendation.mood_cn,
                "styles": mood_recommendation.recommended_styles[:3],
                "items": [],
                "description": mood_recommendation.advice,
            }

            # 添加每个类别的最佳单品
            categories = ["上衣", "裤子", "鞋", "包"]
            for cat in categories:
                if cat in by_category and len(by_category[cat]) > i:
                    garment, score = by_category[cat][i]
                    outfit["items"].append(
                        {
                            "category": cat,
                            "color": garment.main_color.get("name") if garment.main_color else None,
                            "match_score": score["total_score"],
                        }
                    )

            if outfit["items"]:
                ideas.append(outfit)

        return ideas


# 全局实例
_mood_filter: MoodFilter = None


def get_mood_filter() -> MoodFilter:
    """获取情绪筛选器实例"""
    global _mood_filter
    if _mood_filter is None:
        _mood_filter = MoodFilter()
    return _mood_filter
