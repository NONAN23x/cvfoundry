# CvFoundry

CvFoundry turns a source CV and a small policy file into provenance-checked HTML,
editable ODT, and tagged PDF/UA resumes.

## Start here

Create a private local profile:

```bash
./jobs-tailor init profiles/local
```

Then:

1. Write your own `profiles/local/CV.md`, using
   [`profiles/john-doe/CV.md`](profiles/john-doe/CV.md) as the format reference.
2. Edit `profiles/local/resume.json` to choose pages, sections, entries, and bullets.
3. Adjust `profiles/local/Writing-Style.md` if desired.
4. Validate the setup:

```bash
./jobs-tailor doctor
./jobs-tailor validate
```

`profiles/local/`, `profiles/private/`, `knowledge-base/`, `.env*`, and generated
`output/` files are excluded from Git and the Docker build context. Keep personal CVs
and policy overrides there; only the fictional John Doe example is published.

## Build a resume

```bash
./jobs-tailor prepare --job job-description.md --out output/run
# Create output/run/tailoring-payload.json from tailoring-brief.json.
./jobs-tailor build --payload output/run/tailoring-payload.json --out output/run
./jobs-tailor check --out output/run --reinspect
```

The tracked default policy is [`templates/profile/resume.json`](templates/profile/resume.json).
In each profile, `resume.json` is authoritative:

- `document.targetPages` and `document.maxPages` control the one- or two-page limit.
- `sections` controls inclusion and order.
- `selection.entries` controls section entry counts.
- `selection.bulletsPerEntry` controls bullets per experience or project.
- `layout.maximum*Lines` controls rendered line limits.
- `theme` selects fonts, colors, margins, and spacing from `themes/`.

Resolved rules are written to `effective-policy.json`; final layout evidence is written
to `decision-report.json` and `layout-validation.json`.

For profile syntax, Docker usage, and the complete workflow, see
[`docs/ONBOARDING.md`](docs/ONBOARDING.md).

## Requirements

Python 3.11+, LibreOffice Writer with UNO bindings, Poppler utilities, and Fontconfig.
The pinned Docker build provides the supported renderer environment.

## License

CvFoundry uses the MIT License. Bundled Gelasio fonts use the SIL Open Font License 1.1.
