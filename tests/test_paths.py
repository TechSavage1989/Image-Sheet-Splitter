import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from image_sheet_splitter import paths


class PathMigrationTests(unittest.TestCase):
    def test_legacy_default_config_is_copied_to_new_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with mock.patch.object(paths, "_local_appdata_root", return_value=base):
                legacy = paths.legacy_default_config_path()
                legacy.parent.mkdir(parents=True)
                legacy.write_text(json.dumps({"output_dir": "C:/Example"}), encoding="utf-8")
                resolved = paths.resolve_config_path()
                self.assertEqual(resolved, paths.default_config_path())
                self.assertTrue(resolved.exists())
                self.assertEqual(json.loads(resolved.read_text(encoding="utf-8"))["output_dir"], "C:/Example")
                self.assertEqual(paths.config_locator_path().read_text(encoding="utf-8"), str(resolved))

    def test_legacy_custom_locator_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            custom = base / "custom" / "settings.json"
            custom.parent.mkdir(parents=True)
            custom.write_text("{}", encoding="utf-8")
            with mock.patch.object(paths, "_local_appdata_root", return_value=base):
                locator = paths.legacy_config_locator_path()
                locator.parent.mkdir(parents=True)
                locator.write_text(str(custom), encoding="utf-8")
                resolved = paths.resolve_config_path()
                self.assertEqual(resolved, custom)
                self.assertEqual(paths.config_locator_path().read_text(encoding="utf-8"), str(custom))


if __name__ == "__main__":
    unittest.main()
