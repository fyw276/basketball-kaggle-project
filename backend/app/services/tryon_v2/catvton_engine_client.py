"""
Local CatVTON client for backend — integrates CatVTON inference into tryon_v2.

This module provides direct CatVTON inference within the backend, bypassing the
need for a separate VTON inference service. It calls the catvton_runner.py
subprocess to avoid dependency conflicts.

Usage in tryon_v2 API:
    from app.services.tryon_v2.catvton_engine_client import call_local_catvton
    result = await call_local_catvton(garment_bytes, person_bytes, garment_category)
"""

from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)


def _catvton_configured() -> bool:
    """Check if local CatVTON is properly configured and models are available."""
    if not bool(getattr(settings, "CATVTON_ENABLED", False)):
        logger.info("CatVTON _catvton_configured: CATVTON_ENABLED is false")
        return False
    catvton_path = (getattr(settings, "CATVTON_PATH", "") or "").strip()
    if not catvton_path:
        logger.info("CatVTON _catvton_configured: CATVTON_PATH is empty")
        return False
    if not Path(catvton_path).exists():
        logger.info("CatVTON _catvton_configured: CATVTON_PATH does not exist: %s", catvton_path)
        return False

    # Check for CatVTON model (required for actual inference)
    model_path = Path(catvton_path) / "zhengchong_CatVTON"
    if not model_path.exists():
        logger.info(
            "CatVTON _catvton_configured: model path does not exist: %s. "
            "Model will be downloaded on first use (requires HuggingFace access).",
            model_path,
        )
        # Return True - model will be downloaded on first run
        # Only return False if we want to block realistic mode entirely
        return True

    logger.info("CatVTON _catvton_configured: OK (path=%s, model=%s)", catvton_path, model_path)
    return True


def _catvton_category_hint(garment_category: Optional[str]) -> str:
    """Map garment category string to CatVTON type."""
    s = (garment_category or "").strip().lower()
    if any(k in s for k in ("裙", "连衣裙", "dress")):
        return "overall"
    if any(k in s for k in ("下装", "裤", "裤装", "bottom", "短裤")):
        return "lower"
    if any(k in s for k in ("上装", "上衣", "外套", "top", "t恤", "毛衣")):
        return "upper"
    return "upper"


