"""Gemini-powered tool-calling agent loop."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

EventCallback = Callable[[dict], None]

from google import genai
from google.genai import types

from go_issue_agent.artifacts import save_artifacts
from go_issue_agent.gemini_client import (
    DEFAULT_MODEL,
    MAX_API_RETRIES,
    MODEL_FALLBACK_CHAIN,
    RATE_LIMIT_COOLDOWN,
    classify_api_error,
    connect_gemini,
    next_model,
    normalize_api_key,
    parse_retry_seconds,
    resolve_model_chain,
    retry_wait_seconds,
    validate_api_key_present,
)
from go_issue_agent.github_client import (
    clone_repo,
    create_fix_branch,
    fetch_issue,
    get_diff,
)
from go_issue_agent.prompts import (
    build_initial_prompt,
    build_system_prompt,
    load_project_rules,
)
from go_issue_agent.tools import ToolRunner, tool_declarations

DEFAULT_MAX_TURNS = 30
DEFAULT_REPO_BASE = Path("/tmp/agent_repos")


class GoIssueAgent:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_turns: int = DEFAULT_MAX_TURNS,
        repo_base: Path = DEFAULT_REPO_BASE,
        config_dir: Path | None = None,
    ):
        self.model = model
        self.max_turns = max_turns
        self.repo_base = repo_base
        self.config_dir = config_dir or Path(__file__).resolve().parent.parent / "configs"

    def run(
        self,
        issue_url: str,
        output_dir: Path,
        on_event: EventCallback | None = None,
    ) -> dict:
        def emit(event_type: str, **data: object) -> None:
            if on_event:
                on_event({"type": event_type, **data})

        print("\n" + "=" * 60)
        print("STEP 1: Fetch issue from GitHub")
        print("=" * 60)
        emit("phase", phase="fetch_issue", message="Fetching issue from GitHub")
        issue = fetch_issue(issue_url)
        print(f"  Issue #{issue['number']}: {issue['title']}")
        emit("issue", issue=issue)

        print("\n" + "=" * 60)
        print("STEP 2: Clone repository")
        print("=" * 60)
        emit("phase", phase="clone_repo", message="Cloning repository")
        repo_path = clone_repo(issue["repo_url"], issue["repo"], self.repo_base)

        print("\n" + "=" * 60)
        print("STEP 3: Create working branch")
        print("=" * 60)
        emit("phase", phase="create_branch", message="Creating fix branch")
        branch = create_fix_branch(repo_path, issue["number"])
        print(f"  Branch: {branch}")
        emit("branch", branch=branch)

        print("\n" + "=" * 60)
        print("STEP 4: Agent loop (Gemini + tools)")
        print("=" * 60)
        emit("phase", phase="agent_loop", message="Running agent loop")

        raw_key = os.environ.get("GEMINI_API_KEY", "")
        api_key = normalize_api_key(raw_key)
        key_err = validate_api_key_present(api_key)
        if key_err:
            emit("error", message=key_err)
            print(f"ERROR: {key_err}")
            print("  Or run without API: ./run.sh --demo")
            sys.exit(1)

        client = genai.Client(api_key=api_key)
        preferred = [self.model] + [m for m in MODEL_FALLBACK_CHAIN if m != self.model]
        try:
            models_to_try = resolve_model_chain(client, preferred)
        except RuntimeError as exc:
            msg = str(exc)
            emit("error", message=msg)
            print(f"ERROR: {msg}")
            sys.exit(1)

        print("  Connecting to Gemini API...")
        try:
            active_model = connect_gemini(client, models_to_try)
            print(f"  ✓ Connected with model: {active_model}")
        except RuntimeError as exc:
            msg = str(exc)
            emit("error", message=msg)
            print(f"ERROR: {msg}")
            sys.exit(1)

        project_rules = load_project_rules(self.config_dir, issue["owner"], issue["repo"])
        system_prompt = build_system_prompt(project_rules)
        initial_prompt = build_initial_prompt(issue)
        tools = types.Tool(function_declarations=tool_declarations())

        runner = ToolRunner(repo_path)
        history: list = []
        actions: list[dict] = []
        pr_result: dict | None = None
        turn = 0
        api_retries = 0
        blocked_models: set[str] = set()

        while turn < self.max_turns:
            turn += 1
            print(f"\n── Turn {turn}/{self.max_turns} ──────────────────────────────────")
            emit("turn", turn=turn, max_turns=self.max_turns)

            try:
                contents = (
                    history
                    if history
                    else [{"role": "user", "parts": [{"text": initial_prompt}]}]
                )
                if not contents:
                    raise RuntimeError("Internal error: empty contents for Gemini request")

                response = client.models.generate_content(
                    model=active_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        tools=[tools],
                        temperature=0.1,
                    ),
                )

                api_retries = 0  # success — reset retry counter

                if not response or not response.candidates:
                    raise RuntimeError("Empty response from Gemini")

                candidate = response.candidates[0]
                if not history:
                    history.append({"role": "user", "parts": [{"text": initial_prompt}]})
                history.append({"role": "model", "parts": candidate.content.parts})

                fn_calls = [
                    p
                    for p in candidate.content.parts
                    if hasattr(p, "function_call") and p.function_call
                ]

                if not fn_calls:
                    text_parts = [
                        p.text for p in candidate.content.parts if hasattr(p, "text") and p.text
                    ]
                    if text_parts:
                        print(f"  Model: {text_parts[0][:200]}...")
                    print("  No tool calls — stopping.")
                    break

                tool_responses = []
                for part in fn_calls:
                    fc = part.function_call
                    name = fc.name
                    args = dict(fc.args) if fc.args else {}

                    print(f"  → {name}({self._short_args(args)})")
                    emit(
                        "tool",
                        turn=turn,
                        tool=name,
                        args=self._sanitize_args(name, args),
                    )

                    if name == "submit_pr":
                        result, is_submit = runner.run(name, args)
                        action = {
                            "tool": name,
                            "args": args,
                            "result_preview": result[:300],
                            "error": result.startswith("ERROR"),
                        }
                        actions.append(action)

                        if is_submit:
                            pr_result = args
                            print("  ✓ PR summary accepted")
                            emit("tool_result", turn=turn, tool=name, result=result, success=True)
                        else:
                            print(f"  ← {result}")
                            emit("tool_result", turn=turn, tool=name, result=result, success=False)
                        tool_responses.append(
                            types.Part.from_function_response(
                                name=name, response={"result": result}
                            )
                        )
                    else:
                        result, _ = runner.run(name, args)
                        preview = result[:200].replace("\n", " ")
                        print(f"  ← {preview}{'...' if len(result) > 200 else ''}")
                        emit(
                            "tool_result",
                            turn=turn,
                            tool=name,
                            result=preview,
                            success=not result.startswith("ERROR"),
                        )

                        actions.append(
                            {
                                "tool": name,
                                "args": self._sanitize_args(name, args),
                                "result_preview": preview,
                                "error": result.startswith("ERROR"),
                            }
                        )
                        tool_responses.append(
                            types.Part.from_function_response(
                                name=name, response={"result": result}
                            )
                        )

                history.append({"role": "user", "parts": tool_responses})

                if pr_result:
                    break

                time.sleep(1.0)

            except Exception as exc:
                err = str(exc)
                kind = classify_api_error(err)

                if kind == "auth":
                    msg = (
                        "Gemini rejected the API key. Update GEMINI_API_KEY in .env\n"
                        "  https://aistudio.google.com/apikey"
                    )
                    emit("error", message=msg)
                    raise RuntimeError(msg) from exc

                if kind == "model_not_found":
                    blocked_models.add(active_model)
                    alt = next_model(active_model, models_to_try, blocked=blocked_models)
                    if alt:
                        print(f"  Model {active_model} unavailable — switching to {alt}")
                        active_model = alt
                        api_retries = 0
                        turn -= 1
                        continue
                    msg = (
                        f"Gemini model {active_model!r} is not available and no fallback remains.\n"
                        "  Run: ./run.sh --demo"
                    )
                    emit("error", message=msg)
                    raise RuntimeError(msg) from exc

                if kind in ("rate_limit", "unavailable"):
                    api_retries += 1
                    server_wait = parse_retry_seconds(err)
                    switch_after = 3 if kind == "rate_limit" else MAX_API_RETRIES

                    if api_retries >= switch_after:
                        alt = next_model(
                            active_model, models_to_try, blocked=blocked_models
                        )
                        if alt:
                            print(f"  Switching model: {active_model} → {alt}")
                            active_model = alt
                            api_retries = 0
                            turn -= 1
                            continue
                        print(
                            f"  All models busy — waiting {RATE_LIMIT_COOLDOWN}s "
                            f"and retrying {models_to_try[0]}..."
                        )
                        emit(
                            "phase",
                            phase="retry",
                            message=f"Cooldown {RATE_LIMIT_COOLDOWN}s, retry chain",
                        )
                        time.sleep(RATE_LIMIT_COOLDOWN)
                        active_model = models_to_try[0]
                        api_retries = 0
                        turn -= 1
                        continue

                    if api_retries > MAX_API_RETRIES:
                        msg = (
                            f"Gemini API limit reached after {MAX_API_RETRIES} retries.\n"
                            "  Wait a minute and rerun, use a paid API key, or: ./run.sh --demo"
                        )
                        emit("error", message=msg)
                        raise RuntimeError(msg) from exc

                    if server_wait and server_wait <= 120:
                        wait = int(server_wait) + 2
                    else:
                        wait = retry_wait_seconds(api_retries)
                    label = "Rate limit" if kind == "rate_limit" else "Service busy"
                    print(f"  {label} ({api_retries}/{MAX_API_RETRIES}) — waiting {wait}s...")
                    emit("phase", phase="retry", message=f"{label}, retry in {wait}s")
                    time.sleep(wait)
                    turn -= 1
                    continue

                raise

        print("\n" + "=" * 60)
        print("STEP 5: Save artifacts")
        print("=" * 60)

        diff = get_diff(repo_path)
        save_artifacts(output_dir, issue, pr_result, diff, actions, turn, branch)

        print(f"  Output directory: {output_dir.resolve()}")
        print(f"  Turns used: {turn}")
        print(f"  Edits: {runner.edit_count}")
        print(f"  PR ready: {'yes' if pr_result else 'no'}")

        result = {
            "issue": issue,
            "pr": pr_result,
            "turns": turn,
            "edits": runner.edit_count,
            "branch": branch,
            "output_dir": str(output_dir),
            "diff": diff,
            "actions": actions,
            "pr_ready": pr_result is not None,
        }
        emit("complete", result=result)
        return result

    @staticmethod
    def _short_args(args: dict) -> str:
        if "old_str" in args:
            return f"path={args.get('path')!r}, old_str=<{len(args['old_str'])} chars>, ..."
        if "new_str" in args and "old_str" not in args:
            return ", ".join(f"{k}={v!r}" for k, v in args.items())
        return ", ".join(f"{k}={v!r}" for k, v in args.items())

    @staticmethod
    def _sanitize_args(name: str, args: dict) -> dict:
        """Store action log without huge edit payloads."""
        if name != "edit_file":
            return args
        return {
            "path": args.get("path"),
            "old_str_chars": len(args.get("old_str", "")),
            "new_str_chars": len(args.get("new_str", "")),
        }
