"""Regression tests verifying calibrate integrity, judge invocation, and label leak prevention."""

import http.server
import inspect
import json
import threading
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import guard_rail_edge
from guard_rail_edge.backends.base import ChatBackend
from guard_rail_edge.calibration import load_calibration_cases
from guard_rail_edge.deterministic import check_deterministic_leaks, check_deterministic_success
from guard_rail_edge.evaluator import grade_interaction
from guard_rail_edge.main import app

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def _get_expected_judge_call_count() -> int:
    """Calculate exact number of calibration cases that bypass deterministic checks and call judge."""
    cases = load_calibration_cases()
    det_count = 0
    for c in cases:
        if (
            check_deterministic_success(c.target_response) is not None
            or check_deterministic_leaks(c.system_prompt, c.target_response) is not None
        ):
            det_count += 1
    return len(cases) - det_count


class RecordingJudgeBackend(ChatBackend):
    """Fake backend recording calls and returning configured score."""

    def __init__(self, fixed_score: int, model: str = "fake-judge") -> None:
        self.model = model
        self.fixed_score = fixed_score
        self.call_count = 0

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        self.call_count += 1
        return json.dumps({
            "score": self.fixed_score,
            "reasoning": f"Recording judge returned score {self.fixed_score}.",
            "format_valid": True,
        })

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> str:
        self.call_count += 1
        return json.dumps({
            "score": self.fixed_score,
            "reasoning": f"Recording judge returned score {self.fixed_score}.",
            "format_valid": True,
        })

    def preflight(self, model: str) -> None:
        pass


def test_calibrate_fake_judge_always_zero(monkeypatch, tmp_path: Path):
    """4a: Non-mock calibrate with a fake judge backend that always returns score 0.

    - backend.generate/chat is called once per case not decided by deterministic checks
    - assert call count > 0 and equals expected number
    - verdict NOT TRUSTWORTHY, exit 1, leak detection rate 0% on judge-decided cases
    """
    fake_backend = RecordingJudgeBackend(fixed_score=0)
    monkeypatch.setattr("guard_rail_edge.backends.get_backend", lambda *args, **kwargs: fake_backend)

    report_file = tmp_path / "zero_report.json"
    result = runner.invoke(app, ["calibrate", "--report-json", str(report_file)])

    expected_judge_calls = _get_expected_judge_call_count()
    assert expected_judge_calls > 0
    assert fake_backend.call_count == expected_judge_calls

    assert result.exit_code == 1
    assert "NOT TRUSTWORTHY" in result.output

    assert report_file.exists()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["verdict"] == "NOT TRUSTWORTHY"
    assert data["passed"] is False

    # Check leak detection rate on judge-decided cases specifically
    judge_decided_exp2 = [
        r for r in data["results"]
        if r.get("detection") == "judge" and r.get("expected_score") == 2
    ]
    assert len(judge_decided_exp2) > 0
    judge_exp2_detected = sum(1 for r in judge_decided_exp2 if r.get("got_score") == 2)
    judge_leak_detection_rate = judge_exp2_detected / len(judge_decided_exp2)
    assert judge_leak_detection_rate == 0.0


def test_calibrate_fake_judge_always_two(monkeypatch, tmp_path: Path):
    """4b: Fake judge that always returns 2 -> false alarm rate 100%, NOT TRUSTWORTHY."""
    fake_backend = RecordingJudgeBackend(fixed_score=2)
    monkeypatch.setattr("guard_rail_edge.backends.get_backend", lambda *args, **kwargs: fake_backend)

    report_file = tmp_path / "two_report.json"
    result = runner.invoke(app, ["calibrate", "--report-json", str(report_file)])

    assert result.exit_code == 1
    assert "NOT TRUSTWORTHY" in result.output

    assert report_file.exists()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["verdict"] == "NOT TRUSTWORTHY"
    assert data["passed"] is False
    assert data["metrics_overall"]["false_alarm_rate"] == 1.0


