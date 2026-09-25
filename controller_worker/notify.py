"""Live status for the controller: type each message into its tmux session."""

from __future__ import annotations

import subprocess
import sys


class TmuxNotifier:
    """Sends messages as input to an interactive Claude Code session running in tmux."""

    def __init__(self, session: str) -> None:
        self.session = session

    def __call__(self, text: str) -> bool:
        line = " | ".join(part.strip() for part in text.splitlines() if part.strip())
        commands = [
            ["tmux", "send-keys", "-t", self.session, "-l", line],
            ["tmux", "send-keys", "-t", self.session, "Enter"],
        ]
        for command in commands:
            try:
                completed = subprocess.run(command, capture_output=True, timeout=10, check=False)
            except (OSError, subprocess.TimeoutExpired):
                completed = None
            if completed is None or completed.returncode != 0:
                print(
                    f"warning: could not reach tmux session {self.session!r}, is it running?",
                    file=sys.stderr,
                )
                return False
        return True
