# CvFoundry

CvFoundry automates resume tailoring without turning your CV into mush.
You keep one factual `CV.md`; CvFoundry selects source-backed content for a job,
renders HTML/ODT/PDF, and writes evidence files showing what rules were applied.

## Quick start

```bash
uv sync
uv run jobs-tailor init profiles/local
uv run jobs-tailor first-run
```

Then edit your private profile:

1. Write `profiles/local/CV.md` using [`profiles/john-doe/CV.md`](profiles/john-doe/CV.md) as the example format.
2. Edit `profiles/local/resume.toml` to choose the profile rules for pages, sections, entries, and bullets.
3. Optionally adjust `profiles/local/Writing-Style.md`.

Private profiles and generated outputs are ignored by Git. The published example profile is fictional.

## Tailor a resume

```bash
uv run jobs-tailor first-run
uv run jobs-tailor doctor
uv run jobs-tailor validate
uv run jobs-tailor prepare --job job-description.md --out output/run
# Create output/run/tailoring-payload.json from output/run/tailoring-brief.json.
uv run jobs-tailor build --payload output/run/tailoring-payload.json --out output/run
uv run jobs-tailor check --out output/run --reinspect
```

Helpful inspection commands:

```bash
uv run jobs-tailor explain-rules
uv run jobs-tailor status --out output/run
uv run jobs-tailor inspect-run --out output/run
uv run jobs-tailor rerun --out output/run
```

## Rendering

Most commands are normal cross-platform Python. LibreOffice/PDF rendering is the non-negotiable environment-sensitive part; use Docker when native LibreOffice/UNO is not healthy, especially on Windows.

```bash
docker build -t cvfoundry .
docker run --rm -v "$PWD:/workspace" cvfoundry doctor
```

The tracked default rules live in [`templates/profile/resume.toml`](templates/profile/resume.toml).
Detailed setup and rule examples are in [`docs/ONBOARDING.md`](docs/ONBOARDING.md).

## License

CvFoundry uses the MIT License. Bundled Gelasio fonts use the SIL Open Font License 1.1.
