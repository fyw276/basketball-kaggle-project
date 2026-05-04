"""
Minimal VTON HTTP service for VTON_INFERENCE_URL contract.

Supports multiple engines (tried in order):
1. CatVTON — best quality for product→person try-on, <8GB VRAM (bf16)
2. OOTDiffusion — earlier diffusion model
3. Stub blend — demo-only placeholder

Contract: docs/VTON_INTEGRATION.md

Engine selection via environment:
- VTON_ENGINE=catvton|ootd|auto (default: auto)
- VTON_STUB_MODE=true|false (default: false when GPU detected)
- CATVTON_PATH=/path/to/CatVTON
- CATVTON_STEPS=50
- CATVTON_GUIDANCE=2.5
"""

from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="VTON Inference Service", version="0.3.0")

# ─── Configuration ───────────────────────────────────────────────────────────────

VTON_STUB_MODE = os.environ.get("VTON_STUB_MODE", "").strip().lower() in (
    "1", "true", "yes", "on",
)

VTON_FORCE_ENGINE = os.environ.get("VTON_ENGINE", "auto").strip().lower()

VTON_SERVICE_API_KEY = (os.environ.get("VTON_SERVICE_API_KEY") or "").strip()

CATVTON_PATH = os.environ.get("CATVTON_PATH", "").strip()
CATVTON_STEPS = int(os.environ.get("CATVTON_STEPS", "25"))
CATVTON_GUIDANCE = float(os.environ.get("CATVTON_GUIDANCE", "2.5"))
CATVTON_WIDTH = int(os.environ.get("CATVTON_WIDTH", "512"))
CATVTON_HEIGHT = int(os.environ.get("CATVTON_HEIGHT", "768"))
CATVTON_REPAINT = os.environ.get("CATVTON_REPAINT", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# ─── Engine detection ────────────────────────────────────────────────────────────

# OOTDiffusion
OOTD_AVAILABLE = False
try:
    from ootd_engine import get_engine as _ootd_get_engine, is_available as _ootd_available
    OOTD_AVAILABLE = _ootd_available()
    if OOTD_AVAILABLE:
        logger.info("OOTDiffusion is available")
except ImportError:
    logger.warning("OOTDiffusion not available (import failed)")

# CatVTON
CATVTON_AVAILABLE = False
CATVTON_ERROR: Optional[str] = None

def _check_catvton():
    """Check CatVTON availability without loading full model."""
    global CATVTON_AVAILABLE, CATVTON_ERROR
    if CATVTON_AVAILABLE:
        return True
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from catvton_engine import is_available as catvton_is_available
        CATVTON_AVAILABLE = catvton_is_available()
        if CATVTON_AVAILABLE:
            logger.info("CatVTON is available")
        else:
            CATVTON_ERROR = "CatVTON installed but import failed"
        return CATVTON_AVAILABLE
    except Exception as e:
        CATVTON_ERROR = str(e)
        logger.warning(f"CatVTON not available: {e}")
        return False

# Run check in background to not slow down startup
if VTON_FORCE_ENGINE in ("catvton", "auto"):
    threading.Thread(target=_check_catvton, daemon=True).start()


def _check_bearer(request: Request) -> None:
    if not VTON_SERVICE_API_KEY:
        return
    auth = (request.headers.get("authorization") or "").strip()
    if auth != f"Bearer {VTON_SERVICE_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing Bearer token")


def _ootd_category_hint(garment_category: str) -> Optional[int]:
    """OOTDiffusion category mapping: 0=upper, 1=lower, 2=dress."""
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


def _catvton_category_hint(garment_category: str) -> str:
    """CatVTON category mapping: upper|lower|overall."""
    s = (garment_category or "").strip().lower()
    if any(k in s for k in ("裙", "连衣裙", "dress")):
        return "overall"
    if any(k in s for k in ("下装", "裤", "裤装", "bottom", "短裤")):
        return "lower"
    if any(k in s for k in ("上装", "上衣", "外套", "top", "t恤")):
        return "upper"
    return "upper"


def _pil_to_jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    """Save PIL image to JPEG bytes (no BytesIO on Windows)."""
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


# ─── Engine: CatVTON (subprocess) ─────────────────────────────────────────────

