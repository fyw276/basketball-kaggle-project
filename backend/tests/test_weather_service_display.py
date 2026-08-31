"""天气逆地理展示：过滤国道/省道/某某线等易误判道路名，优先展示省市区。"""

import pytest

from app.services.weather_service import (
    _amap_cn_weather_to_wmo_approx,
    _display_address_after_route_filter,
    _format_full_address,
    _is_route_like_road,
    _normalize_admin_parts,
    _normalize_city_query,
    _wgs84_to_gcj02,
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


def test_wgs84_to_gcj02_converts_mainland_china_coordinates():
    latitude, longitude = _wgs84_to_gcj02(31.2304, 121.4737)
    assert latitude == pytest.approx(31.22846, abs=0.0001)
    assert longitude == pytest.approx(121.47822, abs=0.0001)


def test_wgs84_to_gcj02_keeps_overseas_coordinates_unchanged():
    assert _wgs84_to_gcj02(40.7128, -74.0060) == (40.7128, -74.0060)
