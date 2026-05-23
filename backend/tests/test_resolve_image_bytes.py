"""Tests for _resolve_image_bytes helper in analysis API."""

import io
import os
import tempfile
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PIL import Image

os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENABLE_RATE_LIMIT", "false")

from app.api.analysis import _resolve_image_bytes  # noqa: E402


def _make_test_image_bytes() -> bytes:
    img = Image.new("RGB", (10, 10), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def _async_return(val):
    return val


def _make_upload_file(content: bytes, content_type: str = "image/jpeg"):
    """Create a mock UploadFile with async read()."""
    file = MagicMock()
    file.read = MagicMock(return_value=_async_return(content))
    file.content_type = content_type
    return file


@pytest.mark.asyncio
async def test_no_source_raises_400():
    db = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_image_bytes(
            file=None, garment_id=None, image_url=None, db=db, user_id=uuid4()
        )
    assert exc_info.value.status_code == 400
    assert "三选一" in exc_info.value.detail


@pytest.mark.asyncio
async def test_multiple_sources_raises_400():
    db = MagicMock()
    img_bytes = _make_test_image_bytes()
    uf = _make_upload_file(img_bytes)
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_image_bytes(
            file=uf, garment_id="some-id", image_url=None, db=db, user_id=uuid4()
        )
    assert exc_info.value.status_code == 400
    assert "互斥" in exc_info.value.detail


@pytest.mark.asyncio
async def test_invalid_garment_id_raises_400():
    db = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_image_bytes(
            file=None, garment_id="not-a-uuid", image_url=None, db=db, user_id=uuid4()
        )
    assert exc_info.value.status_code == 400
    assert "格式无效" in exc_info.value.detail


@pytest.mark.asyncio
async def test_file_returns_bytes():
    db = MagicMock()
    img_bytes = _make_test_image_bytes()
    uf = _make_upload_file(img_bytes)
    result = await _resolve_image_bytes(
        file=uf, garment_id=None, image_url=None, db=db, user_id=uuid4()
    )
    assert result == img_bytes


@pytest.mark.asyncio
async def test_empty_file_raises_400():
    db = MagicMock()
    uf = _make_upload_file(b"")
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_image_bytes(file=uf, garment_id=None, image_url=None, db=db, user_id=uuid4())
    assert exc_info.value.status_code == 400
    assert "空" in exc_info.value.detail


@pytest.mark.asyncio
async def test_non_image_file_raises_400():
    db = MagicMock()
    uf = _make_upload_file(b"not an image", content_type="text/plain")
    with pytest.raises(HTTPException) as exc_info:
        await _resolve_image_bytes(file=uf, garment_id=None, image_url=None, db=db, user_id=uuid4())
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_garment_id_not_found_raises_404():
    db = MagicMock()
    gid = str(uuid4())
    with patch("app.api.analysis.get_garment_by_id", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_image_bytes(
                file=None, garment_id=gid, image_url=None, db=db, user_id=uuid4()
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_garment_id_wrong_owner_raises_403():
    db = MagicMock()
    gid = str(uuid4())
    owner_id = uuid4()
    garment = MagicMock()
    garment.user_id = uuid4()  # different owner
    with patch("app.api.analysis.get_garment_by_id", return_value=garment):
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_image_bytes(
                file=None, garment_id=gid, image_url=None, db=db, user_id=owner_id
            )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_garment_id_success():
    db = MagicMock()
    img_bytes = _make_test_image_bytes()
    owner_id = uuid4()

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(img_bytes)
        tmp_path = tmp.name

    try:
        garment = MagicMock()
        garment.user_id = owner_id
        garment.image_path = tmp_path
        gid = str(uuid4())
        with patch("app.api.analysis.get_garment_by_id", return_value=garment):
            result = await _resolve_image_bytes(
                file=None, garment_id=gid, image_url=None, db=db, user_id=owner_id
            )
        assert result == img_bytes
    finally:
        os.unlink(tmp_path)
