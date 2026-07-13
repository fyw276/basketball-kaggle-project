"""Tests for detail_fidelity mode category locking for lower-body garments."""

from __future__ import annotations

from app.services.tryon_v2.catvton_engine_client import _catvton_category_hint


class TestCatvtonCategoryHint:
    """Verify _catvton_category_hint maps garment categories to CatVTON types."""

    def test_lower_body_english_bottom(self):
        assert _catvton_category_hint("bottom") == "lower"

    def test_lower_body_chinese_xiazhuang(self):
        assert _catvton_category_hint("下装") == "lower"

    def test_lower_body_chinese_ku(self):
        assert _catvton_category_hint("裤") == "lower"

    def test_lower_body_chinese_kuzi(self):
        assert _catvton_category_hint("裤子") == "lower"

    def test_lower_body_chinese_changku(self):
        assert _catvton_category_hint("长裤") == "lower"

    def test_lower_body_english_pants(self):
        assert _catvton_category_hint("pants") == "lower"

    def test_lower_body_english_shorts(self):
        assert _catvton_category_hint("短裤") == "lower"

    def test_lower_body_lower_keyword(self):
        """cloth_type='lower' must be recognized (was the root cause bug)."""
        assert _catvton_category_hint("lower") == "lower"

    def test_upper_body_english_top(self):
        assert _catvton_category_hint("top") == "upper"

    def test_upper_body_chinese_shangyi(self):
        assert _catvton_category_hint("上衣") == "upper"

    def test_dress_overall(self):
        assert _catvton_category_hint("dress") == "overall"
        assert _catvton_category_hint("连衣裙") == "overall"

    def test_skirt_overall(self):
        assert _catvton_category_hint("skirt") == "overall"
        assert _catvton_category_hint("裙") == "overall"

    def test_empty_defaults_to_upper(self):
        assert _catvton_category_hint("") == "upper"
        assert _catvton_category_hint(None) == "upper"


class TestDetailFidelityClothTypeMapping:
    """Verify the cloth_type mapping logic used in detail_fidelity mode."""

    @staticmethod
    def _compute_cloth_type(garment_category: str | None) -> str:
        from app.services.tryon_v2.category_utils import map_to_catvton_cloth_type

        return map_to_catvton_cloth_type(garment_category)

    def test_bottom_maps_to_lower(self):
        assert self._compute_cloth_type("bottom") == "lower"

    def test_xiazhuang_maps_to_lower(self):
        assert self._compute_cloth_type("下装") == "lower"

    def test_ku_maps_to_lower(self):
        assert self._compute_cloth_type("裤") == "lower"

    def test_kuzi_maps_to_lower(self):
        assert self._compute_cloth_type("裤子") == "lower"

    def test_changku_maps_to_lower(self):
        assert self._compute_cloth_type("长裤") == "lower"

    def test_pants_maps_to_lower(self):
        """English 'pants' must map to lower (was a bug)."""
        assert self._compute_cloth_type("pants") == "lower"

    def test_jeans_and_trousers_map_to_lower(self):
        assert self._compute_cloth_type("jeans") == "lower"
        assert self._compute_cloth_type("trousers") == "lower"
        assert self._compute_cloth_type("牛仔裤") == "lower"

    def test_lower_maps_to_lower(self):
        """'lower' keyword must map to lower."""
        assert self._compute_cloth_type("lower") == "lower"

    def test_duanku_maps_to_lower(self):
        """'短裤' must map to lower."""
        assert self._compute_cloth_type("短裤") == "lower"

    def test_top_maps_to_upper(self):
        assert self._compute_cloth_type("top") == "upper"

    def test_dress_maps_to_overall(self):
        assert self._compute_cloth_type("dress") == "overall"

    def test_none_defaults_to_upper(self):
        assert self._compute_cloth_type(None) == "upper"

    def test_empty_defaults_to_upper(self):
        assert self._compute_cloth_type("") == "upper"


class TestClothTypeRoundTrip:
    """Ensure cloth_type from detail_fidelity survives _catvton_category_hint."""

    def test_lower_survives_hint(self):
        """The critical round-trip: detail_fidelity sets cloth_type='lower',
        call_local_catvton passes it to _catvton_category_hint → must stay 'lower'."""
        cloth_type = "lower"
        assert _catvton_category_hint(cloth_type) == "lower"

    def test_upper_survives_hint(self):
        assert _catvton_category_hint("upper") == "upper"

    def test_dress_survives_hint_as_overall(self):
        """dress → overall is the CatVTON type for full-body garments."""
        assert _catvton_category_hint("dress") == "overall"
