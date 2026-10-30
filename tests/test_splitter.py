import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw
from image_sheet_splitter.app import find_rectangles, vc_profile_name


class SplitterTests(unittest.TestCase):
    def test_known_virtual_console_sizes_are_detected_and_named(self):
        bg = (220, 220, 220, 255)
        image = Image.new("RGBA", (1600, 1500), bg)
        draw = ImageDraw.Draw(image)
        expected = [
            (20, 20, 190, 62),
            (240, 20, 368, 148),
            (20, 220, 874, 700),
            (20, 760, 1300, 1480),
        ]
        colors = [
            (255, 0, 0, 255),
            (0, 255, 0, 255),
            (0, 0, 255, 255),
            (255, 200, 0, 255),
        ]
        for rect, color in zip(expected, colors):
            x0, y0, x1, y1 = rect
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=color)

        detected_bg, rects = find_rectangles(image, tolerance=8, min_width=8, min_height=8)
        self.assertEqual(detected_bg, bg)
        self.assertEqual(rects, expected)
        self.assertEqual(vc_profile_name(170, 42), "Logo.png")
        self.assertEqual(vc_profile_name(128, 128), "Icon.png")
        self.assertEqual(vc_profile_name(854, 480), "Gamepad Image.png")
        self.assertEqual(vc_profile_name(1280, 720), "TV Image.png")

    def test_unrelated_sizes_remain_generic(self):
        self.assertIsNone(vc_profile_name(640, 480))
        self.assertIsNone(vc_profile_name(32, 32))

    def test_small_tolerance_allows_near_match_only(self):
        self.assertEqual(vc_profile_name(129, 127), "Icon.png")
        self.assertIsNone(vc_profile_name(140, 128))


if __name__ == "__main__":
    unittest.main()
