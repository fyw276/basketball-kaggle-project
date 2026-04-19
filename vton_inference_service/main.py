"""
Minimal VTON HTTP service for VTON_INFERENCE_URL contract.

Default: stub mode (no OOTDiffusion/IDM weights) — lightweight blend for E2E wiring.
Replace stub with real inference when GPU + upstream repo are installed.

Contract: docs/VTON_INTEGRATION.md
"""

from __future__ import annotations

import io
import os
import tempfile
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image

app = FastAPI(title="VTON Inference Service", version="0.1.0")

# Default True: safe for dev without GPU weights
VTON_STUB_MODE = os.environ.get("VTON_STUB_MODE", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
VTON_SERVICE_API_KEY = (os.environ.get("VTON_SERVICE_API_KEY") or "").strip()


def _check_bearer(request: Request) -> None:
    if not VTON_SERVICE_API_KEY:
        return
    auth = (request.headers.get("authorization") or "").strip()
    if auth != f"Bearer {VTON_SERVICE_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing Bearer token")


def _ootd_category_hint(garment_category: str) -> Optional[int]:
    """
    OOTDiffusion full-body style mapping (see upstream README):
    0 upper, 1 lower, 2 dress. Used for logging / future native hook.
    """
    s = (garment_category or "").strip().lower()
    if not s:
        return None
    if any(k in s for k in ("裙", "连衣裙", "dress")):
        return 2
    if any(k in s for k in ("下装", "裤", "裤装", "bottom", "短裤")):
        return 1
    if any(k in s for k in ("上装", "上衣", "外套", "top", "t恤")):
        return 0
    return None


def _pil_to_jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    """Avoid BytesIO JPEG encoder quirks on Windows (no fileno)."""
    rgb = img.convert("RGB")
    fd, path = tempfile.mkstemp(suffix=".jpg")
    try:
        os.close(fd)
        rgb.save(path, format="JPEG", quality=quality, optimize=False)
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _stub_tryon(person: Image.Image, garment: Image.Image) -> bytes:
    """Naive blend for pipeline demo only — not real VTON."""
    pw = min(768, max(person.width, 512))
    ph = int(person.height * (pw / person.width))
    p = person.convert("RGB").resize((pw, ph), Image.Resampling.LANCZOS)
    gw = min(pw, max(garment.width, 256))
    gh = int(garment.height * (gw / garment.width))
    g = garment.convert("RGB").resize((gw, gh), Image.Resampling.LANCZOS)
    canvas = p.copy()
    x = (pw - gw) // 2
    y = ph // 3
    canvas.paste(g, (max(0, x), max(0, min(y, ph - gh))))
    blended = Image.blend(canvas, p, 0.55)
    return _pil_to_jpeg_bytes(blended)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "stub_mode": VTON_STUB_MODE,
        "note": "Set VTON_STUB_MODE=false when wiring real OOTDiffusion/IDM inference",
    }


@app.post("/v1/tryon")
async def tryon_v1(
    request: Request,
    garment_file: UploadFile = File(...),
    person_file: UploadFile = File(...),
    model_gender: str = Form("neutral"),
    garment_category: str = Form(""),
    prompt: str = Form(""),
):
    _check_bearer(request)

    g_bytes = await garment_file.read()
    p_bytes = await person_file.read()
    if not g_bytes or not p_bytes:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "empty garment_file or person_file",
            },
        )

    try:
        person_im = Image.open(io.BytesIO(p_bytes))
        garment_im = Image.open(io.BytesIO(g_bytes))
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"invalid image: {e}"},
        )

    cat_hint = _ootd_category_hint(garment_category)
    # Placeholder for real hook: pass cat_hint + model_gender + prompt into OOTDiffusion/IDM
    _ = (model_gender, prompt, cat_hint)

    if not VTON_STUB_MODE:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": (
                    "VTON_STUB_MODE is false but no native inference is wired in this "
                    "service. Replace the handler in main.py with calls to OOTDiffusion "
                    "or IDM-VTON, or set VTON_STUB_MODE=true for demo blend."
                ),
            },
        )

    jpeg = _stub_tryon(person_im, garment_im)
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={
            "X-VTON-Engine": "stub-blend",
            "X-VTON-OOTD-Category-Hint": str(cat_hint) if cat_hint is not None else "",
        },
    )
