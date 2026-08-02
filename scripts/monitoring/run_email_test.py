#!/usr/bin/env python3
"""Run exactly one explicitly confirmed Gmail notification test."""

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
from scripts.monitoring.run_local import find_urlwatch  # noqa: E402


DEFAULT_CONFIG = PROJECT_ROOT / "config" / "urlwatch.email-test.yaml"
DEFAULT_URLS = PROJECT_ROOT / "generated" / "email-test.yaml"
DEFAULT_DATABASE = PROJECT_ROOT / "state" / "db.sqlite"
REQUIRED_CONFIRMATION = "SEND_ONE_GMAIL_TEST"


def render_email_config(template: str, user: str, password: str) -> str:
    user = user.strip()
    if not user or "@" not in user or "\n" in user or "\r" in user:
        raise ValueError("MAIL_USER must be one valid-looking email address")
    if not password or "\n" in password or "\r" in password:
        raise ValueError("MAIL_PASS must be one non-empty line")

    rendered = template.replace("${URLWATCH_EMAIL_USER}", user).replace(
        "${URLWATCH_EMAIL_PASS}", password
    )
    if "${URLWATCH_EMAIL_" in rendered:
        raise ValueError("Email config still contains unresolved placeholders")

    config = yaml.safe_load(rendered) or {}
    email = ((config.get("report") or {}).get("email") or {})
    smtp = email.get("smtp") or {}
    if email.get("enabled") is not True or email.get("method") != "smtp":
        raise ValueError("Email test config must enable the SMTP email reporter")
    if smtp.get("host") != "smtp.gmail.com" or smtp.get("auth") is not True:
        raise ValueError("Email test config must use authenticated Gmail SMTP")
    return rendered


def validate_single_test_job(path: Path, marker: str = DEFAULT_MARKER) -> None:
    try:
        jobs = [
            job
            for job in yaml.safe_load_all(path.read_text(encoding="utf-8"))
            if job is not None
        ]
    except (OSError, yaml.YAMLError) as error:
        raise RuntimeError(f"Failed to read email test jobs: {path}") from error

    if len(jobs) != 1:
        raise ValueError(f"Email test requires exactly one job, got {len(jobs)}")
    expected_filter = [
        {"re.sub": {"pattern": r"\A[\s\S]*\Z", "repl": marker}}
    ]
    job = jobs[0]
    if job.get("kind") != "url" or not job.get("url"):
        raise ValueError("Email test requires exactly one URL job")
    if job.get("filter") != expected_filter:
        raise ValueError("Email test job does not use the approved deterministic marker")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one confirmed Gmail smoke test")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--urls", type=Path, default=DEFAULT_URLS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if os.environ.get("EMAIL_TEST_CONFIRMATION") != REQUIRED_CONFIRMATION:
        raise SystemExit("Explicit EMAIL_TEST_CONFIRMATION is required")
    if not args.database.is_file():
        raise SystemExit(f"SQLite database does not exist: {args.database}")

    validate_single_test_job(args.urls)
    try:
        template = args.config.read_text(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(f"Failed to read email config template: {args.config}") from error
    rendered = render_email_config(
        template,
        os.environ.get("URLWATCH_EMAIL_USER", ""),
        os.environ.get("URLWATCH_EMAIL_PASS", ""),
    )

    print("Mail reporter: enabled for exactly one confirmed Gmail test job")
    if args.dry_run:
        print("Dry run: SMTP connection and monitoring were not started")
        return 0

    environment = os.environ.copy()
    for key in (
        "MAIL_USER",
        "MAIL_PASS",
        "URLWATCH_EMAIL_USER",
        "URLWATCH_EMAIL_PASS",
        "EMAIL_TEST_CONFIRMATION",
    ):
        environment.pop(key, None)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"

    with tempfile.TemporaryDirectory(prefix="monitoring-email-test-") as directory:
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
