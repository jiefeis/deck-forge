# HTML deck and PDF output

Read this for deck-forge's native HTML-to-PDF route or when HTML rendering is
used for visual slides.

## HTML deck rules

- Author a fixed 1920x1080 stage and scale the entire slide.
- Do not depend on browser reflow, scrollbars, or viewport-based font sizes for
  deck PDF output.
- Include the full `viewport-base.css` in the generated HTML.
- Every page must be a `.slide` inside the deck stage.
- Use the same HTML source for previews and final PDF export.
- Load fonts before screenshots; missing fonts change line breaks.
- Use stable text IDs when the deck needs later copy edits.

## PDF export rules

- For visual decks, use screenshot pages with lossless PNG/Flate embedding.
- Avoid JPEG/DCT compression when text crispness matters.
- Check the final PDF if crispness is questioned; `DCTDecode` indicates JPEG
  compression.
- Explain that screenshot PDFs are visual snapshots and text is not selectable.
- Keep the editable HTML source next to the PDF unless the user requests a single
  deliverable only.

## Export-blocking defects

Fix and re-export if any page has:

- clipped text
- overlapped text or objects
- off-canvas objects
- empty-bottom layouts caused by underfilled content
- missing fonts/images
- inconsistent page dimensions
- unexpected animation state

For dense or high-risk decks, inspect the full-size screenshot pages, not only a
thumbnail contact sheet.
