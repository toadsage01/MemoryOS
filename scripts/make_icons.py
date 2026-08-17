"""Generate placeholder icons for the extension. Run once."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "extension" / "icons"
OUT.mkdir(parents=True, exist_ok=True)


def make(size: int, path: Path) -> None:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Slate background, rounded
    pad = max(2, size // 16)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=size // 6,
        fill=(30, 41, 59, 255),  # slate-800
    )
    # A simple "SB" glyph in cream
    try:
        from PIL import ImageFont

        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            int(size * 0.42),
        )
    except Exception:
        font = ImageFont.load_default()
    text = "SB"
    # Manual centering
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
        text,
        font=font,
        fill=(254, 249, 231, 255),  # amber-50
    )
    img.save(path)


if __name__ == "__main__":
    for size in (16, 32, 48, 128):
        make(size, OUT / f"icon-{size}.png")
    print("wrote:", *[f.name for f in OUT.iterdir()])
