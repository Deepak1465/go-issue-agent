# Interview Guide — Go Issue Agent

Use this document to explain the project confidently in your interview. Read it once before the call and skim the Q&A section.

---

## 1. Elevator pitch (30 seconds)

> "I built an agentic AI system that takes a GitHub issue from go-playground/validator, clones the repo, explores the code with tools, applies a minimal fix, runs Go tests, and produces a PR-ready diff and summary. It's not a one-shot prompt — it's a **tool-calling loop** where Gemini decides which tools to use each turn. I used Gemini's free API, kept the architecture simple and inspectable, and added a web UI to demo the flow live."

---

## 2. Problem → Solution

| Assignment requirement | How we address it |
|------------------------|-------------------|
| Take a GitHub issue | `fetch_issue()` via GitHub REST API |
| Inspect repository | `list_files`, `search_code`, `read_file` tools |
| Understand the issue | Issue title/body injected into initial prompt + project rules |
| Identify relevant files | Agent uses `search_code` (grep) + `read_file` |
| Plan a fix | Gemini reasons in the loop; system prompt enforces workflow |
| Modify code | `edit_file` (exact string replace) |
| Run tests/checks | `run_go` tool (`go test`, `go vet`) |
| Generate PR title/body | `submit_pr` tool (gated on passing tests) |
| Easy to run & review | CLI + web UI + README + `sample_output/` |

---

## 3. Architecture (draw this on a whiteboard)

```
User / Instructor
      │
      ▼
┌─────────────┐     ┌──────────────────┐
│  Web UI /   │────▶│  GoIssueAgent    │
│  CLI        │     │  (orchestrator)  │
└─────────────┘     └────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   GitHub API          Gemini 2.5 Flash      Tool Runner
   (fetch issue)       (function calling)    (grep, edit, test)
                             │                   │
                             └──── loop ─────────┘
                                       │
                                       ▼
                              Cloned Go repo
                              + git branch
                              + artifacts
```

### One agent turn

1. Gemini receives conversation history (issue + prior tool results)
2. Gemini returns one or more **function calls** (e.g. `read_file`, `edit_file`)
3. Python executes tools against the cloned repo
4. Tool results are appended to history
5. Repeat until `submit_pr` or max turns

This is the **ReAct pattern** (Reason + Act).

---

## 4. Why I made each design choice

### Gemini 2.5 Flash (free tier)
- **Why:** Assignment allows any LLM; free tier makes it easy for reviewers to run
- **Trade-off:** Less capable than GPT-4/Claude for huge refactors — acceptable because we target small issues

### Tool-calling loop (not one-shot prompt)
- **Why:** Assignment explicitly asks for a "system/framework," not a thin wrapper
- **Benefit:** Auditable action log; agent can recover from test failures

### Six explicit tools
- **Why:** Mirrors how human developers work: explore → read → edit → test
- **Benefit:** Each step is debuggable; interviewer can trace exactly what happened

### `edit_file` uses exact string replace
- **Why:** Forces agent to `read_file` first; prevents hallucinated full-file rewrites
- **Trade-off:** Fragile if whitespace doesn't match — agent re-reads and retries

### `submit_pr` gated on passing tests
- **Why:** Prevents agent from declaring victory without validation
- **How:** `ToolRunner.tests_passed` flag set when `go test` returns 0

### Grep instead of embeddings/RAG
- **Why:** validator repo is ~few hundred Go files; grep is fast, free, deterministic
- **Trade-off:** Wouldn't scale to monorepos with millions of lines — mention you'd add embeddings later

### Project rules in `configs/`
- **Why:** Injects repo-specific knowledge (where validators live, how to run tests)
- **Extensibility:** Add `configs/{owner}_{repo}.md` for other approved projects

### Web UI + CLI
- **Why:** CLI for reviewers/automation; UI for live demo in interview
- **How:** FastAPI serves frontend; background thread runs agent; polling for progress

### Shallow git clone + cache
- **Why:** Faster re-runs during development
- **How:** `/tmp/agent_repos/validator` reused with `git pull`

---

## 5. Walkthrough demo script (for interview)

### Option A — Web UI (recommended for live demo)

```bash
export GEMINI_API_KEY=your_key
./run_web.sh
# Open http://localhost:8000
# Click "View sample output" (works without API key)
# OR paste issue URL and click "Run Agent"
```

