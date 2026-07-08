# AGENTS.md

This repository is CvFoundry: a profile-driven, provenance-safe resume tailoring and
rendering pipeline. Read this file before changing code, profiles, tests, or generated
artifacts.

## Start Here

Read only what the task needs, beginning with:

1. `README.md` for the public workflow.
2. `docs/ONBOARDING.md` for profile and policy setup.
3. `SKILL.md` for tailoring behavior.
4. The selected profile's `CV.md`, `Writing-Style.md`, and `resume.json` for an actual run.
5. `references/output-contract.md` and `references/tailoring-rules.md` when changing pipeline behavior.

## Privacy Boundary

- `profiles/local/` is the default private profile and is ignored by Git and the Docker build context.
- `profiles/private/`, `knowledge-base/`, `.env*`, and `output/` are also private or generated and ignored.
- Never stage, force-add, print, quote, or copy personal profile data into tracked files, tests, logs, or issues.
- Before pushing, inspect `git status`, the staged file list, and the remote tree for private paths.
- `profiles/john-doe/` is fictional public example data. Use it for tests and format guidance only.
- `templates/profile/` is the tracked scaffold copied by `./jobs-tailor init profiles/local`.
- Do not replace private facts with John Doe facts during a real tailoring run.

## Source and Policy Ownership

- A selected profile's `CV.md` is the sole factual source.
- Stable IDs in `<!-- cv: {...} -->` comments must remain unique and traceable.
- `Writing-Style.md` controls voice only; it never authorizes new facts.
- The selected profile's `resume.json` is authoritative for:
  - one- or two-page targets and maximum pages;
  - included section order;
  - selection mode and required or excluded source IDs;
  - entry, bullet, and skill-item budgets;
  - summary, bullet, skill-row, and whitespace limits.
- `themes/<theme>.json` owns fonts, colors, page geometry, typography, bullet geometry, and spacing bounds.
- `templates/profile/resume.json` is the tracked default policy. Personal overrides belong in ignored `profiles/local/resume.json`.

## Non-Negotiable Tailoring Rules

- Never invent or broaden employers, dates, experience, scope, metrics, tools, certifications, links, or claims.
- Include only sections enabled by `resume.json`; omitted sections cannot enter any derivative.
- Preserve source IDs through payload, assembly, rendering, and validation.
- Keep experience in canonical CV chronology.
- Use exactly one prominent job title; do not combine titles with `&`, `/`, or `and`.
- Agents may select, prioritize, and perform source-bounded rewrites only when the profile allows them.
- Deterministic code owns contacts, dates, organizations, links, assembly, presentation, hashes, and QA.
- Never silently remove content, change wording, shrink below configured minimums, or generate filler to force a page fit.

## Normal Workflow

Create the private profile once:

```bash
./jobs-tailor init profiles/local
```

For each job:

```bash
./jobs-tailor doctor
./jobs-tailor validate
./jobs-tailor prepare --job <job-description> --out <run-directory>
./jobs-tailor build --payload <run-directory>/tailoring-payload.json --out <run-directory>
./jobs-tailor check --out <run-directory> --reinspect
```

`prepare` is deterministic and does not call an LLM. The agent-authored v3 payload contains
only the job title, summary with provenance, selected source IDs, permitted bullet rewrites,
and skill priorities.

## Generated Evidence

- `effective-policy.json` records the exact resolved policy.
- `decision-report.json` records selected IDs, page use, spacing, whitespace, and suggestions.
- `layout-validation.json` records geometry, line counts, PDF/UA, tags, fonts, links, reading order, and source hashes.
- HTML, ODT, PDF, assembled JSON, and reports are derivatives. Do not hand-edit them as alternate sources.
- Output generation must remain locked, isolated, atomic, and failure-preserving.

## Rendering and QA

- Support one- and two-page A4 or Letter portrait resumes.
- Let sections flow naturally across pages; keep only headings with their first content and entry headers with their first bullet.
- Search configured spacing from comfortable to compact and choose the least compressed layout that fits.
- Accept genuinely short two-page output as `source-limited`; reject whitespace caused by artificial page breaks.
- PDF acceptance requires configured page limits, embedded configured fonts, valid links, semantic reading order, PDF/UA metadata, Writer/LibreOffice metadata, and current source hashes.
- LibreOffice may fail silently under sandbox restrictions. Distinguish runtime failure from content or layout failure before editing code.

## Development Rules

- Prefer `rg` for search and `apply_patch` for edits.
- Preserve unrelated user changes and ignored private files.
- Keep public examples fictional and use reserved example domains and phone numbers.
- Do not add an LLM SDK, vendor API key, or remote font dependency.
- Keep compatibility wrappers only where documented; new logic belongs in the profile-driven v3 path.
- Update schemas, docs, and tests together when changing public configuration.

## Verification

Run the narrowest relevant test first, then before pushing run:

```bash
python3 -m unittest discover -s tests -v
docker build -t cvfoundry:test .
docker run --rm --entrypoint python3 \
  -e RUN_LIBREOFFICE_INTEGRATION=1 \
  cvfoundry:test -m unittest discover -s tests -v
```

Also verify that a clean tracked export passes, the Docker image contains no private
paths, `git status` is clean, local `main` matches `origin/main`, and GitHub Actions is green.