def _run_catvton_sync(
    *,
    person_bytes: bytes,
    garment_bytes: bytes,
    cloth_type: str,
    seed: int = -1,
    timeout: int = 600,
    debug_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run CatVTON inference synchronously via subprocess.

    Returns dict with keys: result_image (PIL Image), status, message, metadata
    Returns error dict on failure.
    """
    # Check configuration
    if not _catvton_configured():
        return {
            "result_image": None,
            "status": "error",
            "message": "CatVTON not configured",
            "metadata": {
                "reason": "not_configured",
                "hint": "Set CATVTON_ENABLED=true and CATVTON_PATH in config",
            },
        }

    catvton_path = (getattr(settings, "CATVTON_PATH", "") or "").strip()
    width = int(getattr(settings, "CATVTON_WIDTH", 768) or 768)
    height = int(getattr(settings, "CATVTON_HEIGHT", 1024) or 1024)
    steps = int(getattr(settings, "CATVTON_STEPS", 50) or 50)
    guidance = float(getattr(settings, "CATVTON_GUIDANCE", 2.5) or 2.5)
    repaint = bool(getattr(settings, "CATVTON_REPAINT", True))

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
        # Path structure:
        # catvton_engine_client.py is at backend/app/services/tryon_v2/
        # parent.parent = backend/app, parent.parent.parent.parent.parent = repo root
        backend_dir = Path(__file__).parent.parent.parent  # → backend/app/
        workspace_root = Path(__file__).parent.parent.parent.parent.parent  # → clothing-assistant/
        runner_paths = [
            workspace_root / "vton_inference_service" / "catvton_runner.py",
            workspace_root / "backend" / "vton_inference_service" / "catvton_runner.py",
            backend_dir / "vton_inference_service" / "catvton_runner.py",
            Path(catvton_path) / "catvton_runner.py" if catvton_path else None,
        ]
        runner_path = None
        for p in runner_paths:
            _exists = p.exists() if p else False
            logger.info(
                "CatVTON runner search: path=%s exists=%s backend_dir=%s workspace_root=%s",
                str(p) if p else None,
                _exists,
                str(backend_dir),
                str(workspace_root),
            )
            if _exists:
                runner_path = p
                break

        if runner_path is None:
            return {
                "result_image": None,
                "status": "error",
                "message": "CatVTON runner script not found",
                "metadata": {
                    "reason": "runner_not_found",
                    "searched_paths": [str(p) for p in runner_paths if p],
                },
            }

        cmd = [
            sys.executable,
            str(runner_path),
            "--person",
            person_path,
            "--garment",
            garment_path,
            "--output",
            output_path,
            "--type",
            cloth_type,
            "--width",
            str(width),
            "--height",
            str(height),
            "--steps",
            str(steps),
            "--guidance",
            str(guidance),
            "--seed",
            str(seed),
        ]
        if not repaint:
            cmd.append("--no-repaint")

        # Read precision and offload from settings
        precision = getattr(settings, "CATVTON_MIXED_PRECISION", "bf16") or "bf16"
        cmd.extend(["--precision", precision])
        if getattr(settings, "CATVTON_CPU_OFFLOAD", False):
            cmd.append("--cpu-offload")

        cmd.extend(["--catvton-path", catvton_path])

        # Enable debug intermediate saves (useful for diagnosing mask/skeleton quality)
        if debug_dir:
            cmd.extend(["--debug-dir", str(debug_dir)])

        logger.info(
            f"Running local CatVTON: cloth_type={cloth_type}, "
            f"size={width}x{height}, steps={steps}, guidance={guidance}"
        )

        # Run subprocess
        logger.info("CatVTON subprocess starting: %s", " ".join(cmd[:6]) + "...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(backend_dir),
        )

        # Log subprocess output for debugging
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    logger.info("CatVTON stdout: %s", line.strip())
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                if line.strip():
                    logger.warning("CatVTON stderr: %s", line.strip())

        if result.returncode != 0:
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            combined = stdout + "\n" + stderr

            if "CATVTON_NOT_AVAILABLE" in combined or result.returncode == 10:
                return {
                    "result_image": None,
                    "status": "error",
                    "message": "CatVTON not installed or import failed",
                    "metadata": {
                        "reason": "catvton_not_available",
                        "hint": "Run: git clone https://github.com/Zheng-Chong/CatVTON.git",
                        "stderr": stderr[:500],
                    },
                }

            error_lines = [line for line in combined.splitlines() if line.startswith("ERROR:")]
            if error_lines:
                error_msg = error_lines[0].replace("ERROR:", "").strip()
            else:
                error_msg = combined[:500] if combined else f"exit code {result.returncode}"

            return {
                "result_image": None,
                "status": "error",
                "message": f"CatVTON inference failed: {error_msg}",
                "metadata": {
                    "reason": "inference_failed",
                    "stderr": stderr[:500],
                    "returncode": result.returncode,
                },
            }

        # Read result
        with open(output_path, "rb") as f:
            result_bytes = f.read()

        img = Image.open(io.BytesIO(result_bytes)).convert("RGB")
        return {
            "result_image": img,
            "status": "success",
            "message": "CatVTON 试衣完成",
            "metadata": {
                "model": "catvton_local",
                "engine": "catvton",
                "category": cloth_type,
                "width": width,
                "height": height,
                "steps": steps,
                "guidance": guidance,
            },
        }

    except subprocess.TimeoutExpired:
        return {
            "result_image": None,
            "status": "error",
            "message": "CatVTON inference timeout",
            "metadata": {
                "reason": "timeout",
                "timeout_s": timeout,
                "hint": "Increase CATVTON_TIMEOUT_SECONDS or reduce CATVTON_STEPS",
            },
        }
    except Exception as e:
        logger.exception("CatVTON inference error: %s", e)
        return {
            "result_image": None,
            "status": "error",
            "message": f"CatVTON error: {str(e)}",
            "metadata": {
                "reason": "exception",
                "error": str(e),
            },
        }
    finally:
        for path in [person_path, garment_path, output_path]:
            try:
                os.unlink(path)
            except OSError:
                pass


async def call_local_catvton(
    *,
    garment_bytes: bytes,
    person_bytes: bytes,
    garment_category: Optional[str] = None,
    seed: int = -1,
    debug_dir: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Call local CatVTON for virtual try-on.

    Args:
        garment_bytes: JPEG bytes of the garment product image.
        person_bytes: JPEG bytes of the person full-body image.
        garment_category: Garment category string (e.g. "top", "上装", "bottom").
        seed: Random seed (-1 = random).

    Returns:
        Dict with keys: result_image (PIL Image), status, message, metadata
        Returns None if CatVTON is not configured.
    """
    import asyncio

    if not _catvton_configured():
        return None

    catvton_type = _catvton_category_hint(garment_category)
    timeout = int(getattr(settings, "CATVTON_TIMEOUT_SECONDS", 600) or 600)

    # Read debug_dir from settings if not explicitly provided
    debug_dir_setting = getattr(settings, "CATVTON_DEBUG_DIR", "") or ""
    if debug_dir is None:
        debug_dir = debug_dir_setting.strip() or None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: _run_catvton_sync(
            person_bytes=person_bytes,
            garment_bytes=garment_bytes,
            cloth_type=catvton_type,
            seed=seed,
            timeout=timeout,
            debug_dir=debug_dir,
        ),
    )


