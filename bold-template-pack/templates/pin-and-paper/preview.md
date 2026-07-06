# Pin & Paper Preview Card

Use this small file for title-slide previews only. For final deck generation, read this template's full `design.md` after selection.

## Selection Metadata

- Slug: `pin-and-paper`

## Visual Snapshot

A field-notebook editorial system rendered as yellow legal-pad paper with deep cobalt-blue ink. Every slide carries a fractalnoise paper-grain overlay, hand-drawn safety-pin SVG illustrations that "pin" cards to the page, and a hand-script Caveat face for personal annotations. Space Grotesk at heavy weights carries the printed headlines; DM Mono handles archival labels. The aesthetic borrows from analog field reports, vintage public-notice boards, and the diary pages of scientific notebooks — closer to a lab journal pinned to a corkboard than a polished deck.

Pin & Paper is a field-notebook editorial system built on a single material premise: every slide is yellow legal-pad paper. The paper is rendered through a base color (#EFE56A — saturated cadmium yellow), two soft radial-gradient highlights (upper-left light, lower-right shadow), and a non-optional fractal-noise grain overlay on a ::before pseudo-element with multiply blend. This stack creates a surface that reads as physical paper under raking light. Without the grain, the system collapses into flat cartoon-yellow; the texture is foundational, not decorative.

## Preview Ingredients

- Palette: paper #EFE56A; paper-2 #F5ECA0; paper-3 #E8D85A; paper-extra #FBE6A4; cream #F8F1D6; kraft #C9A66B; ink #1F3A8A; ink-soft #2D4FB8
- Typography: Space Grotesk; Caveat; DM Mono
- Signature move: Yellow paper background (`paper-surface`) with two layered radial gradients and a non-optional fractal-noise grain overlay (`paper-grain-overlay`) on every slide.
- Signature move: Deep cobalt-blue ink (#1F3A8A) as the universal text, border, divider, and pin-illustration color.
- Signature move: Cream card surfaces (#F8F1D6) with 1.5px ink borders, 4px micro-radius, and a hard ink-blue offset shadow (5px–6px, zero blur).
- Signature move: Hand-drawn safety-pin SVG illustrations (`pin-illustration`) — closed and open variants — pinned to cards at slight rotation angles.
- Signature move: Three-voice typography: Space Grotesk for print headlines, Caveat hand-script for personal voice, DM Mono for archival labels.
