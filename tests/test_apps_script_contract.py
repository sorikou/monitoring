from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"


class AppsScriptContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.code = (APP_ROOT / "Code.gs").read_text(encoding="utf-8")
        cls.index = (APP_ROOT / "Index.html").read_text(encoding="utf-8")
        cls.manifest = json.loads(
            (APP_ROOT / "appsscript.json").read_text(encoding="utf-8")
        )

    def test_web_app_allows_anonymous_access(self) -> None:
        self.assertEqual(
            self.manifest["webapp"]["access"], "ANYONE_ANONYMOUS"
        )
        self.assertEqual(
            self.manifest["webapp"]["executeAs"], "USER_DEPLOYING"
        )

    def test_server_uses_explicit_spreadsheet_id_and_lock(self) -> None:
        self.assertIn("SpreadsheetApp.openById(spreadsheetId)", self.code)
        self.assertIn("PropertiesService.getScriptProperties()", self.code)
        self.assertIn("LockService.getScriptLock()", self.code)
        self.assertIn("lock.waitLock(LOCK_TIMEOUT_MS)", self.code)
        self.assertIn("lock.releaseLock()", self.code)

    def test_server_exposes_required_registry_operations(self) -> None:
        for function_name in (
            "getInitialData",
            "listEntries",
            "validateEntry",
            "addEntry",
            "updateEntry",
            "setEntryEnabled",
            "archiveEntry",
            "restoreEntry",
        ):
            self.assertIn(f"function {function_name}(", self.code)

    def test_update_only_writes_mutable_columns(self) -> None:
        update_start = self.code.index("function updateEntry(")
        update_end = self.code.index("function setEntryEnabled(")
        update_body = self.code[update_start:update_end]
        self.assertIn("getRange(location.rowNumber, 2, 1, 6)", update_body)
        self.assertIn(
            "getRange(location.rowNumber, 9).setValue(new Date())",
            update_body,
        )
        self.assertNotIn("applyRowFormatting_", update_body)
        self.assertNotIn("existing.createdAt", update_body)
        self.assertNotIn("setValue(normalized.id)", update_body)

    def test_typed_table_formatting_errors_are_ignored(self) -> None:
        self.assertIn("function applyCellStructureSafely_(operation)", self.code)
        self.assertIn("typed column|型付きの列|型指定された列", self.code)

    def test_ui_contains_search_filters_and_safe_lifecycle_actions(self) -> None:
        for token in (
            'id="searchInput"',
            'value="enabled"',
            'value="disabled"',
            'value="archived"',
            "archiveEntry",
            "restoreEntry",
            "setEntryEnabled",
            "URLを変更すると監視履歴との対応が変わる可能性があります",
        ):
            self.assertIn(token, self.index)

    def test_app_does_not_trigger_monitoring_or_send_mail(self) -> None:
        combined = self.code + self.index
        self.assertNotIn("UrlFetchApp", combined)
        self.assertNotIn("MailApp", combined)
        self.assertNotIn("GmailApp", combined)
        self.assertNotIn("workflow_dispatch", combined)


if __name__ == "__main__":
    unittest.main()
