from app.models.feedback_event import FeedbackEvent
from tests.api_json import unwrap_json


def test_vowwear_loop_feedback_event_is_persisted(client, auth_headers, test_session_factory):
    response = client.post(
        "/api/v1/feedback/events",
        headers=auth_headers,
        json={
            "event_type": "view",
            "source": "vowwear_loop",
            "scene": "日常休闲",
            "payload": {
                "overall_similarity": 0.72,
                "coverage_score": 0.5,
                "scene_hint": "日常休闲",
                "missing_categories": ["shoes"],
                "selected_garment_ids": [],
            },
        },
    )

    data = unwrap_json(response)

    assert response.status_code == 200
    assert data["event_type"] == "view"

    db = test_session_factory()
    try:
        event = db.query(FeedbackEvent).one()
        assert event.source == "vowwear_loop"
        assert event.scene == "日常休闲"
        assert event.payload["overall_similarity"] == 0.72
        assert event.payload["selected_garment_ids"] == []
    finally:
        db.close()
