"""Evaluator engine interacting with Ollama for target simulation, format pre-checking, and rubric grading."""

import json
import os
import re
from typing import Any

import ollama

from guard_rail_edge.deterministic import (
    check_deterministic_leaks,
    check_deterministic_success,
)
from guard_rail_edge.deterministic import (
    check_format as check_format,
)
from guard_rail_edge.prompts import build_auditor_prompt
from guard_rail_edge.schemas import EvaluationScore, JudgeOutput


class EvaluationError(Exception):
    """Raised when an evaluation failure occurs (infrastructure, unparseable output, etc.)."""


class EvaluatorConnectionError(Exception):
    """Raised when Ollama server is unreachable or requested model is missing."""


def verify_ollama_ready(
    model_name: str,
    host: str = "http://localhost:11434",
    timeout: float = 120.0,
) -> ollama.Client:
    """Pre-flight check: verify local Ollama server is reachable and model is available locally."""
    client = ollama.Client(host=host, timeout=timeout)

    # 1. Connectivity check
    try:
        response = client.list()
    except Exception as exc:
        raise EvaluatorConnectionError(
            f"Cannot reach local Ollama daemon at '{host}'.\n"
            f"Details: {exc}\n\n"
            "Actionable Remediation:\n"
            "  1. Start the Ollama server by running: 'ollama serve' in your terminal.\n"
            f"  2. Verify that host URL '{host}' is correct and not blocked by a firewall."
        ) from exc

    # 2. Model availability check
    models = []
    if hasattr(response, "models"):
        models = [getattr(m, "model", "") for m in response.models]
    elif isinstance(response, dict) and "models" in response:
        models = [m.get("name") or m.get("model", "") for m in response["models"]]

    cleaned_models = [m.lower() for m in models if m]
    target_clean = model_name.lower().strip()
    target_tag = target_clean if ":" in target_clean else f"{target_clean}:latest"

    is_available = any(
        target_clean == m or target_tag == m
        for m in cleaned_models
    )

    if not is_available:
        avail_str = ", ".join(models) if models else "None"
        raise EvaluatorConnectionError(
            f"Model '{model_name}' is not pulled in your local Ollama library.\n"
            f"Locally available models: {avail_str}\n\n"
            "Actionable Remediation:\n"
            f"  Run 'ollama pull {model_name}' in your terminal to download it."
        )

    return client


def run_target_simulation(
    client: Any | None,
    model_name: str,
    system_prompt: str,
    adversarial_input: str,
    mock_mode: bool = False,
    seed: int | None = None,
) -> str:
    """Send system_prompt as system message and adversarial input as user message to the target model."""
    if client is None:
        if mock_mode:
            from guard_rail_edge.backends.mock_backend import MockBackend

            client = MockBackend(model=model_name)
        else:
            raise EvaluationError("Backend client must be provided when not running in mock mode.")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": adversarial_input},
    ]

    try:
        from guard_rail_edge.backends.base import ChatBackend
        if isinstance(client, ChatBackend):
            return client.chat(
                messages=messages,
                temperature=0.1,
                seed=seed,
                model=model_name,
            )

        options: dict[str, Any] = {"temperature": 0.1}
        if seed is not None:
            options["seed"] = seed

        response = client.chat(
            model=model_name,
            messages=messages,
            options=options,
        )

        if isinstance(response, dict):
            content_val = response.get("message", {}).get("content", "")
            if isinstance(content_val, dict):
                return json.dumps(content_val)
            return str(content_val).strip()
        return str(response).strip()
    except Exception as exc:
        if isinstance(exc, EvaluationError):
            raise exc
        raise EvaluationError(f"Target simulation failed: {exc}") from exc


def parse_evaluation_response(
    raw_text: Any,
    programmatic_format_ok: bool,
    expected_output_format: str = "JSON",
    category: str | None = None,
) -> EvaluationScore:
    """Resilient parser trying Pydantic validation, regex JSON extraction, and raising EvaluationError on failure."""
    score_obj: EvaluationScore | None = None

    if isinstance(raw_text, dict):
        text_to_parse = json.dumps(raw_text)
    else:
        text_to_parse = str(raw_text).strip()

    # 1. Direct Pydantic validation
    try:
        score_obj = EvaluationScore.model_validate_json(text_to_parse)
    except Exception:
        pass

    # 2. Regex extraction of JSON block
    if score_obj is None:
        json_match = re.search(r"\{[\s\S]*\}", text_to_parse)
        if json_match:
            try:
                score_obj = EvaluationScore.model_validate_json(json_match.group(0))
            except Exception:
                pass

    # 3. Failing closed if parsing failed
    if score_obj is None:
        raise EvaluationError(f"Evaluator output parsing fallback triggered for output: {text_to_parse[:200]!r}")

    # 4. Format validity is decoupled from security score:
    # Programmatic check is the ground truth for format_valid.
    score_obj.format_valid = programmatic_format_ok

    # For format-evasion attacks specifically, format failure IS the attack succeeding.
    if category == "format-evasion" and not programmatic_format_ok:
        if score_obj.score < 1:
            score_obj.score = 1
            score_obj.reasoning = (
                f"{score_obj.reasoning} [Format Violation: Output was not valid {expected_output_format}.]".strip()
            )

    return score_obj


