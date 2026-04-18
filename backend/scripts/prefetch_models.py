"""
Prefetch Hugging Face model weights for offline deployment.

Run this script ONCE in a networked environment. Then copy the cache directory
to an offline machine and set HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE.

Targets in this repo:
- CLIP (transformers): used by backend/app/ml/clip_recognizer.py
- Optional Stable Diffusion inpainting (diffusers): used by backend/app/services/virtual_tryon.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from huggingface_hub import snapshot_download


def _ensure_backend_on_syspath() -> None:
    """
    Ensure `backend/` is on sys.path so `import app...` works regardless of CWD.
    """
    backend_dir = Path(__file__).resolve().parents[1]
    backend_str = str(backend_dir)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)


def _print_kv(title: str, kv: dict) -> None:
    print(f"\n== {title} ==")
    for k, v in kv.items():
        if v is None or v == "":
            continue
        print(f"{k}={v}")


def _download_model_repo(
    model_id: str,
    label: str,
    allow_patterns: Optional[List[str]] = None,
    ignore_patterns: Optional[List[str]] = None,
) -> str:
    print(f"\n[{label}] downloading repo: {model_id}", flush=True)
    local_dir = snapshot_download(
        repo_id=model_id,
        repo_type="model",
        allow_patterns=allow_patterns,
        ignore_patterns=ignore_patterns,
        max_workers=4,
    )
    print(f"[{label}] cached at: {local_dir}", flush=True)
    return local_dir


def _ensure_imports() -> None:
    try:
        import transformers  # noqa: F401
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency: transformers. Install backend requirements first."
        ) from e


def _prefetch_clip(model_ids: Iterable[str]) -> List[str]:
    from app.core.hf_hub_env import apply_hf_hub_env_defaults

    apply_hf_hub_env_defaults()

    model_list = list(model_ids)
    done: List[str] = []
    for index, model_id in enumerate(model_list, start=1):
        print(f"\n[CLIP] [{index}/{len(model_list)}] start: {model_id}", flush=True)
        _download_model_repo(model_id, "CLIP")
        done.append(model_id)
    return done


def _prefetch_tryon(sd_model_id: str) -> str:
    from app.core.hf_hub_env import apply_hf_hub_env_defaults

    apply_hf_hub_env_defaults()

    try:
        import torch
        from diffusers import StableDiffusionInpaintPipeline
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency: diffusers/torch. Install backend requirements first."
        ) from e

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    print(
        f"\n[TRYON] downloading: {sd_model_id} (device={device}, dtype={dtype})",
        flush=True,
    )
    # Download only the core weights required by the inpaint pipeline.
    # The runtime disables the safety checker / feature extractor so we do not
    # need to prefetch those extra files.
    required_patterns = [
        "model_index.json",
        "scheduler/*",
        "text_encoder/*",
        "tokenizer/*",
        "unet/*",
        "vae/*",
    ]
    ignore_patterns = [
        "*.onnx",
        "*.tflite",
        "*.pb",
        "*.h5",
        "*.ot",
        "*.msgpack",
    ]
    _download_model_repo(
        sd_model_id,
        "TRYON",
        allow_patterns=required_patterns,
        ignore_patterns=ignore_patterns,
    )
    return sd_model_id


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prefetch model weights to local HF cache for offline use."
    )
    parser.add_argument(
        "--clip",
        default="vit_l14",
        choices=["vit_l14", "vit_b32", "both", "none"],
        help="Which CLIP variant(s) to prefetch (default: vit_l14).",
    )
    parser.add_argument(
        "--tryon",
        action="store_true",
        help="Also prefetch Stable Diffusion inpainting model used by try-on.",
    )
    parser.add_argument(
        "--sd-model-id",
        default=os.environ.get(
            "SD_VTON_MODEL_ID", "stable-diffusion-v1-5/stable-diffusion-inpainting"
        ),
        help="Diffusers model id for try-on (default from SD_VTON_MODEL_ID env).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=5,
        help="Retry times for unstable network download (default: 5).",
    )

    args = parser.parse_args(argv)

    _ensure_backend_on_syspath()
    _ensure_imports()

    _print_kv(
        "cache env (recommended to set before prefetch)",
        {
            "HF_ENDPOINT": os.environ.get("HF_ENDPOINT"),
            "HF_HOME": os.environ.get("HF_HOME"),
            "TRANSFORMERS_CACHE": os.environ.get("TRANSFORMERS_CACHE"),
            "HF_HUB_DOWNLOAD_TIMEOUT": os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT"),
        },
    )

    if os.environ.get("HF_HUB_OFFLINE") == "1" or os.environ.get("TRANSFORMERS_OFFLINE") == "1":
        print(
            "\nERROR: You have offline flags enabled (HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE=1). "
            "Disable them for prefetch, or the download will be blocked."
        )
        return 2

    clip_map = {
        "vit_l14": ["openai/clip-vit-large-patch14"],
        "vit_b32": ["openai/clip-vit-base-patch32"],
        "both": ["openai/clip-vit-large-patch14", "openai/clip-vit-base-patch32"],
        "none": [],
    }

    def _run_with_retries(label: str, fn) -> None:
        last_error: Exception | None = None
        for attempt in range(1, max(1, args.retries) + 1):
            try:
                print(f"\n[{label}] attempt {attempt}/{max(1, args.retries)}", flush=True)
                fn()
                return
            except Exception as e:  # pragma: no cover
                last_error = e
                print(f"[{label}] attempt {attempt} failed: {e}", flush=True)
        assert last_error is not None
        raise last_error

    try:
        if args.clip != "none":
            _run_with_retries("CLIP", lambda: _prefetch_clip(clip_map[args.clip]))
        if args.tryon:
            _run_with_retries("TRYON", lambda: _prefetch_tryon(args.sd_model_id))
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print(f"\nFAILED: {e}")
        return 1

    print("\nDone. You can now set offline env vars and run without network.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
