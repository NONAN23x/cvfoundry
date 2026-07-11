---
name: jobs-tailoring
description: Tailor a configured profile for a supplied job description, preserving factual provenance and producing validated HTML, ODT, and tagged PDF artifacts.
---

# Jobs Tailoring

Use for `/jobs-tailor`, resume-tailoring requests, or pasted job descriptions.

## Read First

1. `profiles/<profile>/CV.md` - sole factual source
2. `profiles/<profile>/Writing-Style.md` - voice only
3. `profiles/<profile>/resume.toml` - profile rules
4. `themes/<theme>.json` - presentation policy
5. `config/email-policy.json` when an email draft is requested
6. `references/tailoring-rules.md`
7. `references/output-contract.md`
8. `references/email-contract.md` when an email draft is requested

Never copy personal facts from another file. Stable IDs and project metadata are stored in compact `<!-- cv: {...} -->` comments inside `CV.md`.

## Non-Negotiable Rules

- Never invent or broaden experience, scope, metrics, dates, employers, certifications, links, or tools.
- Obey the selected profile's `resume.toml` and generated `effective-policy.json`.
- Retain `sourceId` on every selected entry and bullet. Provide non-empty `summarySourceIds`.
- Write only dynamic decisions to `tailoring-payload.json`.
- Omit deterministic `mode = "ordered"` sections from the payload; code copies their resolved CV-order entries.
- Never reproduce locked contact details, dates, entry metadata, assembled schema metadata, or source hashes in the payload.
- Tailor through selection, ordering, compact rewrites, and truthful terminology alignment.
- Keep the final headline to exactly one prominent role title.
- Experience order is deterministic and follows canonical CV chronology.
- Final acceptance for normal agent runs comes from `jobs-tailor check --reinspect` and generated validation artifacts. Do not open Chrome, Browser Connector, Computer Use, screenshots, rendered PNGs, or any other manual visual audit unless the user explicitly asks for visual/layout inspection.

## Workflow

```bash
uv run jobs-tailor first-run --profile <profile-dir>
uv run jobs-tailor validate --profile <profile-dir>
uv run jobs-tailor explain-rules --profile <profile-dir>
uv run jobs-tailor prepare --profile <profile-dir> --job <job-description> --out <output-dir>
```

If `first-run` fails, stop and ask the user to finish profile setup. Create schema-v3 `tailoring-payload.json` from `tailoring-brief.json` and `payload-skeleton.json` with only permitted editorial decisions. Then run:

```bash
uv run jobs-tailor build --renderer auto --profile <profile-dir> --payload <output-dir>/tailoring-payload.json --out <output-dir>
uv run jobs-tailor check --profile <profile-dir> --out <output-dir> --reinspect
```

Revise only the payload and rerun until QA passes. Use `uv run jobs-tailor status --out <output-dir>` or `uv run jobs-tailor inspect-run --out <output-dir>` to understand current state. Do not add a separate agent visual-audit step unless the user asks for one.

Use lowercase kebab-case folders:
`output/<company>-<role>-YYYY-MM-DD/`

## Runtime Contracts

- `uv run jobs-tailor prepare ...` writes the deterministic brief and effective policy.
- `uv run jobs-tailor build ...` assembles, renders, and validates artifacts.
- `uv run jobs-tailor rerun --out <output-dir>` rebuilds from the current payload.
- Generation is atomic and locked per output folder.
- Rendering uses an isolated LibreOffice profile; Docker is acceptable for the renderer environment.
