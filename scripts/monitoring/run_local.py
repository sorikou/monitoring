#!/usr/bin/env python3
"""Run urlwatch locally after proving that every mail reporter is disabled."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "urlwatch.local.yaml"
DEFAULT_URLS = PROJECT_ROOT / "generated" / "urls.yaml"
DEFAULT_DATABASE = PROJECT_ROOT / "state" / "db.sqlite"


def validate_mail_disabled(config_path: Path) -> None:
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise RuntimeError(f"Failed to read urlwatch config: {config_path}") from error

    email_enabled = ((config.get("report") or {}).get("email") or {}).get("enabled")
    legacy_email_enabled = ((config.get("reporters") or {}).get("email") or {}).get(
        "enabled"
    )
    if email_enabled is not False or legacy_email_enabled is True:
        raise ValueError("Local monitoring requires report.email.enabled: false")


def find_urlwatch() -> str:
    executable_name = "urlwatch.exe" if os.name == "nt" else "urlwatch"
    beside_python = Path(sys.executable).with_name(executable_name)
    if beside_python.exists():
        return str(beside_python)
    located = shutil.which("urlwatch")
    if located:
        return located
    raise RuntimeError("urlwatch is not installed in the active Python environment")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one mail-disabled urlwatch pass")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--urls", type=Path, default=DEFAULT_URLS)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_mail_disabled(args.config)
    if not args.urls.is_file():
        raise SystemExit(f"Generated urls file does not exist: {args.urls}")
    if not args.database.is_file():
        raise SystemExit(f"Local SQLite database does not exist: {args.database}")

    command = [
        find_urlwatch(),
        "--config",
        str(args.config),
        "--urls",
        str(args.urls),
        "--cache",
        str(args.database),
    ]
    if args.verbose:
        command.append("--verbose")
    print("Mail reporters: disabled")
    print("Running:", " ".join(command))
    if args.dry_run:
        return 0

    environment = os.environ.copy()
    for key in ("MAIL_USER", "MAIL_PASS", "URLWATCH_EMAIL_USER", "URLWATCH_EMAIL_PASS"):
        environment.pop(key, None)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
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
