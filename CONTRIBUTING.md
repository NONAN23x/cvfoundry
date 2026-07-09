# Contributing

1. Create a branch from `main`.
2. Keep personal CVs and generated output out of commits.
3. Run `uv sync` and `uv run python -m unittest discover -s tests -v`.
4. For renderer changes, also run the LibreOffice integration tests through Docker.
5. Open a focused pull request describing behavior and verification.

Test data must be fictional and use reserved example domains and phone numbers.
