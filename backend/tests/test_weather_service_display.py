"""天气逆地理展示：过滤国道/省道/某某线等易误判道路名，优先展示省市区。"""

import pytest

from app.services.weather_service import (
    _amap_cn_weather_to_wmo_approx,
    _display_address_after_route_filter,
    _format_full_address,
    _is_route_like_road,
    _normalize_admin_parts,
    _normalize_city_query,
    _should_try_nominatim_after_geocode,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("山深线", True),
        ("G205国道", True),
        ("某省道", True),
        ("京沪高速", True),
        ("长安街", False),
        ("建设路", False),
        ("", False),
    ],
)
def test_is_route_like_road(text, expected):
    assert _is_route_like_road(text) is expected


def test_display_drops_route_street_keeps_admin():
    p, c, d, s_out, full = _display_address_after_route_filter(
        "河北省", "沧州市", "盐山县", "山深线"
    )
    assert s_out == ""
    assert "山深线" not in full
    assert full == "河北省 沧州市 盐山县"


def test_display_keeps_normal_street():
    p, c, d, s_out, full = _display_address_after_route_filter(
        "河北省", "沧州市", "盐山县", "银河大街"
    )
    assert s_out == "银河大街"
    assert "银河大街" in full


def test_display_when_only_route_no_admin_fallback():
    """无省市区时仍保留原 street，避免变成空串。"""
    p, c, d, s_out, full = _display_address_after_route_filter("", "", "", "山深线")
    assert s_out == "山深线"
    assert "山深线" in full


def test_normalize_city_query_strips_cn_suffixes():
    assert _normalize_city_query("郑州市") == "郑州"
    assert _normalize_city_query("河南省郑州市") == "郑州"
    assert _normalize_city_query("  郑州 市  ") == "郑州"
    assert _normalize_city_query("香港特别行政区") == "香港"


def test_normalize_admin_parts_dedup_city_district():
    p, c, d, s = _normalize_admin_parts("河南", "郑州", "郑州", "")
    assert p == "河南省"
    assert c == "郑州市"
    assert d == ""
    assert _format_full_address(p, c, d, s) == "河南省 郑州市"


def test_amap_cn_weather_to_wmo_approx_maps_common():
    assert _amap_cn_weather_to_wmo_approx("晴") == 0
    assert _amap_cn_weather_to_wmo_approx("多云") == 2
    assert _amap_cn_weather_to_wmo_approx("阴") == 3
    assert _amap_cn_weather_to_wmo_approx("阵雨") == 61
    assert _amap_cn_weather_to_wmo_approx("雷阵雨") == 95


def test_amap_reverse_success_is_not_overridden_by_nominatim():
    assert _should_try_nominatim_after_geocode("amap") is False
    assert _should_try_nominatim_after_geocode("open_meteo_zh") is True
    assert _should_try_nominatim_after_geocode("none") is True
