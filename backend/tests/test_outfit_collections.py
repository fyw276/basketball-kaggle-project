"""
Tests for outfit collection API endpoints
"""

import io
from uuid import uuid4

import pytest
from PIL import Image


def make_test_image():
    """Create a test image in memory"""
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class TestOutfitCollection:
    """Test outfit collection endpoints"""

    def _create_garment(self, client, headers, category="上衣", color_name="白"):
        """Helper: create a garment and return its ID"""
        img = make_test_image()
        r = client.post(
            "/api/v1/wardrobe/garments",
            data={
                "category": category,
                "main_color_name": color_name,
                "main_color_rgb": "255,255,255",
                "main_color_hsv": "0,0,100",
                "main_color_hex": "#ffffff",
                "style_tags": "通勤",
            },
            files={"file": ("test.png", img, "image/png")},
            headers=headers,
        )
        assert r.status_code == 201, f"Garment creation failed: {r.text}"
        return r.json()["garment_id"]

    def test_save_outfit_collection(self, client, auth_headers):
        """Test saving a new outfit collection"""
        garment_id_1 = self._create_garment(client, auth_headers, "上衣", "白")
        garment_id_2 = self._create_garment(client, auth_headers, "裤子", "黑")

        collection_data = {
            "name": "通勤商务装",
            "scene": "通勤上班",
            "description": "适合日常通勤的简约搭配",
            "garment_ids": [garment_id_1, garment_id_2],
        }
        response = client.post(
            "/api/v1/outfits/collections",
            json=collection_data,
            headers=auth_headers,
        )
        assert response.status_code == 201, f"Save collection failed: {response.text}"
        data = response.json()
        assert data["name"] == "通勤商务装"
        assert data["scene"] == "通勤上班"
        assert len(data["items"]) == 2

    def test_list_outfit_collections(self, client, auth_headers):
        """Test listing outfit collections"""
        response = client.get("/api/v1/outfits/collections", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_get_outfit_collection(self, client, auth_headers):
        """Test getting a single outfit collection"""
        garment_id = self._create_garment(client, auth_headers, "上衣", "蓝")

        collection_data = {
            "name": "我的收藏",
            "scene": "约会",
            "description": "测试套装",
            "garment_ids": [garment_id],
        }
        save_resp = client.post(
            "/api/v1/outfits/collections",
            json=collection_data,
            headers=auth_headers,
        )
        assert save_resp.status_code == 201
        collection_id = save_resp.json()["collection_id"]

        get_resp = client.get(
            f"/api/v1/outfits/collections/{collection_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200, f"Get collection failed: {get_resp.text}"
        data = get_resp.json()
        assert data["name"] == "我的收藏"
        assert data["scene"] == "约会"

    def test_delete_outfit_collection(self, client, auth_headers):
        """Test deleting an outfit collection"""
        garment_id = self._create_garment(client, auth_headers, "外套", "灰")

        collection_data = {
            "name": "待删除套装",
            "scene": "休闲日常",
            "garment_ids": [garment_id],
        }
        save_resp = client.post(
            "/api/v1/outfits/collections",
            json=collection_data,
            headers=auth_headers,
        )
        assert save_resp.status_code == 201
        collection_id = save_resp.json()["collection_id"]

        del_resp = client.delete(
            f"/api/v1/outfits/collections/{collection_id}",
            headers=auth_headers,
        )
        assert del_resp.status_code == 204

        get_resp = client.get(
            f"/api/v1/outfits/collections/{collection_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 404

    def test_wear_outfit(self, client, auth_headers):
        """Test recording outfit wear"""
        garment_id = self._create_garment(client, auth_headers, "裙子", "红")

        collection_data = {
            "name": "约会装",
            "scene": "约会",
            "garment_ids": [garment_id],
        }
        save_resp = client.post(
            "/api/v1/outfits/collections",
            json=collection_data,
            headers=auth_headers,
        )
        assert save_resp.status_code == 201
        collection_id = save_resp.json()["collection_id"]

        wear_resp = client.post(
            f"/api/v1/outfits/collections/{collection_id}/wear",
            headers=auth_headers,
        )
        assert wear_resp.status_code == 200, f"Wear failed: {wear_resp.text}"
        data = wear_resp.json()
        assert data["worn_times"] >= 1

    def test_invalid_garment_id(self, client, auth_headers):
        """Test saving collection with invalid garment ID"""
        collection_data = {
            "name": "测试套装",
            "scene": "通勤上班",
            "garment_ids": ["not-a-valid-uuid"],
        }
        response = client.post(
            "/api/v1/outfits/collections",
            json=collection_data,
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_not_found_collection(self, client, auth_headers):
        """Test getting non-existent collection"""
        fake_id = str(uuid4())
        get_resp = client.get(
            f"/api/v1/outfits/collections/{fake_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 404
