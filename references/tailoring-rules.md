# Tailoring Rules

## Selection

- Parse facts only from the selected profile's `CV.md`.
- Extract the role, company, must-haves, responsibilities, domain terms, and seniority signals.
- Generate the deterministic fit report before selecting content.
- Keep strong original bullets; prefer source-backed swaps before rewrites.
- Select only the sections, entries, and bullets allowed by `resume.toml` and the generated `effective-policy.json`.
- Provide exactly one prominent `jobTitle`. The system uses that explicit title directly as the final headline instead of inferring one from the JD.

## Writing

- Pass 1: cover the JD's strongest truthful requirements.
- Pass 2: humanize verbs, rhythm, and emphasis without weakening ATS terms.
- Pass 3: remove repetition and compress every required row for final-PDF fit.
- Mirror accurate job terminology without keyword stuffing.
- Preserve every bullet's `sourceId`; never add unsupported numbers.
- Keep all required entries and deterministic ordered sections.
- Experience stays in canonical CV chronology; do not reorder it by relevance.
- Do not emit canonical contact details, certifications, achievements, education, entry labels, dates, project stacks, schema metadata, or CV hashes. The assembler injects them from `CV.md`.
- Summary: write a one- to three-line elevator pitch that presents professional identity, strongest role-relevant capabilities, working character, and value to the team.
- The summary must describe the candidate as a whole. Do not turn it into a compressed project list, a sequence of “built” claims, or a keyword inventory.
- Use at most one compact proof point when it materially strengthens the pitch; leave detailed evidence to experience and projects.
- Make the voice calm, bold, and confident while remaining grounded in `CV.md`.
- Respect configured bullet and skill-row line limits.
- Treat skills as a CV-derived baseline, not a JD-keyword-only list.
- For each skill category, provide the strongest truthful JD-relevant skills as priorities. The assembler retains the baseline and replaces no more than the configured number of lower-priority items.
- Resolve overflow by tightening low-signal wording, not deleting the broad skill baseline or shrinking isolated text.

## Priority

1. Truth and provenance from `CV.md`
2. ATS clarity
3. Direct, human wording from `Writing-Style.md`
4. One-page layout

## Tailoring Payload

Write `tailoring-payload.json` with exactly these top-level fields:

- `jobTitle`
- `summary`: an object with `text` and `sourceIds`
- `sections`: only tailorable sections from `tailoring-brief.json`, each with permitted source IDs and bounded rewrites

Omit locked/deterministic sections such as `mode = "ordered"` certifications or achievements; the assembler expands those from `CV.md` in CV order.

The skill priority list is not necessarily the final rendered list. The assembler starts with configured CV-derived skills, promotes matching priority items, and only replaces within the configured limit. All other resume fields are locked and deterministically assembled from `CV.md`. The final rendered headline comes directly from `jobTitle`, so do not spend tokens inventing alternate role labels.
