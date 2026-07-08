# CvFoundry

Profile-driven, provenance-safe resume tailoring with deterministic HTML, editable ODT,
and tagged PDF/UA output. Version 3 separates factual content, editorial policy, and visual
design so another person can create a profile without changing Python code.

## Quick start

```bash
./jobs-tailor init profiles/my-profile
# Replace the scaffold facts in profiles/my-profile/CV.md.
# Choose sections/page budgets in resume.json and visual tokens in themes/*.json.
./jobs-tailor validate --profile profiles/my-profile
./jobs-tailor prepare --profile profiles/my-profile --job job-description.md --out output/run
# An agent writes output/run/tailoring-payload.json from tailoring-brief.json.
./jobs-tailor build --profile profiles/my-profile \
  --payload output/run/tailoring-payload.json --out output/run
./jobs-tailor check --profile profiles/my-profile --out output/run --reinspect
```

The same commands run in the pinned container:

```bash
docker compose run --rm jobs-tailor validate --profile profiles/my-profile
```

See [the onboarding guide](docs/ONBOARDING.md) and the validated
`profiles/john-doe` Rust developer profile for a complete shareable example.

## Source and configuration contract

- `profiles/<name>/CV.md` is the sole factual source.
- `profiles/<name>/Writing-Style.md` controls voice only.
- `profiles/<name>/resume.json` controls contact fields, eligible sections, ordering,
  one/two-page targets, selection budgets, and rewrite permissions.
- `themes/<theme>.json` controls local fonts, colors, page geometry, typography, and
  bounded comfortable/compact spacing.
- `tailoring-payload.json` contains only agent decisions. Generated JSON, HTML, ODT,
  PDF, and validation reports are disposable derivatives.

Supported section types are `summary`, `timeline`, `portfolio`, `publications`,
`credentials`, `bullets`, `education`, and `skills`. The bundled profile scaffold shows
Projects, Open Source, and Publications together in one `CV.md`; only sections enabled
in `resume.json` are eligible for a run.

For a two-page target, preparation exposes the maximum configured source-backed content.
The renderer first uses comfortable spacing and retries with configured compact spacing
only when necessary. It never invents filler or silently removes content. A shorter result
with no additional eligible content is reported as `source-limited`.

## Resume rules

`profiles/<name>/resume.json` is authoritative for content and page rules. The values
actually applied to a run are written to `effective-policy.json` and embedded in
`tailoring-brief.json`. A compact `decision-report.json` records resolved counts,
selected IDs, final page use, spacing, whitespace, and revision suggestions.

| Setting | Effect |
| --- | --- |
| `document.targetPages` | Desired length: `1` resolves preferred budgets; `2` resolves maximum budgets. |
| `document.maxPages` | Hard PDF page cap. Must be at least `targetPages`. |
| `sections` | Exact inclusion and rendered order. Omitted sections cannot enter any output. |
| `sections[].selection.mode` | `all` uses all eligible items; `ranked` requires the resolved number of payload selections; `explicit` starts with required IDs. |
| `selection.entries` | Minimum, preferred, and maximum entries for the section, clamped to eligible CV items. |
| `selection.bulletsPerEntry` | Per-entry bullet budget, independently clamped to each source entry. |
| `selection.itemsPerEntry` | Per-category skill item budget. |
| `selection.requiredSourceIds` / `excludedSourceIds` | Mandatory or forbidden source IDs. |
| `layout.maximumSummaryLines` | Maximum rendered summary lines. |
| `layout.maximumBulletLines` | Maximum rendered lines for each bullet. |
| `layout.maximumSkillRowLines` | Maximum rendered lines for each skill row. |
| `layout.maximumIntermediatePageWhitespaceMm` | Rejects premature breaks on non-final pages; defaults to 25 mm. |
| `theme` | Selects `themes/<theme>.json`, which owns fonts, colors, margins, type scale, and bounded spacing. |

One-page configuration:

```json
{"document": {"pageSize": "A4", "targetPages": 1, "maxPages": 1}}
```

Expanded two-page configuration:

```json
{"document": {"pageSize": "A4", "targetPages": 2, "maxPages": 2}}
```

Budget resolution never creates filler. For example, if a two-page run resolves five
bullets but a selected CV entry has only three, that entry receives three. Sections and
entries flow sequentially across pages; only headings with their first content and entry
headers with their first bullet are kept together.

## Agent-neutral workflow

`prepare` creates `tailoring-brief.json` with deterministic JD rankings, eligible source
IDs, budgets, exclusions, and page goals. Any agent may author the documented v3 payload;
the project does not bundle an LLM SDK or require an API key. `build` validates provenance,
assembles locked facts, renders atomically, and writes `layout-validation.json` v4.

Versioned JSON schemas live under `schemas/`. Legacy v2 payloads can be converted with:

```bash
./jobs-tailor migrate-v2 --payload old-payload.json --out tailoring-payload.json
```

The migration is idempotent. Existing scripts remain available as a one-release
compatibility surface.

The public default is the fictional `profiles/john-doe` Rust developer profile. Every
profile is self-contained; the pipeline never depends on an untracked private CV.

The pipeline parses stable provenance IDs from human-readable Markdown, ranks experience and projects against a job description, validates supported claims, creates semantic HTML and editable ODT, then exports a tagged PDF/UA document through LibreOffice Writer.

## Requirements

- Python 3.11+ with LibreOffice UNO bindings
- LibreOffice Writer 24.2+ (native verification also covers 26.2)
- Poppler: `pdfinfo`, `pdftotext`, `pdffonts`, `pdftoppm`
- Fontconfig and the bundled Gelasio fonts

Check the environment:

```bash
python3 scripts/doctor.py
```

## Commands

```bash
python3 scripts/generate_fit_summary.py job-description.md profiles/john-doe/CV.md output/run
python3 scripts/install_output_runner.py output/run
python3 scripts/assemble_resume.py output/run/tailoring-payload.json output/run/tailored-resume.json
python3 scripts/generate_resume.py output/run/tailored-resume.json output/run
python3 scripts/check_resume_quality.py output/run
python3 -m unittest discover -s tests -v
```

Each output folder includes the raw JD, fit report, effective policy, compact agent-authored tailoring payload, assembled resume JSON, semantic HTML preview, editable ODT, tagged PDF, final-PDF validation report, a thin regeneration wrapper, and tailoring notes. When outreach is requested, the folder also includes a deterministic `email-draft.md` and `email-metadata.json`.

`CV.md` is the only factual source. `Writing-Style.md` may shape phrasing but cannot add facts. Generated JSON, HTML, ODT, and PDF files are disposable derivatives.

The agent writes only `tailoring-payload.json`: job title, summary and provenance,
selected source IDs, permitted source-backed bullet rewrites, and skill priorities.
Deterministic assembly injects contacts, dates, organizations, links, configured locked
sections, schema metadata, and source hashes.

Generation uses an output lock, isolated LibreOffice profiles, temporary artifacts, and atomic replacement. QA re-inspects the final PDF for provenance, tags, PDF/UA metadata, Writer/LibreOffice metadata, configured dimensions and page count, reading order, embedded configured fonts, links, wrapping, and per-page whitespace.

Email drafting is contract-based as well: `config/email-policy.json` defines subject and body constraints, and `references/email-contract.md` defines the required artifacts and template.

## License

CvFoundry is licensed under the MIT License. Bundled Gelasio font files are licensed
separately under the SIL Open Font License 1.1; see `assets/fonts/OFL.txt`.
