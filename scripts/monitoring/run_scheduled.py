#!/usr/bin/env python3
"""Run all enabled registry jobs with Gmail for a confirmed scheduled pass."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.monitoring.prepare_email_test import DEFAULT_MARKER  # noqa: E402
from scripts.monitoring.run_email_test import render_email_config  # noqa: E402
from scripts.monitoring.run_local import find_urlwatch  # noqa: E402


DEFAULT_CONFIG = PROJECT_ROOT / "config" / "urlwatch.email.yaml"
DEFAULT_URLS = PROJECT_ROOT / "generated" / "urls.yaml"
DEFAULT_DATABASE = PROJECT_ROOT / "state" / "db.sqlite"
REQUIRED_CONFIRMATION = "RUN_ENABLED_WITH_GMAIL"


def validate_scheduled_jobs(
    path: Path, expected_count: int | None = None
) -> int:
    try:
        jobs = [
            job
            for job in yaml.safe_load_all(path.read_text(encoding="utf-8"))
            if job is not None
        ]
    except (OSError, yaml.YAMLError) as error:
        raise RuntimeError(f"Failed to read scheduled jobs: {path}") from error

    if not jobs:
        raise ValueError("Scheduled monitoring requires at least one enabled job")

    if expected_count is not None and len(jobs) != expected_count:
        raise ValueError(
            f"Scheduled monitoring requires exactly {expected_count} jobs, "
            f"got {len(jobs)}"
        )

    urls: list[str] = []
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("Scheduled monitoring requires URL jobs only")
        url = job.get("url")
        if job.get("kind") != "url" or not isinstance(url, str) or not url.strip():
            raise ValueError("Scheduled monitoring requires URL jobs only")
        if str(job.get("name", "")).startswith("Gmail smoke test:"):
            raise ValueError("Gmail smoke-test jobs cannot run on the schedule")
        if DEFAULT_MARKER in str(job.get("filter", "")):
            raise ValueError("Gmail smoke-test markers cannot run on the schedule")
        urls.append(url.strip())

    if len(set(urls)) != len(urls):
        raise ValueError("Scheduled monitoring requires unique URLs")

    return len(jobs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run all enabled monitoring jobs with Gmail enabled"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--urls", type=Path, default=DEFAULT_URLS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--expected-count",
        type=int,
        help="optionally require an exact job count before monitoring",
    )
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.environ.get("SCHEDULED_MONITORING_CONFIRMATION") != REQUIRED_CONFIRMATION:
        raise SystemExit("Explicit SCHEDULED_MONITORING_CONFIRMATION is required")
    if not args.database.is_file():
        raise SystemExit(f"SQLite database does not exist: {args.database}")

    job_count = validate_scheduled_jobs(args.urls, args.expected_count)
    try:
        template = args.config.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(f"Failed to read email config template: {args.config}") from error
    rendered = render_email_config(
        template,
        os.environ.get("URLWATCH_EMAIL_USER", ""),
        os.environ.get("URLWATCH_EMAIL_PASS", ""),
    )

    print(
        "Mail reporter: enabled for confirmed scheduled monitoring of "
        f"{job_count} jobs"
    )
    if args.dry_run:
        print("Dry run: SMTP connection and monitoring were not started")
        return 0

    environment = os.environ.copy()
    for key in (
        "MAIL_USER",
        "MAIL_PASS",
        "URLWATCH_EMAIL_USER",
        "URLWATCH_EMAIL_PASS",
        "SCHEDULED_MONITORING_CONFIRMATION",
    ):
        environment.pop(key, None)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"

    with tempfile.TemporaryDirectory(prefix="monitoring-scheduled-") as directory:
        config_path = Path(directory) / "urlwatch.yaml"
        config_path.write_text(rendered, encoding="utf-8")
        config_path.chmod(0o600)
        command = [
            find_urlwatch(),
            "--config",
            str(config_path),
            "--urls",
            str(args.urls),
            "--cache",
            str(args.database),
        ]
        if args.verbose:
            command.append("--verbose")
        try:
            completed = subprocess.run(
                command,
                check=False,
                env=environment,
                timeout=args.timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"urlwatch exceeded {args.timeout} seconds") from error
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
