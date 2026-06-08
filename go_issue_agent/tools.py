"""Agent tools for repository exploration, editing, and validation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from google.genai import types

MAX_FILE_BYTES = 50_000
MAX_OUTPUT_CHARS = 12_000


def tool_declarations() -> list[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(
            name="read_file",
            description="Read a file from the repository. Always call before edit_file.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Relative path from repo root, e.g. baked_in.go",
                    )
                },
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="list_files",
            description="List files and directories. Use '.' for repo root.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(
                        type=types.Type.STRING,
                        description="Relative directory path, or '.' for root",
                    )
                },
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="search_code",
            description="Search for a pattern in .go files (grep). Returns matching lines.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                        description="Search string or regex fragment",
                    )
                },
                required=["query"],
            ),
        ),
        types.FunctionDeclaration(
            name="edit_file",
            description=(
                "Replace the first occurrence of old_str with new_str in a file. "
                "old_str must match exactly."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING),
                    "old_str": types.Schema(type=types.Type.STRING),
                    "new_str": types.Schema(type=types.Type.STRING),
                },
                required=["path", "old_str", "new_str"],
            ),
        ),
        types.FunctionDeclaration(
            name="run_go",
            description=(
                "Run a go command in the repo. Examples: "
                "'test -run TestIsCron ./...', 'vet ./...', 'test ./...'"
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "args": types.Schema(
                        type=types.Type.STRING,
                        description="Arguments after 'go', space-separated",
                    )
                },
                required=["args"],
            ),
        ),
        types.FunctionDeclaration(
            name="submit_pr",
            description="Submit the final PR title and body. Call only when tests pass.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING),
                    "body": types.Schema(type=types.Type.STRING),
                },
                required=["title", "body"],
            ),
        ),
    ]


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated, {len(text) - limit} chars omitted]"


def _resolve_path(repo_path: Path, path: str) -> Path | None:
    full = (repo_path / path).resolve()
    try:
        full.relative_to(repo_path.resolve())
    except ValueError:
        return None
    return full


class ToolRunner:
    """Executes agent tools against a cloned repository."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.tests_passed = False
        self.edit_count = 0

    def read_file(self, path: str) -> str:
        full = _resolve_path(self.repo_path, path)
        if full is None:
            return f"ERROR: Path escapes repo: {path}"
        if not full.exists():
            return f"ERROR: File not found: {path}"
        if not full.is_file():
            return f"ERROR: Not a file: {path}"
        try:
            content = full.read_text(encoding="utf-8")
        except Exception as exc:
            return f"ERROR: {exc}"
        if len(content.encode()) > MAX_FILE_BYTES:
            return content[:MAX_FILE_BYTES] + "\n...[TRUNCATED]"
        return content

    def list_files(self, path: str) -> str:
        full = self.repo_path if path == "." else _resolve_path(self.repo_path, path)
        if full is None:
            return f"ERROR: Path escapes repo: {path}"
        if not full.exists():
            return f"ERROR: Path not found: {path}"
        try:
            entries = sorted(full.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            lines = []
            for entry in entries:
                rel = entry.relative_to(self.repo_path)
                prefix = "DIR " if entry.is_dir() else "FILE"
                lines.append(f"{prefix} {rel}")
            return "\n".join(lines) or "(empty directory)"
        except Exception as exc:
            return f"ERROR: {exc}"

    def search_code(self, query: str) -> str:
        try:
            result = subprocess.run(
                ["grep", "-rn", "--include=*.go", query, "."],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout.strip() or f"No matches for '{query}'"
            return _truncate(output)
        except Exception as exc:
            return f"ERROR: {exc}"

    def edit_file(self, path: str, old_str: str, new_str: str) -> str:
        full = _resolve_path(self.repo_path, path)
        if full is None:
            return f"ERROR: Path escapes repo: {path}"
        try:
            content = full.read_text(encoding="utf-8")
            if old_str not in content:
                return f"ERROR: old_str not found in {path}. Read the file again and copy exact text."
            if old_str == new_str:
                return "ERROR: old_str and new_str are identical"
            full.write_text(content.replace(old_str, new_str, 1), encoding="utf-8")
            self.edit_count += 1
            return f"SUCCESS: Edited {path} ({self.edit_count} edit(s) total)"
        except Exception as exc:
            return f"ERROR: {exc}"

    def run_go(self, args: str) -> str:
        cmd = ["go"] + args.split()
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=180,
            )
            status = "PASSED" if result.returncode == 0 else "FAILED"
            if "test" in args and result.returncode == 0:
                self.tests_passed = True
            output = _truncate(result.stdout + result.stderr)
            return f"[go {' '.join(cmd[1:])} — {status}]\n{output}"
        except FileNotFoundError:
            return "ERROR: 'go' not found. Install Go 1.21+ and ensure it is on PATH."
        except subprocess.TimeoutExpired:
            return "ERROR: Command timed out after 180s"
        except Exception as exc:
            return f"ERROR: {exc}"

    def run(self, name: str, inputs: dict) -> tuple[str, bool]:
        """Run a tool. Returns (result, is_submit)."""
        if name == "read_file":
            return self.read_file(inputs["path"]), False
        if name == "list_files":
            return self.list_files(inputs["path"]), False
        if name == "search_code":
            return self.search_code(inputs["query"]), False
        if name == "edit_file":
            return self.edit_file(inputs["path"], inputs["old_str"], inputs["new_str"]), False
        if name == "run_go":
            return self.run_go(inputs["args"]), False
        if name == "submit_pr":
            if self.edit_count == 0:
                return "ERROR: No edits made yet. Fix the issue before submitting.", False
            if not self.tests_passed:
                return (
                    "ERROR: Tests have not passed yet. Run go test and fix failures first.",
                    False,
                )
            return "PR summary accepted.", True
        return f"ERROR: Unknown tool '{name}'", False
