"""Refresh stored wardrobe colors from existing garment image files.

Usage:
    python scripts/refresh_wardrobe_colors.py --dry-run
    python scripts/refresh_wardrobe_colors.py --apply
    python scripts/refresh_wardrobe_colors.py --user-id USER_ID --apply
    python scripts/refresh_wardrobe_colors.py --garment-id GARMENT_ID --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.ml.color_extractor import ColorExtractor
from app.models.garment import Garment


def _color_name(color: object) -> str:
    if isinstance(color, dict):
        return str(color.get("name") or "?")
    return "?"


def _color_names(main_color: object, secondary_colors: object) -> str:
    names = [_color_name(main_color)]
    if isinstance(secondary_colors, list):
        names.extend(_color_name(color) for color in secondary_colors)
    return "".join(name for name in names if name and name != "?") or "?"


def _model_dump(color: object) -> dict:
    if hasattr(color, "model_dump"):
        return color.model_dump()
    if hasattr(color, "dict"):
        return color.dict()
    raise TypeError(f"Unsupported color object: {type(color)!r}")


def _same_colors(old_main: object, old_secondary: object, new_colors: list[object]) -> bool:
    if not new_colors:
        return False
    old_main_name = _color_name(old_main)
    old_secondary_names = []
    if isinstance(old_secondary, list):
        old_secondary_names = [_color_name(color) for color in old_secondary]
    new_names = [_color_name(_model_dump(color)) for color in new_colors]
    return old_main_name == new_names[0] and old_secondary_names == new_names[1:]


def _read_image_bytes(image_path: str) -> bytes:
    path = Path(image_path or "")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path.read_bytes()


def _iter_garments(db, user_id: str | None, garment_id: str | None) -> Iterable[Garment]:
    query = db.query(Garment).order_by(Garment.created_at.asc())
    if user_id:
        query = query.filter(Garment.user_id == user_id)
    if garment_id:
        query = query.filter(Garment.garment_id == garment_id)
    return query.all()


def refresh_colors(*, user_id: str | None, garment_id: str | None, apply: bool) -> int:
    extractor = ColorExtractor(n_colors=3)
    db = SessionLocal()
    changed = 0
    skipped = 0
    unchanged = 0

    try:
        garments = list(_iter_garments(db, user_id, garment_id))
        mode = "APPLY" if apply else "DRY-RUN"
        print(f"{mode}: scanning {len(garments)} garment(s)")

        for garment in garments:
            old_main = garment.main_color
            old_secondary = garment.secondary_colors or []
            old_label = _color_names(old_main, old_secondary)

            try:
                image_bytes = _read_image_bytes(garment.image_path)
                colors = extractor.extract_colors(image_bytes)
            except Exception as exc:
                skipped += 1
                print(f"SKIP {garment.garment_id} {garment.category}: {exc}")
                continue

            if not colors:
                skipped += 1
                print(f"SKIP {garment.garment_id} {garment.category}: no colors extracted")
                continue

            new_main = _model_dump(colors[0])
            new_secondary = [_model_dump(color) for color in colors[1:]]
            new_label = _color_names(new_main, new_secondary)

            if _same_colors(old_main, old_secondary, colors):
                unchanged += 1
                print(f"OK   {garment.garment_id} {garment.category}: {old_label}")
                continue

            changed += 1
            print(f"CHG  {garment.garment_id} {garment.category}: {old_label} -> {new_label}")

            if apply:
                garment.main_color = new_main
                garment.secondary_colors = new_secondary
                db.add(garment)

        if apply:
            db.commit()
        else:
            db.rollback()

        print(f"Done: changed={changed}, unchanged={unchanged}, skipped={skipped}")
        return 0 if skipped == 0 else 1
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-extract main_color and secondary_colors for saved wardrobe items.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    mode.add_argument("--apply", action="store_true", help="Write refreshed colors to the DB.")
    parser.add_argument("--user-id", help="Refresh only one user's garments.")
    parser.add_argument("--garment-id", help="Refresh only one garment.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return refresh_colors(
        user_id=args.user_id,
        garment_id=args.garment_id,
        apply=bool(args.apply),
    )


if __name__ == "__main__":
    raise SystemExit(main())
