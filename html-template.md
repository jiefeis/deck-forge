# HTML Presentation Template

Reference architecture for generating slide presentations. Every presentation follows a fixed 16:9 stage model: slides are authored at 1920×1080 and the whole stage scales to fit the browser window.

## Contents

- Base HTML structure
- Required JavaScript features
- Inline editing implementation
- Reserved chrome class names
- Image pipeline
- Code quality and file structure

## Base HTML Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Presentation Title</title>

    <!-- Fonts: Fontshare/Google Fonts by default; brand or local fonts when
         brand, offline delivery, or CJK glyph coverage requires them -->
    <link rel="stylesheet" href="https://api.fontshare.com/v2/css?f[]=...">

    <style>
        /* ===========================================
           CSS CUSTOM PROPERTIES (THEME)
           Change these to change the whole look
           =========================================== */
        :root {
            /* Colors — from chosen style preset */
            --bg-primary: #0a0f1c;
            --bg-secondary: #111827;
            --text-primary: #ffffff;
            --text-secondary: #9ca3af;
            --accent: #00ffcc;
            --accent-glow: rgba(0, 255, 204, 0.3);

            /* Typography — authored at 1920×1080 stage size */
            --font-display: 'Clash Display', sans-serif;
            --font-body: 'Satoshi', sans-serif;
            --title-size: 112px;
            --subtitle-size: 34px;
            --body-size: 28px;

            /* Spacing — authored at 1920×1080 stage size */
            --slide-padding: 72px;
            --content-gap: 32px;

            /* Animation */
            --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
            --duration-normal: 0.6s;
        }

        /* ===========================================
           BASE STYLES
           =========================================== */
        * { margin: 0; padding: 0; box-sizing: border-box; }

        /* --- PASTE viewport-base.css CONTENTS HERE --- */

        /* ===========================================
           ANIMATIONS
           Trigger via .visible class on the active slide
           =========================================== */
        .reveal {
            opacity: 0;
            transform: translateY(30px);
            transition: opacity var(--duration-normal) var(--ease-out-expo),
                        transform var(--duration-normal) var(--ease-out-expo);
        }

        .slide.visible .reveal {
            opacity: 1;
            transform: translateY(0);
        }

        /* Stagger children for sequential reveal */
        .reveal:nth-child(1) { transition-delay: 0.1s; }
        .reveal:nth-child(2) { transition-delay: 0.2s; }
        .reveal:nth-child(3) { transition-delay: 0.3s; }
        .reveal:nth-child(4) { transition-delay: 0.4s; }

        /* ... preset-specific styles ... */
    </style>
</head>
<body>
    <div class="deck-viewport">
        <main class="deck-stage" id="deckStage">
            <section class="slide title-slide active">
                <h1 class="reveal">Presentation Title</h1>
                <p class="reveal">Subtitle or author</p>
            </section>

            <section class="slide">
                <div class="slide-content">
                    <h2 class="reveal">Slide Title</h2>
                    <p class="reveal">Content...</p>
                </div>
            </section>

            <!-- More slides... -->
        </main>
    </div>

    <script>
        /* ===========================================
           SLIDE PRESENTATION CONTROLLER
           =========================================== */
        class SlidePresentation {
            constructor() {
                this.slides = document.querySelectorAll('.slide');
                this.currentSlide = 0;
                this.stage = document.getElementById('deckStage');
                this.setupStageScale();
                this.setupKeyboardNav();
                this.setupTouchNav();
                this.showSlide(0);
            }

            setupStageScale() {
                const scale = () => {
                    const chrome = document.querySelector('.deck-controls');
                    const reserve = chrome && getComputedStyle(chrome).display !== 'none' ? Math.ceil(chrome.getBoundingClientRect().height) + 28 : 0;
                    const availableHeight = Math.max(1, window.innerHeight - reserve);
                    const factor = Math.min(window.innerWidth / 1920, availableHeight / 1080);
                    const x = (window.innerWidth - 1920 * factor) / 2;
                    const y = (availableHeight - 1080 * factor) / 2;
                    this.stage.style.transform = `translate(${x}px, ${y}px) scale(${factor})`;
                };
                scale();
                window.addEventListener('resize', scale);
            }

            setupKeyboardNav() {
                // Preserve native control/editing input; then implement deck shortcuts.
                window.addEventListener('keydown', (e) => {
                    if (e.defaultPrevented || e.isComposing || e.altKey || e.ctrlKey || e.metaKey) return;
                    if (e.target.closest?.('button,a,input,textarea,select,[contenteditable],[role="button"],[role="textbox"],[role="slider"]')) return;
                    const actions = {ArrowRight: 1, ArrowDown: 1, PageDown: 1, " ": 1, ArrowLeft: -1, ArrowUp: -1, PageUp: -1};
                    if (e.key in actions) { e.preventDefault(); this.showSlide(this.currentSlide + actions[e.key]); }
                    else if (e.key === "Home" || e.key === "End") { e.preventDefault(); this.showSlide(e.key === "Home" ? 0 : this.slides.length - 1); }
                });
            }

            setupTouchNav() {
                // Touch/swipe support for mobile
            }

            showSlide(index) {
                this.currentSlide = Math.max(0, Math.min(index, this.slides.length - 1));
                this.slides.forEach((slide, i) => {
                    slide.classList.toggle('active', i === this.currentSlide);
                    slide.classList.toggle('visible', i === this.currentSlide);
                });
            }
        }

        new SlidePresentation();
    </script>