def get_catvton_status() -> Dict[str, Any]:
    """Get CatVTON configuration and availability status."""
    configured = _catvton_configured()

    catvton_path = (getattr(settings, "CATVTON_PATH", "") or "").strip()
    path_exists = Path(catvton_path).exists() if catvton_path else False

    # Check for CatVTON runner script
    runner_paths = [
        Path(__file__).parent.parent.parent.parent.parent
        / "vton_inference_service"
        / "catvton_runner.py",
        Path(__file__).parent.parent.parent / "vton_inference_service" / "catvton_runner.py",
    ]
    runner_exists = any(p.exists() for p in runner_paths if p)

    # Check for CatVTON model in the path
    catvton_model_path = Path(catvton_path) / "zhengchong_CatVTON" if catvton_path else None
    model_exists = catvton_model_path.exists() if catvton_model_path else False

    return {
        "enabled": bool(getattr(settings, "CATVTON_ENABLED", False)),
        "configured": configured,
        "path": catvton_path,
        "path_exists": path_exists,
        "runner_exists": runner_exists,
        "model_exists": model_exists,
        "model_path": str(catvton_model_path) if catvton_model_path else None,
        "width": int(getattr(settings, "CATVTON_WIDTH", 768) or 768),
        "height": int(getattr(settings, "CATVTON_HEIGHT", 1024) or 1024),
        "steps": int(getattr(settings, "CATVTON_STEPS", 50) or 50),
        "guidance": float(getattr(settings, "CATVTON_GUIDANCE", 2.5) or 2.5),
        "repaint": bool(getattr(settings, "CATVTON_REPAINT", True)),
        "timeout_s": int(getattr(settings, "CATVTON_TIMEOUT_SECONDS", 600) or 600),
    }


def log_catvton_status(prefix: str = "") -> str:
    """Log CatVTON status and return a summary string for startup logs."""
    status = get_catvton_status()
    lines = []
    if prefix:
        lines.append(f"{prefix} CatVTON Status:")

    lines.append(f"  enabled={status['enabled']}")
    lines.append(f"  configured={status['configured']}")
    lines.append(f"  catvton_path={status['path']}")
    lines.append(f"  path_exists={status['path_exists']}")
    lines.append(f"  runner_exists={status['runner_exists']}")
    lines.append(f"  model_exists={status['model_exists']}")

    summary = " | ".join(
        [
            f"CatVTON enabled={status['enabled']}",
            f"path={'OK' if status['path_exists'] else 'MISSING'}",
            f"runner={'OK' if status['runner_exists'] else 'MISSING'}",
            f"model={'OK' if status['model_exists'] else 'NOT_DOWNLOADED'}",
        ]
    )

    for line in lines:
        logger.info(line)

    return summary