def _run_catvton_subprocess(
    person_bytes: bytes,
    garment_bytes: bytes,
    cloth_type: str,
    seed: int = -1,
    timeout: int = 600,
) -> bytes:
    """
    Run CatVTON as subprocess to avoid dependency conflicts with main service.

    Writes images to temp files, runs catvton_runner.py, reads result.

    Returns JPEG bytes on success.

    Raises RuntimeError on failure.
    """
    # Write images to temp files
    fd_person, person_path = tempfile.mkstemp(suffix=".jpg")
    fd_garment, garment_path = tempfile.mkstemp(suffix=".jpg")
    fd_output, output_path = tempfile.mkstemp(suffix=".jpg")

    try:
        os.close(fd_person)
        os.close(fd_garment)
        os.close(fd_output)

        # Write input images
        person_im = Image.open(io.BytesIO(person_bytes))
        garment_im = Image.open(io.BytesIO(garment_bytes))
        person_im.save(person_path, format="JPEG", quality=95)
        garment_im.save(garment_path, format="JPEG", quality=95)

        # Build command
        cmd = [
            sys.executable, "-m", "vton_inference_service.catvton_runner",
            "--person", person_path,
            "--garment", garment_path,
            "--output", output_path,
            "--type", cloth_type,
            "--width", str(CATVTON_WIDTH),
            "--height", str(CATVTON_HEIGHT),
            "--steps", str(CATVTON_STEPS),
            "--guidance", str(CATVTON_GUIDANCE),
            "--seed", str(seed),
        ]
        if not CATVTON_REPAINT:
            cmd.append("--no-repaint")
        if CATVTON_PATH:
            cmd.extend(["--catvton-path", CATVTON_PATH])

        # Run subprocess
        logger.info(f"Running CatVTON subprocess: {' '.join(cmd[:6])} ...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Path(__file__).parent.parent),
        )

        if result.returncode != 0:
            # Parse error
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            combined = stdout + "\n" + stderr

            if "CATVTON_NOT_AVAILABLE" in combined or result.returncode == 10:
                raise RuntimeError(
                    "CatVTON not installed. Set CATVTON_PATH or run: "
                    "git clone https://github.com/Zheng-Chong/CatVTON.git"
                )

            # Extract error message
            error_lines = [
                line for line in combined.splitlines()
                if line.startswith("ERROR:")
            ]
            if error_lines:
                error_msg = error_lines[0].replace("ERROR:", "").strip()
            else:
                error_msg = combined[:500] if combined else f"exit code {result.returncode}"

            raise RuntimeError(f"CatVTON inference failed: {error_msg}")

        # Read result
        with open(output_path, "rb") as f:
            return f.read()

    finally:
        for path in [person_path, garment_path, output_path]:
            try:
                os.unlink(path)
            except OSError:
                pass


# ─── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check with detailed engine status."""
    status = {
        "status": "ok",
        "stub_mode": VTON_STUB_MODE,
        "ootd_available": OOTD_AVAILABLE,
        "catvton_available": CATVTON_AVAILABLE,
        "catvton_error": CATVTON_ERROR,
        "force_engine": VTON_FORCE_ENGINE,
        "note": (
            "VTON_STUB_MODE=true uses naive blend (demo only). "
            "For real try-on: install CatVTON (recommended) or OOTDiffusion."
        ),
    }

    if OOTD_AVAILABLE:
        try:
            from ootd_engine import get_device_info
            status["device_info"] = get_device_info()
        except Exception as e:
            status["device_info_error"] = str(e)

    if CATVTON_AVAILABLE:
        try:
            from catvton_engine import get_device_info
            status["device_info"] = get_device_info()
        except Exception:
            pass

    return status


# ─── Try-on endpoint ─────────────────────────────────────────────────────────────

