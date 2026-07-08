# CvFoundry onboarding

## 1. Create a private profile

```bash
./jobs-tailor init profiles/local
```

`profiles/local/` is ignored by Git and the Docker build context. It contains your private:

- `CV.md`: the only factual source.
- `resume.json`: page, section, entry, and bullet rules.
- `Writing-Style.md`: wording preferences only.

Do not edit the tracked John Doe profile for personal use. Read
`profiles/john-doe/CV.md` to learn the required headings, metadata comments, stable IDs,
links, and bullet format, then write your own facts in `profiles/local/CV.md`.

## 2. Configure resume rules

The scaffolded `profiles/local/resume.json` starts from the tracked
`templates/profile/resume.json` default.

| Rule | Purpose |
| --- | --- |
| `document.targetPages` | Desired length: `1` uses preferred budgets; `2` uses maximum budgets. |
| `document.maxPages` | Hard one- or two-page PDF cap. |
| `sections` | Exact included sections and rendered order. |
| `selection.mode` | `all`, job-ranked selection, or explicit required IDs. |
| `selection.entries` | Minimum, preferred, and maximum entries. |
| `selection.bulletsPerEntry` | Minimum, preferred, and maximum bullets per entry. |
| `selection.itemsPerEntry` | Skill items retained per skill category. |
| `layout.maximumSummaryLines` | Maximum rendered summary lines. |
| `layout.maximumBulletLines` | Maximum rendered lines per bullet. |
| `layout.maximumSkillRowLines` | Maximum rendered lines per skill row. |
| `theme` | Tracked theme containing fonts, colors, geometry, and spacing. |

For two pages, set both `targetPages` and `maxPages` to `2`. CvFoundry expands toward
maximum source-backed budgets and never invents filler.

## 3. Validate

```bash
./jobs-tailor doctor
./jobs-tailor validate
```

Fix every reported profile, font, runtime, or policy error before building.

## 4. Prepare and build

```bash
./jobs-tailor prepare --job job-description.md --out output/run
./jobs-tailor build --payload output/run/tailoring-payload.json --out output/run
./jobs-tailor check --out output/run --reinspect
```

`prepare` does not call an LLM. It creates a deterministic brief from the job description
and eligible source IDs. An agent or person writes the small tailoring payload; CvFoundry
then injects locked facts, renders outputs, and validates provenance and layout.

## 5. Inspect the result

- `effective-policy.json`: exact resolved section, entry, and bullet counts.
- `decision-report.json`: selections, page use, spacing, whitespace, and suggestions.
- `layout-validation.json`: PDF geometry, fonts, links, accessibility, and overflow checks.

Generated resumes stay under ignored `output/`. To intentionally publish a reusable
fictional profile, place it outside `profiles/local/` and review every file before adding it.
