"""
Analysis API endpoints (similarity, recommendations, suitability)
"""

import io
import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from PIL import Image
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


def _coerce_str_list(val) -> List[str]:
    """画像里 JSON 字段在 SQLite 下偶发为 str，统一为 List[str]，避免推荐引擎迭代 None。"""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return [val] if val.strip() else []
    return []


MAX_OUTFIT_UPLOAD_IMAGES = 5


def _merge_clip_like_results(results: List[dict]) -> dict:
    """多张图：特征向量取平均，风格标签合并去重，品类取第一张（主图）。"""
    if not results:
        raise ValueError("empty clip results")
    if len(results) == 1:
        return results[0]
    vecs = [list(r["feature_vector"]) for r in results]
    max_len = max(len(v) for v in vecs)
    padded = [v + [0.0] * (max_len - len(v)) for v in vecs]
    n0 = max_len
    avg = [sum(padded[i][j] for i in range(len(padded))) / len(padded) for j in range(n0)]
    tag_seen = set()
    tags: List[str] = []
    for r in results:
        for t in r.get("style_tags") or []:
            if t not in tag_seen:
                tag_seen.add(t)
                tags.append(t)
    cat = results[0]["category"]
    confs = [float(r.get("category_confidence", 0.5)) for r in results]
    conf = sum(confs) / len(confs)
    occ_seen = set()
    occasions: List[str] = []
    for r in results:
        for o in r.get("occasions") or []:
            if o not in occ_seen:
                occ_seen.add(o)
                occasions.append(o)
    out = dict(results[0])
    out.update(
        {
            "feature_vector": avg,
            "style_tags": tags,
            "category": cat,
            "category_confidence": conf,
            "occasions": occasions,
        }
    )
    return out


def _recognize_image_bytes_to_clip_dict(image_bytes: bytes) -> dict:
    """单张图 → CLIP 结果 dict；失败则 MobileNet 兜底。"""
    try:
        from app.ml.clip_recognizer import get_clip_recognizer

        recognizer = get_clip_recognizer()
        return recognizer.recognize(image_bytes)
    except Exception as e:
        from app.core.logging import setup_logging

        logger = setup_logging()
        logger.warning(f"CLIP recognition failed, fallback to ImageRecognizer: {e}")
        legacy = ImageRecognizer().recognize(image_bytes)
        return {
            "category": legacy.category,
            "category_confidence": getattr(legacy, "category_confidence", 0.5),
            "style_tags": legacy.style_tags,
            "fit_type": None,
            "feature_vector": list(legacy.feature_vector),
            "main_color": legacy.main_color.model_dump(),
        }


def _map_ui_scene_to_engine(scene: Optional[str]) -> Optional[str]:
    """前端「穿搭推荐」场景 chip 与 SCENE_OUTFIT_TEMPLATES 键对齐。"""
    if not scene:
        return None
    from app.services.outfit_recommender_3d import SCENE_OUTFIT_TEMPLATES

    ui_to_engine = {
        "日常休闲": "休闲日常",
        "职场商务": "通勤上班",
        "约会聚会": "约会",
        "运动健身": "运动健身",
        "正式场合": "商务正式",
    }
    mapped = ui_to_engine.get(scene.strip(), scene.strip())
    if mapped in SCENE_OUTFIT_TEMPLATES:
        return mapped
    if scene.strip() in SCENE_OUTFIT_TEMPLATES:
        return scene.strip()
    return None


# 复用识别器，避免每次请求重新加载分类器/特征提取器（首次后显著加快相似度检测）
_image_recognizer_instance: Optional[ImageRecognizer] = None


def _get_image_recognizer() -> ImageRecognizer:
    global _image_recognizer_instance
    if _image_recognizer_instance is None:
        _image_recognizer_instance = ImageRecognizer()
    return _image_recognizer_instance


def _normalize_similarity_category(category: Optional[str]) -> str:
    text = (category or "").strip().lower()
    if not text:
        return "unknown"

    top_keywords = [
        "上衣",
        "t恤",
        "t-shirt",
        "shirt",
        "衬衫",
        "卫衣",
        "毛衣",
        "针织",
        "外套",
        "夹克",
        "top",
        "coat",
    ]
    bottom_keywords = [
        "裤",
        "pants",
        "trousers",
        "jeans",
        "短裤",
        "半裙",
        "半身裙",
        "skirt",
        "裙子",
    ]
    dress_keywords = ["连衣裙", "dress"]
    shoes_keywords = ["鞋", "shoe", "sneaker", "靴", "boot", "凉鞋", "sandals"]
    bag_keywords = ["包", "bag", "backpack", "handbag", "tote"]
    accessory_keywords = [
        "帽",
        "hat",
        "围巾",
        "scarf",
        "腰带",
        "belt",
        "首饰",
        "accessory",
        "眼镜",
        "glasses",
        "袜",
    ]

    if any(k in text for k in top_keywords):
        return "top"
    if any(k in text for k in bottom_keywords):
        return "bottom"
    if any(k in text for k in dress_keywords):
        return "dress"
    if any(k in text for k in shoes_keywords):
        return "shoes"
    if any(k in text for k in bag_keywords):
        return "bag"
    if any(k in text for k in accessory_keywords):
        return "accessory"
    return "unknown"


