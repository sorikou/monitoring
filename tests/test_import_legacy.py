from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "scripts" / "registry" / "import_legacy.py"
SPEC = importlib.util.spec_from_file_location("import_legacy", MODULE_PATH)
assert SPEC and SPEC.loader
import_legacy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = import_legacy
SPEC.loader.exec_module(import_legacy)


class ImportLegacyTests(unittest.TestCase):
    def test_preserved_template_has_55_unique_jobs(self) -> None:
        source = PROJECT_ROOT / "migration" / "urls_template.legacy.yaml"
        jobs = import_legacy.parse_legacy_template(source.read_text(encoding="utf-8"))

        self.assertEqual(len(jobs), 55)
        self.assertEqual(len({job.url for job in jobs}), 55)
        self.assertEqual(sum(job.site == "syosetu" for job in jobs), 30)

    def test_generated_yaml_replaces_title_placeholders(self) -> None:
        source = PROJECT_ROOT / "migration" / "urls_template.legacy.yaml"
        jobs = import_legacy.parse_legacy_template(source.read_text(encoding="utf-8"))
        generated = import_legacy.build_urlwatch_yaml(jobs)

        self.assertNotIn(import_legacy.TITLE_PLACEHOLDER, generated)
        self.assertEqual(generated.count("\nurl:"), 55)

    def test_duplicate_url_is_rejected(self) -> None:
        source = """---
kind: url
name: "one"
url: "https://example.com/work"
filter:
  - html2text
---
kind: url
name: "two"
url: "https://example.com/work"
filter:
  - html2text
"""

        with self.assertRaisesRegex(ValueError, "Duplicate URL"):
            import_legacy.parse_legacy_template(source)


if __name__ == "__main__":
    unittest.main()
