"""
agent.py — Go Issue Agent (Gemini)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from google import genai
from google.genai import types

# ── Constants ──────────────────────────────────────────────────────────────────
MODEL = "gemini-2.5-flash"          # Best free tier model
MAX_TURNS = 25
REPO_BASE = Path("/tmp/agent_repos")

# ── Tools ──────────────────────────────────────────────────────────────────────
TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="read_file", description="Read full file. Always before editing.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={"path": types.Schema(type=types.Type.STRING)}, required=["path"])
    ),
    types.FunctionDeclaration(
        name="list_files", description="List files. Start with '.'",
        parameters=types.Schema(type=types.Type.OBJECT, properties={"path": types.Schema(type=types.Type.STRING)}, required=["path"])
    ),
    types.FunctionDeclaration(
        name="search_code", description="Search in Go files.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={"query": types.Schema(type=types.Type.STRING)}, required=["query"])
    ),
    types.FunctionDeclaration(
        name="edit_file", description="Replace old_str with new_str exactly.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={
            "path": types.Schema(type=types.Type.STRING),
            "old_str": types.Schema(type=types.Type.STRING),
            "new_str": types.Schema(type=types.Type.STRING)
        }, required=["path", "old_str", "new_str"])
    ),
    types.FunctionDeclaration(
        name="run_tests", description="Run go test.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={"args": types.Schema(type=types.Type.STRING)}, required=["args"])
    ),
    types.FunctionDeclaration(
        name="submit_pr", description="Call when done and tests pass.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={
            "title": types.Schema(type=types.Type.STRING),
            "body": types.Schema(type=types.Type.STRING)
        }, required=["title", "body"])
    ),
])

# ── Tool Functions (unchanged) ─────────────────────────────────────────────────
def tool_read_file(repo_path: Path, path: str) -> str:
    full_path = repo_path / path
    if not full_path.exists(): return f"ERROR: File not found: {path}"
    try:
        content = full_path.read_text(encoding="utf-8")
        return content if len(content) <= 50000 else content[:50000] + "\n...[TRUNCATED]"
    except Exception as e: return f"ERROR: {e}"

def tool_list_files(repo_path: Path, path: str) -> str:
    full_path = repo_path if path == "." else repo_path / path
    try:
        entries = sorted(full_path.iterdir())
        return "\n".join(f"{'DIR ' if e.is_dir() else 'FILE '}{e.relative_to(repo_path)}" for e in entries)
    except Exception as e: return f"ERROR: {e}"

def tool_search_code(repo_path: Path, query: str) -> str:
    try:
        r = subprocess.run(["grep", "-rn", "--include=*.go", query, "."],
                           cwd=repo_path, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() or f"No matches for '{query}'"
    except Exception as e: return f"ERROR: {e}"

def tool_edit_file(repo_path: Path, path: str, old_str: str, new_str: str) -> str:
    full_path = repo_path / path
    try:
        content = full_path.read_text(encoding="utf-8")
        if old_str not in content: return f"ERROR: old_str not found in {path}"
        full_path.write_text(content.replace(old_str, new_str), encoding="utf-8")
        return f"SUCCESS: Edited {path}"
    except Exception as e: return f"ERROR: {e}"

def tool_run_tests(repo_path: Path, args: str) -> str:
    try:
        r = subprocess.run(["go", "test"] + args.split(), cwd=repo_path,
                           capture_output=True, text=True, timeout=120)
        status = "PASSED" if r.returncode == 0 else "FAILED"
        return f"[Tests {status}]\n{r.stdout + r.stderr}"
    except Exception as e: return f"ERROR: {e}"

def run_tool(name: str, inputs: dict, repo_path: Path) -> str:
    if name == "read_file": return tool_read_file(repo_path, inputs["path"])
    if name == "list_files": return tool_list_files(repo_path, inputs["path"])
    if name == "search_code": return tool_search_code(repo_path, inputs["query"])
    if name == "edit_file": return tool_edit_file(repo_path, inputs["path"], inputs["old_str"], inputs["new_str"])
    if name == "run_tests": return tool_run_tests(repo_path, inputs["args"])
    if name == "submit_pr": return "__SUBMIT__"
    return f"ERROR: Unknown tool {name}"

# ── Helpers ────────────────────────────────────────────────────────────────────
def fetch_issue(issue_url: str) -> dict:
    parts = issue_url.rstrip("/").split("/")
    owner, repo, number = parts[3], parts[4], parts[6]
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    print(f"  Fetching issue: {api_url}")
    resp = requests.get(api_url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {"title": data["title"], "body": data.get("body", ""), "number": data["number"], "url": issue_url, "repo": repo, "repo_url": f"https://github.com/{owner}/{repo}"}

def clone_repo(repo_url: str, repo_name: str) -> Path:
    REPO_BASE.mkdir(parents=True, exist_ok=True)
    dest = REPO_BASE / repo_name
    if dest.exists():
        print(f"  Repo already cloned at {dest} — pulling latest...")
        subprocess.run(["git", "pull", "--quiet"], cwd=dest, check=False)
    else:
        print(f"  Cloning {repo_url}...")
        subprocess.run(["git", "clone", "--depth=1", "--quiet", repo_url, str(dest)], check=True)
    return dest

SYSTEM_PROMPT = """You are an expert Go developer fixing issues.
1. list_files('.') first
2. search_code to locate code
3. read_file before any edit_file
4. Minimal fix + add test
5. run_tests after changes
6. submit_pr when tests pass"""

# ── Main Agent with Retry ──────────────────────────────────────────────────────
def run_agent(issue_url: str, output_dir: Path):
    print("\n" + "="*60)
    print("STEP 1: Fetching issue from GitHub")
    print("="*60)
    issue = fetch_issue(issue_url)
    print(f"  Issue #{issue['number']}: {issue['title']}")

    print("\n" + "="*60)
    print("STEP 2: Cloning repository")
    print("="*60)
    repo_path = clone_repo(issue["repo_url"], issue["repo"])

    print("\n" + "="*60)
    print("STEP 3: Starting Gemini agent loop")
    print("="*60)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ Set GEMINI_API_KEY environment variable")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    initial_prompt = f"""Fix this issue:

