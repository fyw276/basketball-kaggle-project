from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image


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

    debug_dir = Path(debug_session_dir)
    debug_dir.mkdir(parents=True, exist_ok=True)

    image_path = debug_dir / filename
    image.save(image_path)

    if metadata is not None:
        meta_path = image_path.with_suffix(".json")
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
