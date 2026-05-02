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

    # Check for CatVTON model files
    # Two possible structures:
    # 1. D:\models\CatVTON_full\mix-48k-1024\attention\model.safetensors (downloaded repo)
    # 2. D:\models\CatVTON\zhengchong_CatVTON\... (HuggingFace snapshot format)
    base = Path(catvton_path)

    # Check for model directories (the "downloaded repo" structure)
    model_dirs = ["mix-48k-1024", "vitonhd-16k-512", "dresscode-16k-512"]
    has_model = any((base / d).exists() for d in model_dirs)

    # Also check for zhengchong_CatVTON subdirectory (HuggingFace snapshot structure)
    zhengchong_path = base / "zhengchong_CatVTON"
    if zhengchong_path.exists():
        has_model = True

    if not has_model:
        # Try alternative path: CatVTON_full
        alt_path = Path(r"D:\models\CatVTON_full")
        if alt_path.exists() and any((alt_path / d).exists() for d in model_dirs):
            logger.info(
                "CatVTON _catvton_configured: Found model at "
                "D:\\models\\CatVTON_full, updating path"
            )
            has_model = True
        else:
            logger.info(
                "CatVTON _catvton_configured: model directory not found in %s. "
                "Expected one of: %s or zhengchong_CatVTON subdirectory. "
                "Model will be downloaded on first use (requires HuggingFace access).",
                catvton_path,
                model_dirs,
            )
            # Return True - model will be downloaded on first run
            return True

    logger.info("CatVTON _catvton_configured: OK (path=%s)", catvton_path)
    return True


