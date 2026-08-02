#!/usr/bin/env python3
"""Replace one generated URL job's filters with a deterministic test marker."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


DEFAULT_MARKER = "monitoring-gmail-smoke-v1"


def build_email_test_job(jobs: list[dict], marker: str) -> dict:
    if len(jobs) != 1:
        raise ValueError(f"Email test requires exactly one job, got {len(jobs)}")
    if not marker or "\n" in marker or "\r" in marker:
        raise ValueError("Email test marker must be one non-empty line")

    job = dict(jobs[0])
    if job.get("kind") != "url" or not job.get("url"):
        raise ValueError("Email test requires one URL job")

    original_name = str(job.get("name") or job["url"])
    job["name"] = f"Gmail smoke test: {original_name}"
    job["filter"] = [
        {
            "re.sub": {
                "pattern": r"\A[\s\S]*\Z",
                "repl": marker,
            }
        }
    ]
    return job


def read_jobs(path: Path) -> list[dict]:
    try:
        jobs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError) as error:
        raise RuntimeError(f"Failed to read generated jobs: {path}") from error
    return [job for job in jobs if job is not None]


def write_job(path: Path, job: dict) -> None:
    content = yaml.safe_dump_all(
        [job],
        allow_unicode=True,
        explicit_start=True,
        sort_keys=False,
        width=4096,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare one deterministic Gmail test job")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--marker", default=DEFAULT_MARKER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    job = build_email_test_job(read_jobs(args.input), args.marker)
    write_job(args.output, job)
    print(f"Prepared exactly one deterministic email test job: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
