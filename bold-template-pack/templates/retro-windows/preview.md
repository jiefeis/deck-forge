# Retro Windows Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `retro-windows`

## Visual Snapshot

A Windows 95 / 98 desktop-OS aesthetic rendered as a presentation system. Every slide is a window — beveled chrome, navy gradient title bar, MS Sans Serif body type, with chart areas, group boxes, and panels arranged as if they were software UI from 1995. The palette is the original Win9x system colors (gray button-face, navy title bars, white sunken inputs) with retro accent hues (DOS green, brick red, mustard yellow, teal cyan) reserved for status text and chart data. Pixel-font (Press Start 2P) and terminal-font (VT323) appear sparingly for nostalgic punctuation. The effect is half playful nostalgia, half functional dashboard — a deck that reads as a software product running on a CRT monitor.

Retro Windows is a Windows 95 / 98 desktop-OS aesthetic rendered as a slide template. Every slide is structured as a win-window — a beveled rectangular chrome with a navy-gradient title bar, three button icons in the upper right (_, [], X), and a body region containing application-style content. The composition is "this slide is software running on a 1995 desktop, and the content is what the software displays." The conceit is total: there are no slide titles in the modern presentation sense, only window titles styled as filenames (README.DOC, DATAVIEW.CSV, METRICS.LOG).

## Preview Ingredients

- Palette: bg-gray #C0C0C0; bg-light #D4D0C8; bg-dark #808080; white #FFFFFF; black #000000; text-dark #222222; blue-navy #000080; blue-bright #0000A0
- Typography: MS Sans Serif
- Signature move: Every slide is a `win-window` — beveled chrome with navy-gradient title bar and three system buttons (_, [], X).
- Signature move: A fixed 3px-period CRT scanline overlay (`crt-overlay`) sits above all content at 3% opacity.
- Signature move: Bevel-based depth: raised (`panel-raised`, `btn-retro`) and sunken (`panel-sunken`, `group-box`) — no blurred shadows.
- Signature move: The font stack is MS Sans Serif / Segoe UI / Tahoma fallback, with Press Start 2P and VT323 as nostalgic accents.
- Signature move: Status colors (green / red / yellow / cyan) carry semantic meaning: green = OK, red = warning, yellow = moderate, cyan = tertiary data.
