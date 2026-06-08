# Setup Guide — Go Issue Agent

Follow these steps **in order** to run the project with a fresh Gemini API key.

---

## Step 1: Open the project folder in Terminal

```bash
cd ~/Desktop/go-issue-agent
```

---

## Step 2: Get a Gemini API key (new Google account)

1. Open **https://aistudio.google.com/apikey** in your browser
2. Sign in with your **new** Google account
3. Click **"Create API key"**
4. Copy the key (click the copy icon)

---

## Step 3: Put the key in `.env` (only place you need to edit)

> **Important:** Edit **`.env`** — NOT `.env.example`. The app only reads `.env`.

**Create `.env` from the template:**

```bash
cp .env.example .env
```

Open the file **`.env`** in Cursor (left sidebar). It should contain:

```
GEMINI_API_KEY=paste_your_actual_key_here
```

Replace `paste_your_actual_key_here` with the key you copied. Example:

```
GEMINI_API_KEY=AIzaSyDxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Rules:**
- No quotes around the key
- No spaces before or after `=`
- Save the file

---

## Step 4: Clear any old key from Terminal

If you previously ran `export GEMINI_API_KEY=...` in the terminal, clear it:

```bash
unset GEMINI_API_KEY
```

This makes sure the app reads from `.env` only.

---

## Step 5: Install dependencies (first time only)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 6: Run the agent

### Live run (uses Gemini API)

```bash
source .venv/bin/activate
unset GEMINI_API_KEY
./run.sh
```

You should see:

```
Connecting to Gemini API...
✓ Connected with model: gemini-2.0-flash-lite
── Turn 1/30 ──────────────────────────────────
  → list_files(...)
```

Output files appear in `./output/`:
- `report.json`
- `changes.diff`
- `pr_summary.md`

### Demo run (no API key needed)

```bash
./run.sh --demo
```

### Web UI

```bash
./run_web.sh
```

Open **http://localhost:8000** in your browser.

---

## Step 7: Run on a specific issue

```bash
./run.sh https://github.com/go-playground/validator/issues/1561
```

---

## Troubleshooting

| What you see | What to do |
|--------------|------------|
| `No GEMINI_API_KEY found` | Edit `.env` and paste your key |
| `Gemini rejected your API key` | Wrong key — create a new one in AI Studio |
| `429 RESOURCE_EXHAUSTED` / daily quota | Wait 24h, use new Google account key, or `./run.sh --demo` |
| Old key still used | Run `unset GEMINI_API_KEY` then `./run.sh` again |
| `go not found` | Install Go from https://go.dev/dl/ |

---

## Quick reference — copy/paste block

```bash
cd ~/Desktop/go-issue-agent
cp .env.example .env
# → Edit .env and paste your GEMINI_API_KEY

unset GEMINI_API_KEY
source .venv/bin/activate
./run.sh
```

---

## Where the API key is used in code (you don't need to edit these)

| File | What it does |
|------|----------------|
| `.env` | **You edit this** — stores your key |
| `run.sh` | Loads `.env` automatically |
| `main.py` | Loads `.env` with `load_dotenv(override=True)` |
| `go_issue_agent/agent.py` | Reads `GEMINI_API_KEY` and calls Gemini |

**Never commit `.env` to GitHub** — it is already in `.gitignore`.
