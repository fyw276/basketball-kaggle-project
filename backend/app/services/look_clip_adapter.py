from app.ml.clip_recognizer import get_clip_recognizer


class LookClipAdapter:
    def recognize_part(self, image_bytes: bytes) -> dict:
        return get_clip_recognizer().recognize(image_bytes)

    def embed_part(self, image_bytes: bytes) -> list[float]:
        result = self.recognize_part(image_bytes)
        return list(result.get("feature_vector") or [])

    def enrich_part(self, part) -> dict:
        result = self.recognize_part(part.image_bytes)
        if not getattr(part, "category", None):
            part.category = result.get("category")
        if not getattr(part, "style_tags", None):
            part.style_tags = list(result.get("style_tags") or [])
        if not getattr(part, "main_color", None):
            part.main_color = result.get("main_color")
        if not getattr(part, "feature_vector", None):
            part.feature_vector = list(result.get("feature_vector") or [])
        return {
            "category": part.category,
            "style_tags": part.style_tags or [],
            "main_color": part.main_color,
            "feature_vector": part.feature_vector or [],
        }
