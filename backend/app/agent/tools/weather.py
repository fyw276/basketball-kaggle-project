"""Weather tool: get_weather."""

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.agent.tools.registry import register_tool


@register_tool(
    name="get_weather",
    description="查询指定城市的天气信息（温度、天气状况、完整地址）。",
    parameters_schema={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名，如：上海、北京、杭州"},
        },
        "required": ["city"],
    },
    mcp_name="get_weather_by_city",
    category="weather",
)
async def get_weather(*, db: Session, user_id: str, **kw) -> Dict[str, Any]:
    from app.services.weather_service import fetch_weather_by_city_name

    city = kw.get("city", "")
    if not city:
        return {"error": "city is required"}
    result = await fetch_weather_by_city_name(city)
    if not result:
        return {"error": f"Weather not found for: {city}"}
    return {
        "city": result.get("city", ""),
        "temperature": result.get("temperature"),
        "weather": result.get("weather", ""),
        "full_address": result.get("full_address", ""),
        "weather_source": result.get("weather_source", ""),
    }
