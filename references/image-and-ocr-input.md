# Image and OCR input

Read this when source material is a screenshot, photo, scanned page, chart image,
or when images must become deck pages.

## Decide image role

- If the user needs editable slides, do not paste a whole screenshot as the final
  slide unless they accept a non-editable result.
- Use images as evidence or visual assets, then recreate labels, titles, and
  annotations as editable text when practical.
- For complex charts that are hard to rebuild, crop or preserve the chart image
  and rebuild surrounding text as editable objects.

## Preserve visual intent

- Preserve white backgrounds when the source is white; do not add grid/dark
  backgrounds unless requested.
- Avoid decorative treatments that make real data, charts, or UI screenshots
  harder to inspect.
- Check image resolution after cropping and scaling.
- Avoid blurry enlarged screenshots.

## OCR and transcription

- Treat OCR as a draft. Compare against the visible source and fix line breaks,
  punctuation, and domain terms manually.
- Keep the source image nearby until the recreated page has been visually checked.
- If OCR confidence is low, ask or mark uncertain text rather than fabricating.

## Building slides from images

- Match the source layout first if the task is reformat.
- Recreate content hierarchy, not merely text.
- Validate that all image-derived text is inside its intended box after rendering.
