"""FastAPI server for the Go Issue Agent web UI."""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv

load_dotenv(override=True)
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from go_issue_agent.agent import GoIssueAgent

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
SAMPLE_DIR = ROOT / "sample_output"
RUNS_DIR = ROOT / "runs"

app = FastAPI(title="Go Issue Agent", version="1.0.0")

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class RunRequest(BaseModel):
    issue_url: str = Field(..., description="GitHub issue URL")
    max_turns: int = Field(30, ge=5, le=50)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_sample() -> dict:
    report_path = SAMPLE_DIR / "report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Sample output not found")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    diff = (SAMPLE_DIR / "changes.diff").read_text(encoding="utf-8")
    pr_md = (SAMPLE_DIR / "pr_summary.md").read_text(encoding="utf-8")
    return {
        "issue": report.get("issue", {}),
        "pr": report.get("pr", {}),
        "branch": report.get("branch"),
        "turns": report.get("turns_used", 0),
        "edits": len([a for a in report.get("actions", []) if a.get("tool") == "edit_file"]),
        "actions": report.get("actions", []),
        "diff": diff,
        "pr_summary_md": pr_md,
        "pr_ready": bool(report.get("pr")),
        "demo": True,
    }


def _run_job(job_id: str, issue_url: str, max_turns: int) -> None:
    output_dir = RUNS_DIR / job_id

    def on_event(event: dict) -> None:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job:
                return
            job["events"].append(event)
            job["updated_at"] = _utc_now()
            if event["type"] == "phase":
                job["phase"] = event.get("phase")
                job["message"] = event.get("message")
            elif event["type"] == "issue":
                job["issue"] = event.get("issue")
            elif event["type"] == "branch":
                job["branch"] = event.get("branch")
            elif event["type"] == "turn":
                job["turn"] = event.get("turn")
                job["max_turns"] = event.get("max_turns")
            elif event["type"] == "error":
                job["status"] = "failed"
                job["error"] = event.get("message")
            elif event["type"] == "complete":
                job["status"] = "completed"
                job["result"] = event.get("result")

    try:
        agent = GoIssueAgent(max_turns=max_turns)
        result = agent.run(issue_url, output_dir, on_event=on_event)
        pr_md_path = output_dir / "pr_summary.md"
        with _jobs_lock:
            job = _jobs[job_id]
            job["status"] = "completed"
            job["result"] = result
            job["pr_summary_md"] = (
                pr_md_path.read_text(encoding="utf-8") if pr_md_path.exists() else ""
            )
            job["updated_at"] = _utc_now()
    except SystemExit:
        with _jobs_lock:
            if job_id in _jobs and _jobs[job_id]["status"] == "running":
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = "Agent exited — check GEMINI_API_KEY"
                _jobs[job_id]["updated_at"] = _utc_now()
    except Exception as exc:
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = str(exc)
                _jobs[job_id]["updated_at"] = _utc_now()


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY")),
        "go_available": _go_available(),
    }


@app.get("/api/sample")
def sample() -> dict:
    return _load_sample()


@app.post("/api/run")
def start_run(req: RunRequest) -> dict:
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(
            status_code=400,
            detail="GEMINI_API_KEY not set on server. Add it to .env and restart.",
        )
    if "github.com" not in req.issue_url or "/issues/" not in req.issue_url:
        raise HTTPException(status_code=400, detail="Invalid GitHub issue URL")

    job_id = str(uuid.uuid4())[:8]
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "issue_url": req.issue_url,
            "phase": "starting",
            "message": "Starting agent...",
            "turn": 0,
            "max_turns": req.max_turns,
            "events": [],
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, req.issue_url, req.max_turns),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return dict(job)


def _go_available() -> bool:
    import shutil

    return shutil.which("go") is not None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
