"""
Suitability scoring schemas
"""

from typing import Dict, List

from pydantic import BaseModel, Field


class SuitabilityResult(BaseModel):
    """适合度评分结果"""

    suitability_score: int = Field(..., ge=0, le=100, description="综合评分")
    color_score: int = Field(..., ge=0, le=100, description="颜色适合度")
    fit_score: int = Field(..., ge=0, le=100, description="版型适合度")
    style_score: int = Field(..., ge=0, le=100, description="风格适合度")
    explanation: Dict[str, str] = Field(..., description="各维度评分说明")
    recommended_occasions: List[str] = Field(default_factory=list, description="推荐场合")
    suggestions: List[str] = Field(default_factory=list, description="改进建议")

    class Config:
        json_schema_extra = {
            "example": {
                "suitability_score": 75,
                "color_score": 80,
                "fit_score": 70,
                "style_score": 75,
                "explanation": {
                    "color": "粉色与您的冷白肤色搭配度较高，能提亮肤色",
                    "fit": "修身版型可能会强化肩部线条，建议选择落肩款式",
                    "style": "甜美风格与您的通勤偏好有一定差异",
                },
                "recommended_occasions": ["约会", "聚会"],
                "suggestions": [
                    "建议选择落肩或宽松版型以避免强化肩部",
                    "可搭配简约配饰平衡甜美感",
                ],
            }
        }
