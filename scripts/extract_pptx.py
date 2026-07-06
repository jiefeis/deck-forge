#!/usr/bin/env python3
"""
Extract all content from a PowerPoint file (.pptx).
Returns a JSON structure with slides, text, tables, images, and notes.

Usage:
    python extract_pptx.py <input.pptx> [output_dir]

Requires: pip install python-pptx
"""

import argparse
import json
import os
import sys

try:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
except ImportError:
    sys.exit("extract_pptx: python-pptx required. Run: pip install python-pptx")


def walk_shapes(shapes):
    """Yield shapes depth-first, expanding group shapes so nothing is lost."""
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from walk_shapes(shape.shapes)
        else:
            yield shape


def get_image(shape, slide_num):
    """Return the shape's embedded image object, or None.

    Covers plain pictures and pictures placed inside placeholders. Linked
    (non-embedded) pictures raise on access; warn and continue instead of
    crashing the whole extraction.
    """
    if shape.shape_type != MSO_SHAPE_TYPE.PICTURE and not shape.is_placeholder:
        return None
    try:
        return shape.image
    except AttributeError:
        return None  # placeholder without an inserted picture
    except Exception as exc:
        print(f"  warning: slide {slide_num}: skipping unreadable image "
              f"(linked, not embedded?): {exc}")
        return None


def extract_pptx(file_path, output_dir="."):
    """
    Extract all content from a PowerPoint file.
    Returns a list of slide data dicts with text, tables, images, and notes.
    """
    prs = Presentation(file_path)
    slides_data = []

    # Create assets directory for extracted images
    assets_dir = os.path.join(output_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    for slide_num, slide in enumerate(prs.slides):
        slide_data = {
            "number": slide_num + 1,
            "title": "",
            "content": [],
            "images": [],
            "notes": "",
        }
        title_shape = slide.shapes.title

        for shape in walk_shapes(slide.shapes):
            # Extract text content
            if shape.has_text_frame:
                if title_shape is not None and shape == title_shape:
                    slide_data["title"] = shape.text
                elif shape.text.strip():
                    slide_data["content"].append(
                        {"type": "text", "content": shape.text}
                    )

            # Extract table cell text
            if shape.has_table:
                rows = [[cell.text for cell in row.cells]
                        for row in shape.table.rows]
                slide_data["content"].append({"type": "table", "rows": rows})

            # Extract images (embedded pictures, incl. picture placeholders)
            image = get_image(shape, slide_num + 1)
            if image is None:
                continue
            try:
                image_bytes = image.blob
                image_ext = image.ext
            except Exception as exc:
                print(f"  warning: slide {slide_num + 1}: could not read "
                      f"image data: {exc}")
                continue
            image_name = f"slide{slide_num + 1}_img{len(slide_data['images']) + 1}.{image_ext}"
            image_path = os.path.join(assets_dir, image_name)

            with open(image_path, "wb") as f:
                f.write(image_bytes)

            slide_data["images"].append(
                {
                    "path": f"assets/{image_name}",
                    "width": shape.width,
                    "height": shape.height,
                }
            )

        # Extract speaker notes
        if slide.has_notes_slide:
            notes_frame = slide.notes_slide.notes_text_frame
            slide_data["notes"] = notes_frame.text

        slides_data.append(slide_data)

    return slides_data


def main():
    # Keep console output safe on non-UTF-8 Windows pipes (GBK/cp1252).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    ap = argparse.ArgumentParser(
        description="Extract text, tables, images, and notes from a .pptx "
                    "into extracted-slides.json + assets/.")
    ap.add_argument("input_pptx", help="path to the .pptx file")
    ap.add_argument("output_dir", nargs="?", default=".",
                    help="directory for extracted-slides.json and assets/ "
                         "(default: current dir)")
    args = ap.parse_args()

    slides = extract_pptx(args.input_pptx, args.output_dir)

    # Write extracted data as JSON
    output_path = os.path.join(args.output_dir, "extracted-slides.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(slides, f, indent=2, ensure_ascii=False)

    print(f"Extracted {len(slides)} slides to {output_path}")
    for s in slides:
        img_count = len(s["images"])
        print(f"  Slide {s['number']}: {s['title'] or '(no title)'} - {img_count} image(s)")


if __name__ == "__main__":
    main()
