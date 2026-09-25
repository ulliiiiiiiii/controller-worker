"""Client for the OpenAI-compatible endpoint that handles the cheap glue steps."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

RETRY_STATUS = frozenset({429, 502, 503, 504})


class GatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class Gateway:
    base_url: str
    model: str
    api_key: str | None = None
    timeout: float = 90.0
    retries: int = 3
    backoff: float = 5.0

    @classmethod
    def from_env(cls) -> Gateway:
        """GATEWAY_BASE_URL and GATEWAY_MODEL, plus GATEWAY_API_KEY if the gateway needs one."""
        base_url = os.environ.get("GATEWAY_BASE_URL")
        model = os.environ.get("GATEWAY_MODEL")
        if not base_url or not model:
            raise GatewayError("set GATEWAY_BASE_URL and GATEWAY_MODEL")
        return cls(base_url.rstrip("/"), model, os.environ.get("GATEWAY_API_KEY"))

    def ask(self, system: str, user: str) -> str:
        """Return the reply text of one chat completion.

        Rate limits, gateway errors (502, 503, 504) and network errors are retried with a
        growing pause. Anything else fails at once.
        """
        request = self._request(system, user)
        for attempt in range(1, self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return _content(json.load(response))
            except urllib.error.HTTPError as error:
                if error.code not in RETRY_STATUS or attempt == self.retries:
                    raise GatewayError(f"gateway answered HTTP {error.code}") from error
            except OSError as error:
                if attempt == self.retries:
                    raise GatewayError(f"gateway unreachable: {error}") from error
            except ValueError as error:
                raise GatewayError("gateway reply is not JSON") from error
            time.sleep(self.backoff * attempt)
        raise GatewayError("retries must be at least 1")

    def _request(self, system: str, user: str) -> urllib.request.Request:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )


def _content(reply: Any) -> str:
    try:
        content = reply["choices"][0]["message"]["content"]
    except (LookupError, TypeError) as error:
        raise GatewayError("gateway reply has no message") from error
    if not isinstance(content, str) or not content.strip():
        raise GatewayError("gateway reply is empty")
    return content
