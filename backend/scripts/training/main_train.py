"""
Unified training entry point - manages all training tasks

Usage:
    python scripts/training/main_train.py --task <task_name> [options]

Available tasks:
    - reextract: Re-extract feature vectors (fix zero vector issues)
    - analyze: Analyze data quality
    - export: Export training data
    - finetune: Fine-tune CLIP model
    - category: Train category classifier
    - style: Train style classifier
    - full: Run full training pipeline
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import torch

# Fix Windows console encoding
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.logging import setup_logging
from scripts.training.data_preprocessor import DataPreprocessor
from scripts.training.trainer_registry import TrainerRegistry, list_available_training_tasks

logger = setup_logging()


def check_gpu() -> dict:
    """Check GPU availability"""
    info = {
        "cuda_available": torch.cuda.is_available(),
        "device": "CPU",
        "device_count": 0,
        "devices": [],
    }

    if torch.cuda.is_available():
        info["device"] = torch.cuda.get_device_name(0)
        info["device_count"] = torch.cuda.device_count()
        for i in range(torch.cuda.device_count()):
            info["devices"].append(
                {
                    "id": i,
                    "name": torch.cuda.get_device_name(i),
                    "memory_total": torch.cuda.get_device_properties(i).total_memory,
                }
            )
        logger.info(f"GPU available: {info['device']}")
    else:
        logger.warning("No GPU available, will use CPU")

    return info


def task_reextract_features():
    """Re-extract feature vectors"""
    logger.info("Starting feature reextraction task")
    preprocessor = DataPreprocessor()

    # First analyze data
    report = preprocessor.analyze_data_quality()
    print(f"\nData Quality Report:")
    print(f"  Total samples: {report['total']}")
    print(f"  Valid features: {report['valid_features']}")
    print(f"  Zero features: {report['zero_features']}")
    print(f"  Images found: {report['images_found']}")
    print(f"  Images missing: {report['images_missing']}")

    if report["zero_features"] == 0:
        print("\nAll feature vectors are valid. No re-extraction needed.")
        return

    print(f"\nStarting re-extraction for {report['zero_features']} zero feature vectors...")
    result = preprocessor.reextract_all_features()

    print(f"\nExtraction complete:")
    print(f"  Success: {result['success']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Skipped: {result['skipped']}")


def task_analyze_data():
    """Analyze data quality"""
    logger.info("Starting data analysis task")
    preprocessor = DataPreprocessor()
    report = preprocessor.analyze_data_quality()

    print("\n=== Data Quality Report ===")
    print(f"\n[Stats] Overall Statistics:")
    print(f"  Total samples: {report['total']}")
    print(f"  Valid features: {report['valid_features']}")
    print(f"  Zero features: {report['zero_features']}")
    print(f"  Images found: {report['images_found']}")
    print(f"  Images missing: {report['images_missing']}")
    print(f"  No category label: {report['invalid_categories']}")

    print(f"\n[Category] Category Distribution:")
    for cat, count in sorted(report["valid_categories"].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    print(f"\n[Style] Style Distribution:")
    for style, count in sorted(report["valid_styles"].items(), key=lambda x: -x[1])[:10]:
        print(f"  {style}: {count}")
    if len(report["valid_styles"]) > 10:
        print(f"  ... and {len(report['valid_styles']) - 10} more styles")


def task_export_data(output_path: str = "./training_data.json"):
    """Export training data"""
    logger.info(f"Starting data export to {output_path}")
    preprocessor = DataPreprocessor()

    # Only export data with valid features
    garments = preprocessor.get_all_garments()
    project_root = Path(__file__).parent.parent.parent

    training_data = []
    for g in garments:
        img_path = g.get("image_path", "")
        if not img_path:
            continue

        full_path = project_root / img_path.replace("\\", "/")
        if not full_path.exists():
            continue

        if not g.get("category"):
            continue

        if not any(g["feature_vector"] != 0):
            continue

        entry = {
            "image_path": str(full_path),
            "category": g["category"],
            "style_tags": g.get("style_tags", []),
            "fit_type": g.get("fit_type"),
            "main_color": g.get("main_color", {}).get("name"),
            "gender_label": g.get("gender_label"),
        }
        training_data.append(entry)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(training_data, f, ensure_ascii=False, indent=2)

    print(f"\nExported {len(training_data)} training samples to: {output_path}")

    # Statistics
    categories = {}
    for item in training_data:
        cat = item["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print("\nCategory Distribution:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")


def task_finetune_clip(data_path: str, epochs: int = 10, batch_size: int = 8):
    """Fine-tune CLIP model"""
    logger.info("Starting CLIP fine-tuning task")

    from scripts.training.clip_finetuner import CLIPFineTuner, TrainingConfig

    # Check data
    if not Path(data_path).exists():
        print(f"Error: Training data file not found: {data_path}")
        print("Please run export task first: python scripts/training/main_train.py --task export")
        return

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if len(data) < 5:
        print(
            f"Warning: Training data is limited ({len(data)} samples). Recommend at least 50 for better results."
        )

    print(f"\nStarting CLIP fine-tuning")
    print(f"  Training data: {len(data)} samples")
    print(f"  Epochs: {epochs}")
    print(f"  Batch size: {batch_size}")
    print(f"  Device: {'GPU' if torch.cuda.is_available() else 'CPU'}")

    config = TrainingConfig(
        num_epochs=epochs,
        batch_size=batch_size,
    )

    trainer = CLIPFineTuner(config=config)
    trainer.train(train_data_path=data_path)

    print("\nTraining complete! Model saved to: models/clip_finetuned/")


def task_train_category():
    """Train category classifier"""
    logger.info("Starting category classifier training")
    print("\nCategory classifier training - in development...")
    print("Requires feature re-extraction and CLIP fine-tuning first.")


def task_train_style():
    """Train style classifier"""
    logger.info("Starting style classifier training")
    print("\nStyle classifier training - in development...")
    print("Requires feature re-extraction and CLIP fine-tuning first.")


def task_full_pipeline(data_path: Optional[str] = None):
    """Full training pipeline"""
    logger.info("Starting full training pipeline")

    print("\n" + "=" * 50)
    print("[CLOTHING] Outfit Recognition Model Full Training")
    print("=" * 50)

    start_time = time.time()

    # Step 1: Analyze data
    print("\n[Step 1/4] Analyzing data quality...")
    task_analyze_data()

    # Step 2: Re-extract features
    print("\n[Step 2/4] Re-extracting feature vectors...")
    task_reextract_features()

    # Step 3: Export training data
    print("\n[Step 3/4] Exporting training data...")
    if data_path is None:
        data_path = str(project_root / "training_data.json")
    task_export_data(data_path)

    # Step 4: Fine-tune CLIP
    print("\n[Step 4/4] Fine-tuning CLIP model...")
    task_finetune_clip(data_path)

    elapsed = time.time() - start_time
    print("\n" + "=" * 50)
    print(f"[OK] Training pipeline completed! Time: {elapsed:.1f}s")
    print("=" * 50)


def main():
    """Main entry"""
    parser = argparse.ArgumentParser(
        description="Outfit Recognition Model Training Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available tasks:
  reextract    Re-extract feature vectors (fix zero vectors)
  analyze      Analyze data quality
  export       Export training data
  finetune     Fine-tune CLIP model
  category     Train category classifier
  style        Train style classifier
  full         Run full training pipeline
  list         List all available tasks

Examples:
  python scripts/training/main_train.py --task analyze
  python scripts/training/main_train.py --task export --output training_data.json
  python scripts/training/main_train.py --task reextract
  python scripts/training/main_train.py --task full
        """,
    )

    parser.add_argument(
        "--task",
        choices=["reextract", "analyze", "export", "finetune", "category", "style", "full", "list"],
        default="list",
        help="Task to execute",
    )
    parser.add_argument("--data", default="./training_data.json", help="Training data path")
    parser.add_argument("--output", default="./training_data.json", help="Output path")
    parser.add_argument("--epochs", type=int, default=10, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size")

    args = parser.parse_args()

    # Show GPU info
    gpu_info = check_gpu()
    print(f"\n[GPU] Status: {gpu_info['device'] if gpu_info['cuda_available'] else 'CPU'}")

    if args.task == "list":
        # List all tasks
        info = list_available_training_tasks()
        print("\n=== Available Training Tasks ===\n")
        for task in info["tasks"]:
            print(f"[*] {task['id']}: {task['name']}")
            print(f"    {task['description']}")
            print(f"    Command: {task['command']}\n")
    elif args.task == "reextract":
        task_reextract_features()
    elif args.task == "analyze":
        task_analyze_data()
    elif args.task == "export":
        task_export_data(args.output)
    elif args.task == "finetune":
        task_finetune_clip(args.data, args.epochs, args.batch_size)
    elif args.task == "category":
        task_train_category()
    elif args.task == "style":
        task_train_style()
    elif args.task == "full":
        task_full_pipeline(args.data)


if __name__ == "__main__":
    main()
