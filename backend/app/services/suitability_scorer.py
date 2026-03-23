"""
Suitability scoring service for evaluating garment suitability based on user profile.

This module implements color, fit, and style suitability scoring algorithms.
"""

from typing import Dict, List, Optional, Tuple

from app.schemas.garment import ColorSchema
from app.schemas.user_profile import UserProfileResponse

# 肤色与颜色匹配规则
SKIN_TONE_COLOR_RULES: Dict[str, Dict[str, List[str]]] = {
    "冷白": {
        "高分": ["蓝色", "紫色", "粉色", "灰色", "黑色"],
        "中分": ["绿色", "白色", "红色"],
        "低分": ["橙色", "黄色", "棕色"],
    },
    "黄皮": {
        "高分": ["蓝色", "绿色", "白色", "灰色"],
        "中分": ["紫色", "粉色", "黑色"],
        "低分": ["黄色", "橙色", "棕色"],
    },
    "小麦": {
        "高分": ["白色", "蓝色", "绿色", "红色"],
        "中分": ["黑色", "灰色", "紫色"],
        "低分": ["黄色", "棕色"],
    },
    "深色": {
        "高分": ["白色", "红色", "蓝色", "黄色"],
        "中分": ["绿色", "紫色", "粉色"],
        "低分": ["黑色", "棕色", "灰色"],
    },
}

# 体型与版型匹配规则
BODY_TYPE_FIT_RULES: Dict[str, Dict[str, int]] = {
    "偏瘦": {
        "修身": 85,
        "标准": 90,
        "宽松": 70,
        "oversized": 60,
    },
    "微胖": {
        "修身": 50,
        "标准": 75,
        "宽松": 90,
        "oversized": 85,
    },
    "梨形": {
        "修身": 60,
        "标准": 80,
        "宽松": 85,
        "oversized": 75,
    },
    "倒三角": {
        "修身": 65,
        "标准": 80,
        "宽松": 90,
        "oversized": 85,
    },
    "沙漏": {
        "修身": 90,
        "标准": 85,
        "宽松": 70,
        "oversized": 60,
    },
    "矩形": {
        "修身": 75,
        "标准": 85,
        "宽松": 80,
        "oversized": 70,
    },
}

# 版型对身体部位的强化效果
FIT_TYPE_EMPHASIS: Dict[str, List[str]] = {
    "修身": ["肩", "腰", "臀", "大腿"],
    "标准": ["肩"],
    "宽松": [],
    "oversized": [],
}


# 风格偏好匹配规则
STYLE_PREFERENCE_RULES: Dict[str, List[str]] = {
    "通勤": ["通勤", "简约", "正式", "优雅"],
    "学院": ["学院", "简约", "休闲", "甜美"],
    "甜酷": ["甜美", "街头", "休闲"],
    "简约": ["简约", "通勤", "优雅", "正式"],
    "街头": ["街头", "休闲", "运动", "朋克"],
    "复古": ["复古", "优雅", "民族"],
    "运动": ["运动", "休闲", "街头"],
    "正式": ["正式", "通勤", "优雅", "简约"],
    "休闲": ["休闲", "简约", "运动", "街头"],
    "甜美": ["甜美", "学院", "优雅"],
    "优雅": ["优雅", "正式", "简约", "通勤"],
    "朋克": ["朋克", "街头", "复古"],
    "民族": ["民族", "复古", "优雅"],
}


