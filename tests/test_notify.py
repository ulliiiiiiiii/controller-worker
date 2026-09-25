from controller_worker import notify
from controller_worker.notify import TmuxNotifier


class Completed:
    def __init__(self, returncode):
        self.returncode = returncode


def test_sends_one_line_then_enter(monkeypatch):
    calls = []
    monkeypatch.setattr(
        notify.subprocess, "run", lambda command, **kwargs: calls.append(command) or Completed(0)
    )
    assert TmuxNotifier("controller")("round 1/3: DONE\nall good")
    assert calls == [
        ["tmux", "send-keys", "-t", "controller", "-l", "round 1/3: DONE | all good"],
        ["tmux", "send-keys", "-t", "controller", "Enter"],
    ]


def test_warns_when_the_session_is_missing(monkeypatch, capsys):
    monkeypatch.setattr(notify.subprocess, "run", lambda command, **kwargs: Completed(1))
    assert not TmuxNotifier("controller")("hello")
    assert "could not reach tmux session 'controller'" in capsys.readouterr().err
