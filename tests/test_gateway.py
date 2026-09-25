import io
import json
import urllib.error

import pytest

from controller_worker import gateway
from controller_worker.gateway import Gateway, GatewayError


def reply(content):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


def http_error(code):
    return urllib.error.HTTPError("https://llm.example/v1", code, "error", {}, None)


@pytest.fixture
def no_sleep(monkeypatch):
    pauses = []
    monkeypatch.setattr(gateway.time, "sleep", pauses.append)
    return pauses


def serve(monkeypatch, *outcomes):
    """Let urlopen return or raise the given outcomes in order and record the requests."""
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        outcome = outcomes[len(requests) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(gateway.urllib.request, "urlopen", fake_urlopen)
    return requests


def test_ask_posts_a_chat_completion(monkeypatch):
    requests = serve(monkeypatch, reply("next step"))
    answer = Gateway("https://llm.example/v1", "free-model", "key").ask("system", "user")
    assert answer == "next step"
    request = requests[0]
    assert request.full_url == "https://llm.example/v1/chat/completions"
    assert request.get_header("Authorization") == "Bearer key"
    assert json.loads(request.data)["model"] == "free-model"


def test_ask_retries_rate_limits_and_gateway_errors(monkeypatch, no_sleep):
    serve(monkeypatch, http_error(429), http_error(503), reply("ok"))
    assert Gateway("https://llm.example/v1", "m").ask("s", "u") == "ok"
    assert no_sleep == [5.0, 10.0]


def test_ask_retries_network_errors(monkeypatch, no_sleep):
    serve(monkeypatch, urllib.error.URLError("refused"), ConnectionResetError(), reply("ok"))
    assert Gateway("https://llm.example/v1", "m").ask("s", "u") == "ok"


def test_ask_gives_up_after_the_last_retry(monkeypatch, no_sleep):
    serve(monkeypatch, *[http_error(503)] * 3)
    with pytest.raises(GatewayError, match="HTTP 503"):
        Gateway("https://llm.example/v1", "m").ask("s", "u")
    assert len(no_sleep) == 2


def test_ask_does_not_retry_client_errors(monkeypatch, no_sleep):
    serve(monkeypatch, http_error(401))
    with pytest.raises(GatewayError, match="HTTP 401"):
        Gateway("https://llm.example/v1", "m").ask("s", "u")
    assert no_sleep == []


@pytest.mark.parametrize(
    "body", [b"not json", b"{}", b'{"choices": [{"message": {"content": null}}]}']
)
def test_ask_rejects_unusable_replies(monkeypatch, body):
    serve(monkeypatch, io.BytesIO(body))
    with pytest.raises(GatewayError):
        Gateway("https://llm.example/v1", "m").ask("s", "u")


def test_from_env(monkeypatch):
    monkeypatch.delenv("GATEWAY_BASE_URL", raising=False)
    with pytest.raises(GatewayError, match="GATEWAY_BASE_URL"):
        Gateway.from_env()
    monkeypatch.setenv("GATEWAY_BASE_URL", "https://llm.example/v1/")
    monkeypatch.setenv("GATEWAY_MODEL", "free-model")
    monkeypatch.delenv("GATEWAY_API_KEY", raising=False)
    assert Gateway.from_env() == Gateway("https://llm.example/v1", "free-model")