## Issue #{issue['number']}: {issue['title']}
{issue['body']}

Start by calling list_files('.')"""

    history = []
    turn = 0
    pr_result = None

    while turn < MAX_TURNS:
        turn += 1
        print(f"\n── Turn {turn}/{MAX_TURNS} ──────────────────────────────────")
        try:
            contents = [{"role": "user", "parts": [{"text": initial_prompt}]}] if turn == 1 else history

            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[TOOLS],
                    temperature=0.1,
                )
            )

            if not response or not response.candidates:
                raise Exception("Empty response")

            candidate = response.candidates[0]

            if turn == 1:
                history.append({"role": "user", "parts": [{"text": initial_prompt}]})

            history.append({"role": "model", "parts": candidate.content.parts})

            fn_calls = [p for p in candidate.content.parts if hasattr(p, "function_call") and p.function_call]

            if not fn_calls:
                print("  Gemini finished.")
                break

            tool_responses = []
            for part in fn_calls:
                fc = part.function_call
                name = fc.name
                args = dict(fc.args) if fc.args else {}

                print(f"  → Tool: {name}")
                if name == "submit_pr":
                    pr_result = args
                    result = "PR ready"
                    print("  ✓ PR ready!")
                else:
                    result = run_tool(name, args, repo_path)
                    print(f"  ← Result: {result[:180]}...")

                tool_responses.append(types.Part.from_function_response(name=name, response={"result": result}))

            history.append({"role": "user", "parts": tool_responses})

            if pr_result:
                break

            time.sleep(1.0)  # Be gentle with rate limits

        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = 30
                print(f"🔄 Rate limit hit (429). Waiting {wait} seconds...")
                time.sleep(wait)
                continue
            elif "503" in err or "UNAVAILABLE" in err:
                print("🔄 Service busy. Waiting 10s...")
                time.sleep(10)
                continue
            print(f"❌ Error: {err}")
            raise

    # Save output
    print("\n" + "="*60)
    print("STEP 4: Saving output")
    print("="*60)

    output_dir.mkdir(parents=True, exist_ok=True)
    diff = subprocess.run(["git", "diff"], cwd=repo_path, capture_output=True, text=True).stdout or "(no changes)"

    summary = "# Pull Request Summary\n\n"
    summary += "## Title\n" + (pr_result.get("title", "fix: cron validator") if pr_result else "N/A") + "\n\n"
    summary += "## Issue\n" + issue["url"] + "\n\n"
    summary += "## Diff\n```diff\n" + diff + "\n```\n"

    (output_dir / "report.json").write_text(json.dumps({"issue": issue, "pr": pr_result or {}, "diff": diff, "turns": turn}, indent=2))
    (output_dir / "changes.diff").write_text(diff)
    (output_dir / "pr_summary.md").write_text(summary)

    print(f"✅ Done in {turn} turns!")
    print(f"Output: {output_dir}/")

# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Go Issue Agent")
    parser.add_argument("--issue", required=True, help="GitHub issue URL")
    parser.add_argument("--output", default="./sample_output")
    args = parser.parse_args()

    run_agent(args.issue, Path(args.output))

if __name__ == "__main__":
    main()