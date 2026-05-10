#!/usr/bin/env python3
"""
Generate reports from evaluation results.

Usage:
    python scripts/generate_report.py --evaluation-id <run_id> --format markdown --output-dir reports/
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation import BenchmarkReporter
from shared.logging import get_logger

logger = get_logger("eval_cli.generate_report")


def load_summary(summary_file: Path) -> dict:
    """Load summary from JSON file."""
    if not summary_file.exists():
        logger.error(f"Summary file not found: {summary_file}")
        sys.exit(1)

    with open(summary_file) as f:
        return json.load(f)


def load_failures(failures_file: Path) -> list:
    """Load failures from JSON file."""
    if not failures_file.exists():
        logger.warning(f"Failures file not found: {failures_file}")
        return []

    with open(failures_file) as f:
        return json.load(f)


def generate_json_report(reporter: BenchmarkReporter, summary: dict) -> str:
    """Generate JSON report."""
    return reporter.generate_json_report(summary)


def generate_markdown_report(reporter: BenchmarkReporter, summary: dict) -> str:
    """Generate markdown report."""
    return reporter.generate_markdown_report(summary)


def generate_failure_report(
    reporter: BenchmarkReporter, failures: list, summary: dict
) -> str:
    """Generate failure report."""
    return reporter.generate_failure_report(failures, summary)


def generate_weak_areas_report(reporter: BenchmarkReporter, summary: dict) -> str:
    """Generate weak areas report."""
    return reporter.generate_weak_areas_report(summary)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate reports from evaluation results")
    parser.add_argument(
        "--evaluation-id",
        required=True,
        help="Evaluation run ID",
    )
    parser.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "json"],
        help="Report format",
    )
    parser.add_argument(
        "--report-type",
        choices=["summary", "failures", "weak-areas", "all"],
        default="all",
        help="Report type to generate",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory containing evaluation results",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Output directory for reports",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    # Build paths
    eval_dir = args.results_dir / args.evaluation_id
    summary_file = eval_dir / "summary.json"
    failures_file = eval_dir / "failures.json"

    if not eval_dir.exists():
        logger.error(f"Evaluation directory not found: {eval_dir}")
        sys.exit(1)

    # Load data
    summary = load_summary(summary_file)
    failures = load_failures(failures_file)

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Generate reports
    reporter = BenchmarkReporter()

    if args.report_type in ["summary", "all"]:
        if args.format == "markdown":
            report = generate_markdown_report(reporter, summary)
            output_file = args.output_dir / f"{args.evaluation_id}_summary.md"
        else:
            report = generate_json_report(reporter, summary)
            output_file = args.output_dir / f"{args.evaluation_id}_summary.json"

        with open(output_file, "w") as f:
            f.write(report)
        logger.info(f"Summary report saved to {output_file}")

    if args.report_type in ["failures", "all"]:
        report = generate_failure_report(reporter, failures, summary)
        output_file = args.output_dir / f"{args.evaluation_id}_failures.md"
        with open(output_file, "w") as f:
            f.write(report)
        logger.info(f"Failure report saved to {output_file}")

    if args.report_type in ["weak-areas", "all"]:
        report = generate_weak_areas_report(reporter, summary)
        output_file = args.output_dir / f"{args.evaluation_id}_weak_areas.md"
        with open(output_file, "w") as f:
            f.write(report)
        logger.info(f"Weak areas report saved to {output_file}")


if __name__ == "__main__":
    main()
