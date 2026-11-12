"""TARGET PC ONLY: author the desktop icon before a Rust build (requires Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw

directory = Path(__file__).resolve().parents[1]/"src-tauri"/"icons"
directory.mkdir(exist_ok=True)
image = Image.new("RGBA", (256, 256), (14, 23, 28, 255))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((12, 12, 244, 244), radius=52, fill=(133, 229, 199, 255))
draw.line([(60, 190), (60, 70), (128, 148), (196, 70), (196, 190)], fill=(17, 44, 41, 255), width=22, joint="curve")
image.save(directory/"icon.png")
image.save(directory/"icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Authored icons in {directory}. Commit these generated assets after target-PC validation.")