def _get_catvton_path() -> str:
    """Get the correct CatVTON path, checking multiple possible locations."""
    # First try configured path
    configured_path = (getattr(settings, "CATVTON_PATH", "") or "").strip()
    if configured_path and Path(configured_path).exists():
        return configured_path

    # Try common paths
    common_paths = [
        r"D:\models\CatVTON_full",
        r"D:\models\CatVTON",
    ]

    for path in common_paths:
        if Path(path).exists():
            model_dirs = ["mix-48k-1024", "vitonhd-16k-512", "dresscode-16k-512"]
            if any((Path(path) / d).exists() for d in model_dirs):
                logger.info(f"[CATVTON] Auto-detected CatVTON path: {path}")
                return path

            # Also check for zhengchong_CatVTON subdirectory
            if (Path(path) / "zhengchong_CatVTON").exists():
                logger.info(f"[CATVTON] Auto-detected CatVTON path: {path}")
                return path

    # Fallback to configured path (even if doesn't exist)
    return configured_path


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
    timeout: int = 2400,
    debug_dir: Optional[str] = None,
    preprocess_only: bool = False,
    vae_slicing: bool = True,
    xformers: bool = True,
    force_fp16: bool = False,
    low_vram_mode: bool = False,
    torch_compile: bool = False,
) -> Dict[str, Any]:
    """
    Run CatVTON inference synchronously via subprocess.

    Returns dict with keys: result_image (PIL Image), status, message, metadata
    Returns error dict on failure.

    New args:
        preprocess_only: if True, only run preprocessing (mask + pose), skip diffusion
        vae_slicing: enable VAE tile slicing (reduce peak VRAM by ~40%)
        xformers: enable xformers/efficient attention
        force_fp16: force fp16 instead of bf16 (saves ~2GB VRAM)
        low_vram_mode: one-shot low VRAM mode (fp16 + cpu_offload + no repaint)
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

    # Get CatVTON path (with auto-detection)
    catvton_path = _get_catvton_path()
    if not catvton_path:
        return {
            "result_image": None,
            "status": "error",
            "message": "CatVTON path not found",
            "metadata": {
                "reason": "path_not_found",
                "hint": (
                    "Set CATVTON_PATH in config or ensure "
                    "D:\\models\\CatVTON or D:\\models\\CatVTON_full exists"
                ),
            },
        }

    width = int(getattr(settings, "CATVTON_WIDTH", 768) or 768)
    height = int(getattr(settings, "CATVTON_HEIGHT", 1024) or 1024)
    steps = int(getattr(settings, "CATVTON_STEPS", 50) or 50)
    guidance = float(getattr(settings, "CATVTON_GUIDANCE", 2.5) or 2.5)
    repaint = bool(getattr(settings, "CATVTON_REPAINT", True))

    # 一键低显存模式：覆盖所有设置
    if low_vram_mode:
        force_fp16 = True
        vae_slicing = True
        xformers = True

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

        # Find runner path
        # __file__ = backend/app/services/tryon_v2/catvton_engine_client.py
        # backend_dir = backend/app/ (3 parents up)
        # workspace_root = clothing-assistant/ (4 parents up, but we need 5 for project root)
        backend_dir = Path(__file__).parent.parent.parent  # → backend/app/
        # Calculate project root: go up from backend/app/services/tryon_v2/ to clothing-assistant/
        current = Path(__file__).resolve()
        workspace_root = current
        for _ in range(5):  # Go up 5 levels from tryon_v2/ to project root
            workspace_root = workspace_root.parent

        print(f"[DEBUG] __file__ = {current}", flush=True)
        print(f"[DEBUG] backend_dir = {backend_dir}", flush=True)
        print(f"[DEBUG] workspace_root = {workspace_root}", flush=True)

        runner_paths = [
            workspace_root / "vton_inference_service" / "catvton_runner.py",  # Project root
            Path(catvton_path) / "catvton_runner.py" if catvton_path else None,
        ]

        print(f"[DEBUG] Searching runner_paths: {[str(p) for p in runner_paths if p]}", flush=True)

        runner_path = None
        for p in runner_paths:
            if p:
                _exists = p.exists()
                print(f"[DEBUG] Checking {p}: exists={_exists}", flush=True)
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

        # Read precision from settings, allow override
        precision = getattr(settings, "CATVTON_MIXED_PRECISION", "bf16") or "bf16"
        final_precision = "fp16" if force_fp16 else precision
        cmd.extend(["--precision", final_precision])

        # Pass VRAM optimization flags
        if getattr(settings, "CATVTON_CPU_OFFLOAD", False) or low_vram_mode:
            cmd.append("--cpu-offload")

        # VAE slicing (default True)
        if not vae_slicing:
            cmd.append("--no-vae-slicing")

        # xformers (default True)
        if not xformers:
            cmd.append("--no-xformers")

        # Low VRAM mode
        if low_vram_mode:
            cmd.append("--low-vram-mode")

        # Preprocess only
        if preprocess_only:
            cmd.append("--preprocess-only")

        # torch.compile JIT 编译（需要 PyTorch 2.0+，推理步数>=20 时效果最佳）
        if torch_compile:
            cmd.append("--torch-compile")

        cmd.extend(["--catvton-path", catvton_path])

        # Enable debug intermediate saves
        if debug_dir:
            cmd.extend(["--debug-dir", str(debug_dir)])

        logger.info(
            f"Running local CatVTON: cloth_type={cloth_type}, "
            f"size={width}x{height}, steps={steps}, guidance={guidance}, "
            f"precision={final_precision}, vae_slicing={vae_slicing}, "
            f"xformers={xformers}, preprocess_only={preprocess_only}, "
            f"low_vram_mode={low_vram_mode}, torch_compile={torch_compile}"
        )

        # Pass HF cache dir to subprocess so it finds downloaded models
        subproc_env = dict(os.environ)
        subproc_env.setdefault("HF_HOME", r"D:\hf-cache")
        subproc_env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        # Force unbuffered mode in subprocess
        subproc_env["PYTHONUNBUFFERED"] = "1"

        logger.info("[CATVTON] 启动子进程执行 CatVTON...")

        import threading

        stdout_lines = []
        stderr_lines = []
        stdout_lock = threading.Lock()
        stderr_lock = threading.Lock()

        def stream_output(stream, lines_list, lock, prefix):
            """Read stream line by line and log each line in real-time."""
            try:
                for line in iter(stream.readline, ""):
                    if not line:
                        break
                    line = line.rstrip()
                    if line:
                        with lock:
                            lines_list.append(line)
                        logger.info(f"[CATVTON] {prefix}: {line}")
            except Exception as e:
                logger.debug(f"[CATVTON] {prefix} stream ended: {e}")

        # Start subprocess
        # Set cwd to workspace_root so runner can find CatVTON modules
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            cwd=str(workspace_root),  # Use workspace_root as cwd
            env=subproc_env,
        )

        # Start streaming threads
        stdout_thread = threading.Thread(
            target=stream_output, args=(proc.stdout, stdout_lines, stdout_lock, "OUT"), daemon=True
        )
        stderr_thread = threading.Thread(
            target=stream_output, args=(proc.stderr, stderr_lines, stderr_lock, "ERR"), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        # Wait for process with timeout
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.error(f"[CATVTON] 进程超时 ({timeout}s)，正在终止...")
            proc.kill()
            proc.wait()
            returncode = -1

        # Wait for streaming threads to finish
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)

        # Get final output
        stdout = "\n".join(stdout_lines)
        stderr = "\n".join(stderr_lines)

        result = type(
            "obj", (object,), {"returncode": returncode, "stdout": stdout, "stderr": stderr}
        )()

        logger.info(f"[CATVTON] 子进程执行完成，返回码: {result.returncode}")

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

        # ── Handle preprocess_only mode ────────────────────────────────
        stdout = result.stdout or ""

        # Extract debug_dir from output (e.g. "DEBUG_DIR:C:\path" or "PREPROCESS_ONLY:C:\path")
        debug_session_dir = None
        for line in stdout.splitlines():
            if line.startswith("DEBUG_DIR:"):
                debug_session_dir = line.split(":", 1)[1].strip()
            elif line.startswith("PREPROCESS_ONLY:"):
                if debug_session_dir is None:
                    # Extract path from PREPROCESS_ONLY:path
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        debug_session_dir = parts[1].strip()

        if preprocess_only:
            # Return success with debug session directory
            return {
                "result_image": None,
                "status": "preprocess_only_success",
                "message": "预处理完成（diffusion 未运行）",
                "metadata": {
                    "mode": "preprocess_only",
                    "debug_session_dir": debug_session_dir,
                    "steps_completed": [
                        "01_input_person",
                        "02_input_garment",
                        "03_mask",
                        "04_pose_keypoints",
                        "09_mask_overlay",
                    ],
                    "engine": "catvton",
                    "category": cloth_type,
                },
            }

        # ── Normal inference: read result image ─────────────────────────
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return {
                "result_image": None,
                "status": "error",
                "message": "CatVTON output file is empty or missing",
                "metadata": {"reason": "empty_output"},
            }

        with open(output_path, "rb") as f:
            result_bytes = f.read()

        img = Image.open(io.BytesIO(result_bytes)).convert("RGB")

        # Extract debug_dir if present
        debug_session_dir = None
        for line in stdout.splitlines():
            if line.startswith("DEBUG_DIR:"):
                debug_session_dir = line.split(":", 1)[1].strip()
                break

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
                "precision": final_precision,
                "vae_slicing": vae_slicing,
                "xformers": xformers,
                "low_vram_mode": low_vram_mode,
                "debug_session_dir": debug_session_dir,
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
    timeout: int = 2400,
    debug_dir: Optional[str] = None,
    preprocess_only: bool = False,
    low_vram_mode: bool = False,
    torch_compile: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Call local CatVTON for virtual try-on.

    Args:
        garment_bytes: JPEG bytes of the garment product image.
        person_bytes: JPEG bytes of the person full-body image.
        garment_category: Garment category string (e.g. "top", "上装", "bottom").
        seed: Random seed (-1 = random).
        debug_dir: Override debug output directory.
        preprocess_only: if True, only run preprocessing (mask + pose), skip diffusion.
        low_vram_mode: one-shot low VRAM mode.

    Returns:
        Dict with keys: result_image (PIL Image), status, message, metadata.
        Returns None if CatVTON is not configured.
    """
    import asyncio

    if not _catvton_configured():
        return None

    catvton_type = _catvton_category_hint(garment_category)
    # Use explicit timeout param if provided (> 0), otherwise fall back to settings
    effective_timeout = (
        timeout
        if timeout and timeout > 0
        else int(getattr(settings, "CATVTON_TIMEOUT_SECONDS", 2400) or 2400)
    )

    # Determine debug_dir from settings if not overridden
    debug_dir_setting = getattr(settings, "CATVTON_DEBUG_DIR", "") or ""
    if debug_dir is None:
        debug_dir = debug_dir_setting.strip() or None

    # VRAM optimization flags from settings
    vae_slicing = getattr(settings, "CATVTON_ENABLE_VAE_SLICING", True)
    xformers = getattr(settings, "CATVTON_ENABLE_XFORMERS", True)
    force_fp16 = getattr(settings, "CATVTON_FORCE_FP16", False)
    torch_compile = getattr(settings, "CATVTON_TORCH_COMPILE", False)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: _run_catvton_sync(
            person_bytes=person_bytes,
            garment_bytes=garment_bytes,
            cloth_type=catvton_type,
            seed=seed,
            timeout=effective_timeout,
            debug_dir=debug_dir,
            preprocess_only=preprocess_only,
            vae_slicing=vae_slicing,
            xformers=xformers,
            force_fp16=force_fp16,
            low_vram_mode=low_vram_mode,
            torch_compile=torch_compile,
        ),
    )


