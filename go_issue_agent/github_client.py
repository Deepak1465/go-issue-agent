"""GitHub issue fetching and repository cloning."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import requests

ISSUE_URL_RE = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)"
)


def parse_issue_url(issue_url: str) -> tuple[str, str, int]:
    match = ISSUE_URL_RE.match(issue_url.rstrip("/"))
    if not match:
        raise ValueError(f"Invalid GitHub issue URL: {issue_url}")
    return match.group("owner"), match.group("repo"), int(match.group("number"))


def fetch_issue(issue_url: str) -> dict:
    owner, repo, number = parse_issue_url(issue_url)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    print(f"  Fetching issue: {api_url}")
    resp = requests.get(
        api_url,
        headers={"Accept": "application/vnd.github.v3+json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "number": data["number"],
        "title": data["title"],
        "body": data.get("body") or "",
        "url": issue_url,
        "owner": owner,
        "repo": repo,
        "repo_url": f"https://github.com/{owner}/{repo}",
    }


def clone_repo(repo_url: str, repo_name: str, base_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    dest = base_dir / repo_name
    if dest.exists():
        print(f"  Repo already at {dest} — pulling latest...")
        subprocess.run(["git", "pull", "--quiet"], cwd=dest, check=False)
    else:
        print(f"  Cloning {repo_url}...")
        subprocess.run(
            ["git", "clone", "--depth=1", "--quiet", repo_url, str(dest)],
            check=True,
        )
    return dest


def create_fix_branch(repo_path: Path, issue_number: int) -> str:
    branch = f"agent/fix-issue-{issue_number}"
    subprocess.run(["git", "checkout", "-B", branch], cwd=repo_path, check=True)
    return branch


def get_diff(repo_path: Path) -> str:
    result = subprocess.run(
        ["git", "diff"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.stdout or "(no changes)"
