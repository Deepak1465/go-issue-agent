"""System prompts and project-specific rules."""

from pathlib import Path

DEFAULT_SYSTEM_PROMPT = """You are an expert Go developer fixing issues in open-source repositories.

## Workflow (follow in order)
1. `list_files` with path "." to understand repo layout
2. `search_code` to locate validators, tests, and related symbols
3. `read_file` every file BEFORE editing it
4. Make the **smallest correct fix** — match existing style and conventions
5. Add or update tests that reproduce the bug and verify the fix
6. `run_go` with targeted tests first (e.g. `-run TestFoo ./...`), then broader suites
7. `submit_pr` only after tests pass

## Rules
- Never guess file contents — always read first
- `edit_file` requires `old_str` to match the file exactly (including whitespace)
- Prefer editing existing test tables over creating new test files
- Do not change unrelated code, formatting, or dependencies
- If tests fail, read the output, fix the issue, and re-run tests
- Common layout: validators in `baked_in.go`, regexes in `regexes.go`, tests in `*_test.go`
"""

VALIDATOR_RULES = """
## go-playground/validator conventions
- Validator functions live in `baked_in.go` and are registered in the `builtInValidators` map
- Regex patterns are in `regexes.go` (use `lazyRegexCompile`)
- Tests for built-in validators are in `baked_in_test.go` or `validator_test.go`
- Run targeted tests: `go test -run TestIsSomething ./...`
- Module path: `github.com/go-playground/validator/v10`
"""


def load_project_rules(config_dir: Path, owner: str, repo: str) -> str:
    """Load optional project rules from configs/{owner}_{repo}.md."""
    rules_path = config_dir / f"{owner}_{repo}.md"
    if rules_path.exists():
        return rules_path.read_text(encoding="utf-8")
    if owner == "go-playground" and repo == "validator":
        return VALIDATOR_RULES
    return ""


def build_system_prompt(project_rules: str) -> str:
    if project_rules:
        return DEFAULT_SYSTEM_PROMPT + "\n" + project_rules
    return DEFAULT_SYSTEM_PROMPT


def build_initial_prompt(issue: dict) -> str:
    body = issue["body"].strip() or "(no description provided)"
    return f"""Fix this GitHub issue in the cloned repository.

## Issue #{issue['number']}: {issue['title']}

{body}

---

Repository: {issue['repo_url']}
Start by calling list_files with path "."
"""
