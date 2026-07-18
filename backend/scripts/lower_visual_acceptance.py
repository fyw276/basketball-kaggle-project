"""Lower-body try-on visual acceptance runner (preprocess_only then optional full).

Usage (from backend/):
  python scripts/lower_visual_acceptance.py --preprocess-only
  python scripts/lower_visual_acceptance.py --full --mode hybrid
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("HF_HOME", r"D:\hf-cache")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

PERSON_PATH = BACKEND_ROOT / "scripts" / "test_person.jpg"
EVAL_DIR = REPO_ROOT / "data" / "eval" / "recognition" / "images"

CASES = [
    {"name": "denim", "garment": EVAL_DIR / "item_037.jpg", "label": "牛仔裤"},
    {"name": "black", "garment": EVAL_DIR / "item_032.jpg", "label": "黑裤"},
    {"name": "light", "garment": EVAL_DIR / "item_034.jpg", "label": "浅色裤"},
    {"name": "gray_shorts", "garment": EVAL_DIR / "item_029.jpg", "label": "短裤"},
    {"name": "blue", "garment": EVAL_DIR / "item_035.jpg", "label": "蓝裤"},
]


def _json_default(obj):
    """Serialize numpy scalars that slip into mask QC / metadata."""
    if hasattr(obj, "item"):
        return obj.item()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _to_jpeg_bytes(img: Image.Image, quality: int = 95) -> bytes:
    import io

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _analyze_mask(mask_path: Path, person_path: Path | None = None) -> dict:
    """Heuristic QC for lower-body mask coverage."""
    import numpy as np

    mask = np.asarray(Image.open(mask_path).convert("L"))
    h, w = mask.shape
    binary = mask > 127
    coverage = float(binary.mean())
    ys, xs = np.where(binary)
    if xs.size == 0:
        return {
            "ok": False,
            "reason": "empty_mask",
            "coverage": 0.0,
        }

    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    top_band = binary[: int(h * 0.18)].mean()
    mid_band = binary[int(h * 0.35) : int(h * 0.75)].mean()
    bottom_band = binary[int(h * 0.85) :].mean()
    face_band = binary[: int(h * 0.12), int(w * 0.25) : int(w * 0.75)].mean()

    # SCHP masks are tighter than polygon fallbacks; allow slightly lower coverage.
    ok = (
        coverage >= 0.06
        and coverage <= 0.55
        and y0 <= int(h * 0.55)
        and y1 >= int(h * 0.85)
        and face_band < 0.05
        and mid_band > 0.08
    )
    reasons = []
    if coverage < 0.06:
        reasons.append("coverage_too_low")
    if coverage > 0.55:
        reasons.append("coverage_too_high")
    if y0 > int(h * 0.55):
        reasons.append("waist_too_low")
    if y1 < int(h * 0.85):
        reasons.append("ankles_not_covered")
    if face_band >= 0.05:
        reasons.append("face_leaking")
    if mid_band <= 0.08:
        reasons.append("legs_sparse")

    return {
        "ok": bool(ok),
        "coverage": round(float(coverage), 4),
        "bbox": [int(x0), int(y0), int(x1), int(y1)],
        "bbox_y_ratio": [round(float(y0) / h, 3), round(float(y1) / h, 3)],
        "top_band": round(float(top_band), 4),
        "mid_band": round(float(mid_band), 4),
        "bottom_band": round(float(bottom_band), 4),
        "face_band": round(float(face_band), 4),
        "reasons": reasons,
    }


async def run_case(
    *,
    case: dict,
    person_img: Image.Image,
    out_root: Path,
    preprocess_only: bool,
    mode: str,
) -> dict:
    from app.services.tryon_v2.category_utils import map_to_catvton_cloth_type
    from app.services.tryon_v2.catvton_engine_client import call_local_catvton

    garment_path: Path = case["garment"]
    if not garment_path.is_file():
        return {"name": case["name"], "status": "missing_garment", "path": str(garment_path)}

    garment_img = Image.open(garment_path).convert("RGB")
    cloth_type = map_to_catvton_cloth_type(case["label"])
    case_dir = out_root / case["name"]
    case_dir.mkdir(parents=True, exist_ok=True)
    person_img.save(case_dir / "00_person.jpg", quality=95)
    garment_img.save(case_dir / "00_garment.jpg", quality=95)

    print(f"\n=== {case['name']} ({case['label']}) -> cloth_type={cloth_type} ===")
    result = await call_local_catvton(
        garment_bytes=_to_jpeg_bytes(garment_img),
        person_bytes=_to_jpeg_bytes(person_img),
        garment_category=cloth_type,
        preprocess_only=preprocess_only,
        debug_dir=str(case_dir),
    )

    meta = result.get("metadata") or {}
    debug_session_dir = meta.get("debug_session_dir") or str(case_dir)
    summary = {
        "name": case["name"],
        "label": case["label"],
        "cloth_type": cloth_type,
        "status": result.get("status"),
        "message": result.get("message"),
        "debug_session_dir": debug_session_dir,
        "mode": mode if not preprocess_only else "preprocess_only",
        "mask_qc": None,
    }

    # Find mask artifacts under debug_session_dir or case_dir
    search_roots = [Path(debug_session_dir), case_dir]
    mask_path = None
    for root in search_roots:
        preferred = [
            root / "03_mask.png",
            *sorted(root.glob("**/03_mask.png")),
        ]
        for candidate in preferred:
            if candidate.is_file():
                mask_path = candidate
                break
        if mask_path:
            break

    if mask_path and mask_path.is_file():
        summary["mask_path"] = str(mask_path)
        summary["mask_qc"] = _analyze_mask(mask_path)
        print(f"  mask_qc: {summary['mask_qc']}")
    else:
        print("  WARN: 03_mask.png not found")

    # Save result image if full run
    result_img = result.get("result_image")
    if result_img is not None:
        out_img = case_dir / f"result_{mode}.jpg"
        if isinstance(result_img, Image.Image):
            result_img.convert("RGB").save(out_img, quality=95)
        summary["result_image"] = str(out_img)

    (case_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return summary


async def main_async(args: argparse.Namespace) -> int:
    if not PERSON_PATH.is_file():
        print(f"ERROR: person image missing: {PERSON_PATH}")
        return 2

    person_img = Image.open(PERSON_PATH).convert("RGB")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = REPO_ROOT / "debug_output" / f"lower_accept_{ts}"
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"Output root: {out_root}")
    print(f"Person: {PERSON_PATH} size={person_img.size}")
    print(f"preprocess_only={args.preprocess_only} mode={args.mode}")

    selected = CASES
    if args.only:
        names = {x.strip() for x in args.only.split(",") if x.strip()}
        selected = [c for c in CASES if c["name"] in names]

    summaries = []
    for case in selected:
        try:
            summaries.append(
                await run_case(
                    case=case,
                    person_img=person_img,
                    out_root=out_root,
                    preprocess_only=args.preprocess_only,
                    mode=args.mode,
                )
            )
        except Exception as exc:
            print(f"  FAILED {case['name']}: {exc}")
            summaries.append({"name": case["name"], "status": "exception", "error": str(exc)})

    report = {
        "output_root": str(out_root),
        "preprocess_only": args.preprocess_only,
        "mode": args.mode,
        "cases": summaries,
    }
    report_path = out_root / "acceptance_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(f"\nReport: {report_path}")

    ok_masks = sum(1 for s in summaries if (s.get("mask_qc") or {}).get("ok"))
    print(f"Mask QC pass: {ok_masks}/{len(summaries)}")
    return 0 if ok_masks == len(summaries) else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preprocess-only", action="store_true", default=False)
    parser.add_argument("--full", action="store_true", default=False)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "detail_fidelity"])
    parser.add_argument("--only", default="", help="comma-separated case names")
    args = parser.parse_args()
    if not args.full:
        args.preprocess_only = True
    else:
        args.preprocess_only = False
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