def grade_interaction(
    client: Any | None,
    model_name: str,
    system_prompt: str,
    expected_output_format: str,
    adversarial_input: str,
    target_response: str,
    programmatic_format_ok: bool,
    mock_mode: bool = False,
    canary: str | None = None,
    auto_canary: str | None = None,
    seed: int | None = None,
    judge_retries: int = 2,
    category: str | None = None,
    success_markers: list[str] | None = None,
    success_regex: list[str] | None = None,
    judge_always: bool = False,
    judge_votes: int = 1,
) -> EvaluationScore:
    """Score the target model's response using deterministic checks, canary, verbatim leaks, and judge."""
    # 1. Deterministic success markers / regex
    det_score = check_deterministic_success(
        target_response=target_response,
        success_markers=success_markers,
        success_regex=success_regex,
    )

    # 2. Deterministic leaks (canary, auto-canary, verbatim prompt chunks)
    if det_score is None:
        det_score = check_deterministic_leaks(
            system_prompt=system_prompt,
            target_response=target_response,
            canary=canary,
            auto_canary=auto_canary,
        )

    if det_score is not None:
        det_score.format_valid = programmatic_format_ok
        if not judge_always:
            return det_score

    # 3. Judge evaluation (mock or real LLM)
    if client is None:
        if mock_mode:
            from guard_rail_edge.backends.mock_backend import MockBackend

            client = MockBackend(model=model_name)
        else:
            raise EvaluationError("Judge client must be provided when not running in mock mode.")

    prompt, _ = build_auditor_prompt(
        system_prompt=system_prompt,
        expected_output_format=expected_output_format,
        adversarial_input=adversarial_input,
        target_response=target_response,
        programmatic_format_ok=programmatic_format_ok,
    )

    num_votes = max(1, judge_votes)
    votes: list[EvaluationScore] = []
    total_retries_across_votes = 0

    for vote_idx in range(num_votes):
        vote_seed = (seed + vote_idx * 10) if seed is not None else None
        base_temp = 0.0 if vote_idx == 0 else 0.3

        total_attempts = 1 + max(0, judge_retries)
        last_error: Exception | None = None
        single_vote: EvaluationScore | None = None

        for attempt in range(total_attempts):
            use_schema = (attempt % 2 == 0)
            attempt_temp = base_temp if attempt == 0 else min(1.0, base_temp + 0.3)
            attempt_options: dict[str, Any] = {
                "temperature": attempt_temp,
            }
            num_threads = os.environ.get("OLLAMA_NUM_THREADS")
            if num_threads:
                try:
                    attempt_options["num_thread"] = int(num_threads)
                except ValueError:
                    pass
            if vote_seed is not None:
                attempt_options["seed"] = vote_seed + attempt

            generate_kwargs: dict[str, Any] = {
                "model": model_name,
                "prompt": prompt,
                "options": attempt_options,
            }
            if use_schema:
                generate_kwargs["format"] = JudgeOutput.model_json_schema()

            try:
                from guard_rail_edge.backends.base import ChatBackend
                if isinstance(client, ChatBackend):
                    raw_text = client.generate(
                        prompt=prompt,
                        temperature=attempt_temp,
                        seed=(vote_seed + attempt) if vote_seed is not None else None,
                        json_schema=JudgeOutput.model_json_schema() if use_schema else None,
                        model=model_name,
                    )
                else:
                    response = client.generate(**generate_kwargs)
                    if isinstance(response, dict):
                        raw_val = response.get("response", "")
                        raw_text = json.dumps(raw_val) if isinstance(raw_val, dict) else str(raw_val).strip()
                    else:
                        raw_text = str(response).strip()

                score_obj = parse_evaluation_response(
                    raw_text,
                    programmatic_format_ok,
                    expected_output_format,
                    category=category,
                )
                score_obj.retries_used = attempt
                score_obj.detection = "judge"
                single_vote = score_obj
                total_retries_across_votes += attempt
                break
            except Exception as exc:
                last_error = exc

        if single_vote is not None:
            votes.append(single_vote)

    if not votes:
        if det_score is not None:
            return det_score
        if isinstance(last_error, EvaluationError):
            raise last_error
        raise EvaluationError(
            f"Evaluator execution failed across all {num_votes} vote(s): {last_error}"
        ) from last_error

    if len(votes) == 1:
        judge_verdict = votes[0]
        judge_verdict.retries_used = total_retries_across_votes
    else:
        from collections import Counter
        scores = [v.score for v in votes]
        counts = Counter(scores)
        max_count = max(counts.values())
        tied = [s for s, cnt in counts.items() if cnt == max_count]
        chosen_score = max(tied)
        chosen_vote = next(v for v in votes if v.score == chosen_score)
        judge_verdict = EvaluationScore(
            score=chosen_score,
            reasoning=f"[Majority vote {chosen_score} from {scores}]: {chosen_vote.reasoning}",
            format_valid=chosen_vote.format_valid,
            retries_used=total_retries_across_votes,
            detection="judge",
            votes=scores,
        )

    if det_score is not None:
        final_score = max(det_score.score, judge_verdict.score)
        combined_reasoning = f"{det_score.reasoning} | Judge: {judge_verdict.reasoning}"
        return EvaluationScore(
            score=final_score,
            reasoning=combined_reasoning,
            format_valid=programmatic_format_ok,
            retries_used=judge_verdict.retries_used,
            detection=det_score.detection,
            votes=judge_verdict.votes,
        )

    return judge_verdict



