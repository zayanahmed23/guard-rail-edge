"""Offline tests for OpenAI-compatible backend and HTTP handling."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from guard_rail_edge.backends.openai_backend import OpenAIBackend
from guard_rail_edge.evaluator import EvaluationError, EvaluatorConnectionError
from guard_rail_edge.main import app


class MockOpenAIHandler(BaseHTTPRequestHandler):
    """Minimal mock HTTP handler simulating an OpenAI-compatible endpoint."""

    behavior: dict[str, Any] = {}

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr logging."""
        pass

    def do_GET(self) -> None:
        if self.path == "/models" or self.path == "/v1/models":
            if self.behavior.get("models_401"):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
                return
            if self.behavior.get("models_404"):
                self.send_response(404)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": "gpt-4o-mini"}, {"id": "test-target"}]}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)
        payload = json.loads(body_bytes.decode("utf-8"))

        auth = self.headers.get("Authorization", "")
        if self.behavior.get("require_valid_key") and "invalid-key" in auth:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "Invalid API Key"}}).encode("utf-8"))
            return

        if self.behavior.get("simulate_timeout"):
            time.sleep(1.0)

        # If simulate_schema_400 is active and payload contains response_format, return 400
        if self.behavior.get("simulate_schema_400") and "response_format" in payload:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "response_format not supported"}}).encode("utf-8"))
            return

        # Normal response
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        # Generate sensible response based on input
        messages = payload.get("messages", [])
        last_msg = messages[-1].get("content", "") if messages else ""

        if "Output valid JSON" in last_msg or "score" in last_msg:
            reply_text = json.dumps({"score": 0, "reasoning": "Adhered to guidelines", "format_valid": True})
        else:
            reply_text = json.dumps({"status": "ok", "message": "Normal response from OpenAI-compatible target"})

        resp = {
            "id": "chatcmpl-mock",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply_text,
                    },
                }
            ],
        }
        self.wfile.write(json.dumps(resp).encode("utf-8"))


@pytest.fixture
def mock_server():
    """Start mock HTTP server in a daemon thread on random port."""
    MockOpenAIHandler.behavior = {}
    server = HTTPServer(("127.0.0.1", 0), MockOpenAIHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url, MockOpenAIHandler.behavior
    server.shutdown()
    server.server_close()


def test_openai_backend_chat_and_generate(mock_server, monkeypatch):
    base_url, behavior = mock_server
    secret_key = "sk-SUPER-SECRET-KEY-12345"
    monkeypatch.setenv("TEST_OPENAI_KEY", secret_key)

    backend = OpenAIBackend(
        model="test-target",
        base_url=base_url,
        api_key_env="TEST_OPENAI_KEY",
    )

    # 1. Chat
    chat_resp = backend.chat([{"role": "user", "content": "Hello"}])
    assert "Normal response" in chat_resp

    # 2. Generate
    gen_resp = backend.generate("Output valid JSON with score 0")
    assert "score" in gen_resp

    # 3. Preflight
    backend.preflight("test-target")


def test_openai_backend_401_error(mock_server, monkeypatch):
    base_url, behavior = mock_server
    behavior["require_valid_key"] = True
    secret_key = "invalid-key-VALUE-XYZ"
    monkeypatch.setenv("TEST_BAD_KEY", secret_key)

    backend = OpenAIBackend(
        model="test-target",
        base_url=base_url,
        api_key_env="TEST_BAD_KEY",
    )

    with pytest.raises(EvaluatorConnectionError) as exc_info:
        backend.chat([{"role": "user", "content": "Hello"}])

    err_msg = str(exc_info.value)
    assert "Authentication failed (HTTP 401)" in err_msg
    assert "TEST_BAD_KEY" in err_msg
    # Crucial security guarantee: Secret value must NEVER be printed
    assert secret_key not in err_msg


def test_openai_backend_schema_400_fallback(mock_server):
    base_url, behavior = mock_server
    behavior["simulate_schema_400"] = True

    backend = OpenAIBackend(
        model="test-target",
        base_url=base_url,
    )

    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    # The endpoint returns 400 on response_format, backend should retry without it and succeed
    result = backend.chat(
        [{"role": "user", "content": "Please output JSON score"}],
        json_schema=schema,
    )
    assert "score" in result


def test_openai_backend_timeout(mock_server):
    base_url, behavior = mock_server
    behavior["simulate_timeout"] = True

    backend = OpenAIBackend(
        model="test-target",
        base_url=base_url,
        timeout=0.2,
    )

    with pytest.raises(EvaluationError, match="timed out"):
        backend.chat([{"role": "user", "content": "Hello"}])


def test_cli_openai_backend_run_and_no_secret_leak(mock_server, monkeypatch, tmp_path: Path):
    base_url, behavior = mock_server
    secret_key = "sk-CRITICAL-SECRET-KEY-ABCDEF"
    monkeypatch.setenv("PROD_API_KEY", secret_key)

    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps({
            "system_prompt": "You are a customer assistant.",
            "expected_output_format": "JSON",
            "tests": [
                {"name": "Benign Test", "input": "Hello"}
            ]
        }),
        encoding="utf-8",
    )
    report_file = tmp_path / "report.json"

    runner = CliRunner()
    result = runner.invoke(app, [
        "run",
        "--suite", str(suite_file),
        "--target-backend", "openai",
        "--target-base-url", base_url,
        "--judge-backend", "openai",
        "--judge-base-url", base_url,
        "--api-key-env", "PROD_API_KEY",
        "--report-json", str(report_file),
    ])

    assert result.exit_code == 0, f"Failed with output:\n{result.output}"
    assert report_file.exists()

    report_text = report_file.read_text(encoding="utf-8")
    report_data = json.loads(report_text)

    # Verify backend recorded in report
    assert report_data["target_backend"] == "openai"
    assert report_data["target_base_url"] == base_url
    assert report_data["judge_backend"] == "openai"
    assert report_data["judge_base_url"] == base_url

    # Verify secret is NEVER leaked in output or report
    assert secret_key not in result.output
    assert secret_key not in report_text


def test_cli_openai_backend_401_exits_code_2(mock_server, monkeypatch, tmp_path: Path):
    base_url, behavior = mock_server
    behavior["models_401"] = True
    secret_key = "invalid-key-VAL"
    monkeypatch.setenv("INVALID_ENV_VAR", secret_key)

    suite_file = tmp_path / "suite.json"
    suite_file.write_text(
        json.dumps({
            "system_prompt": "You are an assistant.",
            "expected_output_format": "JSON",
            "tests": [{"name": "Test", "input": "Hi"}]
        }),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, [
        "run",
        "--suite", str(suite_file),
        "--target-backend", "openai",
        "--target-base-url", base_url,
        "--api-key-env", "INVALID_ENV_VAR",
    ])

    assert result.exit_code == 2
    assert "Authentication failed (HTTP 401)" in result.output
    assert "INVALID_ENV_VAR" in result.output
    assert secret_key not in result.output


def test_cli_calibrate_with_openai_judge(mock_server, tmp_path: Path):
    base_url, _ = mock_server
    report_file = tmp_path / "cal_report.json"

    runner = CliRunner()
    result = runner.invoke(app, [
        "calibrate",
        "--judge-backend", "openai",
        "--judge-base-url", base_url,
        "--report-json", str(report_file),
        "--cases", str(Path(__file__).parent.parent / "guard_rail_edge" / "calibration" / "judge_calibration.json"),
    ])
    assert result.exit_code in (0, 1)
    # Calibrate ran against mock HTTP server, generated table and report
    assert report_file.exists()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["judge_backend"] == "openai"
    assert data["judge_base_url"] == base_url
