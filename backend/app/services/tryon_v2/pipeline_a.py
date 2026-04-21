"""Try-on v2 pipeline A implementation (MVP)."""

from __future__ import annotations

from typing import Any

from PIL import Image

from app.services.tryon_v2.input_gate import evaluate_input_gate
from app.services.tryon_v2.qc import evaluate_qc
from app.services.virtual_tryon import get_tryon_service, sanitize_tryon_prompt


def run_pipeline_a(
    person_image: Image.Image,
    garment_image: Image.Image,
    garment_category: str,
    prompt: str | None = None,
    model_gender: str = "neutral",
    strict_identity: bool = True,
    thresholds: dict[str, float] | None = None,
    qc_threshold: float = 0.6,
) -> dict[str, Any]:
    gate = evaluate_input_gate(
        person_image=person_image,
        garment_image=garment_image,
        garment_category=garment_category,
        strict=bool(strict_identity),
        thresholds=thresholds,
    )
    if not gate.passed:
        return {
            "status": "error",
            "message": gate.message,
            "error_code": gate.error_code,
            "retryable": gate.retryable,
            "action_hint": gate.action_hint,
            "qc_scores": gate.scores,
            "metadata": {"pipeline": "A", "stage": "input_gate"},
        }

    prompt_clean = sanitize_tryon_prompt(prompt or "")

    service = get_tryon_service()
    result = service.tryon_garment(
        garment_image=garment_image,
        person_image=person_image,
        prompt=prompt_clean,
        model_gender=model_gender,
        garment_category=garment_category,
        force_fallback=bool(strict_identity),
    )

    image = result.get("result_image") if isinstance(result, dict) else None
    if image is None:
        return {
            "status": "error",
            "message": str((result or {}).get("message") or "下装贴合失败"),
            "error_code": "TRYON_V2_INTERNAL_WARP_FAILED",
            "retryable": True,
            "action_hint": "请稍后重试，或更换更清晰的人像与商品图。",
            "qc_scores": gate.scores,
            "metadata": {
                "pipeline": "A",
                "stage": "warp",
                "upstream_metadata": (
                    (result or {}).get("metadata") if isinstance(result, dict) else {}
                ),
            },
        }

    qc = evaluate_qc(
        person_image=person_image,
        result_image=image,
        threshold=qc_threshold,
    )
    merged_scores = dict(gate.scores)
    merged_scores.update(qc.scores)

    if not qc.passed:
        return {
            "status": "error",
            "message": qc.message,
            "error_code": "TRYON_V2_QC_NOT_PASSED",
            "retryable": False,
            "action_hint": qc.action_hint,
            "qc_scores": merged_scores,
            "metadata": {
                "pipeline": "A",
                "stage": "qc",
                "qc_threshold": qc.threshold,
                "strict_identity": bool(strict_identity),
                "upstream_status": (
                    (result or {}).get("status") if isinstance(result, dict) else None
                ),
                "upstream_metadata": (
                    (result or {}).get("metadata") if isinstance(result, dict) else {}
                ),
            },
        }

    return {
        "status": "success",
        "message": "方案A试衣成功",
        "result_image": image,
        "error_code": None,
        "retryable": False,
        "action_hint": None,
        "qc_scores": merged_scores,
        "metadata": {
            "pipeline": "A",
            "strict_identity": bool(strict_identity),
            "qc_threshold": qc.threshold,
            "upstream_status": (result or {}).get("status") if isinstance(result, dict) else None,
            "upstream_metadata": (result or {}).get("metadata") if isinstance(result, dict) else {},
        },
    }
