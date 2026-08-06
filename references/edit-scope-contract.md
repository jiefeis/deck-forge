# Native edit scope contract

Read this before any source-preserving PPTX change, especially when the user
says "minimal change", names selected pages, limits edits to text, or requires
untouched slides to remain identical.

## Contents

- Freeze the contract
- Baseline before editing
- Edit within scope
- Verify after the final write
- Failure rule

## Freeze the contract

Record these facts before writing the output file:

- exact source and output paths; never edit the only source copy in place
- artifact mode: native edit, not HTML/PDF regeneration
- physical slide indices and stable slide IDs in scope
- visible ordinal, displayed marker, title/content anchor, and mother/reference
  page for every target when hidden or inserted pages exist
- allowed changes: text, run formatting, fill, font, page number, geometry, order,
  hidden state, relationships, or media — list only what the request permits
- forbidden changes: all unlisted slides/properties plus shared masters, layouts,
  themes, and global presentation settings unless explicitly authorized
- page-count/order policy, hidden-backup policy, and whether visible or physical
  numbering is intended
- baseline SHA-256; hash gating and rebaseline follow
  `references/source-contract.md` → "Rebaseline when the user changes the
  source"
- final-delivery rule, including "only one file" when requested

Translate user wording into the narrowest contract. For example, "only change
the text boxes on the named slides" forbids shape movement, background changes,
shared-layout edits, page reordering, and edits to every other slide.

## Baseline before editing

Create a read-only manifest and retain it outside the delivery folder:

```bash
python <skill-root>/scripts/audit_pptx_structure.py manifest <before.pptx> \
  --json -o <scratch>/before-manifest.json
```

Record target slide IDs from the manifest. Use physical page numbers only as a
human-facing label; true slide order and stable IDs guard against reordered or
hidden pages.

When a mother draft, visible-only reference, or hidden/inserted pages are
involved, build the page-address ledger per
`references/native-redesign-fidelity.md` → "Keep four page identities
separate" and record how the user's wording maps to it.

If the task adds newly authored slides, merges slides from another deck, or
fills template pages, also baseline typography with
`scripts/audit_pptx_typography.py` and report same-role font/size
inconsistencies to the user before mutating — see
`references/pptx-native-editing.md` → "Typography baseline when adding or
merging slides".

## Edit within scope

- Work on a copy and write to the agreed output path.
- Prefer slide-local edits. Do not modify shared layout/master/theme parts to fix
  one page.
- Duplicate and hide originals only when requested. Keep backup slides outside
  the visible sequence policy and preserve their `show=0` state.
- For a text-only task, edit text runs and explicitly authorized run properties;
  do not replace the whole slide with an image or reconstruct its layout.
- If the required fix exceeds the contract, stop and ask before broadening it.

## Verify after the final write

Run the structural comparison with the authorized slide set. Page-level
authorization alone is not enough: it permits every property on that page.
Create a narrow property scope such as:

```json
{
  "version": 1,
  "rules": [
    {
      "id": "style-only",
      "pages": "3,7",
      "properties": ["background", "color", "typography"]
    }
  ]
}
```

Rules may select physical source `pages` and/or stable `slide_ids`. For an
explicit insertion, use `target_pages` or `target_slide_ids` with `order`; these
selectors are resolved only against the final deck. Property names are explicit;
wildcards, unknown fields, overlapping claims, invalid selectors, and entirely
unused rules fail closed.

Available property families are `text`, `typography`, `color`, `background`,
`geometry`, `shape-tree`, `relationships`, `media-data`, `notes`, `timing`,
`hidden`, `order`, and `other`. A shared master/layout/theme or global slide-size
change always fails this narrow audit; use a separately reviewed workflow when
the user explicitly authorizes a shared-system change.

```bash
python <skill-root>/scripts/audit_pptx_structure.py compare \
  <before.pptx> <after.pptx> --allow-slides <target-pages>

python <skill-root>/scripts/audit_pptx_properties.py \
  <before.pptx> <after.pptx> --scope <scratch>/scope.json
```

The comparison must fail on unauthorized slide changes, page-count/order drift,
hidden-state drift, or shared master/layout/theme edits unless the command
explicitly allows them. Then:

1. Run the task-specific audits, including page-number or translation checks.
2. Render baseline and final PPTX with the same engine, then run
   `scripts/audit_rendered_pages.py` with the same authorized slide set.
3. Open/render the final PPTX after the last save and inspect every visible page.
4. For every requested hidden backup, verify both OOXML identity/dependencies
   and rendered pixels with explicit source→backup mapping; never unhide it in
   the deliverable:

   ```bash
   python <skill-root>/scripts/audit_pptx_backups.py \
     <source.pptx> <after.pptx> --map <source-page>:<backup-page>
   python <skill-root>/scripts/audit_rendered_pages.py \
     <scratch/source-render> <scratch/final-hidden-render> \
     --page-map <source-page>:<backup-page>
   ```

   Repeat each mapping option for every backup.
5. Run a zip integrity check (no corrupt members, no duplicate entries),
   confirm the target app opens the file (skip when no GUI app is available;
   rendered-page verification stands in), and confirm the delivery folder
   contains only the requested artifact(s).
6. Hash gating and rebaseline follow `references/source-contract.md` →
   "Rebaseline when the user changes the source".

## Failure rule

Do not waive an audit failure because the contact sheet "looks close". Explain
the authorized exception in the command or fix the output and rerun the check.
