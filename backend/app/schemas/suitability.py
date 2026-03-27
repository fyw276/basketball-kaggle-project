"""
Suitability scoring schemas
"""

from typing import Dict, List

from pydantic import BaseModel, Field


class SuitabilityResult(BaseModel):
    """适合度评分结果（场景-体型-风格 三维模型）"""

    suitability_score: int = Field(..., ge=0, le=100, description="综合评分（加权平均）")
    color_score: int = Field(..., ge=0, le=100, description="颜色适合度（肤色匹配）")
    fit_score: int = Field(..., ge=0, le=100, description="版型适合度（体型适配）")
    style_score: int = Field(..., ge=0, le=100, description="风格适合度（个人偏好匹配）")
    explanation: Dict[str, str] = Field(..., description="各维度评分说明")
    recommended_occasions: List[str] = Field(default_factory=list, description="推荐场合")
    suggestions: List[str] = Field(default_factory=list, description="改进建议")

    class Config:
        json_schema_extra = {
            "example": {
                "suitability_score": 82,
                "color_score": 90,
                "fit_score": 75,
                "style_score": 80,
                "explanation": {
                    "scene": "服装适合通勤上班、商务正式等场合，与您的风格偏好高度匹配，色彩搭配也协调。",
                    "body": "修身版型可能强化肩部线条，建议选择宽松或落肩款式",
                    "style": "通勤、简约风格与您的通勤、简约偏好完全契合",
                },
                "recommended_occasions": ["通勤上班", "商务正式", "校园"],
                "suggestions": [
                    "建议选择宽松或落肩款式，避免强化肩部线条",
                ],
            }
        }
