# Output Contract

Use `output/<company>-<role>-YYYY-MM-DD/`.

Required files:

- `job-description.md`
- `fit-summary.json`
- `fit-summary.md`
- `tailoring-brief.json`
- `effective-policy.json`
- `decision-report.json`
- `tailoring-payload.json`
- `tailored-resume.json`
- `tailored-resume.html`
- `tailored-resume.odt`
- `<first-name>-<job-title>.pdf`, derived deterministically from the locked CV name and
  tailored headline (for example, `John-Rust-Software-Developer.pdf`)
- `layout-validation.json`
- executable `rerun.py` helper that delegates to `jobs-tailor rerun`
- `tailoring-notes.md`

Conditionally required when email drafting is requested:

- `email-draft.md`
- `email-metadata.json`

A run succeeds only when `jobs-tailor check --profile <profile> --out <run> --reinspect`
returns `ok: true`. The final PDF must meet the configured one- or two-page cap, page
geometry, font, line limits, links, and whitespace bounds; it must also retain semantic
reading order, embedded fonts, PDF/UA tags, Writer/LibreOffice metadata, provenance, and
current source hashes. `effective-policy.json` is the inspectable record of resolved
section, entry, and per-source bullet counts.

`tailoring-payload.json` is the only agent-authored resume input. `tailored-resume.json` and all rendered files are deterministic derivatives. Edit the payload, then run `uv run jobs-tailor rerun --out <output-dir>` or execute the generated `rerun.py`; do not hand-edit assembled JSON, HTML, ODT, or PDF as alternate sources.
