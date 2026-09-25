"""The controller loop: plan a step, let the worker run it, decide whether the task is done."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from .worker import TaskResult

MAX_RESULT_CHARS = 2000

PLAN_PROMPT = """\
You plan the work of an AI agent that executes tasks on its own machine.
Given the overall task and the results so far, reply with exactly one concrete next step
in one or two sentences, and nothing else. The agent already runs on the target machine,
so the step must not tell it to connect to that machine first.
"""

JUDGE_PROMPT = """\
You decide whether a task is complete, based on the latest result.
Reply with exactly one word: DONE or CONTINUE.
"""


class Planner(Protocol):
    def ask(self, system: str, user: str) -> str: ...


class Worker(Protocol):
    def run(self, task: str) -> TaskResult: ...


@dataclass
class Round:
    step: str
    result: str
    ok: bool
    cost_usd: float
    verdict: str


@dataclass
class Run:
    task: str
    status: str = "running"
    rounds: list[Round] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(item.cost_usd for item in self.rounds)


def verdict(reply: str) -> str:
    """DONE only if the reply starts with that word, anything else means CONTINUE.

    A substring check would read "CONTINUE, not DONE yet" as finished.
    """
    words = reply.split()
    first = words[0].strip(".,;:!*\"'`").upper() if words else ""
    return "DONE" if first == "DONE" else "CONTINUE"


def orchestrate(
    task: str,
    planner: Planner,
    worker: Worker,
    *,
    max_rounds: int = 3,
    notify: Callable[[str], object] = print,
    state_file: Path | None = None,
) -> Run:
    """Work on `task` for at most `max_rounds` rounds and return what happened."""
    run = Run(task)
    _save(run, state_file)
    try:
        for number in range(1, max_rounds + 1):
            step = planner.ask(PLAN_PROMPT, _plan_input(run)).strip()
            result = worker.run(step)
            decision = verdict(
                planner.ask(
                    JUDGE_PROMPT,
                    f"Task: {task}\nLatest step: {step}\nLatest result: {_clip(result.text)}",
                )
            )
            run.rounds.append(Round(step, result.text, result.ok, result.cost_usd, decision))
            _save(run, state_file)
            notify(
                f"round {number}/{max_rounds}: {decision} | step: {step}"
                f" | result: {_clip(result.text, 300)} | cost: ${result.cost_usd:.2f}"
            )
            if decision == "DONE":
                run.status = "done"
                break
        else:
            run.status = f"stopped after {max_rounds} rounds"
    except Exception as error:
        run.status = f"failed: {error}"
        _save(run, state_file)
        notify(f"run failed: {error}")
        raise
    _save(run, state_file)
    return run


def _plan_input(run: Run) -> str:
    history = [
        {"step": item.step, "result": _clip(item.result), "ok": item.ok} for item in run.rounds
    ]
    return (
        f"Task: {run.task}\n"
        f"Results so far: {json.dumps(history, ensure_ascii=False)}\n"
        "What is the next step?"
    )


def _clip(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _save(run: Run, state_file: Path | None) -> None:
    if state_file is None:
        return
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state = {**asdict(run), "cost_usd": run.cost_usd}
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
