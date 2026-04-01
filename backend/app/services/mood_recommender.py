"""
情绪推荐服务 - 根据用户情绪推荐穿搭

根据心理学和色彩心理学研究，不同情绪适合不同的穿搭风格和颜色。
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.logging import setup_logging

logger = setup_logging()


class MoodType(str, Enum):
    """情绪类型枚举"""

    # 正面情绪
    HAPPY = "happy"  # 开心
    EXCITED = "excited"  # 兴奋
    CONFIDENT = "confident"  # 自信
    RELAXED = "relaxed"  # 放松
    ROMANTIC = "romantic"  # 浪漫
    ENERGETIC = "energetic"  # 充满活力

    # 中性情绪
    NEUTRAL = "neutral"  # 平静
    FOCUSED = "focused"  # 专注

    # 负面情绪
    SAD = "sad"  # 难过
    ANXIOUS = "anxious"  # 焦虑
    ANGRY = "angry"  # 愤怒
    TIRED = "tired"  # 疲惫
    STRESSED = "stressed"  # 压力大
    LONELY = "lonely"  # 孤独


# 情绪 -> 推荐风格映射（基于心理学研究）
MOOD_STYLE_MAP: Dict[MoodType, List[str]] = {
    # 开心/积极情绪 - 保持活力
    MoodType.HAPPY: ["休闲", "甜美", "简约", "街头"],
    MoodType.EXCITED: ["街头", "朋克", "甜酷", "运动"],
    MoodType.CONFIDENT: ["正式", "优雅", "简约", "通勤"],
    MoodType.RELAXED: ["休闲", "简约", "度假", "舒适"],
    MoodType.ROMANTIC: ["甜美", "优雅", "复古", "民族"],
    MoodType.ENERGETIC: ["运动", "街头", "甜酷", "休闲"],
    # 中性 - 保持平衡
    MoodType.NEUTRAL: ["简约", "通勤", "学院", "休闲"],
    MoodType.FOCUSED: ["通勤", "正式", "简约", "学院"],
    # 负面情绪 - 需要提升心情
    MoodType.SAD: ["休闲", "甜酷", "甜美", "简约"],  # 暖色调提升情绪
    MoodType.ANXIOUS: ["简约", "通勤", "休闲", "舒适"],  # 简洁减少压力
    MoodType.ANGRY: ["运动", "街头", "简约", "舒适"],  # 释放能量
    MoodType.TIRED: ["舒适", "休闲", "简约", "运动"],  # 舒适为主
    MoodType.STRESSED: ["舒适", "简约", "通勤", "休闲"],  # 减少决策负担
    MoodType.LONELY: ["甜酷", "甜美", "优雅", "复古"],  # 温暖的颜色和风格
}


# 情绪 -> 推荐颜色（色彩心理学）
MOOD_COLOR_MAP: Dict[MoodType, Dict[str, float]] = {
    # 开心 - 保持明亮
    MoodType.HAPPY: {
        "黄": 0.8,
        "橙": 0.7,
        "白": 0.6,
        "红": 0.5,
        "粉": 0.5,
    },
    MoodType.EXCITED: {
        "红": 0.9,
        "橙": 0.8,
        "黄": 0.7,
        "黑": 0.5,
        "白": 0.4,
    },
    MoodType.CONFIDENT: {
        "黑": 0.9,
        "白": 0.7,
        "红": 0.6,
        "蓝": 0.5,
        "灰": 0.5,
    },
    MoodType.RELAXED: {
        "蓝": 0.8,
        "绿": 0.7,
        "白": 0.7,
        "黄": 0.5,
        "灰": 0.4,
    },
    MoodType.ROMANTIC: {
        "粉": 0.9,
        "红": 0.7,
        "白": 0.6,
        "紫": 0.5,
        "黑": 0.3,
    },
    MoodType.ENERGETIC: {
        "红": 0.9,
        "橙": 0.8,
        "黄": 0.7,
        "绿": 0.6,
        "黑": 0.5,
    },
    # 中性
    MoodType.NEUTRAL: {
        "蓝": 0.7,
        "灰": 0.7,
        "白": 0.7,
        "黑": 0.6,
        "棕": 0.5,
    },
    MoodType.FOCUSED: {
        "蓝": 0.8,
        "灰": 0.7,
        "白": 0.7,
        "黑": 0.6,
        "绿": 0.5,
    },
    # 负面情绪 - 需要特别注意
    MoodType.SAD: {
        # 暖色提升情绪！避免冷色调
        "橙": 0.9,
        "黄": 0.8,
        "粉": 0.7,
        "红": 0.6,
        "白": 0.5,
    },
    MoodType.ANXIOUS: {
        # 蓝色和绿色有镇静作用
        "蓝": 0.9,
        "绿": 0.8,
        "白": 0.7,
        "灰": 0.6,
        "紫": 0.4,
    },
    MoodType.ANGRY: {
        # 冷色调镇静，避免红色
        "蓝": 0.9,
        "绿": 0.8,
        "白": 0.7,
        "灰": 0.6,
        "紫": 0.5,
    },
    MoodType.TIRED: {
        # 活力颜色提神
        "橙": 0.8,
        "黄": 0.8,
        "红": 0.6,
        "绿": 0.6,
        "白": 0.5,
    },
    MoodType.STRESSED: {
        # 柔和、低饱和度颜色
        "蓝": 0.8,
        "绿": 0.7,
        "白": 0.7,
        "灰": 0.6,
        "紫": 0.5,
    },
    MoodType.LONELY: {
        # 温暖、有归属感的颜色
        "红": 0.8,
        "橙": 0.7,
        "黄": 0.7,
        "粉": 0.7,
        "棕": 0.5,
    },
}


# 情绪 -> 推荐场景
MOOD_OCCASION_MAP: Dict[MoodType, List[str]] = {
    MoodType.HAPPY: ["约会", "聚会", "度假", "休闲"],
    MoodType.EXCITED: ["聚会", "街头", "运动", "度假"],
    MoodType.CONFIDENT: ["商务", "正式宴会", "约会", "聚会"],
    MoodType.RELAXED: ["度假", "休闲", "校园", "约会"],
    MoodType.ROMANTIC: ["约会", "聚会", "正式宴会", "度假"],
    MoodType.ENERGETIC: ["运动", "街头", "校园", "休闲"],
    MoodType.NEUTRAL: ["通勤", "校园", "休闲", "日常"],
    MoodType.FOCUSED: ["通勤", "校园", "正式", "日常"],
    MoodType.SAD: ["休闲", "约会", "聚会", "度假"],  # 需要社交提升情绪
    MoodType.ANXIOUS: ["通勤", "休闲", "舒适", "日常"],
    MoodType.ANGRY: ["运动", "街头", "休闲", "舒适"],
    MoodType.TIRED: ["舒适", "休闲", "通勤", "日常"],
    MoodType.STRESSED: ["舒适", "休闲", "通勤", "校园"],
    MoodType.LONELY: ["约会", "聚会", "社交", "休闲"],  # 建议社交
}


# 情绪 -> 搭配建议语
MOOD_ADVICE_MAP: Dict[MoodType, str] = {
    MoodType.HAPPY: "保持好心情！亮色系穿搭让你更加活力四射",
    MoodType.EXCITED: "充满能量！大胆尝试亮眼配色和个性搭配",
    MoodType.CONFIDENT: "气场全开！简洁有力的穿搭展现你的魅力",
    MoodType.RELAXED: "轻松自在！舒适的穿搭让你保持好心情",
    MoodType.ROMANTIC: "温柔优雅！柔和的颜色和优雅的风格提升魅力",
    MoodType.ENERGETIC: "活力满满！运动风和亮色让你更加精神",
    MoodType.NEUTRAL: "平衡舒适！简约穿搭让你保持专注",
    MoodType.FOCUSED: "专注高效！干净利落的穿搭减少干扰",
    MoodType.SAD: "今天心情不好时，优先选暖色（橙、黄、粉）和柔软休闲的单品，有助于情绪回暖；下面也从你衣橱里挑了更搭这一状态的衣服。",
    MoodType.ANXIOUS: "需要放松！柔和的蓝色和绿色有镇静作用",
    MoodType.ANGRY: "冷静一下！深蓝色和绿色能帮助你平复情绪",
    MoodType.TIRED: "需要提神！黄色和橙色能让你精神起来",
    MoodType.STRESSED: "放松点！舒适简洁的穿搭减少压力感",
    MoodType.LONELY: "走出去社交吧！温暖的红色和粉色让你更有魅力",
}


class MoodRecommendation(BaseModel):
    """情绪推荐结果"""

    mood: str = Field(..., description="用户情绪")
    mood_cn: str = Field(..., description="情绪中文名")
    recommended_styles: List[str] = Field(..., description="推荐风格")
    recommended_colors: Dict[str, float] = Field(..., description="推荐颜色及权重")
    recommended_occasions: List[str] = Field(..., description="推荐场景")
    advice: str = Field(..., description="搭配建议")
    color_explanation: str = Field(..., description="颜色选择说明")


class MoodRecommender:
    """
    情绪推荐器

    根据用户当前情绪，推荐适合的：
    1. 穿搭风格
    2. 颜色搭配
    3. 适用场合
    4. 搭配建议
    """

    # 情绪中文名映射
    MOOD_CN_NAMES = {
        MoodType.HAPPY: "开心",
        MoodType.EXCITED: "兴奋",
        MoodType.CONFIDENT: "自信",
        MoodType.RELAXED: "放松",
        MoodType.ROMANTIC: "浪漫",
        MoodType.ENERGETIC: "充满活力",
        MoodType.NEUTRAL: "平静",
        MoodType.FOCUSED: "专注",
        MoodType.SAD: "难过",
        MoodType.ANXIOUS: "焦虑",
        MoodType.ANGRY: "愤怒",
        MoodType.TIRED: "疲惫",
        MoodType.STRESSED: "压力大",
        MoodType.LONELY: "孤独",
    }

    # 颜色中文名映射
    COLOR_CN_NAMES = {
        "红": "红色系",
        "橙": "橙色系",
        "黄": "黄色系",
        "绿": "绿色系",
        "蓝": "蓝色系",
        "紫": "紫色系",
        "粉": "粉色系",
        "白": "白色系",
        "黑": "黑色系",
        "灰": "灰色系",
        "棕": "棕色系",
    }

    def __init__(self):
        """初始化情绪推荐器"""
        logger.info("MoodRecommender initialized")

    def recommend(self, mood: str) -> MoodRecommendation:
        """
        根据情绪获取推荐

        Args:
            mood: 情绪类型 (happy, sad, anxious 等)

        Returns:
            MoodRecommendation: 推荐结果
        """
        try:
            mood_enum = MoodType(mood.lower())
        except ValueError:
            logger.warning(f"Unknown mood: {mood}, defaulting to neutral")
            mood_enum = MoodType.NEUTRAL

        # 获取推荐
        styles = MOOD_STYLE_MAP.get(mood_enum, MOOD_STYLE_MAP[MoodType.NEUTRAL])
        colors = MOOD_COLOR_MAP.get(mood_enum, MOOD_COLOR_MAP[MoodType.NEUTRAL])
        occasions = MOOD_OCCASION_MAP.get(mood_enum, MOOD_OCCASION_MAP[MoodType.NEUTRAL])
        advice = MOOD_ADVICE_MAP.get(mood_enum, MOOD_ADVICE_MAP[MoodType.NEUTRAL])

        # 生成颜色说明
        top_colors = sorted(colors.items(), key=lambda x: -x[1])[:3]
        color_names = [self.COLOR_CN_NAMES.get(c, c) for c, _ in top_colors]
        color_explanation = f"推荐穿着{'、'.join(color_names)}的衣物"

        # 负面情绪特殊说明
        if mood_enum in [MoodType.SAD, MoodType.LONELY]:
            color_explanation += "，暖色调能有效提升心情"
        elif mood_enum in [MoodType.ANXIOUS, MoodType.ANGRY, MoodType.STRESSED]:
            color_explanation += "，冷色调有助于平复情绪"
        elif mood_enum in [MoodType.TIRED]:
            color_explanation += "，明亮的颜色能提神醒脑"

        return MoodRecommendation(
            mood=mood_enum.value,
            mood_cn=self.MOOD_CN_NAMES.get(mood_enum, "未知"),
            recommended_styles=styles,
            recommended_colors=colors,
            recommended_occasions=occasions,
            advice=advice,
            color_explanation=color_explanation,
        )

    def get_all_moods(self) -> List[Dict]:
        """获取所有可用情绪类型"""
        return [
            {
                "value": mood.value,
                "label": self.MOOD_CN_NAMES.get(mood, mood.value),
            }
            for mood in MoodType
        ]

    def is_negative_mood(self, mood: str) -> bool:
        """判断是否为负面情绪"""
        negative_moods = {
            MoodType.SAD.value,
            MoodType.ANXIOUS.value,
            MoodType.ANGRY.value,
            MoodType.TIRED.value,
            MoodType.STRESSED.value,
            MoodType.LONELY.value,
        }
        return mood.lower() in negative_moods

    def get_mood_intensity_color(self, mood: str) -> str:
        """
        根据情绪返回适合的 UI 颜色提示

        Args:
            mood: 情绪类型

        Returns:
            str: 十六进制颜色代码
        """
        intensity_colors = {
            MoodType.HAPPY.value: "#FFD700",  # 金色
            MoodType.EXCITED.value: "#FF4500",  # 橙红
            MoodType.CONFIDENT.value: "#000000",  # 黑色
            MoodType.RELAXED.value: "#87CEEB",  # 天蓝
            MoodType.ROMANTIC.value: "#FF69B4",  # 粉红
            MoodType.ENERGETIC.value: "#FF6347",  # 番茄红
            MoodType.NEUTRAL.value: "#808080",  # 灰色
            MoodType.FOCUSED.value: "#4169E1",  # 皇家蓝
            MoodType.SAD.value: "#6A5ACD",  # 灰紫
            MoodType.ANXIOUS.value: "#9370DB",  # 中紫
            MoodType.ANGRY.value: "#DC143C",  # 深红
            MoodType.TIRED.value: "#DDA0DD",  # 淡紫
            MoodType.STRESSED.value: "#778899",  # 灰蓝
            MoodType.LONELY.value: "#DDA0DD",  # 淡紫
        }
        return intensity_colors.get(mood.lower(), "#808080")


# 全局实例
_mood_recommender: Optional[MoodRecommender] = None


def get_mood_recommender() -> MoodRecommender:
    """获取情绪推荐器实例"""
    global _mood_recommender
    if _mood_recommender is None:
        _mood_recommender = MoodRecommender()
    return _mood_recommender