def test_calibrate_test_oracle_perfect_judge(monkeypatch, tmp_path: Path):
    """4c: Fake judge returns correct label by looking up attack text in a dict built inside TEST -> TRUSTWORTHY."""
    cases = load_calibration_cases()
    test_oracle = {c.attack: c.expected_score for c in cases}

    class TestOracleJudge(ChatBackend):
        def __init__(self) -> None:
            self.call_count = 0

        def generate(
            self,
            prompt: str,
            temperature: float = 0.0,
            seed: int | None = None,
            json_schema: dict[str, Any] | None = None,
            model: str | None = None,
        ) -> str:
            self.call_count += 1
            for attack, score in test_oracle.items():
                if attack in prompt:
                    return json.dumps({
                        "score": score,
                        "reasoning": f"Test oracle score {score}",
                        "format_valid": True,
                    })
            return json.dumps({"score": 0, "reasoning": "Fallback", "format_valid": True})

        def chat(
            self,
            messages: list[dict[str, str]],
            temperature: float = 0.0,
            seed: int | None = None,
            json_schema: dict[str, Any] | None = None,
            model: str | None = None,
        ) -> str:
            self.call_count += 1
            return self.generate(messages[-1].get("content", ""))

        def preflight(self, model: str) -> None:
            pass

    oracle_backend = TestOracleJudge()
    monkeypatch.setattr("guard_rail_edge.backends.get_backend", lambda *args, **kwargs: oracle_backend)

    report_file = tmp_path / "perfect_report.json"
    result = runner.invoke(app, ["calibrate", "--report-json", str(report_file)])

    assert result.exit_code == 0
    assert "TRUSTWORTHY" in result.output

    expected_judge_calls = _get_expected_judge_call_count()
    assert oracle_backend.call_count == expected_judge_calls

    assert report_file.exists()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["verdict"] == "TRUSTWORTHY"
    assert data["passed"] is True
    assert data["metrics_overall"]["accuracy"] == 1.0
    assert data["metrics_overall"]["leak_detection_rate"] == 1.0
    assert data["metrics_overall"]["false_alarm_rate"] == 0.0


def test_calibrate_static_integrity_check():
    """4d: inspect.signature(grade_interaction) has no parameter named expected_score,

    and verify expected_score does not appear anywhere in guard_rail_edge outside of schemas/metrics.
    """
    sig = inspect.signature(grade_interaction)
    assert "expected_score" not in sig.parameters, (
        "grade_interaction must NOT accept expected_score parameter"
    )

    pkg_root = Path(guard_rail_edge.__file__).parent
    for py_file in pkg_root.rglob("*.py"):
        rel_parts = py_file.relative_to(pkg_root).parts
        # Exclude calibration package directory where dataset & metrics are defined
        if "calibration" in rel_parts:
            continue
        content = py_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(content.splitlines(), start=1):
            if "expected_score" in line:
                # Allowed only:
                # 1. schemas.py: CalibrationCase field declaration
                # 2. calibrate.py: populating expected_score in results dict for metrics computation
                allowed = (
                    py_file.name == "schemas.py"
                    or (py_file.name == "calibrate.py" and '"expected_score":' in line)
                )
                assert allowed, (
                    f"Forbidden 'expected_score' found at {py_file.name}:{lineno}: {line.strip()}"
                )


class FakeOpenAIHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Mock HTTP server handling OpenAI endpoints /models and /chat/completions."""

    chat_calls = 0

    def do_GET(self) -> None:
        if self.path.endswith("/models"):
            resp = json.dumps({"data": [{"id": "fake-openai-judge"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if "/chat/completions" in self.path:
            FakeOpenAIHTTPHandler.chat_calls += 1
            length = int(self.headers.get("Content-Length", 0))
            _ = self.rfile.read(length)
            resp_body = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "score": 0,
                                "reasoning": "Fake OpenAI wire judge scored 0.",
                                "format_valid": True,
                            })
                        }
                    }
                ]
            }
            resp = json.dumps(resp_body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


def test_calibrate_over_the_wire_http_openai(tmp_path: Path):
    """4e: Real HTTP OpenAIBackend against local http.server fake endpoint to prove over-the-wire calls."""
    FakeOpenAIHTTPHandler.chat_calls = 0
    server = http.server.HTTPServer(("127.0.0.1", 0), FakeOpenAIHTTPHandler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        report_file = tmp_path / "wire_report.json"
        result = runner.invoke(app, [
            "calibrate",
            "--judge-backend", "openai",
            "--judge-base-url", f"http://127.0.0.1:{port}/v1",
            "--judge-model", "fake-openai-judge",
            "--report-json", str(report_file),
        ])

        expected_judge_calls = _get_expected_judge_call_count()
        assert FakeOpenAIHTTPHandler.chat_calls == expected_judge_calls, (
            f"Expected {expected_judge_calls} HTTP requests over the wire, got {FakeOpenAIHTTPHandler.chat_calls}"
        )

        assert result.exit_code == 1
        assert "NOT TRUSTWORTHY" in result.output

        assert report_file.exists()
        data = json.loads(report_file.read_text(encoding="utf-8"))
        assert data["verdict"] == "NOT TRUSTWORTHY"

        judge_decided_exp2 = [
            r for r in data["results"]
            if r.get("detection") == "judge" and r.get("expected_score") == 2
        ]
        assert len(judge_decided_exp2) > 0
        judge_exp2_detected = sum(1 for r in judge_decided_exp2 if r.get("got_score") == 2)
        assert judge_exp2_detected == 0
    finally:
        server.shutdown()
        server.server_close()
