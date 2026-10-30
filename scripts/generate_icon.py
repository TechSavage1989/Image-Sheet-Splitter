from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PNG = ROOT / "assets" / "icons" / "Image_Sheet_Splitter.png"
ICO = ROOT / "assets" / "icons" / "Image_Sheet_Splitter.ico"
SIZES = [(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(96,96),(128,128),(192,192),(256,256)]

def main():
    image = Image.open(PNG).convert("RGBA")
    if image.size != (256, 256):
        image = image.resize((256, 256), Image.Resampling.LANCZOS)
    image.save(ICO, format="ICO", sizes=SIZES)
    print(f"Generated {ICO}")

if __name__ == "__main__":
    main()
