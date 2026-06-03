"""Evaluate garment category and color recognition accuracy.

Reads:
  data/eval/recognition/labels.csv
  data/eval/recognition/images/<image_file>

Writes:
  data/eval/recognition/results.csv
  data/eval/recognition/summary.txt

The script intentionally avoids app.services.local_inference so evaluation is
not inflated by hash/path lookup of known training images.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
PROJECT_ROOT = SCRIPT_PATH.parents[2]
DEFAULT_EVAL_DIR = PROJECT_ROOT / "data" / "eval" / "recognition"

# The app logger uses Loguru enqueue=True by default. In this desktop/sandbox
# environment, Windows multiprocessing pipes can raise WinError 5, so disable
# queued file logging for this standalone evaluation script.
os.environ.setdefault("APP_LOG_ENQUEUE", "0")
os.environ.setdefault("LOG_LEVEL", "ERROR")
os.environ["LOKY_MAX_CPU_COUNT"] = os.environ.get("LOKY_MAX_CPU_COUNT") or "4"
warnings.filterwarnings(
    "ignore",
    message="Could not find the number of physical cores.*",
    category=UserWarning,
)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


CATEGORY_ALIASES = {
    "top": "上衣",
    "tops": "上衣",
    "upper": "上衣",
    "shirt": "上衣",
    "t-shirt": "上衣",
    "tshirt": "上衣",
    "hoodie": "上衣",
    "sweater": "上衣",
    "上衣": "上衣",
    "上装": "上衣",
    "外套": "外套",
    "outer": "外套",
    "outerwear": "外套",
    "coat": "外套",
    "jacket": "外套",
    "blazer": "外套",
    "裤子": "裤子",
    "裤": "裤子",
    "下装": "裤子",
    "bottom": "裤子",
    "bottoms": "裤子",
    "lower": "裤子",
    "pants": "裤子",
    "jeans": "裤子",
    "trousers": "裤子",
    "裙子": "裙子",
    "半身裙": "裙子",
    "skirt": "裙子",
    "连衣裙": "连衣裙",
    "连衣裙子": "连衣裙",
    "dress": "连衣裙",
    "onepiece": "连衣裙",
    "one-piece": "连衣裙",
    "鞋": "鞋",
    "鞋子": "鞋",
    "shoes": "鞋",
    "shoe": "鞋",
    "sneaker": "鞋",
    "sneakers": "鞋",
    "boot": "鞋",
    "boots": "鞋",
    "包": "包",
    "包包": "包",
    "bag": "包",
    "bags": "包",
    "handbag": "包",
    "backpack": "包",
    "tote": "包",
}


COLOR_FAMILIES = {
    "黑": "黑色",
    "黑色": "黑色",
    "白": "白色",
    "白色": "白色",
    "米白": "白色",
    "米白色": "白色",
    "灰": "灰色",
    "灰色": "灰色",
    "深灰": "灰色",
    "银": "灰色",
    "银色": "灰色",
    "红": "红色",
    "红色": "红色",
    "酒红": "红色",
    "粉": "粉色",
    "粉色": "粉色",
    "灰粉": "粉色",
    "橙": "橙色",
    "橙色": "橙色",
    "橙红": "橙色",
    "黄": "黄色",
    "黄色": "黄色",
    "米": "黄色",
    "米黄": "黄色",
    "米黄色": "黄色",
    "浅金": "黄色",
    "浅金色": "黄色",
    "香槟": "黄色",
    "香槟色": "黄色",
    "卡其": "黄色",
    "金": "黄色",
    "绿": "绿色",
    "绿色": "绿色",
    "浅绿": "绿色",
    "浅绿色": "绿色",
    "青": "绿色",
    "浅青": "绿色",
    "浅青色": "绿色",
    "墨绿": "绿色",
    "蓝": "蓝色",
    "蓝色": "蓝色",
    "浅蓝": "蓝色",
    "浅蓝色": "蓝色",
    "深蓝": "蓝色",
    "深蓝色": "蓝色",
    "藏蓝": "蓝色",
    "藏蓝色": "蓝色",
    "藏青": "蓝色",
    "牛仔蓝": "蓝色",
    "雾霾蓝": "蓝色",
    "紫": "紫色",
    "紫色": "紫色",
    "浅紫": "紫色",
    "棕": "棕色",
    "棕色": "棕色",
    "驼": "棕色",
    "驼色": "棕色",
    "咖": "棕色",
    "咖啡色": "棕色",
}


@dataclass
class Prediction:
    category_raw: str
    category_normalized: str
    category_confidence: float
    color_raw: str
    color_normalized: str
    color_confidence: float
    color_rgb: str
    error: str = ""


_CATEGORY_CLASSIFIER: Any | None = None
_COLOR_EXTRACTOR: Any | None = None


def normalize_category(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if not text:
        return "未知"
    if text in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[text]
    if lowered in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[lowered]
    for key, normalized in CATEGORY_ALIASES.items():
        if key and key in lowered:
            return normalized
    return text


def normalize_true_color(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未知"
    if text in COLOR_FAMILIES:
        return COLOR_FAMILIES[text]
    for key, family in COLOR_FAMILIES.items():
        if key and key in text:
            return family
    return text


def normalize_color_from_rgb(rgb: Any, fallback_name: str = "") -> str:
    if rgb is None:
        return normalize_true_color(fallback_name)
    try:
        r, g, b = [int(x) for x in rgb]
    except Exception:
        return normalize_true_color(fallback_name)

    max_c = max(r, g, b)
    min_c = min(r, g, b)
    delta = max_c - min_c
    value = max_c / 255.0
    sat = 0.0 if max_c == 0 else delta / max_c

    if value <= 0.22:
        return "黑色"
    if sat <= 0.16:
        if value >= 0.78:
            return "白色"
        return "灰色"

    import colorsys

    hue = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)[0] * 360.0

    if 345 <= hue or hue < 12:
        return "红色"
    if 12 <= hue < 32:
        if value < 0.70 and sat < 0.70:
            return "棕色"
        return "橙色"
    if 32 <= hue < 58:
        return "黄色"
    if 58 <= hue < 160:
        return "绿色"
    if 160 <= hue < 245:
        return "蓝色"
    if 245 <= hue < 310:
        return "紫色"
    if 310 <= hue < 345:
        return "粉色"
    return normalize_true_color(fallback_name)


def rgb_to_text(rgb: Any) -> str:
    try:
        r, g, b = [int(x) for x in rgb]
        return f"{r},{g},{b}"
    except Exception:
        return ""


def recognize_image(image_bytes: bytes, use_finetuned: bool) -> Prediction:
    global _CATEGORY_CLASSIFIER, _COLOR_EXTRACTOR

    category_result: dict[str, Any] | None = None

    if use_finetuned:
        try:
            from app.services.finetuned_infer_client import try_finetuned_infer

            category_result = try_finetuned_infer(image_bytes, feature="recognition_accuracy_eval")
        except Exception:
            category_result = None

    if not category_result:
        # 优先使用 CLIP 分类器，它对服装识别更准确
        try:
            from app.ml.clip_category_classifier import CLIPCategoryClassifier

            # 每次评估都创建新实例，确保使用最新的 prompts
            if not hasattr(recognize_image, "_clip_classifier"):
                recognize_image._clip_classifier = CLIPCategoryClassifier()
            category_raw, category_confidence = recognize_image._clip_classifier.classify_category(
                image_bytes
            )
            category_raw = str(category_raw)
            category_confidence = float(category_confidence or 0.0)
            print(f"  [CLIP] category={category_raw}, confidence={category_confidence:.4f}")
        except Exception as exc:
            print(f"  [CLIP failed: {exc}]")
            # CLIP 不可用时 fallback 到 MobileNetV2
            if _CATEGORY_CLASSIFIER is None:
                from app.ml.category_classifier import CategoryClassifier

                _CATEGORY_CLASSIFIER = CategoryClassifier()
            category_raw, category_confidence = _CATEGORY_CLASSIFIER.classify_category(image_bytes)
            category_raw = str(category_raw)
            category_confidence = float(category_confidence or 0.0)
    else:
        category_raw = str(category_result.get("category") or "")
        category_confidence = float(category_result.get("category_confidence") or 0.0)

    if _COLOR_EXTRACTOR is None:
        from app.ml.color_extractor import ColorExtractor

        _COLOR_EXTRACTOR = ColorExtractor(n_colors=3)

    colors = _COLOR_EXTRACTOR.extract_colors(image_bytes)
    main_color = colors[0] if colors else None
    color_raw = str(getattr(main_color, "name", "") or "")
    color_confidence = float(getattr(main_color, "confidence", 0.0) or 0.0)
    color_rgb = getattr(main_color, "rgb", None)

    return Prediction(
        category_raw=category_raw,
        category_normalized=normalize_category(category_raw),
        category_confidence=category_confidence,
        color_raw=color_raw,
        color_normalized=normalize_true_color(color_raw),
        color_confidence=color_confidence,
        color_rgb=rgb_to_text(color_rgb),
    )


def format_pct(correct: int, total: int) -> str:
    if total <= 0:
        return "0.00%"
    return f"{correct / total * 100:.2f}%"


def build_confusion_matrix(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, Counter]]:
    labels = sorted(
        {str(row["true_category_norm"]) for row in rows}
        | {str(row["pred_category_norm"]) for row in rows}
    )
    matrix: dict[str, Counter] = {label: Counter() for label in labels}
    for row in rows:
        matrix[str(row["true_category_norm"])][str(row["pred_category_norm"])] += 1
    return labels, matrix


def render_summary(rows: list[dict[str, Any]]) -> str:
    total = len(rows)
    category_correct = sum(1 for row in rows if row["category_correct"] == "1")
    color_strict_correct = sum(1 for row in rows if row["color_strict_correct"] == "1")
    color_family_correct = sum(1 for row in rows if row["color_family_correct"] == "1")
    combined_strict_correct = sum(1 for row in rows if row["combined_strict_correct"] == "1")
    combined_family_correct = sum(1 for row in rows if row["combined_family_correct"] == "1")

    lines = [
        f"总图片数: {total}",
        f"类别准确率: {format_pct(category_correct, total)} (正确{category_correct}/{total}张)",
        (
            "颜色严格准确率: "
            f"{format_pct(color_strict_correct, total)} "
            f"(正确{color_strict_correct}/{total}张)"
        ),
        (
            "颜色色系准确率: "
            f"{format_pct(color_family_correct, total)} "
            f"(正确{color_family_correct}/{total}张)"
        ),
        (
            "综合严格准确率: "
            f"{format_pct(combined_strict_correct, total)} "
            f"(正确{combined_strict_correct}/{total}张)"
        ),
        (
            "综合色系准确率: "
            f"{format_pct(combined_family_correct, total)} "
            f"(正确{combined_family_correct}/{total}张)"
        ),
        "",
        "各类别准确率:",
    ]

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[str(row["true_category_norm"])].append(row)
    for category in sorted(by_category):
        items = by_category[category]
        correct = sum(1 for row in items if row["category_correct"] == "1")
        lines.append(
            f"  {category}: {format_pct(correct, len(items))} " f"(正确{correct}/{len(items)}张)"
        )

    labels, matrix = build_confusion_matrix(rows)
    col_width = max(8, *(len(label) + 3 for label in labels))
    lines.extend(
        [
            "",
            "混淆矩阵:",
            "".join(["真实\\预测".ljust(col_width)] + [x.ljust(col_width) for x in labels]),
        ]
    )
    for true_label in labels:
        line = [true_label.ljust(col_width)]
        for pred_label in labels:
            line.append(str(matrix[true_label][pred_label]).ljust(col_width))
        lines.append("".join(line))

    error_rows = [row for row in rows if row.get("error")]
    if error_rows:
        lines.extend(["", "失败样本:"])
        for row in error_rows:
            lines.append(f"  {row['image_file']}: {row['error']}")

    return os.linesep.join(lines) + os.linesep


def evaluate(args: argparse.Namespace) -> int:
    eval_dir = Path(args.eval_dir).resolve()
    labels_path = Path(args.labels).resolve() if args.labels else eval_dir / "labels.csv"
    images_dir = Path(args.images_dir).resolve() if args.images_dir else eval_dir / "images"
    results_path = Path(args.results).resolve() if args.results else eval_dir / "results.csv"
    summary_path = Path(args.summary).resolve() if args.summary else eval_dir / "summary.txt"

    with labels_path.open("r", encoding="utf-8-sig", newline="") as f:
        label_rows = list(csv.DictReader(f))

    output_rows: list[dict[str, Any]] = []
    for idx, label in enumerate(label_rows, start=1):
        image_file = str(label.get("image_file") or "").strip()
        true_category = str(label.get("true_category") or "").strip()
        true_color = str(label.get("true_color") or "").strip()
        notes = str(label.get("notes") or "").strip()

        true_category_norm = normalize_category(true_category)
        true_color_norm = normalize_true_color(true_color)
        image_path = images_dir / image_file

        row: dict[str, Any] = {
            "image_file": image_file,
            "true_category": true_category,
            "true_category_norm": true_category_norm,
            "pred_category": "",
            "pred_category_norm": "",
            "category_confidence": "",
            "category_correct": "0",
            "true_color": true_color,
            "true_color_norm": true_color_norm,
            "pred_color": "",
            "pred_color_norm": "",
            "pred_color_rgb": "",
            "color_confidence": "",
            "color_strict_correct": "0",
            "color_family_correct": "0",
            "combined_strict_correct": "0",
            "combined_family_correct": "0",
            "notes": notes,
            "error": "",
        }

        try:
            if not image_path.is_file():
                raise FileNotFoundError(f"image not found: {image_path}")
            prediction = recognize_image(image_path.read_bytes(), use_finetuned=args.use_finetuned)
            row.update(
                {
                    "pred_category": prediction.category_raw,
                    "pred_category_norm": prediction.category_normalized,
                    "category_confidence": f"{prediction.category_confidence:.4f}",
                    "pred_color": prediction.color_raw,
                    "pred_color_norm": prediction.color_normalized,
                    "pred_color_rgb": prediction.color_rgb,
                    "color_confidence": f"{prediction.color_confidence:.4f}",
                }
            )
            category_ok = prediction.category_normalized == true_category_norm
            color_strict_ok = prediction.color_raw == true_color
            color_family_ok = prediction.color_normalized == true_color_norm
            row["category_correct"] = "1" if category_ok else "0"
            row["color_strict_correct"] = "1" if color_strict_ok else "0"
            row["color_family_correct"] = "1" if color_family_ok else "0"
            row["combined_strict_correct"] = "1" if category_ok and color_strict_ok else "0"
            row["combined_family_correct"] = "1" if category_ok and color_family_ok else "0"
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"

        output_rows.append(row)
        if not args.quiet:
            status = "OK" if row["category_correct"] == "1" else "MISS"
            print(f"[{idx:02d}/{len(label_rows):02d}] {image_file} category={status}")

    results_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(output_rows[0].keys()) if output_rows else []
    with results_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    summary_text = render_summary(output_rows)
    summary_path.write_text(summary_text, encoding="utf-8-sig")
    print(summary_text)
    print(f"results: {results_path}")
    print(f"summary: {summary_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate recognition category/color accuracy on labeled images."
    )
    parser.add_argument("--eval-dir", default=str(DEFAULT_EVAL_DIR))
    parser.add_argument("--labels", default=None)
    parser.add_argument("--images-dir", default=None)
    parser.add_argument("--results", default=None)
    parser.add_argument("--summary", default=None)
    parser.add_argument(
        "--use-finetuned",
        action="store_true",
        help=(
            "Try external fine-tuned inference first. Disabled by default to avoid "
            "network/API availability changing the evaluation."
        ),
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(evaluate(parse_args()))
