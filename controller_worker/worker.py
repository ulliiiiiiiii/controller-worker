"""Run tasks with headless Claude Code on the worker machine."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

DEFAULT_BUDGET_USD = 1.0


@dataclass(frozen=True)
class TaskResult:
    text: str
    ok: bool
    cost_usd: float = 0.0
    session_id: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def parse_claude_output(output: str) -> TaskResult:
    """Read the result of `claude --print --output-format json`."""
    try:
        data: Any = json.loads(output)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return TaskResult(text=output.strip() or "(no output)", ok=False)
    cost = data.get("total_cost_usd")
    session = data.get("session_id")
    return TaskResult(
        text=str(data.get("result") or "(no result)"),
        ok=not data.get("is_error", False),
        cost_usd=float(cost) if isinstance(cost, (int, float)) else 0.0,
        session_id=session if isinstance(session, str) and session else None,
    )


def run_task(
    task: str,
    *,
    budget_usd: float = DEFAULT_BUDGET_USD,
    session_file: Path | None = None,
    claude: str = "claude",
    timeout: float = 1800,
) -> TaskResult:
    """Run one task in Claude Code with a hard cost limit for this call.

    With a session file, each task resumes the session of the previous one, so the worker
    keeps its context from round to round.
    """
    argv = [claude, "--print", "--output-format", "json", "--max-budget-usd", f"{budget_usd:g}"]
    if session_file is not None and session_file.exists():
        session_id = session_file.read_text().strip()
        if session_id:
            argv += ["--resume", session_id]
    try:
        completed = subprocess.run(
            argv, input=task, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return TaskResult(text=f"worker timed out after {timeout:g} s", ok=False)
    result = parse_claude_output(completed.stdout)
    if completed.returncode != 0 and result.ok:
        result = replace(result, ok=False)
    if session_file is not None and result.session_id:
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(result.session_id)
    return result


@dataclass(frozen=True)
class RemoteWorker:
    """Runs `controller-worker run-task` on another machine over SSH."""

    host: str
    command: str = "controller-worker run-task"
    ssh: Sequence[str] = ("ssh", "-o", "BatchMode=yes")
    timeout: float = 1900  # a little longer than the worker's own limit

    def run(self, task: str) -> TaskResult:
        try:
            completed = subprocess.run(
                [*self.ssh, self.host, self.command],
                input=task,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return TaskResult(text=f"no answer from {self.host} after {self.timeout:g} s", ok=False)
        try:
            data = json.loads(completed.stdout)
            return TaskResult(**data)
        except (ValueError, TypeError):
            detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
            return TaskResult(text=f"worker on {self.host} failed: {detail}", ok=False)
