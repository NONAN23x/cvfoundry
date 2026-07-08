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
- executable `generate-resume.sh` wrapper that delegates to `assets/generate-resume.sh`
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

`tailoring-payload.json` is the only agent-authored resume input. `tailored-resume.json` and all rendered files are deterministic derivatives. Install the wrapper with `python3 scripts/install_output_runner.py <output-dir>`, edit the payload, then rerun `generate-resume.sh`; do not hand-edit assembled JSON, HTML, ODT, or PDF as alternate sources.
