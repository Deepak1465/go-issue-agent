#!/usr/bin/env bash
# Quick start script for Go Issue Agent
set -euo pipefail

cd "$(dirname "$0")"

DEMO=false
ISSUE_URL="https://github.com/go-playground/validator/issues/1561"
OUTPUT_DIR="./output"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo) DEMO=true; shift ;;
    -h|--help)
      echo "Usage: ./run.sh [--demo] [issue_url] [output_dir]"
      echo "  --demo   Run without API (uses sample_output/)"
      exit 0
      ;;
    *)
      if [[ "$1" == http* ]]; then
        ISSUE_URL="$1"
      else
        OUTPUT_DIR="$1"
      fi
      shift
      ;;
  esac
done

# Always load .env (overrides any old key still exported in the terminal)
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ "$DEMO" == true ]]; then
  :
elif [[ -z "${GEMINI_API_KEY:-}" ]] || [[ "${GEMINI_API_KEY}" == "paste_your_key_here" ]]; then
  # Common mistake: key pasted in .env.example instead of .env
  if [[ -f .env.example ]]; then
    EXAMPLE_KEY=$(grep -E '^GEMINI_API_KEY=' .env.example | cut -d= -f2- | tr -d '"' | tr -d "'")
    if [[ -n "$EXAMPLE_KEY" && "$EXAMPLE_KEY" != "paste_your_key_here" ]]; then
      echo "Found API key in .env.example — copying to .env for you..."
      {
        echo "# Gemini API key — https://aistudio.google.com/apikey"
        grep -E '^GEMINI_API_KEY=' .env.example
      } > .env
      set -a
      # shellcheck disable=SC1091
      source .env
      set +a
    fi
  fi
fi

if [[ "$DEMO" != true ]] && { [[ -z "${GEMINI_API_KEY:-}" ]] || [[ "${GEMINI_API_KEY}" == "paste_your_key_here" ]]; }; then
  echo "ERROR: No GEMINI_API_KEY in .env"
  echo ""
  echo "  Put your key in the file:  .env   (NOT .env.example)"
  echo "  Line should look like:     GEMINI_API_KEY=your_key_here"
  echo ""
  echo "  Quick setup:"
  echo "    cp .env.example .env"
  echo "    # open .env and paste your key"
  echo "    unset GEMINI_API_KEY && ./run.sh"
  echo ""
  echo "  Or without API: ./run.sh --demo"
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [[ "$DEMO" == true ]]; then
  python main.py --demo --issue "$ISSUE_URL" --output "$OUTPUT_DIR"
else
  python main.py --issue "$ISSUE_URL" --output "$OUTPUT_DIR"
fi

echo ""
echo "Artifacts written to: $OUTPUT_DIR"
