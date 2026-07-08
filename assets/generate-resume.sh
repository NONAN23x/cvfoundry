#!/usr/bin/env bash

set -euo pipefail

if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [output-dir]" >&2
  exit 1
fi

if [[ $# -eq 1 ]]; then
  cd "$1"
else
  cd "$(dirname "$0")"
fi

PAYLOAD_JSON="tailoring-payload.json"
RESUME_JSON="tailored-resume.json"
TOOL_ROOT="$(cd ../.. && pwd)"
ASSEMBLER="$TOOL_ROOT/scripts/assemble_resume.py"
GENERATOR="$TOOL_ROOT/scripts/generate_resume.py"
QA="$TOOL_ROOT/scripts/check_resume_quality.py"
LOCK_FILE=".generate.lock"

if [[ ! -f "$PAYLOAD_JSON" ]]; then
  echo "Missing $PAYLOAD_JSON in $(pwd)." >&2
  exit 1
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another resume generation is active in $(pwd)." >&2
  exit 1
fi

export JOBS_TAILORING_PIPELINE_LOCK=1

python3 "$ASSEMBLER" "$PAYLOAD_JSON" "$RESUME_JSON"
python3 "$GENERATOR" "$RESUME_JSON" "$(pwd)"
python3 "$QA" "$(pwd)"
PDF_NAME="$(python3 -c 'import json, pathlib, sys; sys.path.insert(0, str(pathlib.Path(sys.argv[1]).parent)); from artifact_names import final_pdf_filename; print(final_pdf_filename(json.load(open(sys.argv[2]))))' "$GENERATOR" "$RESUME_JSON")"
echo "Generated and validated tailored-resume.html, tailored-resume.odt, and $PDF_NAME."
