# Retro Windows Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `retro-windows`

## Visual Snapshot

Cover recipe:

- Surface: desktop gray #808080 fills the stage; slide padding 42px 56px 77px 56px keeps the desktop border visible around the chrome.
- Window: one win-window on button-face #D4D0C8 with the beveled-raised treatment — 2px white top/left + 2px black bottom/right plus the double inset shadow.
- Title bar: navy #000080 → #0000A0 horizontal gradient at 7px 14px padding, carrying a 32px win-icon square, an uppercase filename title (`PRESENTATION.EXE`) at 25px weight 700 white, and the `_` `[]` `X` cluster at the right.
- Body: 35px 42px 42px 42px padding; the splash headline centered in Press Start 2P at 35–42px navy, or `{typography.text-xl}` 56px weight 700 navy when the pixel face is skipped.
- Support: a sunken white marquee well with scrolling text, plus an optional raised status strip along the bottom of the window body.
- Texture: the 3px-period CRT scanline overlay at 3% black opacity sits above every element.
- Chrome: nav dots, slide counter, and the VT323 28px nav hint are deck chrome; anything that must survive into the PDF uses a non-reserved class (never `.progress-bar` / `.slide-counter`).

## Preview Ingredients

- Palette: bg-gray #C0C0C0; bg-light #D4D0C8; bg-dark #808080; white #FFFFFF; black #000000; text-dark #222222; blue-navy #000080; blue-bright #0000A0
- Typography: MS Sans Serif
- Signature move: Every slide is a `win-window` — beveled chrome with navy-gradient title bar and three system buttons (_, [], X).
- Signature move: A fixed 3px-period CRT scanline overlay (`crt-overlay`) sits above all content at 3% opacity.
- Signature move: Bevel-based depth: raised (`panel-raised`, `btn-retro`) and sunken (`panel-sunken`, `group-box`) — no blurred shadows.
- Signature move: The font stack is MS Sans Serif / Segoe UI / Tahoma fallback, with Press Start 2P and VT323 as nostalgic accents.
- Signature move: Status colors (green / red / yellow / cyan) carry semantic meaning: green = OK, red = warning, yellow = moderate, cyan = tertiary data.
