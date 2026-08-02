#!/usr/bin/env python3
"""Convert the preserved legacy URL template into migration-ready data.

This script deliberately uses only the Python standard library. It preserves the
legacy urlwatch filter blocks while producing a CSV that can be imported into
Google Sheets.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "migration" / "urls_template.legacy.yaml"
DEFAULT_CSV_OUTPUT = PROJECT_ROOT / "migration" / "registry-seed.csv"
DEFAULT_URLS_OUTPUT = PROJECT_ROOT / "generated" / "urls.yaml"
TITLE_PLACEHOLDER = "{{TITLE_PLACEHOLDER}}"
DOCUMENT_SEPARATOR = re.compile(r"(?m)^---\s*$")
FILTER_PRESETS = {
    ("- html2text",): "anime-news",
    (
        "- html2text",
        "- re.findall: '(?s)最新話(.*?)この作品に対するご感想はこちらから'",
    ): "comic-valkyrie-work",
    (
        "- html2text",
        "- re.findall: '(?s)チャプター(.*?)作品インフォメーション'",
    ): "gangan-online-work",
    (
        "- html2text",
        "- re.findall: '(?s)無料配信中の漫画(.*?)ランキング'",
    ): "gaugau-work",
    (
        "- html2text",
        "- re.findall: '(?s)次回の新チャプター追加(.*?)予定です'",
    ): "manga-up-work",
    (
        "- html2text",
        "- re.findall: '(?s)最新話を読む(.*?)その他マンガ'",
    ): "niconico-manga-work",
    (
        "- html2text",
        "- re.findall: '(?s)作者：(.*?)この作品をブックマークに登録している人はこんな作品も読んでいます'",
    ): "syosetu-work",
    (
        "- html2text",
        "- grepi: '（改）'",
        "- re.findall: '(?s)作者：(.*?)この作品をブックマークに登録している人はこんな作品も読んでいます'",
    ): "syosetu-work-ignore-revised",
    (
        "- html2text",
        "- re.findall: '(?s)必要ポイント(.*?)「全話無料」対象作品はコチラ!!!'",
    ): "yanmaga-work",
}


@dataclass(frozen=True)
class LegacyJob:
    name: str
    site: str
    preset: str
    url: str
    body: str


def _yaml_scalar(body: str, field: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(field)}:\s*(.*?)\s*$", body)
    if not match:
        return None

    value = match.group(1).strip()
    if value.startswith('"'):
        try:
            return str(json.loads(value))
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid quoted {field}: {value}") from error
    return value.split(" #", 1)[0].strip("'")


def site_for_url(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        raise ValueError(f"URL has no hostname: {url}")
    if hostname == "ncode.syosetu.com":
        return "syosetu"
    return hostname.removeprefix("www.")


def active_filter_lines(body: str) -> tuple[str, ...]:
    lines = body.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line == "filter:")
    except StopIteration as error:
        raise ValueError("Legacy URL job has no filter block") from error
    return tuple(
        line.strip()
        for line in lines[start + 1 :]
        if line.strip() and not line.lstrip().startswith("#")
    )


def preset_for_body(body: str) -> str:
    filter_lines = active_filter_lines(body)
    try:
        return FILTER_PRESETS[filter_lines]
    except KeyError as error:
        raise ValueError(f"No preset mapping for legacy filters: {filter_lines}") from error


def parse_legacy_template(text: str) -> list[LegacyJob]:
    jobs: list[LegacyJob] = []
    seen_urls: set[str] = set()

    for raw_body in DOCUMENT_SEPARATOR.split(text):
        body = raw_body.strip("\r\n")
        url = _yaml_scalar(body, "url")
        if not url:
            continue

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported URL scheme: {url}")
        if url in seen_urls:
            raise ValueError(f"Duplicate URL: {url}")
        seen_urls.add(url)

        legacy_name = _yaml_scalar(body, "name") or url
        name = url if legacy_name == TITLE_PLACEHOLDER else legacy_name
        jobs.append(
            LegacyJob(
                name=name,
                site=site_for_url(url),
                preset=preset_for_body(body),
                url=url,
                body=body,
            )
        )

    if not jobs:
        raise ValueError("No URL jobs were found in the legacy template")
    return jobs


def build_registry_csv(jobs: list[LegacyJob]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "id",
            "enabled",
            "site",
            "preset",
            "url",
            "name",
            "memo",
            "updated_at",
        ),
        lineterminator="\n",
    )
    writer.writeheader()
    for index, job in enumerate(jobs, 1):
        writer.writerow(
            {
                "id": f"monitor-{index:04d}",
                "enabled": "true",
                "site": job.site,
                "preset": job.preset,
                "url": job.url,
                "name": job.name,
                "memo": "",
                "updated_at": "",
            }
        )
    return buffer.getvalue().encode("utf-8-sig")


def build_urlwatch_yaml(jobs: list[LegacyJob]) -> str:
    documents: list[str] = []
    for job in jobs:
        replacement = "name: " + json.dumps(job.name, ensure_ascii=False)
        active_lines = [
            line
            for line in job.body.splitlines()
            if not line.lstrip().startswith("#")
        ]
        active_body = "\n".join(active_lines).strip()
        body, replacements = re.subn(
            r"(?m)^name:\s*.*$",
            lambda _: replacement,
            active_body,
            count=1,
        )
        if replacements != 1:
            raise ValueError(f"Job has no top-level name field: {job.url}")
        documents.append("---\n" + body.rstrip())
    return "\n".join(documents) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import preserved legacy URL jobs without retyping them."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--urls-output", type=Path, default=DEFAULT_URLS_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and report only; do not write output files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jobs = parse_legacy_template(args.input.read_text(encoding="utf-8"))

    if args.check:
        print(f"Validated {len(jobs)} unique URL jobs")
        return 0

    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    args.urls_output.parent.mkdir(parents=True, exist_ok=True)
    args.csv_output.write_bytes(build_registry_csv(jobs))
    args.urls_output.write_text(build_urlwatch_yaml(jobs), encoding="utf-8")

    print(f"Imported {len(jobs)} unique URL jobs")
    print(f"Spreadsheet seed: {args.csv_output}")
    print(f"urlwatch input: {args.urls_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
