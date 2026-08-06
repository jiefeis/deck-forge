#!/usr/bin/env python3
"""Build an aligned contact sheet from one or more rendered slide folders.

Example:
    python make_contact_sheet.py \
      --row source=render/source --row target=render/target \
      --output render/contact-sheet.png --columns 5

Input images should be named ``slide-001.png`` etc. Missing physical pages stay
blank, which makes hidden/missing/reordered output visible instead of shifting
the remaining thumbnails into false alignment.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("make_contact_sheet: Pillow required. Run: pip install Pillow")


SLIDE_RE = re.compile(r"slide-(\d+)\.png$", re.IGNORECASE)


def parse_row(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("row must be LABEL=DIRECTORY")
    label, raw = value.split("=", 1)
    if not label.strip():
        raise argparse.ArgumentTypeError("row label cannot be empty")
    directory = Path(raw).expanduser().resolve()
    if not directory.is_dir():
        raise argparse.ArgumentTypeError(f"row directory not found: {directory}")
    return label.strip(), directory


def indexed_images(directory: Path) -> dict[int, Path]:
    out: dict[int, Path] = {}
    for path in directory.glob("slide-*.png"):
        match = SLIDE_RE.search(path.name)
        if match:
            out[int(match.group(1))] = path
    if not out:
        raise ValueError(f"no slide-*.png images found in {directory}")
    return out


def fit_image(path: Path, width: int, height: int) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), "white")
    x = (width - image.width) // 2
    y = (height - image.height) // 2
    canvas.paste(image, (x, y))
    return canvas


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def build(rows: list[tuple[str, Path]], output: Path, columns: int,
          thumb_width: int) -> None:
    data = [(label, indexed_images(directory)) for label, directory in rows]
    all_indices = sorted({index for _, images in data for index in images})
    if not all_indices:
        raise ValueError("no slide images found")

    ratio = 9 / 16
    thumb_height = round(thumb_width * ratio)
    gutter = max(120, thumb_width // 3)
    top = 30
    row_gap = 14
    group_gap = 34
    page_label_h = 28
    groups = (len(all_indices) + columns - 1) // columns
    group_h = page_label_h + len(rows) * (thumb_height + row_gap)
    sheet_w = gutter + columns * thumb_width
    sheet_h = top + groups * group_h + max(0, groups - 1) * group_gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = load_font(max(14, thumb_width // 20))

    for group in range(groups):
        chunk = all_indices[group * columns:(group + 1) * columns]
        y0 = top + group * (group_h + group_gap)
        for col, index in enumerate(chunk):
            x = gutter + col * thumb_width
            draw.text((x + 6, y0 + 6), f"Slide {index}", fill="#202020", font=font)

        for row_index, (label, images) in enumerate(data):
            y = y0 + page_label_h + row_index * (thumb_height + row_gap)
            draw.text((10, y + 8), label, fill="#202020", font=font)
            for col, index in enumerate(chunk):
                x = gutter + col * thumb_width
                path = images.get(index)
                if path:
                    sheet.paste(fit_image(path, thumb_width, thumb_height), (x, y))
                else:
                    draw.rectangle((x, y, x + thumb_width - 1, y + thumb_height - 1),
                                   outline="#d00000", width=2)
                    draw.text((x + 8, y + 8), "MISSING", fill="#d00000", font=font)

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG", optimize=True)
    print(f"Contact sheet: {output} ({len(all_indices)} physical pages, {len(rows)} rows)")


def main() -> None:
    # Printed paths may contain non-ASCII; never let a cp1252/cp936 console
    # pipe kill the run with UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--row", action="append", required=True, type=parse_row,
                        help="labeled render directory, e.g. source=render/source")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--thumb-width", type=int, default=320)
    args = parser.parse_args()
    if args.columns < 1 or args.thumb_width < 120:
        parser.error("--columns must be >=1 and --thumb-width must be >=120")
    build(args.row, args.output.resolve(), args.columns, args.thumb_width)


if __name__ == "__main__":
    main()
