"""Command line interface."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .gateway import Gateway, GatewayError
from .notify import TmuxNotifier
from .orchestrator import orchestrate
from .usage import DEFAULT_LOG_DIR, Usage, analyse, collect
from .worker import DEFAULT_BUDGET_USD, RemoteWorker, run_task

STATE_DIR = Path.home() / ".local" / "state" / "controller-worker"


def cmd_run(args: argparse.Namespace) -> int:
    notify = TmuxNotifier(args.notify_tmux) if args.notify_tmux else print
    worker = RemoteWorker(args.worker, command=args.worker_command)
    run = orchestrate(
        args.task,
        Gateway.from_env(),
        worker,
        max_rounds=args.rounds,
        notify=notify,
        state_file=args.state,
    )
    print(f"{run.status}, {len(run.rounds)} rounds, ${run.cost_usd:.2f}, details in {args.state}")
    return 0 if run.status == "done" else 1


def cmd_run_task(args: argparse.Namespace) -> int:
    task = sys.stdin.read().strip()
    if not task:
        print("expected the task on stdin", file=sys.stderr)
        return 2
    result = run_task(
        task, budget_usd=args.budget_usd, session_file=args.session_file, claude=args.claude
    )
    print(result.to_json())
    return 0 if result.ok else 1


def cmd_stats(args: argparse.Namespace) -> int:
    print(collect(args.log_dir).to_json())
    return 0


def cmd_usage(args: argparse.Namespace) -> int:
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", args.worker, f"{args.worker_program} stats"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    try:
        worker = Usage(**json.loads(completed.stdout))
    except (ValueError, TypeError):
        print(f"no stats from {args.worker}: {completed.stderr.strip()}", file=sys.stderr)
        return 1
    print(analyse(collect(args.log_dir), worker, Gateway.from_env()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="controller-worker",
        description="Delegate work from one Claude Code instance to another over SSH.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run = commands.add_parser("run", help="work on a task with the worker (controller side)")
    run.add_argument("task")
    run.add_argument("--worker", required=True, metavar="HOST", help="SSH host of the worker")
    run.add_argument("--rounds", type=int, default=3, help="maximum number of rounds")
    run.add_argument("--notify-tmux", metavar="SESSION", help="send status to this tmux session")
    run.add_argument("--state", type=Path, default=STATE_DIR / "last-run.json")
    run.add_argument(
        "--worker-command",
        default="controller-worker run-task",
        help="command to run on the worker host",
    )
    run.set_defaults(handler=cmd_run)

    task = commands.add_parser("run-task", help="run one task from stdin (worker side)")
    task.add_argument(
        "--budget-usd",
        type=float,
        default=float(os.environ.get("WORKER_BUDGET_USD", DEFAULT_BUDGET_USD)),
        help="hard cost limit per task (default: $WORKER_BUDGET_USD or 1.0)",
    )
    task.add_argument("--session-file", type=Path, default=STATE_DIR / "worker-session")
    task.add_argument("--claude", default="claude", help="Claude Code executable")
    task.set_defaults(handler=cmd_run_task)

    stats = commands.add_parser("stats", help="usage numbers from the local session logs")
    stats.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    stats.set_defaults(handler=cmd_stats)

    usage = commands.add_parser("usage", help="compare usage of controller and worker")
    usage.add_argument("--worker", required=True, metavar="HOST")
    usage.add_argument("--worker-program", default="controller-worker")
    usage.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    usage.set_defaults(handler=cmd_usage)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except GatewayError as error:
        print(f"controller-worker: {error}", file=sys.stderr)
        return 1
