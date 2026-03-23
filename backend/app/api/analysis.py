"""
Analysis API endpoints (similarity, recommendations, suitability)
"""

from typing import Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.ml.image_recognizer import ImageRecognizer, RecognitionResult
from app.models.user import User
from app.schemas.garment import ColorSchema
from app.services.garment import get_garments_by_user
from app.services.similarity import SimilarityAnalyzer, SimilarityMatch
from app.services.user_profile import get_profile_by_user_id

router = APIRouter(prefix="/analysis", tags=["Analysis"])


class SimilarGarmentInfo(BaseModel):
    """Similar garment information"""

    garment_id: str
    similarity_score: float = Field(..., ge=0, le=1)
    similarity_level: str
    image_url: str
    category: str
    main_color: ColorSchema


class SimilarityAnalysisResponse(BaseModel):
    """Similarity analysis response"""

    target_garment: dict = Field(..., description="Target garment recognition result")
    similar_garments: List[SimilarGarmentInfo] = Field(
        default_factory=list, description="Similar garments from wardrobe"
    )
    has_duplicate_warning: bool = Field(
        ..., description="Whether there are high similarity matches"
    )
    recommendation: str = Field(..., description="Purchase recommendation message")

    class Config:
        json_schema_extra = {
            "example": {
                "target_garment": {
                    "category": "上衣",
                    "main_color": {"name": "蓝", "hex_code": "#3478b4"},
                    "style_tags": ["通勤", "简约"],
                },
                "similar_garments": [
                    {
                        "garment_id": "123e4567-e89b-12d3-a456-426614174000",
                        "similarity_score": 0.85,
                        "similarity_level": "高相似度",
                        "image_url": "/uploads/user123/image.jpg",
                        "category": "上衣",
                        "main_color": {"name": "深蓝", "hex_code": "#1e3a5f"},
                    }
                ],
                "has_duplicate_warning": True,
                "recommendation": "您的衣橱中已有 1 件高度相似的单品，建议谨慎购买。",
            }
        }


@router.post("/similarity", response_model=SimilarityAnalysisResponse)
async def analyze_similarity(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Analyze similarity between uploaded garment and wardrobe

    This endpoint:
    1. Recognizes the uploaded garment image
    2. Extracts feature vector
    3. Compares with all garments in user's wardrobe
    4. Returns similarity matches and duplicate warning
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG, WebP)",
        )

    try:
        # Read image file
        image_bytes = await file.read()

        # Initialize image recognizer
        recognizer = ImageRecognizer()

        # Recognize image
        recognition_result: RecognitionResult = recognizer.recognize(image_bytes)

        # Get user's wardrobe
        wardrobe_garments = get_garments_by_user(db, current_user.user_id)

        if not wardrobe_garments:
            # Empty wardrobe
            return SimilarityAnalysisResponse(
                target_garment={
                    "category": recognition_result.category,
                    "main_color": recognition_result.main_color.model_dump(),
                    "style_tags": recognition_result.style_tags,
                },
                similar_garments=[],
                has_duplicate_warning=False,
                recommendation="您的衣橱中还没有服饰，这是第一件！",
            )

        # Prepare wardrobe features
        import numpy as np

        wardrobe_features = [
            (garment.garment_id, np.array(garment.feature_vector)) for garment in wardrobe_garments
        ]

        # Initialize similarity analyzer
        analyzer = SimilarityAnalyzer(high_threshold=0.8, medium_threshold=0.5)

        # Find similar garments
        target_feature = np.array(recognition_result.feature_vector)
        similarity_matches: List[SimilarityMatch] = analyzer.find_similar_garments(
            target_feature=target_feature,
            wardrobe_features=wardrobe_features,
            min_threshold=0.3,  # Only show matches above 0.3
            top_k=10,  # Top 10 similar garments
        )

        # Build similar garments info
        similar_garments_info = []
        garment_dict = {g.garment_id: g for g in wardrobe_garments}

        for match in similarity_matches:
            garment = garment_dict.get(match.garment_id)
            if garment:
                similar_garments_info.append(
                    SimilarGarmentInfo(
                        garment_id=str(garment.garment_id),
                        similarity_score=match.similarity_score,
                        similarity_level=match.similarity_level,
                        image_url=garment.image_url,
                        category=garment.category,
                        main_color=ColorSchema(**garment.main_color),
                    )
                )

        # Check for duplicate warning
        has_duplicate = analyzer.has_duplicate_warning(similarity_matches)

        # Get user profile for recommendation
        user_profile = get_profile_by_user_id(db, current_user.user_id)
        budget_range = user_profile.budget_range if user_profile else None

        # Generate recommendation message
        recommendation = analyzer.get_recommendation_message(similarity_matches, budget_range)

        return SimilarityAnalysisResponse(
            target_garment={
                "category": recognition_result.category,
                "category_confidence": recognition_result.category_confidence,
                "main_color": recognition_result.main_color.model_dump(),
                "secondary_colors": [c.model_dump() for c in recognition_result.secondary_colors],
                "style_tags": recognition_result.style_tags,
            },
            similar_garments=similar_garments_info,
            has_duplicate_warning=has_duplicate,
            recommendation=recommendation,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image processing failed: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Similarity analysis failed: {str(e)}",
        )


