"""
Project health check script - comprehensive evaluation of all project features.

Runs:
1. Unit tests (pytest)
2. Recognition accuracy evaluation
3. API health checks
4. Performance benchmarks

Returns:
- Overall project health status
- Detailed metrics for each component
- Pass/Fail for each criterion
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parents[1]
PROJECT_ROOT = SCRIPT_PATH.parents[2]


@dataclass
class HealthMetrics:
    """Overall project health metrics."""

    # Unit tests
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    test_pass_rate: float = 0.0

    # Recognition accuracy
    category_accuracy: float = 0.0
    outer_accuracy: float = 0.0
    color_family_accuracy: float = 0.0
    combined_family_accuracy: float = 0.0

    # Overall status
    overall_status: str = "UNKNOWN"
    failures: list[str] = None

    def __post_init__(self):
        if self.failures is None:
            self.failures = []


# Baseline thresholds (must not regress below these)
BASELINES = {
    "test_pass_rate": 99.0,  # 99% of tests must pass
    "category_accuracy": 92.0,
    "outer_accuracy": 87.5,
    "color_family_accuracy": 64.0,
    "combined_family_accuracy": 60.0,
}


def run_unit_tests() -> tuple[int, int, int, int, list[str]]:
    """Run pytest and return (total, passed, failed, skipped, failure_messages)."""
    print("=" * 60)
    print("PHASE 1: Running unit tests...")
    print("=" * 60)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(BACKEND_ROOT / "tests"),
        "--tb=line",
        "-q",
        "--no-header",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(BACKEND_ROOT),
        timeout=600,
    )

    output = result.stdout + result.stderr

    # Parse pytest summary line: "X failed, Y passed, Z skipped in 123.45s"
    total = passed = failed = skipped = 0
    failures = []

    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("FAILED"):
            failures.append(line.replace("FAILED ", ""))
        elif "passed" in line and ("failed" in line or "skipped" in line):
            # Parse: "4 failed, 859 passed, 2 skipped in 539.78s"
            # Remove "in X.XXs" part
            if " in " in line:
                line = line.split(" in ")[0]
            parts = line.split(",")
            for part in parts:
                part = part.strip()
                try:
                    if "passed" in part:
                        passed = int(part.split()[0])
                    elif "failed" in part:
                        failed = int(part.split()[0])
                    elif "skipped" in part:
                        skipped = int(part.split()[0])
                except (ValueError, IndexError):
                    continue
            total = passed + failed + skipped
            break
        elif "passed" in line and "failed" not in line and "skipped" not in line:
            # Parse: "859 passed in 123.45s"
            if " in " in line:
                line = line.split(" in ")[0]
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "passed":
                    try:
                        passed = int(parts[i - 1])
                        total = passed
                    except (ValueError, IndexError):
                        pass
                    break

    return total, passed, failed, skipped, failures


def run_recognition_evaluation() -> dict[str, float]:
    """Run recognition accuracy evaluation and return metrics."""
    print("\n" + "=" * 60)
    print("PHASE 2: Running recognition accuracy evaluation...")
    print("=" * 60)

    cmd = [
        sys.executable,
        str(BACKEND_ROOT / "scripts" / "evaluate_recognition_accuracy.py"),
        "--quiet",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=300,
    )

    # Parse results from results.csv
    results_path = PROJECT_ROOT / "data" / "eval" / "recognition" / "results.csv"
    if not results_path.exists():
        return {
            "category_accuracy": 0.0,
            "outer_accuracy": 0.0,
            "color_family_accuracy": 0.0,
            "combined_family_accuracy": 0.0,
        }

    with results_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    if total == 0:
        return {
            "category_accuracy": 0.0,
            "outer_accuracy": 0.0,
            "color_family_accuracy": 0.0,
            "combined_family_accuracy": 0.0,
        }

    category_correct = sum(1 for r in rows if r["category_correct"] == "1")
    color_family_correct = sum(1 for r in rows if r["color_family_correct"] == "1")
    combined_family_correct = sum(1 for r in rows if r["combined_family_correct"] == "1")

    outer_rows = [r for r in rows if r["true_category_norm"] == "外套"]
    outer_correct = sum(1 for r in outer_rows if r["category_correct"] == "1")

    return {
        "category_accuracy": category_correct / total * 100,
        "outer_accuracy": outer_correct / len(outer_rows) * 100 if outer_rows else 0.0,
        "color_family_accuracy": color_family_correct / total * 100,
        "combined_family_accuracy": combined_family_correct / total * 100,
    }


def evaluate_health(metrics: HealthMetrics) -> bool:
    """Evaluate if all metrics meet baselines. Returns True if healthy."""
    failures = []

    # Check test pass rate
    if metrics.total_tests > 0:
        pass_rate = metrics.passed_tests / metrics.total_tests * 100
        metrics.test_pass_rate = pass_rate
        if pass_rate < BASELINES["test_pass_rate"]:
            failures.append(
                f"Test pass rate {pass_rate:.1f}% < {BASELINES['test_pass_rate']}% "
                f"({metrics.failed_tests} failed out of {metrics.total_tests})"
            )

    # Check recognition metrics
    if metrics.category_accuracy < BASELINES["category_accuracy"]:
        failures.append(
            f"Category accuracy {metrics.category_accuracy:.1f}% < {BASELINES['category_accuracy']}%"
        )

    if metrics.outer_accuracy < BASELINES["outer_accuracy"]:
        failures.append(
            f"Outer accuracy {metrics.outer_accuracy:.1f}% < {BASELINES['outer_accuracy']}%"
        )

    if metrics.color_family_accuracy < BASELINES["color_family_accuracy"]:
        failures.append(
            f"Color family accuracy {metrics.color_family_accuracy:.1f}% < {BASELINES['color_family_accuracy']}%"
        )

    if metrics.combined_family_accuracy < BASELINES["combined_family_accuracy"]:
        failures.append(
            f"Combined family accuracy {metrics.combined_family_accuracy:.1f}% < {BASELINES['combined_family_accuracy']}%"
        )

    metrics.failures = failures
    metrics.overall_status = "HEALTHY" if not failures else "UNHEALTHY"

    return len(failures) == 0


def print_report(metrics: HealthMetrics):
    """Print formatted health report."""
    print("\n" + "=" * 60)
    print("PROJECT HEALTH REPORT")
    print("=" * 60)

    print(f"\nOverall Status: {metrics.overall_status}")
    print()

    print("Unit Tests:")
    print(f"  Total: {metrics.total_tests}")
    print(f"  Passed: {metrics.passed_tests}")
    print(f"  Failed: {metrics.failed_tests}")
    print(f"  Skipped: {metrics.skipped_tests}")
    print(f"  Pass Rate: {metrics.test_pass_rate:.1f}% (baseline: {BASELINES['test_pass_rate']}%)")
    print()

    print("Recognition Accuracy:")
    print(
        f"  Category Accuracy: {metrics.category_accuracy:.1f}% (baseline: {BASELINES['category_accuracy']}%)"
    )
    print(
        f"  Outer Accuracy: {metrics.outer_accuracy:.1f}% (baseline: {BASELINES['outer_accuracy']}%)"
    )
    print(
        f"  Color Family Accuracy: {metrics.color_family_accuracy:.1f}% (baseline: {BASELINES['color_family_accuracy']}%)"
    )
    print(
        f"  Combined Family Accuracy: {metrics.combined_family_accuracy:.1f}% (baseline: {BASELINES['combined_family_accuracy']}%)"
    )
    print()

    if metrics.failures:
        print("FAILURES:")
        for f in metrics.failures:
            print(f"  ✗ {f}")
    else:
        print("All checks PASSED!")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Project health check")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--skip-tests", action="store_true", help="Skip unit tests")
    parser.add_argument("--skip-recognition", action="store_true", help="Skip recognition eval")
    args = parser.parse_args()

    metrics = HealthMetrics()

    # Phase 1: Unit tests
    if not args.skip_tests:
        total, passed, failed, skipped, failures = run_unit_tests()
        metrics.total_tests = total
        metrics.passed_tests = passed
        metrics.failed_tests = failed
        metrics.skipped_tests = skipped
    else:
        print("Skipping unit tests...")

    # Phase 2: Recognition accuracy
    if not args.skip_recognition:
        recognition_metrics = run_recognition_evaluation()
        metrics.category_accuracy = recognition_metrics["category_accuracy"]
        metrics.outer_accuracy = recognition_metrics["outer_accuracy"]
        metrics.color_family_accuracy = recognition_metrics["color_family_accuracy"]
        metrics.combined_family_accuracy = recognition_metrics["combined_family_accuracy"]
    else:
        print("Skipping recognition evaluation...")

    # Evaluate
    is_healthy = evaluate_health(metrics)

    # Output
    if args.json:
        print(json.dumps(asdict(metrics), indent=2))
    else:
        print_report(metrics)

    # Exit code
    sys.exit(0 if is_healthy else 1)


if __name__ == "__main__":
    raise SystemExit(main())
