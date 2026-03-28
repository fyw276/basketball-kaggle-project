"""
尺码映射模块 - 无性别推荐系统

提供跨性别穿搭的尺码建议：
1. 女穿男装：根据女性身高/体重，输出男装尺码建议
2. 男穿女装（仅当 explore_cross_gender=True）：输出女装尺码建议 + 明确提示

尺码对照表基于中国国家标准 GB/T 1335
"""

from typing import Dict, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# 女装尺码对照表（身高/体重）
# ──────────────────────────────────────────────────────────────────────────────
WOMEN_SIZE_CHART: Dict[str, Dict[str, Tuple[int, int]]] = {
    # 尺码: {"height_range": (min, max), "weight_range": (min, max)}
    "XS": {"height": (155, 160), "weight": (42, 48)},
    "S": {"height": (158, 165), "weight": (45, 52)},
    "M": {"height": (162, 170), "weight": (50, 58)},
    "L": {"height": (165, 175), "weight": (55, 65)},
    "XL": {"height": (168, 178), "weight": (62, 72)},
    "XXL": {"height": (172, 180), "weight": (68, 78)},
}


# ──────────────────────────────────────────────────────────────────────────────
# 男装尺码对照表（身高/体重）
# ──────────────────────────────────────────────────────────────────────────────
MEN_SIZE_CHART: Dict[str, Dict[str, Tuple[int, int]]] = {
    "XS": {"height": (165, 170), "weight": (50, 58)},
    "S": {"height": (168, 175), "weight": (55, 65)},
    "M": {"height": (172, 180), "weight": (62, 72)},
    "L": {"height": (175, 183), "weight": (70, 80)},
    "XL": {"height": (178, 186), "weight": (78, 88)},
    "XXL": {"height": (182, 190), "weight": (85, 95)},
    "XXXL": {"height": (186, 195), "weight": (92, 102)},
}


# ──────────────────────────────────────────────────────────────────────────────
# 尺码映射服务
# ──────────────────────────────────────────────────────────────────────────────


class SizeMapper:
    """
    尺码映射服务

    功能：
    1. 女穿男装：根据女性身高/体重，推荐合适的男装尺码
    2. 男穿女装：根据男性身高/体重，推荐合适的女装尺码（+ 提示选大1-2码）
    """

    @staticmethod
    def get_women_size_for_men(height_cm: int, weight_kg: int) -> str:
        """
        根据男性身高/体重，推荐女装尺码

        男穿女装需要选大1-2码，所以先用男性数据找对应的女性尺码，
        然后建议选大一号。

        Args:
            height_cm: 身高（厘米）
            weight_kg: 体重（公斤）

        Returns:
            建议的女装尺码（如 "S（建议选M或L）"）
        """
        # 查找最接近的尺码
        best_size = "M"
        best_score = float("inf")

        for size, ranges in WOMEN_SIZE_CHART.items():
            height_range = ranges["height"]
            weight_range = ranges["weight"]

            # 计算差距
            height_mid = (height_range[0] + height_range[1]) / 2
            weight_mid = (weight_range[0] + weight_range[1]) / 2
            score = abs(height_cm - height_mid) + abs(weight_kg - weight_mid) * 2

            if score < best_score:
                best_score = score
                best_size = size

        # 男士穿女装需要选大1-2码
        size_order = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
        try:
            current_idx = size_order.index(best_size)
            if current_idx + 1 < len(size_order):
                larger_size = size_order[current_idx + 1]
                if current_idx + 2 < len(size_order):
                    largest_size = size_order[current_idx + 2]
                    return f"{best_size}（建议选{larger_size}或{largest_size}）"
                else:
                    return f"{best_size}（建议选{larger_size}）"
        except ValueError:
            pass

        return f"{best_size}（建议选大1-2码）"

    @staticmethod
    def get_men_size_for_women(height_cm: int, weight_kg: int) -> str:
        """
        根据女性身高/体重，推荐男装尺码

        Args:
            height_cm: 身高（厘米）
            weight_kg: 体重（公斤）

        Returns:
            建议的男装尺码（如 "M"）
        """
        best_size = "M"
        best_score = float("inf")

        for size, ranges in MEN_SIZE_CHART.items():
            height_range = ranges["height"]
            weight_range = ranges["weight"]

            # 计算差距
            height_mid = (height_range[0] + height_range[1]) / 2
            weight_mid = (weight_range[0] + weight_range[1]) / 2
            score = abs(height_cm - height_mid) + abs(weight_kg - weight_mid) * 2

            if score < best_score:
                best_score = score
                best_size = size

        # 女穿男装通常选小一码（男装版型偏大）
        size_order = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
        try:
            current_idx = size_order.index(best_size)
            if current_idx > 0:
                smaller_size = size_order[current_idx - 1]
                return f"{best_size}（女穿男款可尝试{smaller_size}）"
        except ValueError:
            pass

        return best_size

    @staticmethod
    def get_size_advice(
        user_gender: str,
        garment_gender_label: str,
        height_cm: int,
        weight_kg: int,
    ) -> Optional[Dict[str, str]]:
        """
        获取尺码建议

        Args:
            user_gender: 用户性别（"男" / "女"）
            garment_gender_label: 服装性别标签（"male" / "female" / "neutral"）
            height_cm: 身高（厘米）
            weight_kg: 体重（公斤）

        Returns:
            包含建议尺码和提示的字典，或 None（无需特殊建议）
        """
        # 同性穿搭无需特殊建议
        if user_gender == "女" and garment_gender_label == "female":
            return None
        if user_gender == "男" and garment_gender_label == "male":
            return None
        # 中性服装无需特殊建议
        if garment_gender_label == "neutral":
            return None

        # 女穿男装
        if user_gender == "女" and garment_gender_label in ["male", "neutral"]:
            suggested_size = SizeMapper.get_men_size_for_women(height_cm, weight_kg)
            return {
                "suggested_size": suggested_size,
                "note": "女穿男款通常选小一码",
                "warning": None,
            }

        # 男穿女装
        if user_gender == "男" and garment_gender_label == "female":
            suggested_size = SizeMapper.get_women_size_for_men(height_cm, weight_kg)
            return {
                "suggested_size": suggested_size,
                "note": "此为女款，建议选大1-2码",
                "warning": "注意：此服装为女款，选购时请注意版型差异",
            }

        return None

    @staticmethod
    def get_size_chart_info(garment_gender_label: str) -> Dict[str, any]:
        """
        获取尺码表信息

        Args:
            garment_gender_label: 服装性别标签（"male" / "female" / "neutral"）

        Returns:
            尺码表信息字典
        """
        if garment_gender_label == "female":
            return {
                "chart": "WOMEN_SIZE_CHART",
                "sizes": list(WOMEN_SIZE_CHART.keys()),
                "note": "女装尺码参考",
            }
        elif garment_gender_label == "male":
            return {
                "chart": "MEN_SIZE_CHART",
                "sizes": list(MEN_SIZE_CHART.keys()),
                "note": "男装尺码参考",
            }
        else:
            return {
                "chart": "NEUTRAL",
                "sizes": [],
                "note": "中性服装尺码因品牌而异，请参考具体商品尺码表",
            }


# 全局实例
_size_mapper: Optional[SizeMapper] = None


def get_size_mapper() -> SizeMapper:
    """获取尺码映射服务实例"""
    global _size_mapper
    if _size_mapper is None:
        _size_mapper = SizeMapper()
    return _size_mapper
