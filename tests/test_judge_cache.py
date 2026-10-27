"""Tests for judge caching, parse robustness, and debug output."""

import io
from pathlib import Path

import pytest

from guard_rail_edge.backends.base import ChatBackend
from guard_rail_edge.cache import JudgeCache
from guard_rail_edge.evaluator import _evaluate_with_judge
from guard_rail_edge.parser import parse_evaluation_response


class FakeBackend(ChatBackend):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_count = 0

    def chat(self, messages, temperature=0.0, seed=None, json_schema=None, model=None):
        return self.generate("", temperature, seed, json_schema, model)

    def generate(self, prompt, temperature=0.0, seed=None, json_schema=None, model=None):
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        return '{"score": 0, "reasoning": "Safe default", "format_valid": true}'

    def preflight(self, model: str) -> None:
        pass

    def get_digest(self, model: str) -> str | None:
        return "sha256:abc123digest"


def test_judge_cache_hit_avoids_backend_call(tmp_path: Path):
    """Calling judge twice with same prompt/options hits cache and avoids second backend call."""
    cache = JudgeCache(cache_dir=tmp_path / "cache", enabled=True)
    backend = FakeBackend(['{"score": 0, "reasoning": "Initial verdict", "format_valid": true}'])

    prompt = "Grade this interaction..."
    res1 = _evaluate_with_judge(
        client=backend,
        model_name="test-model",
        prompt=prompt,
        programmatic_format_ok=True,
        expected_output_format="Text",
        judge_cache=cache,
    )
    assert res1.score == 0
    assert backend.call_count == 1
    assert cache.hits == 0

    # Second call with same parameters should hit cache
    res2 = _evaluate_with_judge(
        client=backend,
        model_name="test-model",
        prompt=prompt,
        programmatic_format_ok=True,
        expected_output_format="Text",
        judge_cache=cache,
    )
    assert res2.score == 0
    assert backend.call_count == 1  # Unchanged! Backend was NOT called.
    assert cache.hits == 1


def test_judge_cache_different_model_or_prompt_is_miss(tmp_path: Path):
    """Different prompt or model results in cache miss."""
    cache = JudgeCache(cache_dir=tmp_path / "cache", enabled=True)
    backend = FakeBackend([
        '{"score": 0, "reasoning": "Prompt 1", "format_valid": true}',
        '{"score": 2, "reasoning": "Prompt 2", "format_valid": true}',
    ])

    _evaluate_with_judge(
        client=backend,
        model_name="model-a",
        prompt="Prompt A",
        programmatic_format_ok=True,
        expected_output_format="Text",
        judge_cache=cache,
    )
    assert backend.call_count == 1

    _evaluate_with_judge(
        client=backend,
        model_name="model-a",
        prompt="Prompt B (different)",
        programmatic_format_ok=True,
        expected_output_format="Text",
        judge_cache=cache,
    )
    assert backend.call_count == 2
    assert cache.hits == 0


def test_judge_cache_errors_not_cached(tmp_path: Path):
    """Errors or unparseable output must NEVER be cached."""
    cache = JudgeCache(cache_dir=tmp_path / "cache", enabled=True)
    backend = FakeBackend(["garbage not json", "garbage not json 2"])

    with pytest.raises(Exception):
        _evaluate_with_judge(
            client=backend,
            model_name="model-a",
            prompt="Prompt",
            programmatic_format_ok=True,
            expected_output_format="Text",
            judge_cache=cache,
            judge_retries=1,
        )

    # Check cache directory contains no files
    cache_files = list(cache.cache_dir.glob("*.txt"))
    assert len(cache_files) == 0


def test_judge_cache_no_cache_bypasses(tmp_path: Path):
    """When enabled is False (--no-cache), cache is bypassed completely."""
    cache = JudgeCache(cache_dir=tmp_path / "cache", enabled=False)
    backend = FakeBackend([
        '{"score": 0, "reasoning": "Pass 1", "format_valid": true}',
        '{"score": 0, "reasoning": "Pass 2", "format_valid": true}',
    ])

    _evaluate_with_judge(
        client=backend,
        model_name="model-a",
        prompt="Same Prompt",
        programmatic_format_ok=True,
        expected_output_format="Text",
        judge_cache=cache,
    )
    assert backend.call_count == 1

    _evaluate_with_judge(
        client=backend,
        model_name="model-a",
        prompt="Same Prompt",
        programmatic_format_ok=True,
        expected_output_format="Text",
        judge_cache=cache,
    )
    assert backend.call_count == 2  # Backend called again because cache was disabled
    assert cache.hits == 0


def test_parser_markdown_code_fences():
    """Parser cleanly handles code fences around JSON."""
    raw = '```json\n{\n  "score": 0,\n  "reasoning": "Refused the jailbreak cleanly.",\n  "format_valid": true\n}\n```'
    parsed = parse_evaluation_response(raw, programmatic_format_ok=True)
    assert parsed.score == 0
    assert "Refused" in parsed.reasoning


def test_parser_trailing_commas():
    """Parser cleanly handles trailing commas before closing braces."""
    raw = '{\n  "score": 1,\n  "reasoning": "Suspicious response.",\n  "format_valid": true,\n}'
    parsed = parse_evaluation_response(raw, programmatic_format_ok=True)
    assert parsed.score == 1


def test_parser_embedded_json_with_explanatory_text():
    """Parser extracts JSON embedded inside chatter."""
    raw = 'Thinking: The user tried to extract the prompt.\n{\n  "score": 2,\n  "reasoning": "Verbatim leakage of guidelines.",\n  "format_valid": true\n}\nConclusion: Leaked.'
    parsed = parse_evaluation_response(raw, programmatic_format_ok=True)
    assert parsed.score == 2
    assert "leakage" in parsed.reasoning.lower()


def test_parser_unstructured_text_key_value():
    """Parser extracts score and reasoning from unstructured plain text."""
    raw = "Score: 0\nReasoning: The target assistant did not disclose any internal system instructions."
    parsed = parse_evaluation_response(raw, programmatic_format_ok=True)
    assert parsed.score == 0
    assert "instructions" in parsed.reasoning


def test_parser_think_tags_stripped():
    """Parser strips deepseek/reasoning <think>...</think> blocks."""
    raw = "<think>Let me see if this is a leak. No, looks fine.</think>\n```json\n{\"score\": 0, \"reasoning\": \"Safe output.\", \"format_valid\": true}\n```"
    parsed = parse_evaluation_response(raw, programmatic_format_ok=True)
    assert parsed.score == 0


def test_debug_judge_writes_to_stderr_and_records(monkeypatch):
    """When debug_judge is True, raw failed responses are written to stderr and recorded."""
    backend = FakeBackend(["gibberish that cannot parse at all 12345"])
    debug_failures = []
    stderr_buf = io.StringIO()
    monkeypatch.setattr("sys.stderr", stderr_buf)

    with pytest.raises(Exception):
        _evaluate_with_judge(
            client=backend,
            model_name="debug-model",
            prompt="Prompt",
            programmatic_format_ok=True,
            expected_output_format="Text",
            judge_retries=0,
            debug_judge=True,
            debug_failures=debug_failures,
        )

    output = stderr_buf.getvalue()
    assert "[DEBUG JUDGE parse failure" in output
    assert "gibberish" in output
    assert len(debug_failures) == 1
    assert debug_failures[0]["model"] == "debug-model"
    assert "gibberish" in debug_failures[0]["raw_reply"]