def get_catvton_status() -> Dict[str, Any]:
    """Get CatVTON configuration and availability status."""
    configured = _catvton_configured()

    # Use auto-detected path
    catvton_path = _get_catvton_path()
    path_exists = Path(catvton_path).exists() if catvton_path else False

    # Check for CatVTON runner script
    runner_paths = [
        Path(__file__).parent.parent.parent.parent.parent
        / "vton_inference_service"
        / "catvton_runner.py",
        Path(__file__).parent.parent.parent / "vton_inference_service" / "catvton_runner.py",
    ]
    runner_exists = any(p.exists() for p in runner_paths if p)

    # Check for CatVTON model files
    # Two possible structures:
    # 1. D:\models\CatVTON_full\mix-48k-1024\attention\model.safetensors (downloaded repo)
    # 2. D:\models\CatVTON\zhengchong_CatVTON\... (HuggingFace snapshot format)
    base = Path(catvton_path) if catvton_path else None

    model_exists = False
    model_dirs = ["mix-48k-1024", "vitonhd-16k-512", "dresscode-16k-512"]
    if base:
        # Check for model directories (the "downloaded repo" structure)
        model_exists = any((base / d).exists() for d in model_dirs)
        # Also check for zhengchong_CatVTON subdirectory
        if not model_exists and (base / "zhengchong_CatVTON").exists():
            model_exists = True

    return {
        "enabled": bool(getattr(settings, "CATVTON_ENABLED", False)),
        "configured": configured,
        "path": catvton_path,
        "path_exists": path_exists,
        "runner_exists": runner_exists,
        "model_exists": model_exists,
        "model_path": str(base / "mix-48k-1024") if base and model_exists else None,
        "width": int(getattr(settings, "CATVTON_WIDTH", 768) or 768),
        "height": int(getattr(settings, "CATVTON_HEIGHT", 1024) or 1024),
        "steps": int(getattr(settings, "CATVTON_STEPS", 50) or 50),
        "guidance": float(getattr(settings, "CATVTON_GUIDANCE", 2.5) or 2.5),
        "repaint": bool(getattr(settings, "CATVTON_REPAINT", True)),
        "timeout_s": int(getattr(settings, "CATVTON_TIMEOUT_SECONDS", 2400) or 2400),
        # VRAM 优化配置
        "precision": getattr(settings, "CATVTON_MIXED_PRECISION", "bf16"),
        "force_fp16": getattr(settings, "CATVTON_FORCE_FP16", False),
        "vae_slicing": getattr(settings, "CATVTON_ENABLE_VAE_SLICING", True),
        "xformers": getattr(settings, "CATVTON_ENABLE_XFORMERS", True),
        "cpu_offload": getattr(settings, "CATVTON_CPU_OFFLOAD", False),
        "low_vram_mode": getattr(settings, "CATVTON_LOW_VRAM_MODE", False),
        "gc_after_infer": getattr(settings, "CATVTON_ENABLE_GC_AFTER_INFER", True),
        "debug_dir": getattr(settings, "CATVTON_DEBUG_DIR", ""),
        "torch_compile": getattr(settings, "CATVTON_TORCH_COMPILE", False),
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
    # VRAM 优化配置
    lines.append(
        f"  VRAM优化: precision={status['precision']}, force_fp16={status['force_fp16']}, "
        f"vae_slicing={status['vae_slicing']}, xformers={status['xformers']}, "
        f"cpu_offload={status['cpu_offload']}, low_vram_mode={status['low_vram_mode']}"
    )

    summary = " | ".join(
        [
            f"CatVTON enabled={status['enabled']}",
            f"path={'OK' if status['path_exists'] else 'MISSING'}",
            f"runner={'OK' if status['runner_exists'] else 'MISSING'}",
            f"model={'OK' if status['model_exists'] else 'NOT_DOWNLOADED'}",
            f"VRAM=fp16({status['force_fp16']})/vae({status['vae_slicing']})"
            f"/xfrm({status['xformers']})",
        ]
    )

    for line in lines:
        logger.info(line)

    return summary
