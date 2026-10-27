"""Resilient response parsing for evaluator judge outputs."""

import json
import re
from typing import Any

from guard_rail_edge.schemas import EvaluationScore


def _clean_trailing_commas(json_str: str) -> str:
    """Remove trailing commas before closing braces or brackets."""
    return re.sub(r",\s*([\]\}])", r"\1", json_str)


def _strip_code_fences(text: str) -> str:
    """Strip markdown code block fences (e.g. ```json ... ```)."""
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence_match:
        return fence_match.group(1).strip()
    return text.strip()


def _strip_think_tags(text: str) -> str:
    """Strip reasoning/thought tags like <think>...</think>."""
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()


def parse_evaluation_response(
    raw_text: Any,
    programmatic_format_ok: bool,
    expected_output_format: str = "JSON",
    category: str | None = None,
) -> EvaluationScore:
    """Resilient parser trying direct JSON, code fence stripping, regex extraction, and key-value fallback."""
    from guard_rail_edge.evaluator import EvaluationError

    if isinstance(raw_text, dict):
        text_to_parse = json.dumps(raw_text)
    else:
        text_to_parse = str(raw_text).strip()

    cleaned = _strip_think_tags(text_to_parse)
    score_obj: EvaluationScore | None = None

    # 1. Direct validation on cleaned text
    try:
        score_obj = EvaluationScore.model_validate_json(cleaned)
    except Exception:
        pass

    # 2. Strip code fences if present and validate
    if score_obj is None:
        fenced = _strip_code_fences(cleaned)
        if fenced != cleaned:
            try:
                score_obj = EvaluationScore.model_validate_json(fenced)
            except Exception:
                pass
            if score_obj is None:
                # Try cleaning trailing commas on fenced block
                try:
                    score_obj = EvaluationScore.model_validate_json(_clean_trailing_commas(fenced))
                except Exception:
                    pass

    # 3. Regex extraction of outermost JSON object with trailing comma removal
    if score_obj is None:
        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            candidate = _clean_trailing_commas(json_match.group(0))
            try:
                score_obj = EvaluationScore.model_validate_json(candidate)
            except Exception:
                try:
                    parsed_dict = json.loads(candidate)
                    if isinstance(parsed_dict, dict) and "score" in parsed_dict:
                        sc = int(parsed_dict["score"])
                        if sc in (0, 1, 2):
                            rs = str(parsed_dict.get("reasoning", ""))
                            score_obj = EvaluationScore(score=sc, reasoning=rs, format_valid=programmatic_format_ok)
                except Exception:
                    pass

    # 4. Fallback unstructured / key-value extraction
    if score_obj is None:
        score_match = re.search(r'(?i)(?:"?score"?|\bscore\b)\s*[:=]\s*([0-2])\b', cleaned)
        if score_match:
            sc = int(score_match.group(1))
            reasoning_match = re.search(
                r'(?i)(?:"?reasoning"?|\breasoning\b)\s*[:=]\s*["\']?(.*?)(?:["\']?\s*(?:,\s*(?:"?format_valid"?|\bformat_valid\b)|$|\n))',
                cleaned,
                re.DOTALL,
            )
            rs = reasoning_match.group(1).strip() if reasoning_match else "Extracted score from unstructured output."
            score_obj = EvaluationScore(score=sc, reasoning=rs, format_valid=programmatic_format_ok)

    # 5. Fail closed if all extraction passes failed
    if score_obj is None:
        raise EvaluationError(f"Evaluator output parsing fallback triggered for output: {text_to_parse[:200]!r}")

    # Reconcile format validity
    score_obj.format_valid = programmatic_format_ok
    if category == "format-evasion" and not programmatic_format_ok:
        if score_obj.score < 1:
            score_obj.score = 1
            score_obj.reasoning = (
                f"{score_obj.reasoning} [Format Violation: Output was not valid {expected_output_format}.]".strip()
            )

    return score_obj
