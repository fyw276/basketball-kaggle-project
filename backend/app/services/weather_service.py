"""Open-Meteo + Nominatim 逆地理与天气（非 IP），供智能穿搭使用。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from app.core.logging import setup_logging

logger = setup_logging()

NOMINATIM_UA = "ClothingAssistant/1.1 (weather; +https://github.com)"

# 国道/省道/县道/高速及「某某线」等道路编号，逆地理常压在 street 上，对用户展示「省市区」更稳。
_ROUTE_NAME_HINT = re.compile(r"(国道|省道|县道|乡道|高速公路|快速路|环线|绕城|高速|^[Gg]\d{1,4})")

# 常见中文行政区后缀（用于 city 查询容错）
_CN_ADMIN_SUFFIX = re.compile(r"(特别行政区|自治区|自治州|地区|盟|省|市|县|区|旗|镇|乡|街道)$")

# 行政区常见后缀（用于“是否已带后缀”的判断）
_CN_PROVINCE_SUFFIX = ("省", "自治区", "特别行政区")
_CN_CITY_SUFFIX = ("市", "自治州", "地区", "盟")
_CN_DISTRICT_SUFFIX = ("区", "县", "市", "旗")


def _normalize_city_query(name: str) -> str:
    """
    归一化中文城市名查询：
    - 去空白
    - 去常见后缀（省/市/自治区/特别行政区等）
    - 兼容“河南省郑州市”这类：取最后一级并去后缀
    """
    s = (name or "").strip()
    if not s:
        return ""
    # 去掉所有空白（用户输入常见“郑州 市”）
    s = re.sub(r"\s+", "", s)
    # 去掉常见前缀“中华人民共和国/中国”
    s = s.replace("中华人民共和国", "").replace("中国", "").strip()
    # 若包含分隔符，取最后一级（省 市 城市）
    for sep in (" ", "-", "·", "/", "\\", ",", "，"):
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if parts:
                s = parts[-1]
    # 若是“河南省郑州市/新疆维吾尔自治区乌鲁木齐市”这类串联，取最后一级行政区名
    for token in ("特别行政区", "自治区", "省"):
        idx = s.rfind(token)
        if idx >= 0:
            tail = s[idx + len(token) :].strip()
            if tail:
                s = tail
            else:
                # “香港特别行政区”尾部无 tail，则取 token 前的主体
                s = s[:idx].strip() or s
            break
    # 去末尾后缀（可能需要多次：如“郑州市”）
    for _ in range(2):
        s2 = _CN_ADMIN_SUFFIX.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    return s


def _ensure_suffix(part: str, kind: str) -> str:
    """
    为省/市/区字段补全常见后缀。
    kind: province | city | district
    """
    s = (part or "").strip()
    if not s:
        return ""
    if kind == "province":
        if any(s.endswith(x) for x in _CN_PROVINCE_SUFFIX):
            return s
        if s in ("北京", "上海", "天津", "重庆"):
            return s + "市"
        return s + "省"
    if kind == "city":
        if any(s.endswith(x) for x in _CN_CITY_SUFFIX):
            return s
        return s + "市"
    if kind == "district":
        if any(s.endswith(x) for x in _CN_DISTRICT_SUFFIX):
            return s
        return s + "区"
    return s


def _normalize_admin_parts(
    province: str, city: str, district: str, street: str
) -> Tuple[str, str, str, str]:
    """
    严格清洗省/市/区/街道：
    - 禁止字段重复（如 district==city）
    - 禁止用市名填充区/街道
    - 补全省/市/区后缀（不强行修改 street，避免误加“街道”）
    """
    p = (province or "").strip()
    c = (city or "").strip()
    d = (district or "").strip()
    s = (street or "").strip()

    def _base(x: str) -> str:
        return _CN_ADMIN_SUFFIX.sub("", (x or "").strip())

    bp, bc, bd, bs = _base(p), _base(c), _base(d), _base(s)

    if bd and (bd == bc or bd == bp):
        d = ""
        bd = ""
    if bs and (bs == bd or bs == bc or bs == bp):
        s = ""

    p2 = _ensure_suffix(p, "province")
    c2 = _ensure_suffix(c, "city")
    d2 = _ensure_suffix(d, "district") if d else ""

    if d2 and _base(d2) == _base(c2):
        d2 = ""
    if s and _base(s) in (_base(d2), _base(c2), _base(p2)):
        s = ""

    return p2, c2, d2, s


def _format_full_address(province: str, city: str, district: str, street: str) -> str:
    """统一展示格式：省 市 区 街道（空段剔除，且按 base 去重）。"""
    out: List[str] = []
    seen: set[str] = set()
    for part in (province, city, district, street):
        t = (part or "").strip()
        if not t:
            continue
        b = _CN_ADMIN_SUFFIX.sub("", t)
        if not b or b in seen:
            continue
        seen.add(b)
        out.append(t)
    return _full_address_spaced(out)


def _is_route_like_road(street: str) -> bool:
    """判断是否为线路/国道类道路名（展示时可省略，避免「山深线」等掩盖真实区县感知）。"""
    t = (street or "").strip()
    if not t:
        return False
    if _ROUTE_NAME_HINT.search(t):
        return True
    if t.endswith("线") and len(t) <= 12 and "地铁" not in t and "公交" not in t:
        return True
    return False


def _display_address_after_route_filter(
    province: str, city: str, district: str, street: str
) -> Tuple[str, str, str, str, str]:
    """
    若有省市区且最后一级为线路型道路名，则展示行去掉道路，仅保留省市区。
    返回 (province, city, district, street, full_address)。
    """
    p = (province or "").strip()
    c = (city or "").strip()
    d = (district or "").strip()
    s = (street or "").strip()
    admin_line = _full_address_spaced([p, c, d])
    full = _full_address_spaced([p, c, d, s])
    if s and _is_route_like_road(s) and admin_line.strip():
        return p, c, d, "", admin_line
    return p, c, d, s, full


def wmo_to_cn(weather_code: int) -> str:
    """WMO code → 简短中文天气描述。"""
    if weather_code == 0:
        return "晴"
    if weather_code in (1, 2, 3):
        return "多云"
    if weather_code in (45, 48):
        return "雾"
    if weather_code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "雨"
    if weather_code in (71, 73, 75, 77, 85, 86):
        return "雪"
    if weather_code in (95, 96, 99):
        return "雷雨"
    return "阴"


def _full_address_spaced(parts: List[str]) -> str:
    """省 市 区 街道：空格分隔，空段剔除。"""
    return " ".join(p.strip() for p in parts if p and str(p).strip())


def _structured_from_open_meteo(r: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """Open-Meteo 单条 result → 省、市、区、街道/路。"""
    province = str(r.get("admin1") or "").strip()
    city = str(r.get("admin2") or "").strip()
    district = str(r.get("admin3") or "").strip()
    street = str(r.get("admin4") or "").strip()
    if not street:
        street = str(r.get("name") or "").strip()
    return province, city, district, street


def _line_from_om_result(r0: Dict[str, Any]) -> str:
    """
    从 Open-Meteo reverse 单条结果拼展示用一行地址。
    在 admin1–4 与 name 的组合经 _structured 仍为空时，补用 name/admin/country 等字段。
    """
    if not r0:
        return ""
    p, c, d, s = _structured_from_open_meteo(r0)
    line = _full_address_spaced([p, c, d, s])
    if line.strip():
        return line
    name = str(r0.get("name") or "").strip()
    a1 = str(r0.get("admin1") or "").strip()
    a2 = str(r0.get("admin2") or "").strip()
    a3 = str(r0.get("admin3") or "").strip()
    a4 = str(r0.get("admin4") or "").strip()
    country = str(r0.get("country") or "").strip()
    return _full_address_spaced([a1, a2, a3, a4, name, country])


async def _nominatim_reverse(
    client: httpx.AsyncClient, latitude: float, longitude: float
) -> Optional[Tuple[str, str, str, str, str]]:
    """
    Nominatim 逆地理，补全道路级地址。返回 (province, city, district, street, full_line)。
    """
    url = (
        "https://nominatim.openstreetmap.org/reverse"
        f"?lat={latitude}&lon={longitude}&format=json&accept-language=zh-CN"
    )
    try:
        res = await client.get(url, headers={"User-Agent": NOMINATIM_UA}, timeout=15.0)
        res.raise_for_status()
        data = res.json()
        addr = data.get("address") or {}
        province = str(
            addr.get("state") or addr.get("region") or addr.get("province") or ""
        ).strip()
        city = str(
            addr.get("city")
            or addr.get("town")
            or addr.get("county")
            or addr.get("municipality")
            or ""
        ).strip()
        district = str(
            addr.get("city_district")
            or addr.get("district")
            or addr.get("county")
            or addr.get("suburb")
            or ""
        ).strip()
        if district == city:
            district = str(addr.get("suburb") or addr.get("neighbourhood") or "").strip()
        street = str(
            addr.get("road")
            or addr.get("pedestrian")
            or addr.get("path")
            or addr.get("quarter")
            or addr.get("neighbourhood")
            or addr.get("suburb")
            or addr.get("village")
            or addr.get("hamlet")
            or ""
        ).strip()
        if not province and not city:
            dl = str(data.get("display_name") or "").strip()
            if dl:
                return ("", "", "", "", dl[:240])
            return None
        line = _full_address_spaced([province, city, district, street])
        if not line.strip():
            dl = str(data.get("display_name") or "").strip()
            if dl:
                return ("", "", "", "", dl[:240])
            return None
        return (province, city, district, street, line)
    except Exception as e:
        logger.warning(f"nominatim reverse failed: {e}")
        return None


async def _nominatim_search_city(
    client: httpx.AsyncClient, name: str
) -> Optional[Tuple[float, float, str]]:
    """
    Nominatim 正向地理编码（按城市名搜索），返回 (lat, lon, display_name)。
    仅作为 open-meteo search 无结果时的兜底。
    """
    q = _normalize_city_query(name)
    if not q:
        return None
    url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={quote(q)}&format=json&limit=1&accept-language=zh-CN"
    )
    try:
        res = await client.get(url, headers={"User-Agent": NOMINATIM_UA}, timeout=15.0)
        res.raise_for_status()
        arr = res.json() or []
        if not isinstance(arr, list) or not arr:
            return None
        r0 = arr[0] or {}
        lat = float(r0.get("lat"))
        lon = float(r0.get("lon"))
        dn = str(r0.get("display_name") or q).strip()
        return lat, lon, dn[:240]
    except Exception as e:
        logger.warning(f"nominatim search failed: {e}")
        return None


async def fetch_weather_lat_lon(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    高精度经纬度：Open-Meteo 逆地理 + 必要时 Nominatim 补全；**不在展示字段中出现经纬度数字**。
    """
    async with httpx.AsyncClient(timeout=25.0) as client:
        geo_url = (
            "https://geocoding-api.open-meteo.com/v1/reverse"
            f"?latitude={latitude}&longitude={longitude}&language=zh&format=json"
        )
        city_short = "当前位置"
        r0: Dict[str, Any] = {}
        try:
            gr = await client.get(geo_url)
            gr.raise_for_status()
            gj = gr.json()
            results = gj.get("results") or []
            if results:
                r0 = results[0]
                city_short = str(r0.get("name") or city_short).strip() or city_short
        except Exception as e:
            logger.warning(f"open-meteo reverse failed: {e}")

        om_struct = _structured_from_open_meteo(r0) if r0 else ("", "", "", "")
        op, oc, od, os = om_struct
        line_om = _full_address_spaced([op, oc, od, os])
        p, c, d, s = op, oc, od, os
        full_line = line_om
        nom = await _nominatim_reverse(client, latitude, longitude)
        if nom:
            np, nc, nd, ns, nline = nom
            if np or nc or nd or ns:
                merged = _full_address_spaced([np or op, nc or oc, nd or od, ns or os])
                if len(nline) >= len(merged) and len(nline) >= len(line_om):
                    p, c, d, s = np or op, nc or oc, nd or od, ns or os
                    full_line = nline
                else:
                    p, c, d, s = np or op, nc or oc, nd or od, ns or os
                    full_line = merged or nline
            elif nline:
                full_line = nline
        if not full_line.strip() and r0:
            fb = _line_from_om_result(r0)
            if fb.strip():
                full_line = fb
                om_struct = _structured_from_open_meteo(r0)
                p, c, d, s = om_struct
        if not full_line.strip():
            try:
                geo_url_en = (
                    "https://geocoding-api.open-meteo.com/v1/reverse"
                    f"?latitude={latitude}&longitude={longitude}&language=en&format=json"
                )
                gr2 = await client.get(geo_url_en)
                gr2.raise_for_status()
                gj2 = gr2.json()
                results_en = gj2.get("results") or []
                if results_en:
                    r_en = results_en[0]
                    fb = _line_from_om_result(r_en)
                    if fb.strip():
                        r0 = r_en
                        full_line = fb
                        city_short = str(r_en.get("name") or city_short).strip() or city_short
                        om_struct = _structured_from_open_meteo(r_en)
                        p, c, d, s = om_struct
            except Exception as e:
                logger.warning(f"open-meteo reverse (en fallback) failed: {e}")
        if not full_line.strip() and city_short and city_short != "当前位置":
            full_line = city_short
        if not full_line.strip():
            full_line = "未能解析详细地址，请点击「手动选择地址」"

        p, c, d, s = _normalize_admin_parts(p, c, d, s)
        p, c, d, s, _ = _display_address_after_route_filter(p, c, d, s)
        full_line = _format_full_address(p, c, d, s) or full_line

        wx_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            "&current=temperature_2m,weather_code&timezone=auto"
        )
        wr = await client.get(wx_url)
        wr.raise_for_status()
        wj = wr.json()
        cur = wj.get("current") or {}
        temp = float(cur.get("temperature_2m", 20.0))
        code = int(cur.get("weather_code", 0))
        wcn = wmo_to_cn(code)

        city_short = c or city_short

        return {
            "city": city_short,
            "province": p,
            "addr_city": c,
            "district": d,
            "street": s,
            "full_address": full_line,
            "display_address": full_line,
            "latitude": latitude,
            "longitude": longitude,
            "temperature": temp,
            "weather": wcn,
            "weather_code": code,
        }


