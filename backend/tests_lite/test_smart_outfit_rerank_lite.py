from app.services.smart_outfit_rerank import rerank_outfit_cards


def _card(scene, styles, desc, overall=0.6):
    return {
        "scene": scene,
        "style_tags": styles,
        "description": desc,
        "overall_score": overall,
        "items": [
            {
                "name": "item",
                "category": "上衣",
                "style_tags": styles,
            }
        ],
    }


def test_rerank_prefers_scene_and_style_hits():
    cards = [
        _card("休闲日常", ["休闲"], "casual look", overall=0.7),
        _card("商务正式", ["通勤", "正式"], "office style", overall=0.6),
        _card("约会", ["甜美"], "date outfit", overall=0.8),
    ]

    out = rerank_outfit_cards(
        cards,
        preferred_scene="商务正式",
        style_preferences=["通勤", "正式"],
        weather_note="15C 阴",
        mood="上班",
        top_k=2,
    )

    assert len(out) == 2
    assert out[0]["scene"] == "商务正式"
    assert "rerank_score" in out[0]


def test_rerank_fallback_keeps_results_when_no_signals():
    cards = [
        _card("休闲日常", ["休闲"], "look 1", overall=0.7),
        _card("约会", ["甜美"], "look 2", overall=0.8),
    ]

    out = rerank_outfit_cards(
        cards,
        preferred_scene="",
        style_preferences=[],
        weather_note="",
        mood="",
        top_k=2,
    )

    assert len(out) == 2
    assert out[0]["description"] in {"look 1", "look 2"}
