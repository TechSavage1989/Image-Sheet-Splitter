import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

REQUIRED_H2 = [
    "Features",
    "Download",
    "Requirements",
    "Getting started",
    "How to use",
    "Updates and settings",
    "Troubleshooting",
    "Development",
]


def main():
    text = README.read_text(encoding="utf-8")
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>|^#\s+(.+)$", text, re.IGNORECASE | re.MULTILINE)
    flat_h1 = [a or b for a, b in h1s]
    if flat_h1 != ["Image Sheet Splitter"]:
        raise SystemExit(f"README must contain exactly one H1 named Image Sheet Splitter: {flat_h1}")

    headings = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
    positions = []
    for name in REQUIRED_H2:
        if name not in headings:
            raise SystemExit(f"Missing README section: {name}")
        positions.append(headings.index(name))
    if positions != sorted(positions):
        raise SystemExit("README sections are not in the required order")

    required_nav = ["#download", "#getting-started", "#features", "#updates-and-settings", "#development"]
    for anchor in required_nav:
        if f'href="{anchor}"' not in text:
            raise SystemExit(f"Missing README navigation anchor: {anchor}")

    image_match = re.search(r'<img\s+src="([^"]+)"[^>]*alt="([^"]+)"', text, re.IGNORECASE)
    if not image_match:
        raise SystemExit("README icon is missing or lacks useful alt text")
    image_path = ROOT / image_match.group(1)
    if not image_path.exists():
        raise SystemExit(f"README icon path does not exist: {image_match.group(1)}")

    for relative in ("AGENTS.md", "DEVELOPMENT_HANDOFF.md"):
        if not (ROOT / relative).exists() or f"]({relative})" not in text:
            raise SystemExit(f"README development link is missing or invalid: {relative}")

    print("README structure, navigation anchors, and local asset links verified.")


if __name__ == "__main__":
    main()