async def fetch_weather_by_city_name(name: str) -> Optional[Dict[str, Any]]:
    """按地名搜索，结构与 fetch_weather_lat_lon 一致。"""
    q = (name or "").strip()
    if not q:
        return None
    q_norm = _normalize_city_query(q)
    async with httpx.AsyncClient(timeout=25.0) as client:
        try:
            # 先用 open-meteo search（中文），无结果再尝试去后缀版本与英文兜底
            candidates = [q, q_norm] if q_norm and q_norm != q else [q]
            r0 = None
            lat = lon = None
            cname = ""
            for cand in candidates:
                geo_url = (
                    "https://geocoding-api.open-meteo.com/v1/search"
                    f"?name={quote(cand)}&count=1&language=zh&format=json"
                )
                gr = await client.get(geo_url)
                gr.raise_for_status()
                gj = gr.json()
                results = gj.get("results") or []
                if results:
                    r0 = results[0]
                    lat = float(r0["latitude"])
                    lon = float(r0["longitude"])
                    cname = str(r0.get("name") or cand).strip()
                    break

            # 英文兜底（部分城市中文拼写未命中时）
            if r0 is None:
                for cand in candidates:
                    geo_url = (
                        "https://geocoding-api.open-meteo.com/v1/search"
                        f"?name={quote(cand)}&count=1&language=en&format=json"
                    )
                    gr = await client.get(geo_url)
                    gr.raise_for_status()
                    gj = gr.json()
                    results = gj.get("results") or []
                    if results:
                        r0 = results[0]
                        lat = float(r0["latitude"])
                        lon = float(r0["longitude"])
                        cname = str(r0.get("name") or cand).strip()
                        break

            # Nominatim 正向兜底（open-meteo search 全失败时）
            if r0 is None:
                nom_fwd = await _nominatim_search_city(client, q)
                if not nom_fwd:
                    return None
                lat, lon, cname = nom_fwd
                r0 = {}

            om_struct = _structured_from_open_meteo(r0)
            op, oc, od, os = om_struct
            line_om = _full_address_spaced([op, oc, od, os])
            p, c, d, s = op, oc, od, os
            full_line = line_om or cname
            nom = await _nominatim_reverse(client, lat, lon)
            if nom:
                np, nc, nd, ns, nline = nom
                if np or nc or nd or ns:
                    merged = _full_address_spaced([np or op, nc or oc, nd or od, ns or os])
                    if len(nline) >= len(merged) and len(nline) >= len(line_om):
                        p, c, d, s = np or op, nc or oc, nd or od, ns or os
                        full_line = nline
                    else:
                        p, c, d, s = np or op, nc or oc, nd or od, ns or os
                        full_line = merged or nline
                elif nline:
                    full_line = nline
            if not full_line.strip():
                full_line = cname or "未能解析详细地址，请重新选择"

            p, c, d, s = _normalize_admin_parts(p, c, d, s)
            p, c, d, s, _ = _display_address_after_route_filter(p, c, d, s)
            full_line = _format_full_address(p, c, d, s) or full_line
        except Exception as e:
            logger.warning(f"city geocode failed: {e}")
            return None

        wx_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,weather_code&timezone=auto"
        )
        wr = await client.get(wx_url)
        wr.raise_for_status()
        wj = wr.json()
        cur = wj.get("current") or {}
        temp = float(cur.get("temperature_2m", 20.0))
        code = int(cur.get("weather_code", 0))
        wcn = wmo_to_cn(code)

        return {
            "city": cname,
            "province": p,
            "addr_city": c,
            "district": d,
            "street": s,
            "full_address": full_line,
            "display_address": full_line,
            "latitude": lat,
            "longitude": lon,
            "temperature": temp,
            "weather": wcn,
            "weather_code": code,
        }
