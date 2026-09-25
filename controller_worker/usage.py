"""Usage patterns from the raw Claude Code session logs of both machines.

The numbers come from the logs themselves, never from what an agent reports about its
own work. The gateway only looks for patterns in them.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .orchestrator import Planner

DEFAULT_LOG_DIR = Path.home() / ".claude" / "projects"

ANALYSIS_PROMPT = """\
You look at usage statistics of two Claude Code accounts, a controller that plans and a
worker that executes. Point out patterns, gaps and what could be improved, in at most six
short bullet points. Do not estimate costs.
"""


@dataclass
class Usage:
    records: int = 0
    days: dict[str, int] = field(default_factory=dict)
    models: dict[str, int] = field(default_factory=dict)
    output_tokens: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def collect(log_dir: Path = DEFAULT_LOG_DIR) -> Usage:
    """Count log records per day, and model replies and output tokens per model."""
    days: Counter[str] = Counter()
    models: Counter[str] = Counter()
    tokens: Counter[str] = Counter()
    records = 0
    for path in sorted(log_dir.glob("**/*.jsonl")):
        with path.open(encoding="utf-8", errors="replace") as lines:
            for line in lines:
                try:
                    record: Any = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict):
                    continue
                records += 1
                timestamp = record.get("timestamp")
                if isinstance(timestamp, str) and len(timestamp) >= 10:
                    days[timestamp[:10]] += 1
                message = record.get("message")
                usage = message.get("usage") if isinstance(message, dict) else None
                if isinstance(message, dict) and isinstance(usage, dict):
                    model = str(message.get("model") or "unknown")
                    models[model] += 1
                    output = usage.get("output_tokens")
                    tokens[model] += output if isinstance(output, int) else 0
    return Usage(records, dict(sorted(days.items())), dict(models), dict(tokens))


def analyse(controller: Usage, worker: Usage, planner: Planner) -> str:
    return planner.ask(
        ANALYSIS_PROMPT, f"Controller: {controller.to_json()}\nWorker: {worker.to_json()}"
    )
