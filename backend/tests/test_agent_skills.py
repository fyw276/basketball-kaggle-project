"""Tests for agent skills: CRUD, capture, matching, SSE events, preview."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.agent_skill import AgentSkill
from app.services.skill_matcher import match_skill_for_message
from tests.api_json import unwrap_json

# Stable UUIDs for unit tests
_USER_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER_2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


# ── Unit tests: skill matching service ────────────────────────────────────────


class TestSkillMatching:
    """Test keyword matching logic."""

    def _make_session_with_skills(self, skills_data):
        """Create an in-memory SQLite session with test skills."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        factory = sessionmaker(bind=engine)
        db = factory()
        for sd in skills_data:
            skill = AgentSkill(
                user_id=sd["user_id"],
                name=sd["name"],
                keywords=sd["keywords"],
                enabled=sd.get("enabled", True),
                system_prompt_addon=sd.get("addon", f"addon for {sd['name']}"),
                tool_names=sd.get("tool_names", []),
            )
            db.add(skill)
        db.commit()
        return db

    def test_keyword_match_simple(self):
        db = self._make_session_with_skills(
            [
                {"user_id": _USER_1, "name": "weather", "keywords": ["天气", "查天气"]},
            ]
        )
        skill, matched = match_skill_for_message("今天天气怎么样", db, _USER_1)
        assert skill is not None
        assert skill.name == "weather"
        assert "天气" in matched
        db.close()

    def test_keyword_match_case_insensitive(self):
        db = self._make_session_with_skills(
            [
                {"user_id": _USER_1, "name": "outfit", "keywords": ["OOTD", "搭配"]},
            ]
        )
        skill, matched = match_skill_for_message("帮我搭配一下ootd", db, _USER_1)
        assert skill is not None
        assert "OOTD" in matched
        db.close()

    def test_no_match_returns_none(self):
        db = self._make_session_with_skills(
            [
                {"user_id": _USER_1, "name": "weather", "keywords": ["天气"]},
            ]
        )
        skill, matched = match_skill_for_message("你好", db, _USER_1)
        assert skill is None
        assert matched == []
        db.close()

    def test_disabled_skill_not_matched(self):
        db = self._make_session_with_skills(
            [
                {"user_id": _USER_1, "name": "weather", "keywords": ["天气"], "enabled": False},
            ]
        )
        skill, matched = match_skill_for_message("今天天气", db, _USER_1)
        assert skill is None
        db.close()

    def test_best_match_wins(self):
        db = self._make_session_with_skills(
            [
                {"user_id": _USER_1, "name": "weather", "keywords": ["天气"]},
                {
                    "user_id": _USER_1,
                    "name": "weather_detail",
                    "keywords": ["天气", "温度", "湿度"],
                },
            ]
        )
        skill, matched = match_skill_for_message("今天天气温度湿度怎么样", db, _USER_1)
        assert skill is not None
        assert skill.name == "weather_detail"
        assert len(matched) == 3
        db.close()

    def test_user_isolation(self):
        db = self._make_session_with_skills(
            [
                {"user_id": _USER_1, "name": "weather_u1", "keywords": ["天气"]},
                {"user_id": _USER_2, "name": "weather_u2", "keywords": ["天气"]},
            ]
        )
        skill, _ = match_skill_for_message("今天天气", db, _USER_1)
        assert skill is not None
        assert skill.name == "weather_u1"
        db.close()


# ── Integration tests: API CRUD ───────────────────────────────────────────────


