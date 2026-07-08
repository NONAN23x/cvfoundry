# Tailoring Rules

## Selection

- Parse facts only from the selected profile's `CV.md`.
- Extract the role, company, must-haves, responsibilities, domain terms, and seniority signals.
- Generate the deterministic fit report before selecting content.
- Keep strong original bullets; prefer source-backed swaps before rewrites.
- Choose exactly two relevant projects after reviewing ranking evidence.
- Provide exactly one prominent `jobTitle`. The system uses that explicit title directly as the final headline instead of inferring one from the JD.

## Writing

- Pass 1: cover the JD's strongest truthful requirements.
- Pass 2: humanize verbs, rhythm, and emphasis without weakening ATS terms.
- Pass 3: remove repetition and compress every required row for final-PDF fit.
- Mirror accurate job terminology without keyword stuffing.
- Preserve every bullet's `sourceId`; never add unsupported numbers.
- Keep all required entries and achievements.
- Experience stays in canonical CV chronology; do not reorder it by relevance.
- Do not emit canonical contact details, certifications, achievements, education, entry labels, dates, project stacks, schema metadata, or CV hashes. The assembler injects them from `CV.md`.
- Summary: write a one- to three-line elevator pitch that presents professional identity, strongest role-relevant capabilities, working character, and value to the team.
- The summary must describe the candidate as a whole. Do not turn it into a compressed project list, a sequence of “built” claims, or a keyword inventory.
- Use at most one compact proof point when it materially strengthens the pitch; leave detailed evidence to experience and projects.
- Make the voice calm, bold, and confident while remaining grounded in `CV.md`.
- Bullets and skill rows: exactly one rendered PDF line.
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
- `summary`
- `summarySourceIds`
- `experience`: all three entries, each with only `sourceId` and four `sourceId`/`text` bullets
- `projects`: exactly two entries, each with only `sourceId` and three `sourceId`/`text` bullets
- `skillPriorities`: all four categories, each with only `sourceId` and one or more canonical `priorityItems`

The priority list is not the final rendered list. The assembler starts with the first configured number of skills from each canonical `CV.md` category, promotes matching priority items, and replaces at most two lower-priority baseline items per category. All other resume fields are locked and deterministically assembled from `CV.md`. The final rendered headline comes directly from `jobTitle`, so do not spend tokens inventing alternate role labels.