class SuitabilityScorer:
    """适合度评分组件"""

    def _color_score(
        self, garment_color: ColorSchema, secondary_colors: List[ColorSchema], skin_tone: str
    ) -> Tuple[int, str]:
        """
        计算颜色适合度评分

        Args:
            garment_color: 服饰主色
            secondary_colors: 服饰辅助色列表
            skin_tone: 用户肤色类型

        Returns:
            Tuple[int, str]: (评分 0-100, 说明文字)
        """
        if skin_tone not in SKIN_TONE_COLOR_RULES:
            return 70, "无法判断颜色适合度"

        rules = SKIN_TONE_COLOR_RULES[skin_tone]
        color_name = garment_color.name

        # 计算主色评分
        if color_name in rules["高分"]:
            main_score = 90
            explanation = f"{color_name}与您的{skin_tone}肤色搭配度很高，能提亮肤色"
        elif color_name in rules["中分"]:
            main_score = 70
            explanation = f"{color_name}与您的{skin_tone}肤色搭配度适中"
        elif color_name in rules["低分"]:
            main_score = 50
            explanation = f"{color_name}可能不太适合{skin_tone}肤色，建议选择其他颜色"
        else:
            main_score = 70
            explanation = f"{color_name}与您的{skin_tone}肤色搭配度适中"

        # 如果有辅助色，考虑辅助色的影响（权重较低）
        if secondary_colors:
            secondary_scores = []
            for sec_color in secondary_colors:
                sec_name = sec_color.name
                if sec_name in rules["高分"]:
                    secondary_scores.append(90)
                elif sec_name in rules["中分"]:
                    secondary_scores.append(70)
                elif sec_name in rules["低分"]:
                    secondary_scores.append(50)
                else:
                    secondary_scores.append(70)

            # 主色占80%，辅助色占20%
            avg_secondary = sum(secondary_scores) / len(secondary_scores)
            final_score = int(main_score * 0.8 + avg_secondary * 0.2)

            # 如果辅助色提升了评分，更新说明
            if final_score > main_score:
                explanation += "，辅助色搭配也较为协调"
        else:
            final_score = main_score

        return final_score, explanation

    def _fit_score(
        self, garment_fit: Optional[str], body_type: str, avoid_body_parts: List[str]
    ) -> Tuple[int, str]:
        """
        计算版型适合度评分

        Args:
            garment_fit: 服饰版型（修身/宽松/标准/oversized）
            body_type: 用户体型类型
            avoid_body_parts: 用户不希望强化的身体部位列表

        Returns:
            Tuple[int, str]: (评分 0-100, 说明文字)
        """
        # 如果没有版型信息或体型不在规则中，返回默认评分
        if not garment_fit or body_type not in BODY_TYPE_FIT_RULES:
            return 70, "无法判断版型适合度"

        # 获取基础评分
        base_score = BODY_TYPE_FIT_RULES[body_type].get(garment_fit, 70)

        # 检查是否会强化用户不希望强化的身体部位
        emphasized_parts = FIT_TYPE_EMPHASIS.get(garment_fit, [])
        conflicting_parts = [part for part in avoid_body_parts if part in emphasized_parts]

        if conflicting_parts:
            # 如果会强化不希望强化的部位，降低评分
            penalty = len(conflicting_parts) * 15  # 每个冲突部位扣15分
            final_score = max(base_score - penalty, 30)  # 最低30分

            parts_str = "、".join(conflicting_parts)
            explanation = f"{garment_fit}版型可能会强化{parts_str}线条，建议选择宽松或落肩款式"
        else:
            final_score = base_score
            explanation = f"{garment_fit}版型与您的{body_type}体型搭配度较好"

        return final_score, explanation

    def _style_score(
        self, garment_styles: List[str], user_style_preferences: List[str]
    ) -> Tuple[int, str]:
        """
        计算风格适合度评分

        Args:
            garment_styles: 服饰风格标签列表
            user_style_preferences: 用户风格偏好列表

        Returns:
            Tuple[int, str]: (评分 0-100, 说明文字)
        """
        if not garment_styles or not user_style_preferences:
            return 70, "无法判断风格适合度"

        # 计算匹配度
        total_matches = 0
        perfect_matches = 0
        compatible_matches = 0

        for garment_style in garment_styles:
            for user_pref in user_style_preferences:
                # 获取该偏好的兼容风格列表
                compatible_styles = STYLE_PREFERENCE_RULES.get(user_pref, [user_pref])

                if garment_style == user_pref:
                    # 完全匹配
                    perfect_matches += 1
                    total_matches += 1
                    break  # 已经找到完美匹配，不需要继续检查其他用户偏好
                elif garment_style in compatible_styles:
                    # 兼容匹配
                    compatible_matches += 1
                    total_matches += 1
                    break  # 已经找到兼容匹配，不需要继续检查其他用户偏好

        if total_matches == 0:
            # 没有任何匹配
            final_score = 50
            garment_styles_str = "、".join(garment_styles)
            user_prefs_str = "、".join(user_style_preferences)
            explanation = f"{garment_styles_str}风格与您的{user_prefs_str}偏好差异较大，建议选择更符合个人风格的款式"
        else:
            # 计算评分：完美匹配100分，兼容匹配80分
            total_score = (perfect_matches * 100 + compatible_matches * 80) / len(garment_styles)
            final_score = int(total_score)

            # 生成说明
            garment_styles_str = "、".join(garment_styles)
            user_prefs_str = "、".join(user_style_preferences)

            if final_score >= 95:
                explanation = f"{garment_styles_str}风格与您的{user_prefs_str}偏好完全契合"
            elif final_score >= 75:
                explanation = f"{garment_styles_str}风格与您的{user_prefs_str}偏好较为匹配"
            else:
                explanation = f"{garment_styles_str}风格与您的{user_prefs_str}偏好有一定差异"

        return final_score, explanation

    def calculate_score(
        self,
        garment_color: ColorSchema,
        secondary_colors: List[ColorSchema],
        garment_fit: Optional[str],
        garment_styles: List[str],
        user_profile: "UserProfileResponse",
    ) -> dict:
        """
        计算服饰适合度综合评分

        Args:
            garment_color: 服饰主色
            secondary_colors: 服饰辅助色列表
            garment_fit: 服饰版型
            garment_styles: 服饰风格标签列表
            user_profile: 用户画像

        Returns:
            SuitabilityResult: 适合度评分结果
        """
        # 计算各维度评分
        color_score, color_explanation = self._color_score(
            garment_color, secondary_colors, user_profile.skin_tone
        )

        fit_score, fit_explanation = self._fit_score(
            garment_fit, user_profile.body_type, user_profile.avoid_body_parts
        )

        style_score, style_explanation = self._style_score(
            garment_styles, user_profile.style_preference
        )

        # 计算加权平均（颜色30%，版型40%，风格30%）
        overall_score = int(color_score * 0.3 + fit_score * 0.4 + style_score * 0.3)

        # 生成场合推荐
        recommended_occasions = self._recommend_occasions(
            garment_styles, overall_score, color_score, fit_score, style_score
        )

        # 生成改进建议
        suggestions = self._generate_suggestions(
            color_score,
            color_explanation,
            fit_score,
            fit_explanation,
            style_score,
            style_explanation,
            overall_score,
        )

        # 构建结果
        from app.schemas.suitability import SuitabilityResult

        return SuitabilityResult(
            suitability_score=overall_score,
            color_score=color_score,
            fit_score=fit_score,
            style_score=style_score,
            explanation={
                "color": color_explanation,
                "fit": fit_explanation,
                "style": style_explanation,
            },
            recommended_occasions=recommended_occasions,
            suggestions=suggestions,
        )

    def _recommend_occasions(
        self,
        garment_styles: List[str],
        overall_score: int,
        color_score: int,
        fit_score: int,
        style_score: int,
    ) -> List[str]:
        """
        推荐适合的穿着场合

        Args:
            garment_styles: 服饰风格标签
            overall_score: 综合评分
            color_score: 颜色评分
            fit_score: 版型评分
            style_score: 风格评分

        Returns:
            List[str]: 推荐场合列表
        """
        # 如果综合评分太低，不推荐任何场合
        if overall_score < 50:
            return []

        # 基于风格标签推荐场合
        occasion_map = {
            "正式": ["商务", "正式"],
            "通勤": ["商务", "校园"],
            "学院": ["校园", "休闲"],
            "休闲": ["休闲", "约会"],
            "运动": ["休闲", "运动"],
            "街头": ["休闲", "聚会"],
            "甜美": ["约会", "聚会"],
            "优雅": ["正式", "约会"],
            "简约": ["商务", "休闲", "校园"],
            "复古": ["聚会", "约会"],
            "朋克": ["聚会", "休闲"],
            "民族": ["聚会", "休闲"],
        }

        occasions = set()
        for style in garment_styles:
            if style in occasion_map:
                occasions.update(occasion_map[style])

        # 如果没有匹配的场合，根据评分推荐通用场合
        if not occasions:
            if overall_score >= 70:
                occasions.add("休闲")
            if overall_score >= 80:
                occasions.add("校园")

        return sorted(list(occasions))

    def _generate_suggestions(
        self,
        color_score: int,
        color_explanation: str,
        fit_score: int,
        fit_explanation: str,
        style_score: int,
        style_explanation: str,
        overall_score: int,
    ) -> List[str]:
        """
        生成改进建议

        Args:
            color_score: 颜色评分
            color_explanation: 颜色说明
            fit_score: 版型评分
            fit_explanation: 版型说明
            style_score: 风格评分
            style_explanation: 风格说明
            overall_score: 综合评分

        Returns:
            List[str]: 改进建议列表
        """
        suggestions = []

        # 如果综合评分高，不需要建议
        if overall_score >= 80:
            return suggestions

        # 颜色建议（评分低于60）
        if color_score < 60:
            if "不太适合" in color_explanation or "建议选择其他颜色" in color_explanation:
                suggestions.append("建议选择更适合您肤色的颜色，如蓝色、绿色或白色系")

        # 版型建议（评分低于60）
        if fit_score < 60:
            if "强化" in fit_explanation:
                # 提取建议的版型
                if "宽松" in fit_explanation or "落肩" in fit_explanation:
                    suggestions.append("建议选择宽松或落肩款式，避免强化身体线条")
                else:
                    suggestions.append("建议选择更适合您体型的版型")
            elif "微胖" in fit_explanation and "修身" in fit_explanation:
                suggestions.append("建议选择宽松或标准版型，更显身材优势")

        # 风格建议（评分低于60）
        if style_score < 60:
            if "差异" in style_explanation:
                suggestions.append("建议选择更符合您个人风格偏好的款式")

        # 综合建议
        if overall_score < 60 and not suggestions:
            suggestions.append("建议综合考虑颜色、版型和风格，选择更适合您的服饰")

        return suggestions
