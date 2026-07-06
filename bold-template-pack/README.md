# Bold Template Pack

Maintainer notes for the bold-template-pack. Runtime selection/usage rules live
in SKILL.md and references/workflow.md — this file is not read during deck
generation.

## Pack Origin

The pack imports the `beautiful-html-templates` design systems
(`zarazhangrui/beautiful-html-templates`) into the `deck-forge` skill without
making them the default for every deck. The full source metadata index and the
source `template.html` files are not bundled in the user-facing skill; if a
selected `design.md` lacks a critical implementation detail, reconstruct it
from the `html-template.md` architecture plus the `design.md` token tables —
do not search externally.

## Contents

- `selection-index.json` — compact metadata index (slug, tagline,
  `differs_from`, mood, tone, formality, density, scheme, best_for, avoid_for)
  for all 34 templates. The only file read during shortlist.
- `templates/<slug>/preview.md` — lightweight style card used to build the
  title-slide preview for a shortlisted template.
- `templates/<slug>/design.md` — full design-system reference (YAML token
  front matter plus prose), read only for the single chosen template.

## Maintenance Notes

- Keep `selection-index.json` in sync with `templates/`: one entry per
  directory, matching `template_count`, valid `preview_md`/`design_md` paths,
  and a short `differs_from` line distinguishing each template from its
  nearest aesthetic neighbor.
- Each `design.md` must stay self-sufficient for generation: complete color
  and typography token tables in the front matter, a full Google Fonts
  `<link>` in its Loading section, CJK pairing guidance, and the "deck-forge
  Fixed-Stage Policy" paragraph near the top.
- Each `preview.md` carries only template-specific content: slug, Visual
  Snapshot, Preview Ingredients, and template-specific notes. Shared preview
  rules live in `references/workflow.md` Phase 2 — do not re-add per-file
  boilerplate.
- The templates were extracted by hand-distilling each source template into
  `design.md` token tables and prose; there is no regeneration script in this
  repo. Edits are maintained directly in these files.
