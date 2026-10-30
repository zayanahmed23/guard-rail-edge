"""OpenAI-compatible chat backend using Python standard library urllib only."""

import json
import os
import random
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from guard_rail_edge.backends.base import ChatBackend
from guard_rail_edge.evaluator import EvaluationError, EvaluatorConnectionError


class OpenAIBackend(ChatBackend):
    """Chat backend using OpenAI-compatible HTTP endpoints (OpenAI, vLLM, OpenRouter, Groq, etc.)."""

    def __init__(
        self,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        api_key_env: str = "OPENAI_API_KEY",
        max_rpm: int | None = None,
        backend_type: str = "openai",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key_env = api_key_env
        self.max_rpm = max_rpm
        self.backend_type = backend_type
        self._last_request_time: float = 0.0

    def _get_api_key(self) -> str | None:
        key = os.environ.get(self.api_key_env, "").strip()
        if not key and sys.platform == "win32":
            try:
                import winreg

                roots = [
                    (winreg.HKEY_CURRENT_USER, r"Environment"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                ]
                for root, subpath in roots:
                    try:
                        with winreg.OpenKey(root, subpath) as k:
                            val, _ = winreg.QueryValueEx(k, self.api_key_env)
                            if val and str(val).strip():
                                return str(val).strip()
                    except OSError:
                        pass
            except Exception:
                pass
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

    def _apply_throttle(self) -> None:
        """Throttle requests per minute to stay within free tier quotas."""
        if self.max_rpm and self.max_rpm > 0:
            min_interval = 60.0 / self.max_rpm
            elapsed = time.time() - self._last_request_time
            if self._last_request_time > 0 and elapsed < min_interval:
                wait_sec = min_interval - elapsed
                print(
                    f"[Rate Limit] Throttling ({self.max_rpm} rpm): waiting {wait_sec:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait_sec)
            self._last_request_time = time.time()

    def preflight(self, model: str) -> None:
        """Check endpoint connectivity and API key configuration using GET /models if supported."""
        is_local = "127.0.0.1" in self.base_url or "localhost" in self.base_url
        if self.backend_type in ("groq", "openrouter", "gemini", "github") and not is_local and not self._get_api_key():
            raise EvaluatorConnectionError(
                f"API key environment variable '{self.api_key_env}' is not set or empty."
            )
        self._apply_throttle()
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
            print(
                f"[WARNING] Preflight endpoint probe {models_url} returned HTTP {exc.code}. Proceeding anyway.",
                file=sys.stderr,
            )
        except (socket.timeout, TimeoutError):
            raise EvaluationError(
                f"Connection to backend at '{self.base_url}' timed out after {self.timeout}s."
            ) from None
        except Exception as exc:
            print(f"[WARNING] Preflight probe to {models_url} encountered: {exc}. Proceeding anyway.", file=sys.stderr)

    def list_models(self) -> list[str]:
        """Fetch available model IDs from GET /models."""
        if not self._get_api_key():
            raise EvaluatorConnectionError(
                f"API key environment variable '{self.api_key_env}' is not set or empty."
            )
        self._apply_throttle()
        models_url = f"{self.base_url}/models"
        req = urllib.request.Request(models_url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [str(m.get("id")) for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise EvaluatorConnectionError(
                    f"Authentication failed (HTTP 401). Please check your API key in environment variable '{self.api_key_env}'."
                ) from None
            raise EvaluationError(f"Failed to list models from {models_url} (HTTP {exc.code}): {exc.reason}") from exc
        except Exception as exc:
            raise EvaluationError(f"Failed to list models from {models_url}: {exc}") from exc

    def _send_chat_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send JSON POST request to /chat/completions with throttling and 429/503 retry backoff."""
        chat_url = f"{self.base_url}/chat/completions"
        req_data = json.dumps(payload).encode("utf-8")
        max_rate_retries = 5

        for rate_attempt in range(max_rate_retries + 1):
            self._apply_throttle()
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
                if exc.code in (429, 503):
                    if rate_attempt < max_rate_retries:
                        retry_after = exc.headers.get("Retry-After") if exc.headers else None
                        wait_sec: float
                        if retry_after:
                            try:
                                wait_sec = float(retry_after)
                            except ValueError:
                                wait_sec = float(2 ** (rate_attempt + 1)) + random.uniform(0.1, 0.5)
                        else:
                            wait_sec = float(2 ** (rate_attempt + 1)) + random.uniform(0.1, 0.5)
                        print(
                            f"[Rate Limit] HTTP {exc.code} received. Waiting {wait_sec:.1f}s before retry {rate_attempt + 1}/{max_rate_retries}...",
                            file=sys.stderr,
                        )
                        time.sleep(wait_sec)
                        continue
                    raise EvaluationError(
                        f"OpenAI backend rate limit exceeded after {max_rate_retries} attempts (HTTP {exc.code})."
                    ) from None
                if exc.code == 400 and "response_format" in payload:
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
                if isinstance(exc, (EvaluationError, EvaluatorConnectionError)):
                    raise exc
                raise EvaluationError(f"OpenAI backend execution failed: {exc}") from exc

        raise EvaluationError("OpenAI backend failed unexpectedly across retry loop.")

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
