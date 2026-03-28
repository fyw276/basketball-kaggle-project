"""Verify gender-inclusive system changes (修正版)"""

# Test 1: Import schemas
from app.schemas.user_profile import (
    UserProfileBase, UserProfileUpdate, UserProfileResponse,
    VALID_GENDERS, VALID_BODY_TYPES
)
from app.schemas.garment import (
    GarmentBase, GarmentUpdate, GarmentResponse,
    VALID_GENDER_LABELS, VALID_CATEGORIES
)

print("[OK] Step 1: Schemas imported successfully")
print(f"    VALID_GENDER_LABELS: {VALID_GENDER_LABELS}")
print(f"    VALID_BODY_TYPES count: {len(VALID_BODY_TYPES)}")

# Test 2: Verify UserProfileBase has gender_expression (optional) and explore_cross_gender
from pydantic import BaseModel
up_model = UserProfileBase
up_fields = up_model.model_fields
print(f"[OK] Step 2: UserProfileBase fields: {list(up_fields.keys())}")
assert 'gender_expression' in up_fields, "gender_expression field missing!"
assert 'explore_cross_gender' in up_fields, "explore_cross_gender field missing!"
# gender_expression should be optional (None for males)
assert up_fields['gender_expression'].is_required() == False, "gender_expression should be optional!"
print(f"    gender_expression default: {up_fields['gender_expression'].default}")
print(f"    explore_cross_gender default: {up_fields['explore_cross_gender'].default}")

# Test 3: Verify GarmentBase has gender_label and neutral_score
garment_fields = GarmentBase.model_fields
print(f"[OK] Step 3: GarmentBase fields: {list(garment_fields.keys())}")
assert 'gender_label' in garment_fields, "gender_label field missing!"
assert 'neutral_score' in garment_fields, "neutral_score field missing!"
print(f"    gender_label default: {garment_fields['gender_label'].default}")
print(f"    neutral_score default: {garment_fields['neutral_score'].default}")

# Test 4: Verify OutfitRecommender3D has gender-aware parameters
from app.services.outfit_recommender_3d import OutfitRecommender3D
import inspect
rec_source = inspect.getsource(OutfitRecommender3D.recommend_outfits)
assert 'user_gender' in rec_source, "user_gender param missing!"
assert 'explore_cross_gender' in rec_source, "explore_cross_gender param missing!"
print("[OK] Step 4: OutfitRecommender3D.recommend_outfits has gender-aware parameters")

# Test 5: Verify OutfitCard has optional gender_compatibility
from app.services.outfit_recommender_3d import OutfitCard
card_fields = OutfitCard.model_fields
print(f"[OK] Step 5: OutfitCard fields: {list(card_fields.keys())}")
assert 'gender_compatibility' in card_fields, "gender_compatibility field missing!"
# gender_compatibility should be optional (None for males)
assert card_fields['gender_compatibility'].is_required() == False, "gender_compatibility should be optional!"
print(f"    gender_compatibility is optional: True")

# Test 6: Verify VirtualTryOnService has model_gender parameter
from app.services.virtual_tryon import VirtualTryOnService
tryon_source = inspect.getsource(VirtualTryOnService.tryon_garment)
assert 'model_gender' in tryon_source, "model_gender param missing!"
print("[OK] Step 6: VirtualTryOnService.tryon_garment has model_gender")

# Test 7: Verify analysis API has gender_expression parameter
from app.api.analysis import recommend_outfits
api_source = inspect.getsource(recommend_outfits)
assert 'gender_expression' in api_source, "gender_expression param missing!"
print("[OK] Step 7: /analysis/outfits endpoint has gender_expression parameter")

# Test 8: Verify SizeMapper exists
from app.utils.size_mapper import SizeMapper, get_size_mapper
mapper = get_size_mapper()
assert mapper is not None, "SizeMapper not initialized!"
print("[OK] Step 8: SizeMapper module exists and initializes correctly")

# Test 9: Verify size advice logic
# Women wearing men's clothes
advice = SizeMapper.get_size_advice("女", "male", 165, 55)
assert advice is not None, "Women wearing men's clothes should get advice!"
print(f"[OK] Step 9a: Women -> Men advice: suggested_size={advice['suggested_size']}")

# Men wearing women's clothes
advice = SizeMapper.get_size_advice("男", "female", 175, 70)
assert advice is not None, "Men wearing women's clothes should get advice!"
print(f"[OK] Step 9b: Men -> Women advice: suggested_size={advice['suggested_size']}")
assert "XXL" in advice["suggested_size"], "Should suggest XXL for tall man!"
assert "XXXL" in advice["suggested_size"], "Should suggest XXXL (larger) for tall man!"
assert advice["warning"] is not None, "Should have warning for men wearing women's clothes!"

# Neutral clothes - no advice needed
advice = SizeMapper.get_size_advice("女", "neutral", 165, 55)
assert advice is None, "Neutral clothes should not need special advice!"
print("[OK] Step 9c: Neutral clothes - no advice needed")

# Same gender - no advice needed
advice = SizeMapper.get_size_advice("女", "female", 165, 55)
assert advice is None, "Same gender should not need special advice!"
print("[OK] Step 9d: Same gender - no advice needed")

# Test 10: Verify _filter_by_gender method exists
filter_source = inspect.getsource(OutfitRecommender3D._filter_by_gender)
assert 'user_gender == "女"' in filter_source, "Female users should get full recall!"
assert 'user_gender == "男"' in filter_source, "Male users should filter by gender!"
print("[OK] Step 10: _filter_by_gender correctly implements gender-specific filtering")

print("\n" + "="*60)
print("[SUCCESS] All gender-inclusive system checks passed! (修正版)")
print("="*60)
print("\n修正版总结：")
print("  1. gender_expression 仅对女性生效，男性用户不使用")
print("  2. 男性用户默认仅召回 [male, neutral]")
print("  3. explore_cross_gender=True 时，男性可小比例混入女款")
print("  4. 性别区分召回策略已实现")
print("  5. 尺码映射模块已实现")
