# Go Issue Agent

An agentic AI that takes a GitHub issue from an open-source Go project and autonomously fixes it — reading the codebase, identifying the root cause, patching the code, running tests, and generating a pull request summary.

**Uses Google Gemini API — completely free, no credit card needed.**

## Setup (3 steps, 5 minutes)

### Step 1 — Get a free Gemini API key
Go to https://aistudio.google.com/apikey → sign in with Gmail → Create API Key → copy it.

### Step 2 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Run the agent
```bash
export GEMINI_API_KEY=your-key-here
python agent.py --issue https://github.com/go-playground/validator/issues/1259
```

That's it. Output saved to `sample_output/`.

---

## Example run

```bash
export GEMINI_API_KEY=AIzaSy...
python agent.py --issue https://github.com/go-playground/validator/issues/1259
```

```
STEP 1: Fetching issue from GitHub
  Issue #1259: Cron validator is not correct

STEP 2: Cloning repository
  Cloning https://github.com/go-playground/validator → /tmp/...

STEP 3: Starting Gemini agent loop
── Turn 1/20 ──
  → Tool: list_files({"path": "."})
  ← Result: FILE  baked_in.go ...
── Turn 2/20 ──
  → Tool: search_code({"query": "isCron"})
...
── Turn 10/20 ──
  → Tool: submit_pr({"title": "fix: cron validation support for star step value"})
  ✓ PR ready!

✅ Done in 10 turns.
   Output: ./sample_output/
```

---

## Output files

```
sample_output/
├── pr_summary.md   — PR title, body, and full explanation
├── changes.diff    — Exact git diff of all code changes
└── report.json     — Full session log (issue, PR, actions, turns used)
```

---

## Architecture

```
agent.py
├── fetch_issue()      — GitHub API → issue title + body
├── clone_repo()       — git clone the repo locally
├── TOOLS              — 6 tools Gemini can call
├── run_tool()         — dispatches Gemini's tool calls to real code
└── run_agent()        — the main agent loop
    ├── send issue + tools to Gemini (gemini-2.5-flash)
    ├── Gemini picks a tool → we run it → send result back
    ├── repeat until submit_pr is called
    └── save diff + PR summary to output/
```

### The 6 tools

| Tool | What it does |
|------|-------------|
| `list_files` | List directory contents — used first to orient |
| `read_file` | Read a file's content — always before editing |
| `search_code` | Grep across all .go files — find the right function |
| `edit_file` | Precise string-replace — make the actual fix |
| `run_tests` | Run `go test` — validate the fix works |
| `submit_pr` | Final step — emit PR title + body, stop loop |

### Why this architecture works

Gemini can't run code or read files itself — it only decides *what* to do. Your Python script actually does it. This is the standard "tool-use" agent pattern:

```
Gemini (decides) ←→ Python (acts) ←→ filesystem / shell
```

Each turn: Python sends history → Gemini picks next tool → Python runs it → repeat.
This is better than one-shot prompting because Gemini reads the *actual* code, not a description of it.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes | Free key from aistudio.google.com/apikey |
| `GITHUB_TOKEN` | No | Avoids GitHub rate limits (optional) |

---

## Supported repositories

- `go-playground/validator` ✓ tested — cron issue #1259
- `spf13/cobra` ✓ compatible
- `gin-gonic/gin` ✓ compatible
- `golangci/golangci-lint` ⚠ complex codebase, may need more turns
