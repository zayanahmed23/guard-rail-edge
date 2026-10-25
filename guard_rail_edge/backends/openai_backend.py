"""OpenAI-compatible chat backend using Python standard library urllib only."""

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from typing import Any

from guard_rail_edge.backends.base import ChatBackend
from guard_rail_edge.evaluator import EvaluationError, EvaluatorConnectionError


class OpenAIBackend(ChatBackend):
    """Chat backend using OpenAI-compatible HTTP endpoints (OpenAI, vLLM, OpenRouter, etc.)."""

    def __init__(
        self,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        api_key_env: str = "OPENAI_API_KEY",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key_env = api_key_env

    def _get_api_key(self) -> str | None:
        key = os.environ.get(self.api_key_env, "").strip()
        return key if key else None

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "guard-rail-edge",
        }
        api_key = self._get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def preflight(self, model: str) -> None:
        """Check endpoint connectivity using GET /models if supported."""
        models_url = f"{self.base_url}/models"
        req = urllib.request.Request(models_url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models_list = [m.get("id") for m in data.get("data", []) if isinstance(m, dict)]
                if models_list and model not in models_list:
                    print(
                        f"[WARNING] Model '{model}' not explicitly listed by {self.base_url}/models. Proceeding anyway.",
                        file=sys.stderr,
                    )
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise EvaluatorConnectionError(
                    f"Authentication failed (HTTP 401). Please check your API key in environment variable '{self.api_key_env}'."
                ) from None
            # Many endpoints (vLLM, proxies) may return 404 or 405 for /models without failing /chat/completions
            print(
                f"[WARNING] Preflight endpoint probe {models_url} returned HTTP {exc.code}. Proceeding anyway.",
                file=sys.stderr,
            )
        except (socket.timeout, TimeoutError):
            raise EvaluationError(
                f"Connection to backend at '{self.base_url}' timed out after {self.timeout}s."
            ) from None
        except Exception as exc:
            # Non-blocking connectivity warning
            print(f"[WARNING] Preflight probe to {models_url} encountered: {exc}. Proceeding anyway.", file=sys.stderr)

    def _send_chat_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send JSON POST request to /chat/completions."""
        chat_url = f"{self.base_url}/chat/completions"
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(chat_url, data=req_data, headers=self._get_headers(), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_bytes = resp.read()
                return json.loads(raw_bytes.decode("utf-8"))  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise EvaluatorConnectionError(
                    f"Authentication failed (HTTP 401). Please check your API key in environment variable '{self.api_key_env}'."
                ) from None
            if exc.code == 400 and "response_format" in payload:
                # Fallback on 400: endpoint may not support response_format json_schema
                plain_payload = dict(payload)
                plain_payload.pop("response_format", None)
                plain_data = json.dumps(plain_payload).encode("utf-8")
                plain_req = urllib.request.Request(
                    chat_url, data=plain_data, headers=self._get_headers(), method="POST"
                )
                try:
                    with urllib.request.urlopen(plain_req, timeout=self.timeout) as fallback_resp:
                        return json.loads(fallback_resp.read().decode("utf-8"))  # type: ignore[no-any-return]
                except Exception as fallback_exc:
                    raise EvaluationError(
                        f"OpenAI backend request failed on plain fallback: {fallback_exc}"
                    ) from fallback_exc

            raise EvaluationError(f"OpenAI backend request failed with HTTP {exc.code}: {exc.reason}") from exc
        except (socket.timeout, TimeoutError):
            raise EvaluationError(
                f"OpenAI backend request timed out after {self.timeout}s."
            ) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise EvaluationError(
                    f"OpenAI backend request timed out after {self.timeout}s."
                ) from None
            raise EvaluationError(f"OpenAI backend network error: {exc.reason}") from exc
        except Exception as exc:
            raise EvaluationError(f"OpenAI backend execution failed: {exc}") from exc

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if seed is not None:
            payload["seed"] = seed

        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": json_schema,
                },
            }

        data = self._send_chat_request(payload)
        choices = data.get("choices", [])
        if not choices:
            raise EvaluationError(f"OpenAI backend returned empty choices list: {data}")

        first_choice = choices[0]
        content = first_choice.get("message", {}).get("content", "")
        return str(content).strip()

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(
            messages=messages,
            temperature=temperature,
            seed=seed,
            json_schema=json_schema,
            model=model,
        )
