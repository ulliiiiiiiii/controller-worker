import json

from controller_worker.usage import Usage, analyse, collect


def write_log(path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record) for record in records) + "\nnot json\n")


def test_collect_counts_days_models_and_tokens(tmp_path):
    reply = {"model": "model-a", "usage": {"output_tokens": 120}}
    write_log(
        tmp_path / "project-one" / "session.jsonl",
        {"timestamp": "2026-09-21T10:00:00Z", "message": {"role": "user", "content": "hi"}},
        {"timestamp": "2026-09-21T10:00:05Z", "message": reply},
    )
    write_log(
        tmp_path / "project-two" / "session.jsonl",
        {"timestamp": "2026-09-22T09:00:00Z", "message": {**reply, "model": "model-b"}},
        {"type": "summary"},
    )
    usage = collect(tmp_path)
    assert usage.records == 4
    assert usage.days == {"2026-09-21": 2, "2026-09-22": 1}
    assert usage.models == {"model-a": 1, "model-b": 1}
    assert usage.output_tokens == {"model-a": 120, "model-b": 120}


def test_usage_survives_a_json_round_trip():
    usage = Usage(3, {"2026-09-21": 3}, {"model-a": 2}, {"model-a": 50})
    assert Usage(**json.loads(usage.to_json())) == usage


def test_analyse_sends_both_sides_to_the_planner():
    class Planner:
        def ask(self, system, user):
            self.user = user
            return "- the worker idles on weekends"

    planner = Planner()
    assert analyse(Usage(1), Usage(2), planner) == "- the worker idles on weekends"
    assert '"records": 1' in planner.user and '"records": 2' in planner.user