def _is_similarity_category_compatible(target_group: str, candidate_group: str) -> bool:
    if target_group == "unknown" or candidate_group == "unknown":
        return True
    return target_group == candidate_group


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
    try:
        # Read image file
        image_bytes = await file.read()

        ct = (file.content_type or "").lower()
        if not ct.startswith("image/"):
            try:
                Image.open(io.BytesIO(image_bytes)).verify()
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File must be an image (JPEG, PNG, WebP)",
                )

        # Recognize image（单例，避免重复初始化模型）
        recognizer = _get_image_recognizer()
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

        # Prepare candidate garments with coarse category filtering to reduce
        # cross-category false positives (e.g., top image matching shoes/bags).
        target_group = _normalize_similarity_category(recognition_result.category)
        target_conf = float(getattr(recognition_result, "category_confidence", 0.0) or 0.0)

        filtered_garments = wardrobe_garments
        if target_group != "unknown" and target_conf >= 0.45:
            compatible = [
                g
                for g in wardrobe_garments
                if _is_similarity_category_compatible(
                    target_group,
                    _normalize_similarity_category(getattr(g, "category", None)),
                )
            ]
            if compatible:
                filtered_garments = compatible

        # Prepare wardrobe features
        import numpy as np

        wardrobe_features = [
            (garment.garment_id, np.array(garment.feature_vector)) for garment in filtered_garments
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
        garment_dict = {g.garment_id: g for g in filtered_garments}

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
    file: Optional[UploadFile] = File(
        None,
        description="单张图片（兼容旧客户端，字段名 file）",
    ),
    files: Optional[List[UploadFile]] = File(
        None,
        description="多张图片（字段名 files，可重复；优先于 file）",
    ),
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

    支持 **多张上传**：对每张图做识别后合并特征（向量平均、标签合并），主图（预览）为第一张。

    无性别推荐系统（修正版）：
    - 女性用户（gender == "女"）：全量召回，应用 gender_compatibility 评分
    - 男性用户（gender == "男"）：默认仅召回 [male, neutral]，不应用 gender_compatibility
    - 男性用户（explore_cross_gender=True）：小比例混入 neutral_score>0.7 的女款
    """
    upload_list: List[UploadFile] = []
    if files:
        upload_list = [f for f in files if f is not None]
    if not upload_list and file is not None:
        upload_list = [file]
    if not upload_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少上传一张图片（file 或 files）",
        )
    if len(upload_list) > MAX_OUTFIT_UPLOAD_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"最多上传 {MAX_OUTFIT_UPLOAD_IMAGES} 张图片",
        )

    # Validate num_outfits
    if num_outfits < 1 or num_outfits > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="num_outfits must be between 1 and 10",
        )

    try:
        all_bytes: List[bytes] = []
        filenames: List[str] = []
        for uf in upload_list:
            if not uf.content_type or not uf.content_type.startswith("image/"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="所有文件必须是图片（JPEG, PNG, WebP）",
                )
            all_bytes.append(await uf.read())
            filenames.append((uf.filename or "upload.jpg").strip() or "upload.jpg")

        # 每张图识别，再合并为一次推荐用的「虚拟目标」
        per_image: List[dict] = []
        for b in all_bytes:
            per_image.append(_recognize_image_bytes_to_clip_dict(b))
        clip_result = _merge_clip_like_results(per_image)

        # 主图：第一张（预览与颜色提取）
        image_bytes = all_bytes[0]
        preview_name = filenames[0]

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
        user_style_prefs = _coerce_str_list(user_profile.style_preference if user_profile else [])
        user_body_type = user_profile.body_type if user_profile else None
        avoid_body_parts = _coerce_str_list(user_profile.avoid_body_parts if user_profile else [])
        engine_scene = _map_ui_scene_to_engine(scene)

        # 无性别推荐系统（修正版）：从 profile 获取性别信息
        user_gender = getattr(user_profile, "gender", None) if user_profile else None
        profile_gender_expression = (
            getattr(user_profile, "gender_expression", None) if user_profile else None
        )
        explore_cross_gender = (
            getattr(user_profile, "explore_cross_gender", False) if user_profile else False
        )

        # API 传参优先；若未传参且用户为女性，使用 profile 中的值
        is_female = user_gender == "女"
        if gender_expression is not None:
            # API 显式传参，优先使用
            final_gender_expression = gender_expression if is_female else None
        else:
            # API 未传参：女性使用 profile 值，男性不使用
            final_gender_expression = profile_gender_expression if is_female else None

        # Persist upload so target garment has a real /uploads URL
        # (否则组合里「上衣」常为当前图但 image_url 为空，前端无法显示)
        from uuid import uuid4

        from app.ml.color_extractor import ColorExtractor
        from app.models.garment import Garment
        from app.schemas.garment import ColorSchema
        from app.services.storage import StorageService

        storage = StorageService()
        target_image_path, target_image_url = storage.save_image_bytes(
            image_bytes,
            str(current_user.user_id),
            original_name=preview_name,
        )

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
            image_path=target_image_path,
            image_url=target_image_url,
            feature_vector=feature_vector,
        )

        # Initialize 3D outfit recommender (场景-品类-风格 + 无性别推荐)
        from app.services.feedback_prefs import get_rerank_context
        from app.services.outfit_recommender_3d import OutfitRecommender3D

        recommender = OutfitRecommender3D()
        rerank_ctx = get_rerank_context(db, current_user.user_id)

        # Generate outfit recommendations (无性别推荐系统修正版)
        outfit_cards = recommender.recommend_outfits(
            target_garment=target_garment,
            wardrobe=wardrobe_garments,
            num_outfits=num_outfits,
            user_style_preferences=user_style_prefs,
            user_body_type=user_body_type,
            avoid_body_parts=avoid_body_parts,
            preferred_scene=engine_scene,
            # 无性别推荐系统参数（修正版）
            user_gender=user_gender,
            user_gender_expression=final_gender_expression,
            explore_cross_gender=explore_cross_gender,
            feedback_rerank=rerank_ctx,
        )

        # Convert to dict for response
        outfit_cards_dict = [card.model_dump() for card in outfit_cards]

        return OutfitRecommendationResponse(
            target_garment={
                "category": clip_result["category"],
                "category_confidence": clip_result.get("category_confidence", 0.5),
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
    scene_match_reason: str = Field("", description="场景匹配原因说明")
    body_fit_reason: str = Field("", description="体型适配原因说明")
    style_coordination_reason: str = Field("", description="风格协调原因说明")

    # Frontend legacy-friendly fields (0-1 floats)
    overall_score: float = Field(0.0, ge=0.0, le=1.0, description="Overall score (0-1)")
    scene_score: float = Field(0.0, ge=0.0, le=1.0, description="Scene score (0-1)")
    body_shape_score: float = Field(0.0, ge=0.0, le=1.0, description="Body score (0-1)")
    analysis: str = Field("", description="Summary analysis text")
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

        def _reason_fallback(key: str) -> str:
            exp = (suitability_result.explanation or {}).get(key, "").strip()
            if exp:
                return exp

            body_type = getattr(user_profile, "body_type", "") or ""
            prefs = getattr(user_profile, "style_preference", []) or []
            pref_str = "、".join([str(x) for x in prefs if str(x).strip()][:3])
            gcat = str(clip_result.get("category") or "").strip()
            gfit = str(clip_result.get("fit_type") or "").strip()
            gst = clip_result.get("style_tags") or []
            gst_str = "、".join([str(x) for x in gst if str(x).strip()][:3])

            if key == "scene":
                if gst_str:
                    return f"基于识别到的风格标签（{gst_str}）推断场景适配；可结合你选择的场景做进一步判断。"
                return "缺少可用的风格标签，场景适配主要参考你的偏好与服装类别。"
            if key == "body":
                if body_type and gfit and gcat:
                    return (
                        f"{gcat}的{gfit}版型会影响整体比例，与{body_type}体型的重点修饰方向相关。"
                    )
                if body_type:
                    return f"体型适配会结合你的体型（{body_type}）与衣物的版型/剪裁特征进行判断。"
                return "体型信息不足，建议先在个人设置完善体型与希望修饰部位。"
            if key == "style":
                if pref_str and gst_str:
                    return f"服装风格标签（{gst_str}）与个人偏好（{pref_str}）共同决定风格协调度。"
                if pref_str:
                    return f"风格协调度主要参考你的风格偏好（{pref_str}）与衣物风格特征。"
                return "风格偏好信息不足，建议先在个人设置补充风格偏好。"
            return ""

        scene_reason = _reason_fallback("scene")
        body_reason = _reason_fallback("body")
        style_reason = _reason_fallback("style")

        overall = float(suitability_result.suitability_score) / 100.0
        scene_score = float(getattr(suitability_result, "scene_score", 0) or 0) / 100.0
        body_score = (
            float(getattr(suitability_result, "body_score", suitability_result.fit_score) or 0)
            / 100.0
        )

        summary_bits = []
        if scene_reason:
            summary_bits.append(f"场景：{scene_reason}")
        if body_reason:
            summary_bits.append(f"体型：{body_reason}")
        if style_reason:
            summary_bits.append(f"风格：{style_reason}")
        summary = "；".join(summary_bits)[:520]

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
            scene_match_reason=scene_reason,
            body_fit_reason=body_reason,
            style_coordination_reason=style_reason,
            overall_score=overall,
            scene_score=scene_score,
            body_shape_score=body_score,
            analysis=summary,
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