</body>
</html>
```

## Required JavaScript Features

Every presentation must include:

1. **SlidePresentation Class** — Main controller with:
   - Keyboard navigation (arrows, space, page up/down)
   - Touch/swipe support
   - Mouse wheel navigation
   - Optional progress indicator or page count, kept outside the slide stage

2. **Stage Scaling** — For fixed 16:9 presentation behavior:
   - Keep all slides at 1920×1080 inside `.deck-stage`
   - Scale the whole stage with one transform
   - Letterbox/pillarbox as needed; never reflow slide content per device
   - Reserve space for visible viewer controls before computing the scale;
     chrome must sit outside the authored slide, including at smaller windows.
   - Preserve native Enter/Space on controls and editing keys in text inputs.
     Global slide shortcuts ignore interactive/editable targets, IME composition
     and modifier shortcuts. Expose the page count as a polite live status and
     mark unavailable previous/next actions at deck boundaries.

3. **Optional Enhancements** (match the requested output: HTML preserves interaction; PDF is static. Add hover/cursor effects only when they help the requested browser experience):
   - Particle system background (canvas)
   - Counter animations

4. **Inline Editing** (NOT included by default; add only when the user explicitly asks for in-browser click-to-edit):
   - Edit toggle button (hidden by default, revealed via hover hotzone or `E` key)
   - Auto-save to localStorage
   - Export/save file functionality
   - See "Inline Editing Implementation" section below

## Inline Editing Implementation

Inline editing is NOT included by default; add it only when the user explicitly asks for in-browser click-to-edit (this matches workflow.md Phase 6 — the standard text-edit loop is `edit_texts.py`, not an in-browser editor). Do not ask the user about it during the pre-generation Q&A. If the user does ask for it, the snippets below cover the toggle UI; the `editor` object they call (`editor.toggleEditMode()`, `editor.isActive`) is NOT defined here — implement it yourself (contenteditable toggling on text nodes, localStorage persistence, a save/export action).

If that save/export collects text from more than one slide, it must not read it by on-screen visibility. Inactive slides are hidden with `visibility:hidden` (`viewport-base.css`), and `element.innerText` returns `''` for a `visibility:hidden` element, so an `innerText` harvest run from slide 1 collects empty strings for the other slides and silently blanks them on save — a data-loss bug a computed-style check will not catch. Read from the editor's own data model, or use `textContent` over every slide regardless of active state; `textContent` keeps the text under any CSS hiding but drops the line breaks `innerText` would give, so preserve newline semantics for multi-line fields. Acceptance: after saving an edit made on slide 1, reopen the actually-written file (not the live DOM or `localStorage`, which can mask a file that never updated) and confirm slide 1's new text is present and slides 2..N are intact; a cancelled or failed save must not report success, and a downloaded copy must be labelled an export, not the saved source.

**Do NOT use CSS `~` sibling selector for hover-based show/hide.** The CSS-only approach (`edit-hotzone:hover ~ .edit-toggle`) fails because `pointer-events: none` on the toggle button breaks the hover chain: user hovers hotzone -> button becomes visible -> mouse moves toward button -> leaves hotzone -> button disappears before click.

**Required approach: JS-based hover with 400ms delay timeout.**

HTML:
```html
<div class="edit-hotzone"></div>
<button class="edit-toggle" id="editToggle" title="Edit mode (E)">✏️</button>
```

CSS (visibility controlled by JS classes only):
```css
/* Do NOT use CSS ~ sibling selector for this!
   pointer-events: none breaks the hover chain.
   Must use JS with delay timeout. */
.edit-hotzone {
    position: fixed; top: 0; left: 0;
    width: 80px; height: 80px;
    z-index: 10000;
    cursor: pointer;
}
.edit-toggle {
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s ease;
    z-index: 10001;
}
.edit-toggle.show,
.edit-toggle.active {
    opacity: 1;
    pointer-events: auto;
}
```

JS (three interaction methods):
```javascript
// 1. Click handler on the toggle button
document.getElementById('editToggle').addEventListener('click', () => {
    editor.toggleEditMode();
});

// 2. Hotzone hover with 400ms grace period
const hotzone = document.querySelector('.edit-hotzone');
const editToggle = document.getElementById('editToggle');
let hideTimeout = null;

hotzone.addEventListener('mouseenter', () => {
    clearTimeout(hideTimeout);
    editToggle.classList.add('show');
});
hotzone.addEventListener('mouseleave', () => {
    hideTimeout = setTimeout(() => {
        if (!editor.isActive) editToggle.classList.remove('show');
    }, 400);
});
editToggle.addEventListener('mouseenter', () => {
    clearTimeout(hideTimeout);
});
editToggle.addEventListener('mouseleave', () => {
    hideTimeout = setTimeout(() => {
        if (!editor.isActive) editToggle.classList.remove('show');
    }, 400);
});

