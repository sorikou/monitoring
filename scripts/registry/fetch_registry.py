#!/usr/bin/env python3
"""Fetch and validate the monitoring registry from CSV or Google Sheets."""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRESETS = PROJECT_ROOT / "config" / "site-presets.yaml"
REQUIRED_COLUMNS = {
    "id",
    "enabled",
    "site",
    "preset",
    "url",
    "name",
    "memo",
    "updated_at",
}
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class RegistryEntry:
    id: str
    enabled: bool
    site: str
    preset: str
    url: str
    name: str
    memo: str
    updated_at: str


def parse_enabled(value: str, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"Row {row_number}: invalid enabled value {value!r}")


def google_sheet_csv_url(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.hostname != "docs.google.com" or "/spreadsheets/d/" not in parsed.path:
        return endpoint
    if "/export" in parsed.path or "/pub" in parsed.path:
        return endpoint

    match = re.search(r"/spreadsheets/d/([^/]+)", parsed.path)
    if not match:
        return endpoint
    spreadsheet_id = match.group(1)
    query = parse_qs(parsed.query)
    fragment = parse_qs(parsed.fragment)
    gid = (query.get("gid") or fragment.get("gid") or ["0"])[0]
    return (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export"
        f"?format=csv&gid={gid}"
    )


def read_endpoint(endpoint: str, timeout: float = 30.0) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme in {"http", "https"}:
        url = google_sheet_csv_url(endpoint)
        request = Request(url, headers={"User-Agent": "monitoring-registry/1.0"})
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except Exception as error:
            raise RuntimeError(f"Failed to fetch registry endpoint: {url}") from error
        return payload.decode("utf-8-sig")

    if parsed.scheme == "file":
        path = Path(unquote(parsed.path.lstrip("/")))
    else:
        path = Path(endpoint)
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise RuntimeError(f"Failed to read registry file: {path}") from error


def load_preset_config(path: Path = DEFAULT_PRESETS) -> dict[str, dict]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise RuntimeError(f"Failed to load preset config: {path}") from error
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Preset config must use schema_version: 1")
    presets = raw.get("presets")
    if not isinstance(presets, dict) or not presets:
        raise ValueError("Preset config has no presets")
    for name, preset in presets.items():
        if not isinstance(preset, dict) or not isinstance(preset.get("filter"), list):
            raise ValueError(f"Preset {name!r} must define a filter list")
    return presets


def parse_registry_csv(text: str, presets: dict[str, dict]) -> list[RegistryEntry]:
    reader = csv.DictReader(io.StringIO(text))
    headers = set(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise ValueError(f"Registry is missing required columns: {', '.join(sorted(missing))}")

    entries: list[RegistryEntry] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    for row_number, row in enumerate(reader, 2):
        entry_id = (row.get("id") or "").strip()
        if not entry_id:
            raise ValueError(f"Row {row_number}: id is required")
        if entry_id in seen_ids:
            raise ValueError(f"Row {row_number}: duplicate id {entry_id!r}")
        seen_ids.add(entry_id)

        enabled = parse_enabled(row.get("enabled") or "", row_number)
        if not enabled:
            continue

        site = (row.get("site") or "").strip()
        preset_name = (row.get("preset") or "").strip()
        url = (row.get("url") or "").strip()
        name = (row.get("name") or "").strip() or url
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError(f"Row {row_number}: invalid URL {url!r}")
        if url in seen_urls:
            raise ValueError(f"Row {row_number}: duplicate enabled URL {url!r}")
        seen_urls.add(url)

        preset = presets.get(preset_name)
        if preset is None:
            raise ValueError(f"Row {row_number}: unknown preset {preset_name!r}")
        allowed_sites = preset.get("sites") or []
        if allowed_sites and site not in allowed_sites:
            raise ValueError(
                f"Row {row_number}: site {site!r} is not allowed by preset {preset_name!r}"
            )

        entries.append(
            RegistryEntry(
                id=entry_id,
                enabled=True,
                site=site,
                preset=preset_name,
                url=url,
                name=name,
                memo=(row.get("memo") or "").strip(),
                updated_at=(row.get("updated_at") or "").strip(),
            )
        )

    if not entries:
        raise ValueError("Registry contains no enabled rows; monitoring was stopped")
    return entries


def load_registry(
    endpoint: str,
    presets_path: Path = DEFAULT_PRESETS,
    timeout: float = 30.0,
) -> tuple[list[RegistryEntry], dict[str, dict]]:
    presets = load_preset_config(presets_path)
    text = read_endpoint(endpoint, timeout=timeout)
    return parse_registry_csv(text, presets), presets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and validate registry CSV data")
    parser.add_argument("--endpoint", default=os.environ.get("REGISTRY_ENDPOINT"))
    parser.add_argument("--presets", type=Path, default=DEFAULT_PRESETS)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.endpoint:
        raise SystemExit("REGISTRY_ENDPOINT or --endpoint is required")
    entries, _ = load_registry(args.endpoint, args.presets, args.timeout)
    print(f"Validated {len(entries)} enabled registry rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
