from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.monitoring.generate_urls import build_urlwatch_jobs, require_expected_count
from scripts.monitoring.prepare_email_test import DEFAULT_MARKER, build_email_test_job
from scripts.monitoring.run_email_test import render_email_config, validate_single_test_job
from scripts.monitoring.run_local import validate_mail_disabled
from scripts.monitoring.run_scheduled import validate_scheduled_jobs
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

    def test_web_registry_schema_uses_title_and_ignores_archived_rows(self) -> None:
        text = """id,enabled,site,preset,url,title,memo,created_at,updated_at,archived
one,true,syosetu,syosetu-work,https://example.com/active,表示名,,2026-08-03,2026-08-03,false
two,true,syosetu,syosetu-work,https://example.com/archived,保管済み,,2026-08-03,2026-08-03,true
"""
        entries = parse_registry_csv(text, self.presets)
        self.assertEqual([entry.id for entry in entries], ["one"])
        self.assertEqual(entries[0].name, "表示名")
        self.assertEqual(entries[0].created_at, "2026-08-03")

    def test_registry_requires_title_or_legacy_name(self) -> None:
        text = """id,enabled,site,preset,url,memo,updated_at
one,true,syosetu,syosetu-work,https://example.com/work,,2026-08-03
"""
        with self.assertRaisesRegex(ValueError, "title.*legacy name"):
            parse_registry_csv(text, self.presets)

    def test_unknown_preset_is_rejected(self) -> None:
        text = """id,enabled,site,preset,url,name,memo,updated_at
one,true,syosetu,missing,https://example.com/work,work,,
"""
        with self.assertRaisesRegex(ValueError, "unknown preset"):
            parse_registry_csv(text, self.presets)

    def test_preset_is_not_restricted_to_known_sites(self) -> None:
        text = """id,enabled,site,preset,url,name,memo,updated_at
one,true,yanineko-anime.com,anime-news,https://yanineko-anime.com/news/,やり直し令嬢は竜帝陛下を攻略中,,
"""
        entries = parse_registry_csv(text, self.presets)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].site, "yanineko-anime.com")
        self.assertEqual(entries[0].preset, "anime-news")

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

    def test_email_test_job_is_exactly_one_deterministic_url(self) -> None:
        job = build_email_test_job(
            [{"kind": "url", "name": "Example", "url": "https://example.com"}],
            DEFAULT_MARKER,
        )
        self.assertEqual(job["name"], "Gmail smoke test: Example")
        self.assertEqual(
            job["filter"],
            [{"re.sub": {"pattern": r"\A[\s\S]*\Z", "repl": DEFAULT_MARKER}}],
        )

    def test_email_test_rejects_multiple_jobs(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one job"):
            build_email_test_job([{}, {}], DEFAULT_MARKER)

    def test_email_config_is_rendered_without_leaking_placeholders(self) -> None:
        template = (PROJECT_ROOT / "config" / "urlwatch.email-test.yaml").read_text(
            encoding="utf-8"
        )
        rendered = render_email_config(template, "user@example.com", "app-password")
        self.assertNotIn("${URLWATCH_EMAIL_", rendered)
        self.assertIn("user@example.com", rendered)
        self.assertIn("app-password", rendered)

    def test_single_prepared_email_job_is_validated(self) -> None:
        job = build_email_test_job(
            [{"kind": "url", "url": "https://example.com"}], DEFAULT_MARKER
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "email-test.yaml"
            path.write_text(
                yaml.safe_dump_all([job], explicit_start=True, sort_keys=False),
                encoding="utf-8",
            )
            validate_single_test_job(path)

    def test_scheduled_monitoring_accepts_dynamic_enabled_job_count(self) -> None:
        jobs = [
            {
                "kind": "url",
                "name": f"Job {index}",
                "url": f"https://example.com/{index}",
                "filter": ["strip"],
            }
            for index in range(54)
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduled.yaml"
            path.write_text(
                yaml.safe_dump_all(jobs, explicit_start=True, sort_keys=False),
                encoding="utf-8",
            )
            self.assertEqual(validate_scheduled_jobs(path), 54)

    def test_scheduled_monitoring_rejects_empty_job_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduled.yaml"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "at least one enabled job"):
                validate_scheduled_jobs(path)

    def test_scheduled_monitoring_rejects_email_smoke_test(self) -> None:
        jobs = [
            {
                "kind": "url",
                "name": f"Job {index}",
                "url": f"https://example.com/{index}",
                "filter": ["strip"],
            }
            for index in range(55)
        ]
        jobs[0] = build_email_test_job([jobs[0]], DEFAULT_MARKER)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduled.yaml"
            path.write_text(
                yaml.safe_dump_all(jobs, explicit_start=True, sort_keys=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "smoke-test"):
                validate_scheduled_jobs(path)


if __name__ == "__main__":
    unittest.main()