@app.post("/v1/tryon")
async def tryon_v1(
    request: Request,
    garment_file: UploadFile = File(...),
    person_file: UploadFile = File(...),
    model_gender: str = Form("neutral"),
    garment_category: str = Form(""),
    prompt: str = Form(""),
    num_inference_steps: int = Form(50),
    guidance_scale: float = Form(2.5),
    seed: int = Form(-1),
):
    """
    Virtual try-on endpoint.

    Engines (tried in order when VTON_STUB_MODE=false):
    1. CatVTON — best quality, auto-mask generation, <8GB VRAM (bf16)
    2. OOTDiffusion — if CatVTON unavailable
    3. Stub blend — demo only

    Override engine: set VTON_ENGINE=catvton or VTON_ENGINE=ootd
    """
    _check_bearer(request)

    g_bytes = await garment_file.read()
    p_bytes = await person_file.read()
    if not g_bytes or not p_bytes:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "empty garment_file or person_file"},
        )

    try:
        person_im = Image.open(io.BytesIO(p_bytes))
        garment_im = Image.open(io.BytesIO(g_bytes))
    except Exception as e:
        logger.error(f"Failed to load images: {e}")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"invalid image: {e}"},
        )

    cat_hint_ootd = _ootd_category_hint(garment_category)
    cat_hint_catvton = _catvton_category_hint(garment_category)

    logger.info(
        f"VTON request: category={garment_category}, "
        f"catvton_type={cat_hint_catvton}, ootd_type={cat_hint_ootd}, "
        f"stub_mode={VTON_STUB_MODE}, ootd_available={OOTD_AVAILABLE}, "
        f"catvton_available={CATVTON_AVAILABLE}, force_engine={VTON_FORCE_ENGINE}"
    )

    # ── Stub mode ──────────────────────────────────────────────────────────────
    if VTON_STUB_MODE:
        logger.info("Using stub mode (naive blend)")
        jpeg = _stub_tryon(person_im, garment_im)
        return Response(
            content=jpeg,
            media_type="image/jpeg",
            headers={
                "X-VTON-Engine": "stub-blend",
                "X-VTON-Category-Hint": cat_hint_catvton,
            },
        )

    # ── Engine selection ───────────────────────────────────────────────────────
    chosen_engine: Optional[str] = None
    result_bytes: Optional[bytes] = None
    error_detail: Optional[str] = None

    engines_to_try: list[tuple[str, bool]] = []
    if VTON_FORCE_ENGINE == "auto":
        engines_to_try = [
            ("catvton", CATVTON_AVAILABLE),
            ("ootd", OOTD_AVAILABLE),
        ]
    elif VTON_FORCE_ENGINE == "catvton":
        engines_to_try = [("catvton", CATVTON_AVAILABLE)]
    elif VTON_FORCE_ENGINE == "ootd":
        engines_to_try = [("ootd", OOTD_AVAILABLE)]

    for engine_name, is_available in engines_to_try:
        if not is_available:
            logger.info(f"Skipping {engine_name} (not available)")
            continue

        if engine_name == "catvton":
            logger.info("Using CatVTON engine")
            cloth_type = cat_hint_catvton
            steps = num_inference_steps if num_inference_steps != 50 else CATVTON_STEPS
            guidance = guidance_scale if guidance_scale != 2.5 else CATVTON_GUIDANCE
            result_bytes = _run_catvton_subprocess(
                person_bytes=p_bytes,
                garment_bytes=g_bytes,
                cloth_type=cloth_type,
                seed=seed if seed >= 0 else -1,
            )
            chosen_engine = "catvton"
            break

        elif engine_name == "ootd":
            logger.info("Using OOTDiffusion engine")
            from ootd_engine import get_engine
            engine = get_engine()
            cat = cat_hint_ootd if cat_hint_ootd is not None else 0
            result_im = engine.infer(
                person_image=person_im,
                garment_image=garment_im,
                category=cat,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
            )
            result_bytes = _pil_to_jpeg_bytes(result_im)
            chosen_engine = "ootdiffusion"
            break

    # ── No fallback: if no engine succeeded, hard error ──────────────────────
    if not result_bytes:
        engines_failed = []
        if not CATVTON_AVAILABLE:
            engines_failed.append(f"CatVTON (not available: {CATVTON_ERROR})")
        if not OOTD_AVAILABLE:
            engines_failed.append("OOTDiffusion (not available)")
        raise HTTPException(
            status_code=503,
            detail=(
                f"No VTON engine available. Tried: {', '.join(engines_failed)}. "
                f"Install CatVTON or OOTDiffusion, or set VTON_STUB_MODE=true for demo only."
            ),
        )

    logger.info(f"VTON completed with engine: {chosen_engine}")
    return Response(
        content=result_bytes,
        media_type="image/jpeg",
        headers={
            "X-VTON-Engine": chosen_engine,
            "X-VTON-Category-Hint": cat_hint_catvton,
        },
    )
