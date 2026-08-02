#!/usr/bin/env python3
"""Generate urlwatch jobs from a validated registry and preset configuration."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.registry.fetch_registry import (  # noqa: E402
    DEFAULT_PRESETS,
    RegistryEntry,
    load_registry,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "generated" / "urls.yaml"


def build_urlwatch_jobs(
    entries: list[RegistryEntry], presets: dict[str, dict]
) -> list[dict]:
    jobs: list[dict] = []
    for entry in entries:
        jobs.append(
            {
                "kind": "url",
                "name": entry.name or entry.url,
                "url": entry.url,
                "filter": presets[entry.preset]["filter"],
            }
        )
    return jobs


def write_jobs(path: Path, jobs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump_all(
        jobs,
        allow_unicode=True,
        explicit_start=True,
        sort_keys=False,
        width=4096,
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate urlwatch YAML from registry")
    parser.add_argument("--endpoint", default=os.environ.get("REGISTRY_ENDPOINT"))
    parser.add_argument("--presets", type=Path, default=DEFAULT_PRESETS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--include-id",
        action="append",
        default=[],
        help="only include this registry id; may be repeated",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.endpoint:
        raise SystemExit("REGISTRY_ENDPOINT or --endpoint is required")
    entries, presets = load_registry(args.endpoint, args.presets, args.timeout)

    if args.include_id:
        requested = set(args.include_id)
        entries = [entry for entry in entries if entry.id in requested]
        missing = requested - {entry.id for entry in entries}
        if missing:
            raise SystemExit(f"Unknown or disabled registry ids: {', '.join(sorted(missing))}")

    jobs = build_urlwatch_jobs(entries, presets)
    if not jobs:
        raise SystemExit("No jobs selected; generated file was not changed")
    write_jobs(args.output, jobs)
    print(f"Generated {len(jobs)} urlwatch jobs: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
