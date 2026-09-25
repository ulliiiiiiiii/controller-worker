import json

import pytest


class FakePlanner:
    """Answers plan and judge prompts from two scripted lists and records every prompt."""

    def __init__(self, steps, verdicts):
        self.steps = list(steps)
        self.verdicts = list(verdicts)
        self.prompts = []

    def ask(self, system, user):
        self.prompts.append(user)
        return (self.verdicts if "DONE or CONTINUE" in system else self.steps).pop(0)


class FakeWorker:
    def __init__(self, result):
        self.result = result
        self.tasks = []

    def run(self, task):
        self.tasks.append(task)
        return self.result


@pytest.fixture
def fake_claude(tmp_path):
    """A stand-in for the claude executable that records its arguments and stdin."""
    log = tmp_path / "calls.jsonl"
    script = tmp_path / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"log = open({str(log)!r}, 'a')\n"
        "log.write(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read()}) + '\\n')\n"
        "print(json.dumps({'result': 'did it', 'total_cost_usd': 0.25,"
        " 'session_id': 'session-1', 'is_error': False}))\n"
    )
    script.chmod(0o755)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()]

    return script, calls