### Option B — CLI (shows you're not hiding behind UI)

```bash
./run.sh https://github.com/go-playground/validator/issues/1561
cat output/report.json
cat output/changes.diff
```

### What to say while demo runs

1. "First it fetches the issue from GitHub — no auth needed for public issues"
2. "It clones validator and creates a branch `agent/fix-issue-1561`"
3. "Now Gemini is in the loop — watch it call list_files, search_code, read_file"
4. "It edits baked_in.go and adds a test case"
5. "It runs `go test -run TestHostnameRFC1123` — submit_pr is blocked until tests pass"
6. "Final output: diff + PR summary in `output/`"

---

## 6. Sample issue explained (#1561)

**Bug:** `hostname_rfc1123` accepts `277.168.0.1` (invalid IPv4 octet) as valid hostname.

**Root cause:** `isHostnameRFC1123` only checked a regex that allows digit-only labels.

**Fix:** Add `hasOutOfRangeIPv4Octets()` — reject dotted-quad strings with octet > 255.

**Files changed:** `baked_in.go`, `validator_test.go`

See `sample_output/` for full diff and action log.

---

## 7. Common interviewer questions & answers

### "Why not just paste the issue into ChatGPT?"

One-shot prompts can't run tests, can't grep the real repo, and hallucinate file contents. My agent **executes tools against a real clone** and must pass `go test` before submitting.

### "How do you prevent the agent from breaking things?"

- Minimal edit tool (string replace, not arbitrary writes)
- Path traversal blocked in `tools.py`
- Test gate on `submit_pr`
- System prompt says "smallest correct fix"
- Max turns limit (30)

### "What if the agent edits the wrong file?"

It might — this isn't production-grade autonomy. Mitigations: project rules in config, grep to find symbols, read-before-edit rule. For production I'd add: diff review step, static analysis, human-in-the-loop approval.

### "How would you scale to larger repos?"

- AST-aware search (not just grep)
- Embeddings + RAG for file retrieval
- Repo map / dependency graph
- Hierarchical planning (plan phase → implement phase)
- Parallel tool calls

### "Why Gemini over OpenAI/Claude?"

Free tier for reviewers; function calling works well; fast. Architecture is LLM-agnostic — swap `genai.Client` for any provider with tool use.

### "How do you handle rate limits?"

Retry with backoff on 429/503 in `agent.py` (30s wait for rate limit).

### "What issues does it fail on?"

Large architectural changes, unclear requirements, issues needing maintainer decisions, security-sensitive changes. I deliberately picked small bug-fix issues.

### "How would you evaluate quality?"

Compare agent diff vs merged PRs on same issues:
- Files touched overlap
- Test additions
- `go test` pass rate
- PR summary quality

### "What's the time/turn complexity?"

Typically 10–20 turns, 2–5 minutes per small issue. Dominated by Gemini latency + `go test` runtime.

### "Did you open a real PR?"

Assignment says optional. I produce local branch + diff + PR summary. Opening PR would be `git push` + `gh pr create` — easy to add.

---

## 8. File map (know these 5 files)

| File | One-line purpose |
|------|------------------|
| `go_issue_agent/agent.py` | Main loop: Gemini ↔ tools |
| `go_issue_agent/tools.py` | Tool implementations + declarations |
| `go_issue_agent/prompts.py` | System prompt + project rules |
| `go_issue_agent/github_client.py` | Issue fetch, clone, branch |
| `web/server.py` | API + serves frontend |

---

## 9. Honest limitations (shows maturity)

- Not production-ready autonomous coding
- Single-repo focus (validator) out of the box
- No automatic GitHub PR creation
- Depends on Gemini API availability
- Complex issues may exceed turn limit
- `edit_file` can fail on whitespace mismatches

---

## 10. If they ask "what would you do with more time?"

1. Add `gh pr create` integration
2. Planning phase (explicit plan tool before edits)
3. AST-based Go search
4. Evaluation harness comparing output to merged PRs
5. Docker compose for zero-setup review
6. Support multiple approved repos via config registry

---

## 11. Key vocabulary to use

- **Agentic** — LLM decides actions in a loop, not single response
- **Tool calling / function calling** — LLM outputs structured tool invocations
- **ReAct** — Reason then Act iteratively
- **Test gate** — Hard constraint before completion
- **Artifacts** — diff, report.json, pr_summary.md

Good luck.