class OutfitRecommendationResponse(BaseModel):
    """Outfit recommendation response"""

    target_garment: dict = Field(..., description="Target garment recognition result")
    outfit_cards: List[dict] = Field(default_factory=list, description="Outfit recommendations")

    class Config:
        json_schema_extra = {
            "example": {
                "target_garment": {
                    "category": "上衣",
                    "main_color": {"name": "白", "hex_code": "#ffffff"},
                    "style_tags": ["简约", "通勤"],
                },
                "outfit_cards": [
                    {
                        "outfit_id": "outfit_1",
                        "items": [],
                        "occasion": "商务",
                        "description": "白色衬衫搭配黑色西裤，适合正式场合",
                        "color_harmony": "中性色搭配",
                        "color_harmony_score": 0.9,
                        "style_consistency": 0.95,
                        "overall_score": 0.92,
                    }
                ],
            }
        }


@router.post("/outfits", response_model=OutfitRecommendationResponse)
async def recommend_outfits(
    file: UploadFile = File(...),
    num_outfits: int = 3,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate outfit recommendations for uploaded garment

    This endpoint:
    1. Recognizes the uploaded garment image
    2. Finds matching garments from wardrobe
    3. Generates outfit combinations
    4. Returns top N outfit recommendations
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG, WebP)",
        )

    # Validate num_outfits
    if num_outfits < 1 or num_outfits > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="num_outfits must be between 1 and 10",
        )

    try:
        # Read image file
        image_bytes = await file.read()

        # Initialize image recognizer
        recognizer = ImageRecognizer()

        # Recognize image
        recognition_result: RecognitionResult = recognizer.recognize(image_bytes)

        # Get user's wardrobe
        wardrobe_garments = get_garments_by_user(db, current_user.user_id)

        if not wardrobe_garments:
            # Empty wardrobe - cannot generate recommendations
            return OutfitRecommendationResponse(
                target_garment={
                    "category": recognition_result.category,
                    "main_color": recognition_result.main_color.model_dump(),
                    "style_tags": recognition_result.style_tags,
                },
                outfit_cards=[],
            )

        # Create a temporary garment object for the target
        from uuid import uuid4

        from app.models.garment import Garment

        target_garment = Garment(
            garment_id=uuid4(),
            user_id=current_user.user_id,
            category=recognition_result.category,
            main_color=recognition_result.main_color.model_dump(),
            secondary_colors=[c.model_dump() for c in recognition_result.secondary_colors],
            style_tags=recognition_result.style_tags,
            fit_type=None,
            image_path="",
            image_url="",
            feature_vector=recognition_result.feature_vector,
        )

        # Initialize outfit recommender
        from app.services.outfit_recommender import OutfitRecommender

        recommender = OutfitRecommender()

        # Generate outfit recommendations
        outfit_cards = recommender.recommend_outfits(
            target_garment=target_garment,
            wardrobe=wardrobe_garments,
            num_outfits=num_outfits,
        )

        # Convert to dict for response
        outfit_cards_dict = [card.model_dump() for card in outfit_cards]

        return OutfitRecommendationResponse(
            target_garment={
                "category": recognition_result.category,
                "category_confidence": recognition_result.category_confidence,
                "main_color": recognition_result.main_color.model_dump(),
                "secondary_colors": [c.model_dump() for c in recognition_result.secondary_colors],
                "style_tags": recognition_result.style_tags,
            },
            outfit_cards=outfit_cards_dict,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image processing failed: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Outfit recommendation failed: {str(e)}",
        )