class TestSkillCRUD:
    """Test skill creation and listing via API."""

    def test_create_skill_manually(self, client, auth_headers):
        resp = client.post(
            "/api/v1/agent/skills",
            json={
                "name": "查天气",
                "description": "查询天气并推荐穿搭",
                "keywords": ["天气", "气温"],
                "system_prompt_addon": "请先调用 get_weather 查询天气。",
                "tool_names": ["get_weather"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = unwrap_json(resp)
        assert data["name"] == "查天气"
        assert data["keywords"] == ["天气", "气温"]
        assert data["active_version"] == 1

    def test_list_skills(self, client, auth_headers):
        client.post(
            "/api/v1/agent/skills",
            json={
                "name": "skill1",
                "keywords": ["k1"],
                "system_prompt_addon": "addon1",
            },
            headers=auth_headers,
        )
        resp = client.get("/api/v1/agent/skills", headers=auth_headers)
        assert resp.status_code == 200
        data = unwrap_json(resp)
        assert len(data) == 1
        assert data[0]["name"] == "skill1"

    def test_list_skills_empty(self, client, auth_headers):
        resp = client.get("/api/v1/agent/skills", headers=auth_headers)
        assert resp.status_code == 200
        data = unwrap_json(resp)
        assert data == []

    def test_skill_isolation_between_users(self, client, auth_headers, second_user_headers):
        client.post(
            "/api/v1/agent/skills",
            json={
                "name": "u1_skill",
                "keywords": ["test"],
                "system_prompt_addon": "addon",
            },
            headers=auth_headers,
        )
        resp = client.get("/api/v1/agent/skills", headers=second_user_headers)
        data = unwrap_json(resp)
        assert len(data) == 0


# ── Integration tests: Capture ────────────────────────────────────────────────


class TestSkillCapture:
    """Test capture from agent run."""

    def test_capture_creates_skill_and_version(self, client, auth_headers):
        resp = client.post(
            "/api/v1/agent/skills/capture",
            json={
                "run_id": "abc123",
                "name": "天气穿搭",
                "description": "查天气后推荐穿搭",
                "keywords": ["天气", "穿搭"],
                "tool_calls": [
                    {"tool_name": "get_weather", "arguments": {"city": "上海"}},
                    {"tool_name": "recommend_outfits", "arguments": {"occasion": "casual"}},
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = unwrap_json(resp)
        assert data["name"] == "天气穿搭"
        assert set(data["tool_names"]) == {"get_weather", "recommend_outfits"}
        assert "get_weather" in data["system_prompt_addon"]
        assert "recommend_outfits" in data["system_prompt_addon"]

    def test_capture_extracts_tool_names(self, client, auth_headers):
        resp = client.post(
            "/api/v1/agent/skills/capture",
            json={
                "run_id": "def456",
                "name": "重复工具",
                "keywords": ["test"],
                "tool_calls": [
                    {"tool_name": "get_weather", "arguments": {}},
                    {"tool_name": "get_weather", "arguments": {"city": "北京"}},
                    {"tool_name": "list_wardrobe", "arguments": {}},
                ],
            },
            headers=auth_headers,
        )
        data = unwrap_json(resp)
        assert set(data["tool_names"]) == {"get_weather", "list_wardrobe"}

    def test_capture_validates_tool_calls_not_empty(self, client, auth_headers):
        resp = client.post(
            "/api/v1/agent/skills/capture",
            json={
                "run_id": "ghi789",
                "name": "empty",
                "keywords": ["test"],
                "tool_calls": [],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422  # Pydantic validation: min_length=1


# ── Integration tests: Execute Preview ────────────────────────────────────────


class TestExecutePreview:
    """Test dry-run preview endpoint."""

    def test_preview_returns_addon_and_keywords(self, client, auth_headers):
        create_resp = client.post(
            "/api/v1/agent/skills",
            json={
                "name": "天气助手",
                "keywords": ["天气", "气温", "下雨"],
                "system_prompt_addon": "请先查天气。",
                "tool_names": ["get_weather"],
            },
            headers=auth_headers,
        )
        skill_id = unwrap_json(create_resp)["skill_id"]

        resp = client.post(
            f"/api/v1/agent/skills/{skill_id}/execute-preview",
            params={"message": "今天会下雨吗"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = unwrap_json(resp)
        assert data["skill_name"] == "天气助手"
        assert "下雨" in data["matched_keywords"]
        assert data["system_prompt_addon"] == "请先查天气。"

    def test_preview_no_match(self, client, auth_headers):
        create_resp = client.post(
            "/api/v1/agent/skills",
            json={
                "name": "天气助手",
                "keywords": ["天气"],
                "system_prompt_addon": "addon",
            },
            headers=auth_headers,
        )
        skill_id = unwrap_json(create_resp)["skill_id"]

        resp = client.post(
            f"/api/v1/agent/skills/{skill_id}/execute-preview",
            params={"message": "你好世界"},
            headers=auth_headers,
        )
        data = unwrap_json(resp)
        assert data["matched_keywords"] == []

    def test_preview_not_found(self, client, auth_headers):
        resp = client.post(
            "/api/v1/agent/skills/00000000-0000-0000-0000-000000000000/execute-preview",
            params={"message": "test"},
            headers=auth_headers,
        )
        assert resp.status_code == 404
