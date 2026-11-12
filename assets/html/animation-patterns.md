# Animation Patterns Reference

Use this reference when generating presentations. Match animations to the intended feeling.

## Effect-to-Feeling Guide

| Feeling | Animations | Visual Cues |
|---------|-----------|-------------|
| **Dramatic / Cinematic** | Slow fade-ins (1-1.5s), large scale transitions (0.9 to 1), parallax scrolling | Dark backgrounds, spotlight effects, full-bleed images |
| **Techy / Futuristic** | Neon glow (box-shadow), glitch/scramble text, grid reveals | Particle systems (canvas), grid patterns, monospace accents, cyan/magenta/electric blue |
| **Playful / Friendly** | Bouncy easing (spring physics), floating/bobbing | Rounded corners, pastel/bright colors, hand-drawn elements |
| **Professional / Corporate** | Subtle fast animations (200-300ms), clean slides | Navy/slate/charcoal, precise spacing, data visualization focus |
| **Calm / Minimal** | Very slow subtle motion, gentle fades | High whitespace, muted palette, serif typography, generous padding |
| **Editorial / Magazine** | Staggered text reveals, image-text interplay | Strong type hierarchy, pull quotes, grid-breaking layouts, serif headlines + sans body |

## Entrance Animations

```css
/* Fade + Slide Up (most versatile) */
.reveal {
    opacity: 0;
    transform: translateY(30px);
    transition: opacity 0.6s var(--ease-out-expo),
                transform 0.6s var(--ease-out-expo);
}
.visible .reveal {
    opacity: 1;
    transform: translateY(0);
}

/* Scale In */
.reveal-scale {
    opacity: 0;
    transform: scale(0.9);
    transition: opacity 0.6s, transform 0.6s var(--ease-out-expo);
}

/* Slide from Left */
.reveal-left {
    opacity: 0;
    transform: translateX(-50px);
    transition: opacity 0.6s, transform 0.6s var(--ease-out-expo);
}

/* Blur In */
.reveal-blur {
    opacity: 0;
    filter: blur(10px);
    transition: opacity 0.8s, filter 0.8s var(--ease-out-expo);
}
```

## Background Effects

```css
/* Gradient Mesh — layered radial gradients for depth */
.gradient-bg {
    background:
        radial-gradient(ellipse at 20% 80%, rgba(120, 0, 255, 0.3) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 20%, rgba(0, 255, 200, 0.2) 0%, transparent 50%),
        var(--bg-primary);
}

/* Noise Texture — inline SVG for grain */
.noise-bg {
    background-image: url("data:image/svg+xml,..."); /* Inline SVG noise */
}

/* Grid Pattern — subtle structural lines */
.grid-bg {
    background-image:
        linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size: 50px 50px;
}
```

## Interactive Effects

The deliverable is a static screenshot PDF — hover/cursor effects (3D tilt, cursor trails, magnetic buttons) are invisible in it. Skip them; add only when the user explicitly asks for an in-browser HTML presentation experience.

## Export Contract (export_pdf.py)

The PDF exporter neutralizes animations so screenshots always capture the final state:

- It globally deactivates CSS `transition`/`animation` (zero duration and delay), so entrance animations snap to their end state before capture.
- It force-reveals elements matching `[class*="reveal"]`, `[data-reveal]`, `[data-anim]`, `.fade-in`, `.animate`, `.anim` (sets `opacity:1; transform:none; visibility:visible`).

Therefore: name entrance-animation classes within this convention (`.reveal`, `.reveal-scale`, `.reveal-left`, `.reveal-blur`, or `data-reveal`/`data-anim` attributes). A hidden-by-default element with a name outside this list may be captured invisible.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Fonts not loading | Check Fontshare/Google Fonts URL; ensure font names match in CSS |
| Animations not triggering | Verify the navigation controller adds `.visible`/`.active` to the `.slide` when switching pages |
| Mobile issues | The whole stage scales with one `transform` — do not write breakpoint media queries; reduce particle count if needed |
| Performance issues | Use `will-change` sparingly; prefer `transform`/`opacity` animations; throttle scroll handlers |
