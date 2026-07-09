# CvFoundry onboarding

## 1. Create a private profile

```bash
uv sync
uv run jobs-tailor init profiles/local
```

`profiles/local/` is ignored by Git and the Docker build context. It contains:

- `CV.md`: your only factual source.
- `resume.toml`: human-editable tailoring rules.
- `Writing-Style.md`: voice preferences only.

Use `profiles/john-doe/CV.md` as the format reference, then write your own facts in
`profiles/local/CV.md`.

## 2. Configure resume rules

The scaffolded profile starts from `templates/profile/resume.toml`.

Common TOML fields:

| Field | Purpose |
| --- | --- |
| `[document].paper` | `A4` or `LETTER`. |
| `[document].target_pages` | Desired resume length. |
| `[document].max_pages` | Hard PDF page cap. |
| `[header].contact` | Contact fields to show. |
| `[[sections]].id` | CV section source ID. |
| `[[sections]].kind` | Section type such as `timeline`, `portfolio`, `skills`, or `education`. |
| `[[sections]].mode` | `all`, `ranked`, `explicit`, or `ordered`. Use `ordered` for deterministic CV-order sections such as certifications and achievements. |
| `[[sections]].entries` | `{ one_page = ..., two_page = ..., minimum = ... }`. |
| `[[sections]].bullets` | Bullet budget for bullet-bearing sections only. |
| `[[sections]].items_per_category` | Skill item budget for skills sections. |
| `[[sections]].required` / `excluded` | Source IDs that must or must not be used. |
| `[quality]` | Output validation thresholds such as whitespace and contact-line expectations. |
| `theme` | Theme file for fonts, colors, margins, typography, and spacing. |

Example one-page section:

```toml
[[sections]]
id = "projects"
kind = "portfolio"
mode = "ranked"
rewrite = "source-bounded"
entries = { one_page = 2, two_page = 5, minimum = 1 }
bullets = { one_page = 3, two_page = 5, minimum = 1 }
bullet_lines = 1
```

Example two-page document target:

```toml
[document]
paper = "A4"
target_pages = 2
max_pages = 2
```

CvFoundry clamps counts to available CV content and never invents filler.

## 3. Validate and inspect

```bash
uv run jobs-tailor doctor
uv run jobs-tailor first-run
uv run jobs-tailor validate
uv run jobs-tailor explain-rules
```

Fix reported profile, font, runtime, or policy errors before building.

## 4. Prepare and build

```bash
uv run jobs-tailor prepare --job job-description.md --out output/run
uv run jobs-tailor build --renderer auto --payload output/run/tailoring-payload.json --out output/run
uv run jobs-tailor check --out output/run --reinspect
```

`prepare` does not call an LLM. It creates a deterministic brief from the job description
and eligible source IDs plus `payload-skeleton.json`. An agent or person writes the small tailoring payload; CvFoundry
then injects locked facts, renders outputs, and validates provenance and layout.

## 5. Inspect or rerun

```bash
uv run jobs-tailor status --out output/run
uv run jobs-tailor inspect-run --out output/run
uv run jobs-tailor rerun --out output/run
```

Generated evidence:

- `effective-policy.json`: exact resolved rule application.
- `decision-report.json`: selections, page use, spacing, whitespace, and suggestions.
- `layout-validation.json`: PDF geometry, fonts, links, accessibility, and overflow checks.

## 6. Renderer environments

Most commands are native cross-platform Python. LibreOffice rendering is environment-sensitive.
Use the Docker image when native LibreOffice/UNO is missing, especially on Windows.
