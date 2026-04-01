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
from typing import Iterable, List


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

    from transformers import CLIPModel, CLIPProcessor

    done: List[str] = []
    for model_id in model_ids:
        print(f"\n[CLIP] downloading: {model_id}")
        # `from_pretrained` will populate HF cache (HF_HOME / TRANSFORMERS_CACHE)
        CLIPModel.from_pretrained(model_id)
        CLIPProcessor.from_pretrained(model_id)
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
    print(f"\n[TRYON] downloading: {sd_model_id} (device={device}, dtype={dtype})")
    StableDiffusionInpaintPipeline.from_pretrained(sd_model_id, torch_dtype=dtype)
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
        default=os.environ.get("SD_VTON_MODEL_ID", "runwayml/stable-diffusion-inpainting"),
        help="Diffusers model id for try-on (default from SD_VTON_MODEL_ID env).",
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

    try:
        if args.clip != "none":
            _prefetch_clip(clip_map[args.clip])
        if args.tryon:
            _prefetch_tryon(args.sd_model_id)
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
