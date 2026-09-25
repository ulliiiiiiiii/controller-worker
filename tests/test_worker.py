import sys

import pytest

from controller_worker.worker import RemoteWorker, TaskResult, parse_claude_output, run_task


def test_parse_claude_output():
    output = '{"result": "done", "total_cost_usd": 0.12, "session_id": "s1", "is_error": false}'
    assert parse_claude_output(output) == TaskResult("done", True, 0.12, "s1")


@pytest.mark.parametrize("output", ["", "Error: budget exceeded", "[1, 2]"])
def test_parse_claude_output_without_json(output):
    result = parse_claude_output(output)
    assert not result.ok
    assert result.text


def test_parse_claude_output_marks_errors():
    assert not parse_claude_output('{"result": "limit reached", "is_error": true}').ok


def test_run_task_passes_the_budget_and_resumes_the_session(fake_claude, tmp_path):
    claude, calls = fake_claude
    session_file = tmp_path / "state" / "session"
    first = run_task("step one", budget_usd=0.5, session_file=session_file, claude=str(claude))
    second = run_task("step two", budget_usd=0.5, session_file=session_file, claude=str(claude))
    assert first == TaskResult("did it", True, 0.25, "session-1")
    assert second.ok
    one, two = calls()
    assert one["argv"] == ["--print", "--output-format", "json", "--max-budget-usd", "0.5"]
    assert one["stdin"] == "step one"
    assert two["argv"][-2:] == ["--resume", "session-1"]


def test_run_task_fails_on_a_non_zero_exit(tmp_path):
    claude = tmp_path / "claude"
    claude.write_text('#!/bin/sh\necho \'{"result": "partial", "is_error": false}\'\nexit 3\n')
    claude.chmod(0o755)
    assert not run_task("step", claude=str(claude)).ok


def test_remote_worker_sends_the_task_on_stdin_and_parses_the_reply():
    echo = "import json, sys; print(json.dumps({'text': sys.stdin.read(), 'ok': True}))"
    worker = RemoteWorker("worker-host", command="ignored", ssh=(sys.executable, "-c", echo))
    assert worker.run("check the disks") == TaskResult("check the disks", True)


def test_remote_worker_reports_failures():
    fail = "import sys; print('Permission denied (publickey)', file=sys.stderr); sys.exit(255)"
    worker = RemoteWorker("worker-host", ssh=(sys.executable, "-c", fail))
    result = worker.run("check the disks")
    assert not result.ok
    assert "Permission denied" in result.text
