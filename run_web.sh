#!/usr/bin/env bash
# Start the Go Issue Agent web UI
set -euo pipefail

cd "$(dirname "$0")"

if [[ -z "${GEMINI_API_KEY:-}" ]] && [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo ""
echo "  Go Issue Agent — Web UI"
echo "  ─────────────────────────────────────"
echo "  Open:  http://localhost:8000"
echo "  Demo:  Click 'View sample output' (no API key needed)"
echo "  Live:  Set GEMINI_API_KEY in .env to run the agent"
echo ""

exec uvicorn web.server:app --host 0.0.0.0 --port 8000 --reload
