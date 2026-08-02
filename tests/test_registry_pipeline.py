from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.monitoring.generate_urls import build_urlwatch_jobs, require_expected_count
from scripts.monitoring.run_local import validate_mail_disabled
from scripts.registry.fetch_registry import (
    google_sheet_csv_url,
    load_preset_config,
    load_registry,
    parse_registry_csv,
)
from scripts.registry.import_legacy import build_urlwatch_yaml, parse_legacy_template


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RegistryPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.presets = load_preset_config(PROJECT_ROOT / "config" / "site-presets.yaml")

    def test_seed_generates_55_jobs_with_legacy_filters(self) -> None:
        entries, presets = load_registry(
            str(PROJECT_ROOT / "migration" / "registry-seed.csv")
        )
        jobs = build_urlwatch_jobs(entries, presets)

        legacy_source = PROJECT_ROOT / "migration" / "urls_template.legacy.yaml"
        legacy_jobs = parse_legacy_template(legacy_source.read_text(encoding="utf-8"))
        parsed_legacy = list(yaml.safe_load_all(build_urlwatch_yaml(legacy_jobs)))

        self.assertEqual(len(jobs), 55)
        self.assertEqual(
            {job["url"]: job["filter"] for job in jobs},
            {job["url"]: job["filter"] for job in parsed_legacy},
        )

    def test_disabled_row_is_not_emitted(self) -> None:
        text = """id,enabled,site,preset,url,name,memo,updated_at
one,false,syosetu,syosetu-work,https://example.com/disabled,disabled,,
two,true,syosetu,syosetu-work,https://example.com/enabled,enabled,,
"""
        entries = parse_registry_csv(text, self.presets)
        self.assertEqual([entry.id for entry in entries], ["two"])

    def test_unknown_preset_is_rejected(self) -> None:
        text = """id,enabled,site,preset,url,name,memo,updated_at
one,true,syosetu,missing,https://example.com/work,work,,
"""
        with self.assertRaisesRegex(ValueError, "unknown preset"):
            parse_registry_csv(text, self.presets)

    def test_duplicate_enabled_url_is_rejected(self) -> None:
        text = """id,enabled,site,preset,url,name,memo,updated_at
one,true,syosetu,syosetu-work,https://example.com/work,one,,
two,true,syosetu,syosetu-work,https://example.com/work,two,,
"""
        with self.assertRaisesRegex(ValueError, "duplicate enabled URL"):
            parse_registry_csv(text, self.presets)

    def test_local_config_requires_email_false(self) -> None:
        validate_mail_disabled(PROJECT_ROOT / "config" / "urlwatch.local.yaml")
        with tempfile.TemporaryDirectory() as directory:
            unsafe = Path(directory) / "unsafe.yaml"
            unsafe.write_text("report:\n  email:\n    enabled: true\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "email.enabled"):
                validate_mail_disabled(unsafe)

    def test_google_sheet_url_is_converted_to_csv_export(self) -> None:
        converted = google_sheet_csv_url(
            "https://docs.google.com/spreadsheets/d/example-id/edit#gid=123"
        )
        self.assertEqual(
            converted,
            "https://docs.google.com/spreadsheets/d/example-id/export?format=csv&gid=123",
        )

    def test_google_sheet_url_without_gid_uses_first_visible_sheet(self) -> None:
        converted = google_sheet_csv_url(
            "https://docs.google.com/spreadsheets/d/example-id/edit?usp=sharing"
        )
        self.assertEqual(
            converted,
            "https://docs.google.com/spreadsheets/d/example-id/gviz/tq?tqx=out:csv",
        )

    def test_expected_job_count_is_enforced_before_writing(self) -> None:
        jobs = [{} for _ in range(55)]
        require_expected_count(jobs, 55)
        with self.assertRaisesRegex(SystemExit, "Expected 54 jobs"):
            require_expected_count(jobs, 54)


if __name__ == "__main__":
    unittest.main()
