from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image


def resolve_debug_session_dir(
    debug_session_dir: str | Path | None,
    *,
    project_root: str | Path | None = None,
) -> Path | None:
    """Resolve CatVTON debug paths consistently from the project root."""
    if not debug_session_dir:
        return None

    debug_dir = Path(debug_session_dir)
    if debug_dir.is_absolute():
        return debug_dir

    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[3]
    return root / debug_dir


def save_debug_stage_image(
    *,
    debug_session_dir: str | None,
    filename: str,
    image: Image.Image | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Save a post-CatVTON debug image plus optional sidecar metadata."""
    if not debug_session_dir or image is None:
        return

    debug_dir = resolve_debug_session_dir(debug_session_dir)
    if debug_dir is None:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)

    image_path = debug_dir / filename
    image.save(image_path)

    if metadata is not None:
        meta_path = image_path.with_suffix(".json")
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def save_debug_stage_bytes(
    *,
    debug_session_dir: str | None,
    filename: str,
    data: bytes | bytearray | memoryview | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Save exact debug bytes plus optional sidecar metadata."""
    if not debug_session_dir or data is None:
        return

    debug_dir = resolve_debug_session_dir(debug_session_dir)
    if debug_dir is None:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)

    output_path = debug_dir / filename
    output_path.write_bytes(bytes(data))

    if metadata is not None:
        meta_path = output_path.with_suffix(".json")
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
