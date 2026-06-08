#!/usr/bin/env python3
"""CLI entry point for Go Issue Agent."""

import argparse
from pathlib import Path

from dotenv import load_dotenv

from go_issue_agent.agent import GoIssueAgent, DEFAULT_MAX_TURNS, DEFAULT_MODEL, DEFAULT_REPO_BASE
from go_issue_agent.demo import run_demo

# .env always wins over stale keys exported in the terminal
load_dotenv(override=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agentic AI for fixing Go GitHub issues (go-playground/validator)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./run.sh --demo                                    # no API key needed
  python main.py --issue https://github.com/.../issues/1561
  python main.py --issue https://github.com/.../issues/1529 --output ./runs/1529
        """,
    )
    parser.add_argument(
        "--issue",
        default="https://github.com/go-playground/validator/issues/1561",
        help="GitHub issue URL",
    )
    parser.add_argument(
        "--output",
        default="./output",
        help="Directory for artifacts: report.json, changes.diff, pr_summary.md (default: ./output)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run without Gemini API using sample_output/ (for demos when quota is exhausted)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Gemini model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help=f"Max agent turns (default: {DEFAULT_MAX_TURNS})",
    )
    parser.add_argument(
        "--repo-dir",
        default=str(DEFAULT_REPO_BASE),
        help=f"Where to clone repos (default: {DEFAULT_REPO_BASE})",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo(Path(args.output), args.issue)
        return

    agent = GoIssueAgent(
        model=args.model,
        max_turns=args.max_turns,
        repo_base=Path(args.repo_dir),
    )
    agent.run(args.issue, Path(args.output))


if __name__ == "__main__":
    main()
