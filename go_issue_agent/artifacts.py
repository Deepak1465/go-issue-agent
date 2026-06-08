"""Save agent run artifacts (diff, report, PR summary)."""

from __future__ import annotations

import json
from pathlib import Path


def save_artifacts(
    output_dir: Path,
    issue: dict,
    pr_result: dict | None,
    diff: str,
    actions: list[dict],
    turns: int,
    branch: str | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "issue": issue,
        "pr": pr_result or {},
        "branch": branch,
        "turns_used": turns,
        "actions": actions,
        "diff_summary": _diff_summary(diff),
    }

    (output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "changes.diff").write_text(diff, encoding="utf-8")
    (output_dir / "pr_summary.md").write_text(
        _build_pr_summary(issue, pr_result, diff, actions, branch),
        encoding="utf-8",
    )


def _diff_summary(diff: str) -> dict:
    if not diff or diff == "(no changes)":
        return {"files_changed": [], "lines_added": 0, "lines_removed": 0}
    files = []
    added = removed = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return {"files_changed": files, "lines_added": added, "lines_removed": removed}


def _build_pr_summary(
    issue: dict,
    pr_result: dict | None,
    diff: str,
    actions: list[dict],
    branch: str | None,
) -> str:
    title = pr_result.get("title", "N/A") if pr_result else "N/A"
    body = pr_result.get("body", "") if pr_result else ""

    lines = [
        "# Pull Request Summary",
        "",
        "## Title",
        title,
        "",
        "## Issue",
        issue["url"],
        "",
    ]

    if branch:
        lines.extend(["## Branch", f"`{branch}`", ""])

    if body:
        lines.extend(["## Description", body, ""])

    lines.extend(
        [
            "## Diff",
            "```diff",
            diff,
            "```",
            "",
            "## Agent Actions",
        ]
    )
    for action in actions:
        tool = action["tool"]
        args = json.dumps(action.get("args", {}), ensure_ascii=False)
        preview = action.get("result_preview", "")
        lines.append(f"- **{tool}** `{args}`")
        if preview and action.get("error"):
            lines.append(f"  - {preview}")

    return "\n".join(lines) + "\n"
