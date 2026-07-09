# AGENTS.md

This repository is CvFoundry: a profile-driven, provenance-safe resume tailoring and rendering pipeline.

## Start Here

Read only what the task needs:

1. `README.md` for the public workflow.
2. `docs/ONBOARDING.md` for profile setup.
3. `SKILL.md` for tailoring behavior.
4. The selected profile's `CV.md`, `Writing-Style.md`, and `resume.toml` for an actual run.
5. `references/output-contract.md` and `references/tailoring-rules.md` when changing pipeline behavior.

## Privacy Boundary

- `profiles/local/` is the default private profile and is ignored by Git and the Docker build context.
- `profiles/private/`, `knowledge-base/`, `.env*`, and `output/` are private or generated and ignored.
- Never stage, force-add, print, quote, or copy personal profile data into tracked files, tests, logs, or issues.
- `profiles/john-doe/` is fictional public example data. Use it for tests and format guidance only.
- `templates/profile/` is the tracked scaffold copied by `uv run jobs-tailor init profiles/local`.

## Source and Rule Ownership

- `CV.md` is the sole factual source.
- `Writing-Style.md` controls voice only; it never authorizes new facts.
- `resume.toml` is the only profile rule file agents should obey for inclusion, order, selection, budgets, and page goals.
- `themes/<theme>.json` owns fonts, colors, page geometry, typography, bullet geometry, and spacing bounds.
- Generated `effective-policy.json`, `decision-report.json`, and `layout-validation.json` show the rules actually applied.

Do not encode profile-specific page counts, bullet counts, or section choices in agent instructions. Read the selected profile rules instead.

## Non-Negotiable Tailoring Rules

- Never invent or broaden employers, dates, experience, scope, metrics, tools, certifications, links, or claims.
- Include only content permitted by the selected profile rules.
- Preserve source IDs through payload, assembly, rendering, and validation.
- Keep experience in canonical CV chronology.
- Use exactly one prominent job title.
- Agents may select, prioritize, and perform source-bounded rewrites only when the profile allows them.
- Sections with `mode = "ordered"` are deterministic: do not include them in `tailoring-payload.json`; the program copies the first resolved CV entries in CV order.
- Deterministic code owns contacts, dates, organizations, links, assembly, presentation, hashes, and QA.
- Never silently remove content, change wording, shrink below configured minimums, or generate filler to force a page fit.

## Normal Workflow

```bash
uv sync
uv run jobs-tailor init profiles/local
uv run jobs-tailor first-run
uv run jobs-tailor doctor
uv run jobs-tailor validate
uv run jobs-tailor prepare --job <job-description> --out <run-directory>
uv run jobs-tailor build --renderer auto --payload <run-directory>/tailoring-payload.json --out <run-directory>
uv run jobs-tailor check --out <run-directory> --reinspect
```

Run `first-run` before tailoring a fresh clone or fresh chat. If it returns `ok: false`, stop and ask the user to finish the profile setup instead of guessing. Use `uv run jobs-tailor explain-rules`, `status`, and `inspect-run` when you need to understand current state before acting.

## Rendering and QA

- Most project commands should stay cross-platform Python.
- LibreOffice/PDF rendering may use Docker when native UNO tooling is missing or unreliable.
- Output generation must remain locked, isolated, atomic, and failure-preserving.
- Let sections flow naturally across pages; keep only structural units together.
- PDF acceptance requires configured page limits, embedded configured fonts, valid links, semantic reading order, PDF/UA metadata, Writer/LibreOffice metadata, and current source hashes.

## Development Rules

- Prefer `rg` for search and `apply_patch` for edits.
- Use uv-native commands: `uv sync`, `uv lock`, and `uv run`; do not use pip or `uv pip`.
- Preserve unrelated user changes and ignored private files.
- Keep public examples fictional and use reserved example domains and phone numbers.
- Do not add an LLM SDK, vendor API key, or remote font dependency.
- Update docs and tests together when changing public configuration.

## Verification

Run the narrowest relevant test first, then before pushing run:

```bash
uv lock --check
uv sync --frozen
uv run python -m unittest discover -s tests -v
docker build -t cvfoundry:test .
docker run --rm --entrypoint uv \
  -e RUN_LIBREOFFICE_INTEGRATION=1 \
  cvfoundry:test run python -m unittest discover -s tests -v
```

Before publishing, verify `git status`, the staged file list, Docker context, and GitHub Actions so private files are not included.
