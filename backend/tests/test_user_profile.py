"""
Tests for user profile module
Tests profile creation, update, validation, and permission control
"""

from fastapi import status
from fastapi.testclient import TestClient

from tests.api_json import unwrap_json


class TestUserProfileCreation:
    """Test user profile creation"""

    def test_create_profile_success(self, client: TestClient, auth_headers: dict):
        """Test creating a valid user profile"""
        profile_data = {
            "gender": "女",
            "gender_expression": 0.75,
            "explore_cross_gender": False,
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤", "简约"],
            "budget_range": "中等",
            "avoid_body_parts": ["肩", "腰"],
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)

        assert response.status_code == status.HTTP_201_CREATED
        data = unwrap_json(response)
        assert data["height"] == 170
        assert data["body_type"] == "偏瘦"
        assert data["skin_tone"] == "冷白"
        assert set(data["style_preference"]) == {"通勤", "简约"}
        assert data["budget_range"] == "中等"
        assert set(data["avoid_body_parts"]) == {"肩", "腰"}
        assert data["gender"] == "女"
        assert data["gender_expression"] == 0.75
        assert "profile_id" in data
        assert "user_id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_profile_minimal_data(self, client: TestClient, auth_headers: dict):
        """Test creating profile with minimal required data"""
        profile_data = {
            "height": 165,
            "body_type": "矩形",
            "skin_tone": "黄皮",
            "style_preference": ["休闲"],
            "budget_range": "经济",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)

        assert response.status_code == status.HTTP_201_CREATED
        data = unwrap_json(response)
        assert data["height"] == 165
        assert data["avoid_body_parts"] == []

    def test_create_profile_duplicate(self, client: TestClient, auth_headers: dict):
        """Test creating duplicate profile fails"""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }

        # Create first profile
        response1 = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response1.status_code == status.HTTP_201_CREATED

        # Try to create second profile
        response2 = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response2.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response2.json()["error"]["message"]

    def test_create_profile_without_auth(self, client: TestClient):
        """Test creating profile without authentication fails"""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }

        response = client.post("/api/v1/profile", json=profile_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestUserProfileValidation:
    """Test user profile data validation"""

    def test_invalid_height_too_low(self, client: TestClient, auth_headers: dict):
        """Test height below minimum fails"""
        profile_data = {
            "height": 50,  # Below 100
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_invalid_height_too_high(self, client: TestClient, auth_headers: dict):
        """Test height above maximum fails"""
        profile_data = {
            "height": 300,  # Above 250
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_invalid_body_type(self, client: TestClient, auth_headers: dict):
        """Test invalid body type fails"""
        profile_data = {
            "height": 170,
            "body_type": "invalid_type",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid body_type" in response.json()["error"]["message"]

    def test_invalid_skin_tone(self, client: TestClient, auth_headers: dict):
        """Test invalid skin tone fails"""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "invalid_tone",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid skin_tone" in response.json()["error"]["message"]

    def test_invalid_style_preference(self, client: TestClient, auth_headers: dict):
        """Test invalid style preference fails"""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤", "invalid_style"],
            "budget_range": "中等",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid style preferences" in response.json()["error"]["message"]

    def test_empty_style_preference(self, client: TestClient, auth_headers: dict):
        """Test empty style preference list fails"""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": [],
            "budget_range": "中等",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_invalid_budget_range(self, client: TestClient, auth_headers: dict):
        """Test invalid budget range fails"""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "invalid_budget",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid budget_range" in response.json()["error"]["message"]

    def test_budget_display_label_is_normalized(self, client: TestClient, auth_headers: dict):
        """Mobile display labels are accepted and stored as backend enum values."""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等消费",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_201_CREATED
        assert unwrap_json(response)["budget_range"] == "中等"

    def test_invalid_avoid_body_parts(self, client: TestClient, auth_headers: dict):
        """Test invalid avoid body parts fails"""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
            "avoid_body_parts": ["肩", "invalid_part"],
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid body parts" in response.json()["error"]["message"]


class TestUserProfileRetrieval:
    """Test user profile retrieval"""

    def test_get_profile_success(self, client: TestClient, auth_headers: dict):
        """Test getting existing profile"""
        # Create profile first
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }
        client.post("/api/v1/profile", json=profile_data, headers=auth_headers)

        # Get profile
        response = client.get("/api/v1/profile", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = unwrap_json(response)
        assert data["height"] == 170
        assert data["body_type"] == "偏瘦"

    def test_get_profile_not_found(self, client: TestClient, auth_headers: dict):
        """Test getting non-existent profile"""
        response = client.get("/api/v1/profile", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["error"]["message"]

    def test_get_profile_without_auth(self, client: TestClient):
        """Test getting profile without authentication fails"""
        response = client.get("/api/v1/profile")
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestUserProfileUpdate:
    """Test user profile update"""

    def test_update_profile_success(self, client: TestClient, auth_headers: dict):
        """Test updating profile with valid data"""
        # Create profile first
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }
        client.post("/api/v1/profile", json=profile_data, headers=auth_headers)

        # Update profile
        update_data = {
            "height": 175,
            "style_preference": ["通勤", "简约", "休闲"],
        }
        response = client.put("/api/v1/profile", json=update_data, headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = unwrap_json(response)
        assert data["height"] == 175
        assert set(data["style_preference"]) == {"通勤", "简约", "休闲"}
        # Other fields should remain unchanged
        assert data["body_type"] == "偏瘦"
        assert data["skin_tone"] == "冷白"

    def test_update_profile_all_fields(self, client: TestClient, auth_headers: dict):
        """Test updating all profile fields"""
        # Create profile first
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }
        client.post("/api/v1/profile", json=profile_data, headers=auth_headers)

        # Update all fields
        update_data = {
            "height": 180,
            "body_type": "沙漏",
            "skin_tone": "小麦",
            "style_preference": ["街头", "运动"],
            "budget_range": "高端",
            "avoid_body_parts": ["大腿"],
        }
        response = client.put("/api/v1/profile", json=update_data, headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = unwrap_json(response)
        assert data["height"] == 180
        assert data["body_type"] == "沙漏"
        assert data["skin_tone"] == "小麦"
        assert set(data["style_preference"]) == {"街头", "运动"}
        assert data["budget_range"] == "高端"
        assert data["avoid_body_parts"] == ["大腿"]

    def test_update_profile_not_found(self, client: TestClient, auth_headers: dict):
        """Test updating non-existent profile fails"""
        update_data = {"height": 175}
        response = client.put("/api/v1/profile", json=update_data, headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["error"]["message"]

    def test_update_profile_invalid_data(self, client: TestClient, auth_headers: dict):
        """Test updating profile with invalid data fails"""
        # Create profile first
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }
        client.post("/api/v1/profile", json=profile_data, headers=auth_headers)

        # Try to update with invalid data
        update_data = {"body_type": "invalid_type"}
        response = client.put("/api/v1/profile", json=update_data, headers=auth_headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_profile_without_auth(self, client: TestClient):
        """Test updating profile without authentication fails"""
        update_data = {"height": 175}
        response = client.put("/api/v1/profile", json=update_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestUserProfilePermissions:
    """Test user profile permission control"""

    def test_user_can_only_access_own_profile(
        self, client: TestClient, auth_headers: dict, second_user_headers: dict
    ):
        """Test users can only access their own profiles"""
        # User 1 creates profile
        profile_data_1 = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
        }
        response1 = client.post("/api/v1/profile", json=profile_data_1, headers=auth_headers)
        assert response1.status_code == status.HTTP_201_CREATED
        user1_profile = unwrap_json(response1)

        # User 2 creates profile
        profile_data_2 = {
            "height": 165,
            "body_type": "梨形",
            "skin_tone": "黄皮",
            "style_preference": ["休闲"],
            "budget_range": "经济",
        }
        response2 = client.post("/api/v1/profile", json=profile_data_2, headers=second_user_headers)
        assert response2.status_code == status.HTTP_201_CREATED
        user2_profile = unwrap_json(response2)

        # User 1 gets their own profile
        response = client.get("/api/v1/profile", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = unwrap_json(response)
        assert data["profile_id"] == user1_profile["profile_id"]
        assert data["height"] == 170

        # User 2 gets their own profile
        response = client.get("/api/v1/profile", headers=second_user_headers)
        assert response.status_code == status.HTTP_200_OK
        data = unwrap_json(response)
        assert data["profile_id"] == user2_profile["profile_id"]
        assert data["height"] == 165

        # Profiles should be different
        assert user1_profile["profile_id"] != user2_profile["profile_id"]


class TestUserProfileEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_all_valid_body_types(self, client: TestClient):
        """Test all valid body types are accepted"""
        valid_body_types = ["偏瘦", "微胖", "梨形", "倒三角", "沙漏", "矩形"]

        for i, body_type in enumerate(valid_body_types):
            # Register new user for each test
            user_data = {
                "username": f"user_body_{i}",
                "email": f"user_body_{i}@example.com",
                "password": "Test123!@#",
            }
            client.post("/api/v1/auth/register", json=user_data)

            # Login
            login_response = client.post(
                "/api/v1/auth/login",
                json={"username": user_data["username"], "password": user_data["password"]},
            )
            token = unwrap_json(login_response)["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Create profile with this body type
            profile_data = {
                "height": 170,
                "body_type": body_type,
                "skin_tone": "冷白",
                "style_preference": ["通勤"],
                "budget_range": "中等",
            }
            response = client.post("/api/v1/profile", json=profile_data, headers=headers)
            assert response.status_code == status.HTTP_201_CREATED
            assert unwrap_json(response)["body_type"] == body_type

    def test_all_valid_skin_tones(self, client: TestClient):
        """Test all valid skin tones are accepted"""
        valid_skin_tones = ["冷白", "黄皮", "小麦", "深色"]

        for i, skin_tone in enumerate(valid_skin_tones):
            # Register new user for each test
            user_data = {
                "username": f"user_skin_{i}",
                "email": f"user_skin_{i}@example.com",
                "password": "Test123!@#",
            }
            client.post("/api/v1/auth/register", json=user_data)

            # Login
            login_response = client.post(
                "/api/v1/auth/login",
                json={"username": user_data["username"], "password": user_data["password"]},
            )
            token = unwrap_json(login_response)["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Create profile with this skin tone
            profile_data = {
                "height": 170,
                "body_type": "偏瘦",
                "skin_tone": skin_tone,
                "style_preference": ["通勤"],
                "budget_range": "中等",
            }
            response = client.post("/api/v1/profile", json=profile_data, headers=headers)
            assert response.status_code == status.HTTP_201_CREATED
            assert unwrap_json(response)["skin_tone"] == skin_tone

    def test_multiple_style_preferences(self, client: TestClient, auth_headers: dict):
        """Test profile with multiple style preferences"""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤", "学院", "甜酷", "简约", "街头"],
            "budget_range": "中等",
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_201_CREATED
        data = unwrap_json(response)
        assert len(data["style_preference"]) == 5

    def test_multiple_avoid_body_parts(self, client: TestClient, auth_headers: dict):
        """Test profile with multiple avoid body parts"""
        profile_data = {
            "height": 170,
            "body_type": "偏瘦",
            "skin_tone": "冷白",
            "style_preference": ["通勤"],
            "budget_range": "中等",
            "avoid_body_parts": ["肩", "腰", "臀", "大腿"],
        }

        response = client.post("/api/v1/profile", json=profile_data, headers=auth_headers)
        assert response.status_code == status.HTTP_201_CREATED
        data = unwrap_json(response)
        assert len(data["avoid_body_parts"]) == 4