class SuitabilityAnalysisResponse(BaseModel):
    """Suitability analysis response"""

    garment: dict = Field(..., description="Garment recognition result")
    suitability_score: int = Field(..., ge=0, le=100, description="Overall suitability score")
    color_score: int = Field(..., ge=0, le=100, description="Color suitability score")
    fit_score: int = Field(..., ge=0, le=100, description="Fit suitability score")
    style_score: int = Field(..., ge=0, le=100, description="Style suitability score")
    explanation: Dict[str, str] = Field(..., description="Score explanations")
    recommended_occasions: List[str] = Field(
        default_factory=list, description="Recommended occasions"
    )
    suggestions: List[str] = Field(default_factory=list, description="Improvement suggestions")

    class Config:
        json_schema_extra = {
            "example": {
                "garment": {
                    "category": "上衣",
                    "main_color": {"name": "粉色", "hex_code": "#ffc0cb"},
                    "style_tags": ["甜美"],
                    "fit_type": "修身",
                },
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


@router.post("/suitability", response_model=SuitabilityAnalysisResponse)
async def analyze_suitability(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Analyze garment suitability for user

    This endpoint:
    1. Recognizes the uploaded garment image
    2. Gets user profile
    3. Calculates color, fit, and style suitability scores
    4. Returns overall score, explanations, and suggestions
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG, WebP)",
        )

    try:
        # Read image file
        image_bytes = await file.read()

        # Initialize image recognizer
        recognizer = ImageRecognizer()

        # Recognize image
        recognition_result: RecognitionResult = recognizer.recognize(image_bytes)

        # Get user profile
        user_profile = get_profile_by_user_id(db, current_user.user_id)

        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please create a profile first.",
            )

        # Initialize suitability scorer
        from app.services.suitability_scorer import SuitabilityScorer

        scorer = SuitabilityScorer()

        # Calculate suitability score
        suitability_result = scorer.calculate_score(
            garment_color=recognition_result.main_color,
            secondary_colors=recognition_result.secondary_colors,
            garment_fit=recognition_result.fit_type,
            garment_styles=recognition_result.style_tags,
            user_profile=user_profile,
        )

        return SuitabilityAnalysisResponse(
            garment={
                "category": recognition_result.category,
                "category_confidence": recognition_result.category_confidence,
                "main_color": recognition_result.main_color.model_dump(),
                "secondary_colors": [c.model_dump() for c in recognition_result.secondary_colors],
                "style_tags": recognition_result.style_tags,
                "fit_type": recognition_result.fit_type,
            },
            suitability_score=suitability_result.suitability_score,
            color_score=suitability_result.color_score,
            fit_score=suitability_result.fit_score,
            style_score=suitability_result.style_score,
            explanation=suitability_result.explanation,
            recommended_occasions=suitability_result.recommended_occasions,
            suggestions=suitability_result.suggestions,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image processing failed: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Suitability analysis failed: {str(e)}",
        )
