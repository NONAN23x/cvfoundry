# CvFoundry

<p align="center">
  <a href="https://github.com/NONAN23x/cvfoundry/actions/workflows/test.yml"><img src="https://github.com/NONAN23x/cvfoundry/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11+"></a>
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/badge/uv-managed-DE5FE9?logo=uv&amp;logoColor=white" alt="uv"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-renderer-2496ED?logo=docker&amp;logoColor=white" alt="Docker renderer"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
</p>

<p align="center">Works with your preferred coding agent</p>

<p align="center">
  <a href="https://docs.anthropic.com/en/docs/claude-code/overview"><img src="https://img.shields.io/badge/Claude_Code-191919?logo=anthropic&amp;logoColor=white" alt="Claude Code"></a>
  <a href="https://openai.com/codex/"><img src="https://img.shields.io/badge/Codex-412991?logo=openai&amp;logoColor=white" alt="Codex"></a>
  <a href="https://opencode.ai/"><img src="https://img.shields.io/badge/OpenCode-000000?logo=opencode&amp;logoColor=white" alt="OpenCode"></a>
  <a href="https://antigravity.google/"><img src="https://img.shields.io/badge/Antigravity-4285F4?logo=google&amp;logoColor=white" alt="Antigravity"></a>
  <a href="https://www.cursor.com/"><img src="https://img.shields.io/badge/Cursor-000000?logo=cursor&amp;logoColor=white" alt="Cursor"></a>
</p>

CvFoundry turns one factual CV into a tailored, source-backed resume. It keeps your private profile out of Git, lets your coding agent do the editorial work within explicit rules, and produces HTML, ODT, PDF, and QA evidence.

## Install dependencies

Install `uv` for the project environment and Docker for consistent LibreOffice/PDF rendering. Docker is only used when the native renderer is unavailable or you choose it explicitly.

<p align="center">
  <a href="https://docs.docker.com/desktop/setup/install/windows-install/"><img src="https://img.shields.io/badge/Docker_Desktop-Windows-2496ED?logo=docker&amp;logoColor=white" alt="Install Docker Desktop on Windows"></a>
  <a href="https://docs.docker.com/desktop/setup/install/mac-install/"><img src="https://img.shields.io/badge/Docker_Desktop-macOS-2496ED?logo=docker&amp;logoColor=white" alt="Install Docker Desktop on macOS"></a>
  <a href="https://docs.docker.com/desktop/setup/install/linux/"><img src="https://img.shields.io/badge/Docker_Desktop-Linux-2496ED?logo=docker&amp;logoColor=white" alt="Install Docker Desktop on Linux"></a>
</p>

Install uv on macOS or Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

For Windows or another installation method, use the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

## Start with your agent

Clone the repository, open it in your favorite coding agent, and ask the agent to onboard the project and complete first-run checks.

```bash
git clone https://github.com/NONAN23x/cvfoundry.git
cd cvfoundry
```

Give your agent this prompt:

> Read `AGENTS.md`, onboard this repository, and run the first-run requirements for my private profile. Stop if anything needs my input.

The agent will install the locked dependencies with `uv`, create `profiles/local/` if needed, verify your renderer, and stop before tailoring if your profile is incomplete. Your private CV, rules, and generated resumes stay ignored by Git.

If you are working without an agent, follow the same steps in [onboarding](docs/ONBOARDING.md).

## Create your profile

After the agent has completed first run, put your facts in `profiles/local/CV.md`. Use the fictional [John Doe example](profiles/john-doe/CV.md) for structure; do not edit the public example for your own resume.

Then set the resume boundaries you want in `profiles/local/resume.toml`: page count, included sections, and entry/bullet limits. `Writing-Style.md` is optional and controls voice only.

## Tailor a job

Save the job description, then tell your agent to tailor it. For a manual run:

```bash
uv run jobs-tailor prepare --job job-description.md --out output/company-role-YYYY-MM-DD
# Write output/company-role-YYYY-MM-DD/tailoring-payload.json from the generated brief.
uv run jobs-tailor build --renderer auto --payload output/company-role-YYYY-MM-DD/tailoring-payload.json --out output/company-role-YYYY-MM-DD
uv run jobs-tailor check --out output/company-role-YYYY-MM-DD --reinspect
```

The final folder contains the tailored HTML, editable ODT, tagged PDF, selected-source evidence, and layout QA. See [the tailoring guide](SKILL.md) when you need to author or review a payload.

## When you need more control

- Need to change page limits, sections, entry counts, or bullet counts? Read [resume rules](docs/ONBOARDING.md#configure-resume-rules).
- Need a two-page resume? Change `target_pages` and `max_pages` in your private `resume.toml`; counts automatically use the two-page values and never invent filler.
- Need Docker because LibreOffice/UNO is unavailable? Read [renderer environments](docs/ONBOARDING.md#renderer-environments).
- Need to see the actual rules used for one run? Run `uv run jobs-tailor explain-rules` or inspect the run's `effective-policy.json`.

## Install from a wheel

For use outside a source checkout:

```bash
uv build --wheel --out-dir dist
uv tool install dist/*.whl
jobs-tailor init profiles/local
```

## License

CvFoundry uses the MIT License. Bundled Gelasio fonts use the SIL Open Font License 1.1.
