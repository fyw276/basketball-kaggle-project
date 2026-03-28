"""
Analysis API endpoints (similarity, recommendations, suitability)
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
    """Outfit recommendation response (3D: 场景-品类-风格 + 无性别推荐)"""

    target_garment: dict = Field(..., description="Target garment recognition result")
    outfit_cards: List[dict] = Field(
        default_factory=list,
        description="Outfit recommendations with 5D scores (scene/category/style/color/gender)",
    )
    gender_expression_used: Optional[float] = Field(
        default=None,
        description="The gender_expression value used for scoring (None for male users)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "target_garment": {
                    "category": "上衣",
                    "main_color": {"name": "白", "hex_code": "#ffffff"},
                    "style_tags": ["简约", "通勤"],
                    "occasions": ["通勤上班", "校园"],
                },
                "outfit_cards": [
                    {
                        "outfit_id": "outfit_1",
                        "scene": "通勤上班",
                        "secondary_scenes": ["商务正式", "校园"],
                        "items": [],
                        "description": "简约通勤穿搭，白色上衣 + 深蓝裤子，通勤干练",
                        "scene_score": 0.92,
                        "category_score": 1.0,
                        "style_score": 0.88,
                        "color_score": 0.85,
                        "gender_compatibility": 0.85,
                        "overall_score": 0.90,
                        "dimension_weights": {
                            "scene": 0.28,
                            "category": 0.22,
                            "style": 0.22,
                            "color": 0.18,
                            "gender": 0.10,
                        },
                    }
                ],
                "gender_expression_used": 0.5,
            }
        }


@router.post("/outfits", response_model=OutfitRecommendationResponse)
async def recommend_outfits(
    file: UploadFile = File(...),
    num_outfits: int = 3,
    scene: Optional[str] = None,
    # 无性别推荐系统参数（修正版）
    gender_expression: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="性别表达指数（仅对女性生效）: 0=偏男性化，1=偏女性化",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate outfit recommendations (3D: 场景-品类-风格 + 无性别推荐)

    无性别推荐系统（修正版）：
    - 女性用户（gender == "女"）：全量召回，应用 gender_compatibility 评分
    - 男性用户（gender == "男"）：默认仅召回 [male, neutral]，不应用 gender_compatibility
    - 男性用户（explore_cross_gender=True）：小比例混入 neutral_score>0.7 的女款
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

        # Recognize image using CLIP (FashionCLIP approach)
        try:
            from app.ml.clip_recognizer import get_clip_recognizer

            recognizer = get_clip_recognizer()
            clip_result = recognizer.recognize(image_bytes)
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image recognition failed: {str(e)}",
            )

        # Get user's wardrobe
        wardrobe_garments = get_garments_by_user(db, current_user.user_id)

        if not wardrobe_garments:
            # Empty wardrobe - cannot generate recommendations
            return OutfitRecommendationResponse(
                target_garment={
                    "category": clip_result["category"],
                    "main_color": clip_result.get("main_color", {}),
                    "style_tags": clip_result["style_tags"],
                },
                outfit_cards=[],
            )

        # Get user's profile for scene and body type inference
        user_profile = get_profile_by_user_id(db, current_user.user_id)
        user_style_prefs = user_profile.style_preference if user_profile else []
        user_body_type = user_profile.body_type if user_profile else None
        avoid_body_parts = user_profile.avoid_body_parts if user_profile else []

        # 无性别推荐系统（修正版）：从 profile 获取性别信息
        user_gender = getattr(user_profile, 'gender', None) if user_profile else None
        profile_gender_expression = getattr(user_profile, 'gender_expression', None) if user_profile else None
        explore_cross_gender = getattr(user_profile, 'explore_cross_gender', False) if user_profile else False

        # API 传参优先；若未传参且用户为女性，使用 profile 中的值
        is_female = user_gender == "女"
        if gender_expression is not None:
            # API 显式传参，优先使用
            final_gender_expression = gender_expression if is_female else None
        else:
            # API 未传参：女性使用 profile 值，男性不使用
            final_gender_expression = profile_gender_expression if is_female else None

        # Create a temporary garment object for the target
        from uuid import uuid4

        from app.ml.color_extractor import ColorExtractor
        from app.models.garment import Garment
        from app.schemas.garment import ColorSchema

        color_extractor = ColorExtractor(n_colors=3)
        colors = color_extractor.extract_colors(image_bytes)
        main_color = (
            colors[0]
            if colors
            else ColorSchema(
                name="灰", rgb=(128, 128, 128), hsv=(0.0, 0.0, 50.0), hex_code="#808080"
            )
        )
        secondary_colors = colors[1:] if len(colors) > 1 else []

        # CLIP feature vector (pad to 1280)
        clip_features = clip_result["feature_vector"]
        feature_dim = len(clip_features)
        if feature_dim == 768:
            feature_vector = clip_features + [0.0] * 512
        elif feature_dim == 512:
            feature_vector = clip_features + [0.0] * 768
        else:
            feature_vector = clip_features[:1280] + [0.0] * max(0, 1280 - len(clip_features))

        target_garment = Garment(
            garment_id=uuid4(),
            user_id=current_user.user_id,
            category=clip_result["category"],
            main_color=main_color.model_dump(),
            secondary_colors=[c.model_dump() for c in secondary_colors],
            style_tags=clip_result["style_tags"],
            fit_type=clip_result.get("fit_type"),
            image_path="",
            image_url="",
            feature_vector=feature_vector,
        )

        # Initialize 3D outfit recommender (场景-品类-风格 + 无性别推荐)
        from app.services.outfit_recommender_3d import OutfitRecommender3D

        recommender = OutfitRecommender3D()

        # Generate outfit recommendations (无性别推荐系统修正版)
        outfit_cards = recommender.recommend_outfits(
            target_garment=target_garment,
            wardrobe=wardrobe_garments,
            num_outfits=num_outfits,
            user_style_preferences=user_style_prefs,
            user_body_type=user_body_type,
            avoid_body_parts=avoid_body_parts,
            preferred_scene=scene,
            # 无性别推荐系统参数（修正版）
            user_gender=user_gender,
            user_gender_expression=final_gender_expression,
            explore_cross_gender=explore_cross_gender,
        )

        # Convert to dict for response
        outfit_cards_dict = [card.model_dump() for card in outfit_cards]

        return OutfitRecommendationResponse(
            target_garment={
                "category": clip_result["category"],
                "category_confidence": clip_result["category_confidence"],
                "main_color": main_color.model_dump(),
                "secondary_colors": [c.model_dump() for c in secondary_colors],
                "style_tags": clip_result["style_tags"],
                "occasions": clip_result.get("occasions", []),
            },
            outfit_cards=outfit_cards_dict,
            gender_expression_used=final_gender_expression if is_female else None,
        )

    except HTTPException:
        raise
    except ValueError as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image processing failed: {str(e)}",
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Outfit recommendation failed: {str(e)}",
        )


class SuitabilityAnalysisResponse(BaseModel):
    """Suitability analysis response"""

    garment: dict = Field(..., description="Garment recognition result (CLIP + color extraction)")
    suitability_score: int = Field(..., ge=0, le=100, description="Overall suitability score")
    color_score: int = Field(..., ge=0, le=100, description="Color suitability score")
    fit_score: int = Field(..., ge=0, le=100, description="Body fit suitability score (体型适配)")
    style_score: int = Field(..., ge=0, le=100, description="Style suitability score")
    explanation: Dict[str, str] = Field(..., description="Score explanations per dimension")
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
                    "occasions": ["约会", "聚会"],
                },
                "suitability_score": 82,
                "color_score": 80,
                "fit_score": 70,
                "style_score": 85,
                "explanation": {
                    "scene": "服装适合约会、聚会等场合，与您的风格偏好高度匹配，色彩搭配也协调。",
                    "body": "修身版型可能会强化肩部线条，建议选择落肩款式",
                    "style": "甜美风格与您的甜美偏好完全契合",
                },
                "recommended_occasions": ["约会", "聚会", "度假旅行"],
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

        # Get user profile
        try:
            user_profile = get_profile_by_user_id(db, current_user.user_id)
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get user profile: {str(e)}",
            )

        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found. Please create a profile first.",
            )

        # Initialize suitability scorer (3D: 场景-体型-风格)
        try:
            from app.services.suitability_scorer_3d import SuitabilityScorer3D

            scorer = SuitabilityScorer3D()
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initialize scorer: {str(e)}",
            )

        # Recognize garment using CLIP (FashionCLIP approach)
        try:
            from app.ml.clip_recognizer import get_clip_recognizer

            recognizer = get_clip_recognizer()
            clip_result = recognizer.recognize(image_bytes)
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image recognition failed: {str(e)}",
            )

        # Extract colors
        from app.ml.color_extractor import ColorExtractor

        color_extractor = ColorExtractor(n_colors=3)
        colors = color_extractor.extract_colors(image_bytes)
        main_color = colors[0] if colors else None
        secondary_colors = colors[1:] if len(colors) > 1 else []

        if not main_color:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to extract color from image",
            )

        # Calculate suitability score (3D: 场景-体型-风格)
        try:
            suitability_result = scorer.calculate_score(
                garment_color=main_color,
                secondary_colors=secondary_colors,
                garment_fit=clip_result.get("fit_type"),
                garment_styles=clip_result["style_tags"],
                garment_category=clip_result["category"],
                user_profile=user_profile,
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Score calculation failed: {str(e)}",
            )

        return SuitabilityAnalysisResponse(
            garment={
                "category": clip_result["category"],
                "category_confidence": clip_result["category_confidence"],
                "main_color": main_color.model_dump(),
                "secondary_colors": [c.model_dump() for c in secondary_colors],
                "style_tags": clip_result["style_tags"],
                "fit_type": clip_result.get("fit_type"),
                "occasions": clip_result.get("occasions", []),
            },
            suitability_score=suitability_result.suitability_score,
            color_score=suitability_result.color_score,
            fit_score=suitability_result.fit_score,
            style_score=suitability_result.style_score,
            explanation=suitability_result.explanation,
            recommended_occasions=suitability_result.recommended_occasions,
            suggestions=suitability_result.suggestions,
        )

    except HTTPException:
        raise
    except ValueError as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image processing failed: {str(e)}",
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Suitability analysis failed: {str(e)}",
        )