// 3. Hotzone direct click
hotzone.addEventListener('click', () => {
    editor.toggleEditMode();
});

// 4. Keyboard shortcut (E key, skip when editing text)
document.addEventListener('keydown', (e) => {
    if ((e.key === 'e' || e.key === 'E') && !e.target.getAttribute('contenteditable')) {
        editor.toggleEditMode();
    }
});
```

## Reserved Chrome Class Names

`scripts/export_pdf.py` hides presentation chrome during PDF export with `display:none !important`. The reserved names (copied from its `EXPORT_CSS`):

- Classes: `.deck-controls`, `.deck-control`, `.deck-nav`, `.deck-navigation`, `.deck-progress`, `.progress`, `.progress-bar`, `.slide-nav`, `.slide-counter`, `.page-counter`, `.nav-dots`, `.edit-toggle`, `.edit-hotzone`, `.edit-mode-banner`, `.boot-check`, `.no-export`, `.no-print`
- Attribute: `[data-export-hide]`

Rules:

- Use these names ONLY for chrome that must disappear from the PDF (navigation, counters, edit UI).
- NEVER use them for design elements inside a slide — a KPI bar named `.progress-bar` or a poster trim named `.progress` silently vanishes from the delivered PDF.
- For compositional elements that look like progress bars (e.g. a persistent bottom strip that is part of the poster design), use a non-reserved name such as `.poster-trim`.
- Conversely, `[data-export-hide]` / `.no-export` are the sanctioned way to mark anything else that must not appear in the PDF.

## Image Pipeline (For Planned Visuals)

Process supplied, sourced, or generated images when the visual brief calls for
them. Text-only input is not a reason to skip planned images; follow
`references/visual-evidence.md` before final HTML composition.

**Dependency:** `pip install Pillow`

### Image Processing

```python
from PIL import Image, ImageDraw

# Circular crop (for logos on modern/clean styles)
def crop_circle(input_path, output_path):
    img = Image.open(input_path).convert('RGBA')
    w, h = img.size
    size = min(w, h)
    left, top = (w - size) // 2, (h - size) // 2
    img = img.crop((left, top, left + size, top + size))
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    img.putalpha(mask)
    img.save(output_path, 'PNG')

# Resize for the authored display box without destroying text/chart detail.
# Never upscale. Use lossless=True for charts, UI, and text screenshots.
def resize_for_display(input_path, output_path, display_w, display_h,
                       export_scale=2, lossless=True):
    img = Image.open(input_path)
    target = (int(display_w * export_scale), int(display_h * export_scale))
    if img.width > target[0] or img.height > target[1]:
        img.thumbnail(target, Image.LANCZOS)
    if lossless:
        img.save(output_path, "PNG", optimize=True)
    else:
        img.convert("RGB").save(
            output_path, "JPEG", quality=92, subsampling=0, optimize=True
        )
```

| Situation | Operation |
|-----------|-----------|
| Chart, UI, or text screenshot | Crop first; preserve at least 2× its authored display box and save lossless PNG |
| Photo | Resize to about 2× its authored display box; JPEG quality 92/subsampling 0 is acceptable |
| Logo | Prefer original SVG or transparent PNG; never enlarge a small raster logo |
| Wrong aspect ratio | Crop intentionally before resizing; keep the subject/data region visible |

Do not resize based on file size alone. A 1MB chart can need more pixels than a
10MB photo because thin lines and text must survive the final 2× PDF capture.

Save processed images with `_processed` suffix. Never overwrite originals.

### Image Placement

Use relative local assets for a folder delivery; embed assets for a requested
single HTML file. Keep source/license notices available in either form:

```html
<img src="assets/logo_round.png" alt="Logo" class="slide-image logo">
<img src="assets/screenshot.png" alt="Screenshot" class="slide-image screenshot">
```

```css
.slide-image {
    max-width: 100%;
    max-height: 400px; /* fixed px — no viewport units inside the fixed 1920×1080 stage */
    object-fit: contain;
    border-radius: 8px;
}
.slide-image.screenshot {
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}
.slide-image.logo {
    max-height: 200px;
}
```

**Adapt border/shadow colors to match the chosen style's accent.** Never repeat the same image on multiple slides (except logos on title + closing).

**Placement patterns:** Logo centered on title slide. Screenshots in two-column layouts with text. Full-bleed images as slide backgrounds with text overlay (use sparingly).

---

## Code Quality

**Comments:** Every section needs clear comments explaining what it does and how to modify it.

**Accessibility:**
- Semantic HTML (`<section>`, `<nav>`, `<main>`)
- Keyboard navigation works fully
- ARIA labels where needed
- `prefers-reduced-motion` support (included in viewport-base.css)

## File Structure

Single presentations:
```
presentation.html    # Self-contained, all CSS/JS inline
assets/              # Images only, if any
```

Multiple presentations in one project:
```
[name].html
[name]-assets/
```
