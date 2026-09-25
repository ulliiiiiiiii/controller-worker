import io
import json
import subprocess
import sys

import pytest

from controller_worker import __version__
from controller_worker.cli import main


def test_run_task_reads_stdin_and_prints_json(fake_claude, tmp_path, monkeypatch, capsys):
    claude, calls = fake_claude
    monkeypatch.setattr(sys, "stdin", io.StringIO("update the packages\n"))
    code = main(
        [
            "run-task",
            "--claude",
            str(claude),
            "--budget-usd",
            "0.3",
            "--session-file",
            str(tmp_path / "session"),
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["text"] == "did it"
    assert calls()[0]["stdin"] == "update the packages"
    assert "0.3" in calls()[0]["argv"]


def test_run_task_needs_a_task(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("  "))
    assert main(["run-task"]) == 2


def test_stats_prints_json(tmp_path, capsys):
    assert main(["stats", "--log-dir", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["records"] == 0


def test_run_without_gateway_configuration(monkeypatch, capsys):
    monkeypatch.delenv("GATEWAY_BASE_URL", raising=False)
    assert main(["run", "task", "--worker", "worker-host"]) == 1
    assert "GATEWAY_BASE_URL" in capsys.readouterr().err


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out == f"controller-worker {__version__}\n"


def test_runs_as_a_module():
    result = subprocess.run(
        [sys.executable, "-m", "controller_worker", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == f"controller-worker {__version__}\n"
