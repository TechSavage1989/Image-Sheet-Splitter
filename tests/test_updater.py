import json
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from image_sheet_splitter import updater
from image_sheet_splitter.updater import (
    UpdateManager,
    create_release_manifest,
    ensure_allowed_url,
    is_newer_version,
    validate_manifest,
)


class UpdaterTests(unittest.TestCase):
    def valid_manifest(self, version="1.8.0"):
        return create_release_manifest(
            version,
            "Image_Sheet_Splitter_Windows_x64_Portable.zip",
            "a" * 64,
            123456,
            ["Test update"],
        )

    def test_version_comparison(self):
        self.assertTrue(is_newer_version("1.8.0", "1.7.0"))
        self.assertFalse(is_newer_version("1.7.0", "1.7.0"))
        self.assertFalse(is_newer_version("1.6.9", "1.7.0"))

    def test_url_allowlist_rejects_http_and_foreign_hosts(self):
        with self.assertRaises(ValueError):
            ensure_allowed_url("http://github.com/example/file")
        with self.assertRaises(ValueError):
            ensure_allowed_url("https://example.com/update.zip")
        self.assertEqual(
            ensure_allowed_url("https://github.com/TechSavage1989/Image-Sheet-Splitter/releases"),
            "https://github.com/TechSavage1989/Image-Sheet-Splitter/releases",
        )

    def test_manifest_identity_is_enforced(self):
        manifest = self.valid_manifest()
        manifest["app_id"] = "Wrong.App"
        with self.assertRaises(ValueError):
            validate_manifest(manifest)

    def test_offline_check_is_not_reported_as_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            with mock.patch.object(updater, "update_state_path", return_value=state):
                manager = UpdateManager("1.7.0")
                with mock.patch.object(updater, "_request_json", side_effect=urllib.error.URLError("offline")):
                    result = manager.check(manual=True)
            self.assertEqual(result.status, "error")
            self.assertNotEqual(result.status, "current")
            self.assertIn("Unable to reach", result.message)

    def test_etag_304_reuses_cached_manifest(self):
        manifest = self.valid_manifest("1.8.0")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            with mock.patch.object(updater, "update_state_path", return_value=state):
                manager = UpdateManager("1.7.0")
                with mock.patch.object(
                    updater,
                    "_request_json",
                    side_effect=[(manifest, '"etag-1"', False), (None, '"etag-1"', True)],
                ) as request:
                    first = manager.check()
                    second = manager.check()
                self.assertEqual(request.call_count, 2)
            self.assertEqual(first.status, "available")
            self.assertEqual(second.status, "available")
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["etag"], '"etag-1"')

    def test_zip_traversal_is_rejected(self):
        for name in ("../escape.exe", "C:/escape.exe", "safe/file:stream", "safe./file.exe", "safe /file.exe"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                updater._safe_zip_member(zipfile.ZipInfo(name))

    def test_manifest_download_filename_cannot_escape_download_directory(self):
        for name in ("../escape.zip", "C:\\escape.zip", "folder/escape.zip", "file:stream.zip"):
            manifest = self.valid_manifest()
            manifest["assets"][updater.PORTABLE_ASSET_KEY]["name"] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
