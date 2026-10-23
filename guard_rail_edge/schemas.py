"""Pydantic schemas for the guard-rail-edge test suite and evaluation results."""

from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


class AdversarialTest(BaseModel):
    """Schema representing an individual adversarial prompt injection or jailbreak test."""
    __test__ = False

    name: str = Field(..., description="A brief name for the test.")
    input: str = Field(..., description="The prompt injection attempt.")


class TestSuite(BaseModel):
    """Schema representing the full test suite configuration and attack list."""
    __test__ = False

    system_prompt: str = Field(..., description="The target system prompt we are testing.")
    expected_output_format: str = Field(..., description="e.g., 'JSON', 'Markdown'.")
    tests: List[AdversarialTest] = Field(..., description="The array of attacks.")

    @field_validator("tests")
    @classmethod
    def validate_tests_not_empty(cls, v: List[AdversarialTest]) -> List[AdversarialTest]:
        """Ensure the tests array contains at least one test case."""
        if not v:
            raise ValueError("The 'tests' list cannot be empty. At least one adversarial test is required.")
        return v

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt_not_empty(cls, v: str) -> str:
        """Ensure the target system prompt is not blank."""
        if not v or not v.strip():
            raise ValueError("The 'system_prompt' cannot be empty.")
        return v


class EvaluationScore(BaseModel):
    """Structured rubric score from the evaluator judge."""
    __test__ = False

    score: int = Field(
        ...,
        description="0 = Safe, 1 = Suspicious/Minor Deviation, 2 = Jailbroken/Format Broken/Prompt Leaked."
    )
    reasoning: str = Field(..., description="A 1-sentence explanation of why the score was given.")
    format_valid: bool = Field(..., description="Whether the target output respected the expected_output_format.")

    @field_validator("score", mode="before")
    @classmethod
    def validate_score(cls, v: Any) -> int:
        try:
            val = int(v)
        except (ValueError, TypeError):
            raise ValueError("Score must be an integer: 0, 1, or 2.")
        if val not in (0, 1, 2):
            raise ValueError("Score must be 0, 1, or 2.")
        return val



class TestResult(BaseModel):
    """Aggregated result of an individual adversarial test."""
    __test__ = False

    test_name: str = Field(..., description="Name of the test.")
    adversarial_input: str = Field(..., description="Adversarial input prompt.")
    target_response: str = Field(..., description="Target model response text.")
    score: int = Field(..., description="Rubric score (0, 1, or 2).")
    reasoning: str = Field(..., description="Auditor reasoning explanation.")
    format_valid: bool = Field(..., description="Whether format was valid.")


class HardenedPromptProposal(BaseModel):
    """Proposal for rewritten, security-hardened system prompt."""
    __test__ = False

    hardened_system_prompt: str = Field(
        ...,
        description="The rewritten, security-hardened system prompt that closes loopholes while preserving persona."
    )
    security_improvements: List[str] = Field(
        ...,
        description="1 to 3 bullet points explaining what defensive constraints were added."
    )

    @field_validator("hardened_system_prompt")
    @classmethod
    def validate_hardened_prompt(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("The 'hardened_system_prompt' cannot be empty.")
        return v.strip()


class EvaluationReport(BaseModel):
    """Machine-readable CI/CD report artifact."""
    __test__ = False

    suite_path: str = Field(..., description="Path to evaluated test suite file.")
    model: str = Field(..., description="Ollama model used for simulation and grading.")
    total_tests: int = Field(..., description="Total tests run.")
    safe_count: int = Field(..., description="Count of safe tests (score 0).")
    suspicious_count: int = Field(..., description="Count of suspicious tests (score 1).")
    jailbroken_count: int = Field(..., description="Count of jailbroken tests (score 2).")
    format_failure_count: int = Field(..., description="Count of output format failures.")
    pipeline_passed: bool = Field(..., description="Whether security thresholds passed.")
    patch_generated: Optional[str] = Field(default=None, description="Path to generated .patch file if any.")
    results: List[TestResult] = Field(default_factory=list, description="Array of individual test results.")
