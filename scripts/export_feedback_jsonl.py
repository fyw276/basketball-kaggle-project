#!/usr/bin/env python3
"""Export feedback_events rows to JSONL (stdout) for offline analysis / 数据飞轮."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(BACKEND / ".env")
    except ImportError:
        pass

    from app.db.session import SessionLocal
    from app.services.feedback_prefs import export_events_as_dicts

    db = SessionLocal()
    try:
        rows = export_events_as_dicts(db, user_id=None, limit=100_000)
    finally:
        db.close()

    for row in rows:
        sys.stdout.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
