import json

import pytest
from conftest import FakePlanner, FakeWorker

from controller_worker.orchestrator import orchestrate, verdict
from controller_worker.worker import TaskResult


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("DONE", "DONE"),
        ("done.", "DONE"),
        ("**DONE**", "DONE"),
        ("CONTINUE, not DONE yet", "CONTINUE"),
        ("Not DONE", "CONTINUE"),
        ("", "CONTINUE"),
        ("I think it is done", "CONTINUE"),
    ],
)
def test_verdict(reply, expected):
    assert verdict(reply) == expected


def test_orchestrate_stops_when_the_task_is_done(tmp_path):
    planner = FakePlanner(["list the disks", "check the smart data"], ["CONTINUE", "DONE"])
    worker = FakeWorker(TaskResult("all healthy", True, 0.1))
    messages = []
    state = tmp_path / "run.json"
    run = orchestrate(
        "check the disks", planner, worker, max_rounds=5, notify=messages.append, state_file=state
    )
    assert run.status == "done"
    assert worker.tasks == ["list the disks", "check the smart data"]
    assert run.cost_usd == pytest.approx(0.2)
    assert [message.split(":")[0] for message in messages] == ["round 1/5", "round 2/5"]
    saved = json.loads(state.read_text())
    assert saved["status"] == "done"
    assert len(saved["rounds"]) == 2


def test_orchestrate_passes_earlier_results_to_the_planner():
    planner = FakePlanner(["step one", "step two"], ["CONTINUE", "CONTINUE"])
    orchestrate(
        "task",
        planner,
        FakeWorker(TaskResult("result one", True)),
        max_rounds=2,
        notify=lambda message: None,
    )
    plan_prompts = [prompt for prompt in planner.prompts if "next step" in prompt]
    assert "result one" not in plan_prompts[0]
    assert "result one" in plan_prompts[1]


def test_orchestrate_stops_at_the_round_limit():
    planner = FakePlanner(["a", "b"], ["CONTINUE", "CONTINUE"])
    run = orchestrate(
        "task", planner, FakeWorker(TaskResult("", True)), max_rounds=2, notify=lambda message: None
    )
    assert run.status == "stopped after 2 rounds"


def test_orchestrate_records_a_failure_before_raising(tmp_path):
    class BrokenPlanner:
        def ask(self, system, user):
            raise RuntimeError("gateway down")

    messages = []
    state = tmp_path / "run.json"
    with pytest.raises(RuntimeError):
        orchestrate(
            "task", BrokenPlanner(), FakeWorker(None), notify=messages.append, state_file=state
        )
    assert json.loads(state.read_text())["status"] == "failed: gateway down"
    assert messages == ["run failed: gateway down"]
