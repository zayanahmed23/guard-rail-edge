"""Tests for hosted judge presets, rate limiting, and models command."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from typer.testing import CliRunner

from guard_rail_edge.backends import get_backend
from guard_rail_edge.backends.openai_backend import OpenAIBackend
from guard_rail_edge.evaluator import EvaluationError
from guard_rail_edge.main import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def test_preset_resolves_url_and_env_var():
    """Provider presets automatically populate default base_url, api_key_env, and max_rpm."""
    b_groq = get_backend("groq", model="llama-3.3-70b-versatile")
    assert isinstance(b_groq, OpenAIBackend)
    assert b_groq.base_url == "https://api.groq.com/openai/v1"
    assert b_groq.api_key_env == "GROQ_API_KEY"
    assert b_groq.max_rpm == 25

    b_openrouter = get_backend("openrouter", model="meta-llama/llama-3-70b")
    assert isinstance(b_openrouter, OpenAIBackend)
    assert b_openrouter.base_url == "https://openrouter.ai/api/v1"
    assert b_openrouter.api_key_env == "OPENROUTER_API_KEY"
    assert b_openrouter.max_rpm == 15

    b_gemini = get_backend("gemini", model="gemini-1.5-flash")
    assert isinstance(b_gemini, OpenAIBackend)
    assert b_gemini.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert b_gemini.api_key_env == "GEMINI_API_KEY"
    assert b_gemini.max_rpm == 10

    b_github = get_backend("github", model="gpt-4o")
    assert isinstance(b_github, OpenAIBackend)
    assert b_github.base_url == "https://models.github.ai/inference"
    assert b_github.api_key_env == "GITHUB_MODELS_TOKEN"
    assert b_github.max_rpm == 10


def test_explicit_base_url_and_key_override_preset():
    """Explicit CLI options override preset defaults."""
    backend = get_backend(
        "groq",
        model="llama3-70b",
        base_url="https://custom.groq.internal/v1",
        api_key_env="CUSTOM_GROQ_KEY",
        max_rpm=50,
    )
    assert isinstance(backend, OpenAIBackend)
    assert backend.base_url == "https://custom.groq.internal/v1"
    assert backend.api_key_env == "CUSTOM_GROQ_KEY"
    assert backend.max_rpm == 50


class MockServerHandler(BaseHTTPRequestHandler):
    attempts = 0
    fail_count = 1

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = json.dumps({
            "data": [
                {"id": "llama-3.3-70b-versatile"},
                {"id": "mixtral-8x7b-32768"},
            ]
        })
        self.wfile.write(body.encode("utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            self.rfile.read(length)
        MockServerHandler.attempts += 1
        if MockServerHandler.attempts <= MockServerHandler.fail_count:
            self.send_response(429)
            self.send_header("Retry-After", "3")
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b'{"error": {"message": "Rate limit reached"}}')
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            body = json.dumps({
                "choices": [
                    {
                        "message": {
                            "content": '{"score": 0, "reasoning": "Safe response after retry.", "format_valid": true}'
                        }
                    }
                ]
            })
            self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        pass


@pytest.fixture
def mock_http_server():
    MockServerHandler.attempts = 0
    MockServerHandler.fail_count = 1
    server = HTTPServer(("127.0.0.1", 0), MockServerHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_429_with_retry_after_waits_and_succeeds(mock_http_server, monkeypatch):
    """HTTP 429 honours Retry-After header and succeeds on retry."""
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setenv("TEST_KEY", "dummy-secret-value")

    backend = OpenAIBackend(
        model="test-model",
        base_url=mock_http_server,
        api_key_env="TEST_KEY",
        timeout=10.0,
    )
    res = backend.generate("Hello world")
    assert "Safe response" in res
    assert sleeps == [3.0]
    assert MockServerHandler.attempts == 2


def test_repeated_429_exhausts_and_raises_evaluation_error(mock_http_server, monkeypatch):
    """5 repeated 429 responses trigger fail-closed EvaluationError."""
    MockServerHandler.fail_count = 10  # Always fail
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setenv("TEST_KEY", "dummy-secret-value")

    backend = OpenAIBackend(
        model="test-model",
        base_url=mock_http_server,
        api_key_env="TEST_KEY",
        timeout=10.0,
    )
    with pytest.raises(EvaluationError) as exc_info:
        backend.generate("Hello world")
    assert "rate limit exceeded" in str(exc_info.value).lower()
    assert len(sleeps) == 5


def test_max_rpm_throttles(monkeypatch):
    """OpenAIBackend enforces requests per minute throttle."""
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    backend = OpenAIBackend(
        model="test-model",
        base_url="http://fake-host",
        api_key_env="TEST_KEY",
        max_rpm=30,  # 30 rpm = 2.0 seconds between calls
    )

    # First call sets time
    backend._last_request_time = 100.0
    monkeypatch.setattr("time.time", lambda: 100.5)  # 0.5s elapsed < 2.0s min interval

    backend._apply_throttle()
    assert len(sleeps) == 1
    assert abs(sleeps[0] - 1.5) < 0.01


def test_api_key_never_leaked_in_output_or_exceptions(mock_http_server, monkeypatch):
    """Ensure secret API key value never appears in errors or messages."""
    secret_token = "sk-live-confidential-token-xyz-12345"
    monkeypatch.setenv("SECRET_ENV_VAR", secret_token)

    backend = OpenAIBackend(
        model="test-model",
        base_url=mock_http_server,
        api_key_env="SECRET_ENV_VAR",
    )

    MockServerHandler.fail_count = 10
    monkeypatch.setattr("time.sleep", lambda s: None)

    with pytest.raises(Exception) as exc_info:
        backend.generate("Test prompt")

    err_text = str(exc_info.value)
    assert secret_token not in err_text
    assert "SECRET_ENV_VAR" in err_text or "rate limit" in err_text


def test_models_command_lists_fake_ids(mock_http_server, monkeypatch):
    """The models CLI command fetches and prints model IDs from GET /models."""
    monkeypatch.setenv("TEST_KEY", "secret-token")
    result = runner.invoke(
        app,
        [
            "models",
            "--backend", "groq",
            "--base-url", mock_http_server,
            "--api-key-env", "TEST_KEY",
        ],
    )
    assert result.exit_code == 0
    assert "llama-3.3-70b-versatile" in result.output
    assert "mixtral-8x7b-32768" in result.output
    assert "secret-token" not in result.output


def test_missing_env_var_reports_expected_preflight_guidance(monkeypatch):
    """When api key env var is missing, preflight and list_models give helpful restart guidance."""
    monkeypatch.delenv("MISSING_TEST_KEY_12345", raising=False)
    backend = OpenAIBackend(
        model="test-model",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="MISSING_TEST_KEY_12345",
        backend_type="groq",
    )

    with pytest.raises(Exception) as exc_preflight:
        backend.preflight("test-model")
    expected_msg = (
        "Environment variable MISSING_TEST_KEY_12345 is not set in this process. "
        "On Windows, after `setx`, restart your terminal/IDE."
    )
    assert expected_msg in str(exc_preflight.value)

    with pytest.raises(Exception) as exc_models:
        backend.list_models()
    assert expected_msg in str(exc_models.value)


def test_no_winreg_in_guard_rail_edge():
    """winreg must never be imported or referenced anywhere in guard_rail_edge source."""
    from pathlib import Path
    pkg_dir = Path(__file__).resolve().parent.parent / "guard_rail_edge"
    matches = []
    for py_file in pkg_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "winreg" in content:
            matches.append(str(py_file))
    assert not matches, f"Found winreg in source files: {matches}"


def test_wilson_confidence_interval_known_values():
    """Verify Wilson 95% confidence interval against known mathematical benchmarks."""
    from guard_rail_edge.calibration import wilson_score_interval

    # 1. 8/8 -> lower bound ~0.676
    low_8_8, high_8_8 = wilson_score_interval(8, 8)
    assert abs(low_8_8 - 0.676) < 0.001
    assert high_8_8 == 1.0

    # 2. 0/8 -> upper bound ~0.324
    low_0_8, high_0_8 = wilson_score_interval(0, 8)
    assert low_0_8 == 0.0
    assert abs(high_0_8 - 0.324) < 0.001

    # 3. 16/20 -> ~[0.584, 0.919]
    low_16_20, high_16_20 = wilson_score_interval(16, 20)
    assert abs(low_16_20 - 0.584) < 0.001
    assert abs(high_16_20 - 0.919) < 0.001

    # 4. Zero denominator edge case
    assert wilson_score_interval(0, 0) == (0.0, 0.0)


def test_parse_retries_and_rate_limit_waits_counters(mock_http_server, monkeypatch):
    """Test that OpenAIBackend tracks rate_limit_waits and compute_calibration_metrics computes both."""
    from guard_rail_edge.calibration import compute_calibration_metrics

    # Test backend rate_limit_waits increment on 429
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setenv("TEST_KEY", "dummy-value")

    backend = OpenAIBackend(
        model="test-model",
        base_url=mock_http_server,
        api_key_env="TEST_KEY",
        timeout=10.0,
    )
    assert backend.rate_limit_waits == 0
    backend.generate("Hello")
    # mock_http_server returned 1 HTTP 429 before 200
    assert backend.rate_limit_waits == 1

    # Test compute_calibration_metrics surfaces retries and rate_limit_waits
    fake_results = [
        {"expected_score": 2, "got_score": 2, "retries_used": 2, "rate_limit_waits": 1},
        {"expected_score": 0, "got_score": 0, "retries_used": 1, "rate_limit_waits": 0},
    ]
    metrics = compute_calibration_metrics(fake_results, rate_limit_waits=backend.rate_limit_waits)
    assert metrics["retries"] == 3
    assert metrics["rate_limit_waits"] == 2  # 1 from result item + 1 from backend argument
    assert "leak_detection_ci" in metrics
    assert "false_alarm_ci" in metrics
