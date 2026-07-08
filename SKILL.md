---
name: jobs-tailoring
description: Tailor a configured profile for a supplied job description, preserving factual provenance and producing validated HTML, ODT, and tagged PDF artifacts.
---

# Jobs Tailoring

Use for `/jobs-tailor`, resume-tailoring requests, or pasted job descriptions.

## Read First

1. `profiles/<profile>/CV.md` - sole factual source
2. `profiles/<profile>/Writing-Style.md` - voice only
3. `profiles/<profile>/resume.json` - content/page policy
4. `themes/<theme>.json` - presentation policy
5. `config/email-policy.json` when an email draft is requested
6. `references/tailoring-rules.md`
7. `references/output-contract.md`
8. `references/email-contract.md` when an email draft is requested

Never copy personal facts from another file. Stable IDs and project metadata are stored in compact `<!-- cv: {...} -->` comments inside `CV.md`.

## Non-Negotiable Rules

- Never invent or broaden experience, scope, metrics, dates, employers, certifications, links, or tools.
- Include only sections enabled by the profile configuration and obey each section's source-ID and content budgets.
- Retain `sourceId` on every selected entry and bullet. Provide non-empty `summarySourceIds`.
- Write only the payload schema version and dynamic decisions to `tailoring-payload.json`. Never reproduce locked contact details, dates, entry metadata, assembled schema metadata, or source hashes.
- Tailor through selection, ordering, compact rewrites, and truthful terminology alignment.
- Keep the final headline to exactly one prominent role title. Do not combine role labels with `&`, `/`, or `and`.
- The agent should copy the user-provided job title into `tailoring-payload.json` as `jobTitle`; the assembler uses that title directly instead of inferring one from the JD.
- Experience order is deterministic and follows canonical CV chronology.
- Keep the summary to one through three rendered PDF lines. It must read as a calm, confident elevator pitch about professional identity, strongest capabilities, working character, and value—not as a list of projects or tasks.
- Obey configured line limits: compact one-page profiles normally use one-line bullets; expanded profiles may permit two.
- Produce the configured one- or two-page A4/Letter portrait document. Final acceptance comes from PDF inspection, not prose length or HTML appearance.

## Workflow

1. Run `./jobs-tailor validate --profile <profile-dir>`.
2. Run `./jobs-tailor prepare --profile <profile-dir> --job <job-description> --out <output-dir>`.
3. Create schema-v3 `tailoring-payload.json` from `tailoring-brief.json` with only permitted editorial decisions.
4. Complete three content passes: truthful ATS coverage, concise human wording, then redundancy and one-line-fit cleanup.
5. Select the configured number of strongest entries and retain only supported wording.
6. Run `./jobs-tailor build --profile <profile-dir> --payload <payload> --out <output-dir>`; revise only the payload and rerun until QA passes.
7. Write concise `tailoring-notes.md` covering company, role, matched terms, meaningful edits, honest gaps, and style influence.
8. If the workflow or user requests outreach, create deterministic `email-draft.md` and `email-metadata.json` using `references/email-contract.md`.

Use lowercase kebab-case folders:
`output/<company>-<role>-YYYY-MM-DD/`

## Runtime Contracts

- `scripts/generate_fit_summary.py <job-description> <CV.md> <output-dir>`
- `scripts/assemble_resume.py <tailoring-payload.json> <tailored-resume.json> [--cv CV.md]`
- `scripts/generate_resume.py <tailored-resume.json> <output-dir> [--cv CV.md]`
- `scripts/check_resume_quality.py <output-dir> [--cv CV.md]`
- `scripts/doctor.py`

Generation is atomic and locked per output folder. It uses an isolated LibreOffice profile and only replaces successful artifacts. The PDF must report `Creator: Writer`, a LibreOffice producer, tags, PDF/UA metadata, the configured embedded font, configured page geometry/count, valid reading order, and current source hashes.
