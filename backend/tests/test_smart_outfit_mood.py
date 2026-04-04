"""情绪字段规范化与风格提取（智能穿搭）。"""

from unittest.mock import patch

import pytest

from app.services.smart_outfit_generator import (
    _mood_extra_styles,
    load_image_bytes,
    normalize_mood_input,
)


def test_normalize_mood_empty_and_none():
    assert normalize_mood_input(None) == ""
    assert normalize_mood_input("") == ""
    assert normalize_mood_input("   ") == ""


def test_normalize_mood_strips_control_chars():
    s = "难受\x00，被骂了\r\n"
    out = normalize_mood_input(s)
    assert "\x00" not in out
    assert "\r" not in out
    assert "难受" in out and "被骂了" in out


def test_normalize_mood_length_cap():
    long = "难" * 600
    assert len(normalize_mood_input(long)) == 500


def test_mood_extra_styles_negative_text():
    tags = _mood_extra_styles("难受，被骂了")
    assert tags
    assert "简约" in tags or "温柔" in tags


def test_mood_extra_styles_empty():
    assert _mood_extra_styles("") == []
    assert _mood_extra_styles("   ") == []


@pytest.mark.asyncio
async def test_load_image_bytes_http_uploads_reads_disk_not_loopback(tmp_path):
    """含 /uploads/ 的绝对 URL 应直接读盘，避免 httpx 请求本机导致 502。"""
    import app.services.smart_outfit_generator as sog

    uid_dir = tmp_path / "e1" / "f.jpg"
    uid_dir.parent.mkdir(parents=True)
    uid_dir.write_bytes(b"local-bytes")

    with patch.object(sog.settings, "UPLOAD_DIR", str(tmp_path)):
        url = "http://127.0.0.1:8010/uploads/e1/f.jpg"
        data = await load_image_bytes(url)
        assert data == b"local-bytes"
