from app.services import smart_outfit_generator as sog


def test_reference_recognition_skips_clip_when_finetuned_unavailable(monkeypatch):
    monkeypatch.setattr(sog.logger, "warning", lambda *args, **kwargs: None)

    def _fake_finetuned(image_bytes, feature):
        assert feature == "analysis_recognition"
        return None

    class _LegacyResult:
        category = "上衣"
        category_confidence = 0.77
        style_tags = ["简约", "通勤"]
        feature_vector = [0.1] * 1280

        class _MainColor:
            def model_dump(self):
                return {"name": "白", "rgb": (255, 255, 255)}

        main_color = _MainColor()

    class _FakeImageRecognizer:
        def recognize(self, image_bytes):
            return _LegacyResult()

    monkeypatch.setattr(
        "app.services.finetuned_infer_client.try_finetuned_infer",
        _fake_finetuned,
    )
    monkeypatch.setattr("app.ml.image_recognizer.ImageRecognizer", _FakeImageRecognizer)

    out = sog._recognize_reference_image_nonblocking(b"fake-image")

    assert out["category"] == "上衣"
    assert out["category_confidence"] == 0.77
    assert out["style_tags"] == ["简约", "通勤"]
    assert len(out["feature_vector"]) == 1280
    assert out["main_color"]["name"] == "白"
