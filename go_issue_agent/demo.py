"""Demo mode — run without Gemini API using pre-generated sample output."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def run_demo(output_dir: Path, issue_url: str | None = None) -> dict:
    root = Path(__file__).resolve().parent.parent
    sample_dir = root / "sample_output"
    if not sample_dir.exists():
        raise FileNotFoundError(f"Sample output not found at {sample_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "changes.diff", "pr_summary.md"):
        shutil.copy2(sample_dir / name, output_dir / name)

    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    if issue_url:
        report["issue"]["url"] = issue_url
        (output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("DEMO MODE — using sample_output/ (no Gemini API calls)")
    print("=" * 60)
    print(f"  Issue: #{report['issue']['number']} — {report['issue']['title']}")
    print(f"  PR:    {report.get('pr', {}).get('title', 'N/A')}")
    print(f"  Files: {', '.join(report.get('diff_summary', {}).get('files_changed', []))}")
    print(f"  Output: {output_dir.resolve()}")
    print("\n  To run with live API later: fix .env key and run ./run.sh")

    return {
        "issue": report["issue"],
        "pr": report.get("pr"),
        "turns": report.get("turns_used", 0),
        "output_dir": str(output_dir),
        "demo": True,
    }
