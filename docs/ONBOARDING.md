# Create and share a profile

1. Run `./jobs-tailor init profiles/<name>`.
2. Replace every example fact in `CV.md`; keep each `cv` source ID unique and stable.
3. Edit `resume.json` to choose the page target, section order, selection modes, and budgets.
4. Select or copy a theme under `themes/`; font files must remain local.
5. Run `./jobs-tailor doctor --profile profiles/<name>` and then `validate`.
6. Run `prepare`, author the small v3 payload from its brief, then run `build` and `check --reinspect`.

Start with `profiles/john-doe` to see a complete fictional Rust developer profile. Do not present its placeholder identity or claims as real.

## Inspect what happened

- `effective-policy.json` is the complete resolved machine policy.
- `decision-report.json` is the compact audit trail: available and resolved counts, selected IDs, page result, spacing choice, whitespace, and suggestions.
- `layout-validation.json` contains detailed PDF geometry, font, link, accessibility, and overflow checks.

For a two-page resume, set both `document.targetPages` and `document.maxPages` to `2`. The resolver then uses maximum budgets; it never creates filler when the CV has less content.
