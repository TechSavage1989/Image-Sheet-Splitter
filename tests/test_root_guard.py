import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_root


class RootGuardTests(unittest.TestCase):
    def test_clean_fixture_passes_and_unapproved_root_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("README.md", "AGENTS.md", "DEVELOPMENT_HANDOFF.md"):
                (root / name).write_text("test", encoding="utf-8")
            (root / "src").mkdir()
            self.assertEqual(check_root.unexpected_entries(root), [])

            clutter = root / "temporary-notes.txt"
            clutter.write_text("should fail", encoding="utf-8")
            self.assertEqual(check_root.unexpected_entries(root), ["temporary-notes.txt"])


if __name__ == "__main__":
    unittest.main()
