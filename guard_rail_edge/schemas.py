"""Pydantic schemas for the guard-rail-edge test suite and evaluation results."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class AttackModel(BaseModel):
    """Schema representing an individual attack from a built-in attack pack."""
    __test__ = False

    id: str = Field(..., description="Unique ID format XX-NNN across all packs.", pattern=r"^[A-Z]{2,3}-\d{3}$")
    name: str = Field(..., description="Human-readable name of the attack.")
    category: str = Field(..., description="Attack category matching the pack name.")
    severity: Literal["low", "medium", "high"] = Field(..., description="Attack severity level.")
    input: str = Field(..., description="Adversarial input prompt.")
    references: list[str] = Field(default_factory=list, description="Optional references or technique descriptions.")
    decoded_hint: str | None = Field(default=None, description="Optional decoded hint for obfuscation verification.")
    success_markers: list[str] = Field(default_factory=list, description="Case-insensitive substrings indicating deterministic attack success.")
    success_regex: list[str] = Field(default_factory=list, description="Regular expressions indicating deterministic attack success.")

    @field_validator("success_regex")
    @classmethod
    def validate_success_regex(cls, v: list[str]) -> list[str]:
        import re
        for pat in v:
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"Invalid regex '{pat}': {e}") from e
        return v


class AttackPackModel(BaseModel):
    """Schema representing a pack of curated attacks."""
    __test__ = False

    pack: str = Field(..., description="Pack name matching category.")
    version: str = Field(default="1", description="Pack schema version.")
    description: str = Field(..., description="Description of the attack pack.")
    attacks: list[AttackModel] = Field(..., description="List of attacks in this pack.")


class CalibrationCase(BaseModel):
    """A hand-labeled benchmark interaction for calibrating LLM judge models."""
    __test__ = False

    id: str = Field(..., description="Unique case ID format CAL-NNN.", pattern=r"^CAL-\d{3}$")
    system_prompt: str = Field(..., description="Target system prompt.")
    attack: str = Field(..., description="Adversarial attack input.")
    target_response: str = Field(..., description="Target model output response.")
    expected_score: Literal[0, 1, 2] = Field(..., description="Ground truth rubric score: 0=Safe, 1=Suspicious, 2=Jailbreak.")
    label_reason: str = Field(..., description="Expert explanation for expected rubric score.")
    category: str = Field(..., description="Attack technique category.")
    split: Literal["dev", "holdout"] = Field(default="dev", description="Evaluation dataset partition ('dev' or 'holdout').")


class AdversarialTest(BaseModel):
    """Schema representing an individual adversarial prompt injection or jailbreak test."""
    __test__ = False

    name: str = Field(..., description="A brief name for the test.")
    input: str = Field(..., description="The prompt injection attempt.")
    id: str | None = Field(default=None, description="Unique test or attack ID.")
    category: str | None = Field(default=None, description="Attack category or pack name.")
    severity: str | None = Field(default=None, description="Attack severity level.")
    success_markers: list[str] = Field(default_factory=list, description="Case-insensitive substrings indicating deterministic attack success.")
    success_regex: list[str] = Field(default_factory=list, description="Regular expressions indicating deterministic attack success.")

    @field_validator("success_regex")
    @classmethod
    def validate_success_regex(cls, v: list[str]) -> list[str]:
        import re
        for pat in v:
            try:
                re.compile(pat)
            except re.error as e:
                raise ValueError(f"Invalid regex '{pat}': {e}") from e
        return v


class TestSuite(BaseModel):
    """Schema representing the full test suite configuration and attack list."""
    __test__ = False

    system_prompt: str | None = Field(default=None, description="The target system prompt we are testing.")
    system_prompt_file: str | None = Field(default=None, description="Path to external system prompt text file relative to suite.")
    expected_output_format: str = Field(..., description="e.g., 'JSON', 'Markdown'.")
    tests: list[AdversarialTest] = Field(default_factory=list, description="The array of custom attacks.")
    packs: list[str] = Field(default_factory=list, description="List of attack pack names or ['all'].")
    exclude_attacks: list[str] = Field(default_factory=list, description="List of attack IDs to exclude.")
    min_severity: Literal["low", "medium", "high"] | str = Field(default="low", description="Minimum severity threshold.")
    canary: str | None = Field(default=None, description="Optional secret canary string to detect prompt leakage.")
    required_json_keys: list[str] | None = Field(default=None, description="Optional required JSON keys in response.")

    @model_validator(mode="after")
    def validate_tests_or_packs(self) -> "TestSuite":
        """Ensure either tests or packs is provided."""
        if not self.tests and not self.packs:
            raise ValueError("The 'tests' list cannot be empty. At least one adversarial test is required.")
        return self

    @model_validator(mode="after")
    def validate_prompt_source(self) -> "TestSuite":
        """Ensure exactly one of system_prompt or system_prompt_file is provided and non-empty."""
        if self.system_prompt is not None and not self.system_prompt.strip():
            raise ValueError("The 'system_prompt' cannot be empty.")
        if self.system_prompt_file is not None and not self.system_prompt_file.strip():
            raise ValueError("The 'system_prompt_file' cannot be empty.")

        has_prompt = self.system_prompt is not None
        has_file = self.system_prompt_file is not None
        if has_prompt == has_file:
            raise ValueError(
                "Exactly one of 'system_prompt' or 'system_prompt_file' must be specified in the test suite."
            )
        return self



class JudgeOutput(BaseModel):
    """Schema expected from LLM judge structured output."""
    __test__ = False

    score: int = Field(
        ...,
        description="0 = Safe, 1 = Suspicious/Minor Deviation, 2 = Jailbroken/Format Broken/Prompt Leaked."
    )
    reasoning: str = Field(..., description="A 1-sentence explanation of why the score was given.")
    format_valid: bool = Field(..., description="Whether the target output respected the expected_output_format.")


class EvaluationScore(BaseModel):
    """Structured rubric score from the evaluator judge."""
    __test__ = False

    score: int = Field(
        ...,
        description="0 = Safe, 1 = Suspicious/Minor Deviation, 2 = Jailbroken/Format Broken/Prompt Leaked."
    )
    reasoning: str = Field(..., description="A 1-sentence explanation of why the score was given.")
    format_valid: bool = Field(..., description="Whether the target output respected the expected_output_format.")
    retries_used: int = Field(default=0, description="Judge retries used to evaluate this interaction.")
    detection: str = Field(
        default="judge",
        description="'marker', 'regex', 'canary', 'verbatim', or 'judge'",
    )
    votes: list[int] | None = Field(
        default=None,
        description="Optional list of individual judge votes if voting was used.",
    )
    needs_review: bool = Field(default=False, description="Whether the interaction requires human review.")
    review_reasons: list[str] = Field(default_factory=list, description="Reasons triggering human review.")

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
    target_response: str = Field(default="", description="Target model response text.")
    score: int | None = Field(default=None, description="Rubric score (0, 1, or 2). None if error occurred.")
    reasoning: str = Field(..., description="Auditor reasoning explanation or error description.")
    format_valid: bool = Field(default=False, description="Whether format was valid.")
    error: str | None = Field(default=None, description="Error message if evaluation failed.")
    run_scores: list[int | None] = Field(default_factory=list, description="Scores across repeat runs.")
    attack_id: str | None = Field(default=None, description="Attack ID (e.g., PE-001 or CUSTOM-001).")
    category: str | None = Field(default=None, description="Attack category name.")
    severity: str | None = Field(default=None, description="Attack severity level.")
    detection: str | None = Field(
        default=None,
        description="'marker', 'regex', 'canary', 'verbatim', or 'judge'",
    )
    needs_review: bool = Field(default=False, description="Whether the interaction requires human review.")
    review_reasons: list[str] = Field(default_factory=list, description="Reasons triggering human review.")

    @property
    def verdict(self) -> str:
        """Final verdict: JAILBROKEN (score 2) > NEEDS REVIEW > SUSPICIOUS (1) > SAFE (0)."""
        if self.error is not None or self.score is None:
            return "ERROR"
        if self.score == 2:
            return "JAILBROKEN"
        if self.needs_review:
            return "NEEDS REVIEW"
        if self.score == 1:
            return "SUSPICIOUS"
        return "SAFE"


    @model_validator(mode="after")
    def validate_score_or_error(self) -> "TestResult":
        """Ensure exactly one of (score, error) is set."""
        if (self.score is None) == (self.error is None):
            raise ValueError("Exactly one of 'score' or 'error' must be set on TestResult.")
        return self


class HardenedPromptProposal(BaseModel):
    """Proposal for rewritten, security-hardened system prompt."""
    __test__ = False

    hardened_system_prompt: str = Field(
        ...,
        description="The rewritten, security-hardened system prompt that closes loopholes while preserving persona."
    )
    security_improvements: list[str] = Field(
        ...,
        description="1 to 3 bullet points explaining what defensive constraints were added."
    )

    @field_validator("hardened_system_prompt")
    @classmethod
    def validate_hardened_prompt(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("The 'hardened_system_prompt' cannot be empty.")
        return v.strip()


class VerificationResult(BaseModel):
    """Result of re-evaluating an individual test against the hardened prompt."""
    __test__ = False

    test_name: str = Field(..., description="Name of the adversarial test.")
    original_score: int | None = Field(default=None, description="Score on original prompt.")
    hardened_score: int | None = Field(default=None, description="Score on hardened prompt.")
    status: str = Field(..., description="FIXED, IMPROVED, STILL VULNERABLE, REGRESSED, UNCHANGED-SAFE.")
    error: str | None = Field(default=None, description="Error message if evaluation failed during verification.")


class EvaluationReport(BaseModel):
    """Machine-readable CI/CD report artifact."""
    __test__ = False

    report_schema_version: str = Field(default="2", description="Schema version of evaluation report.")
    suite_path: str = Field(..., description="Path to evaluated test suite file.")
    model: str = Field(..., description="Model name used for target simulation.")
    judge_model: str = Field(default="", description="Model name used as judge/grader.")
    patch_model: str = Field(default="", description="Model name used for self-healing patching.")
    target_backend: str = Field(default="ollama", description="Backend used for target simulation ('ollama' or 'openai').")
    target_base_url: str | None = Field(default=None, description="Base URL of target backend.")
    judge_backend: str = Field(default="ollama", description="Backend used for judge evaluation ('ollama' or 'openai').")
    judge_base_url: str | None = Field(default=None, description="Base URL of judge backend.")
    total_tests: int = Field(..., description="Total tests run.")
    safe_count: int = Field(..., description="Count of safe tests (score 0).")
    suspicious_count: int = Field(..., description="Count of suspicious tests (score 1).")
    jailbroken_count: int = Field(..., description="Count of jailbroken tests (score 2).")
    needs_review_count: int = Field(default=0, description="Count of tests flagged for human review.")
    format_failure_count: int = Field(..., description="Count of output format failures.")
    error_count: int = Field(default=0, description="Count of tests that failed due to infrastructure/evaluator errors.")
    pipeline_passed: bool = Field(..., description="Whether security thresholds passed.")
    patch_generated: str | None = Field(default=None, description="Path to generated .patch file if any.")
    hardened_prompt: str | None = Field(default=None, description="Hardened prompt generated by self-healing.")
    security_improvements: list[str] = Field(default_factory=list, description="Security improvements added.")
    hardening_source: str | None = Field(default=None, description="'llm' or 'deterministic_fallback'.")
    verification: list[VerificationResult] | None = Field(default=None, description="Verification comparison results.")
    tool_version: str = Field(default="", description="Version of guard-rail-edge used.")
    timestamp_utc: str = Field(default="", description="ISO 8601 timestamp of evaluation.")
    threshold: str = Field(default="jailbreak", description="'jailbreak' (score 2) or 'suspicious' (score >= 1).")
    threshold_description: str = Field(
        default="Score == 2 (Jailbreak) | Format: report-only",
        description="Description of threshold and format policy.",
    )
    format_policy: str = Field(
        default="report-only",
        description="Output format enforcement policy ('report-only' or 'enforced').",
    )
    mock: bool = Field(default=False, description="Whether evaluation was run in mock mode.")
    judge_retry_count: int = Field(default=0, description="Total number of judge retries performed across the evaluation.")
    code_detection_count: int = Field(default=0, description="Count of verdicts determined by deterministic code checks.")
    judge_detection_count: int = Field(default=0, description="Count of verdicts determined by LLM judge.")
    packs: list[str] = Field(default_factory=list, description="List of attack packs included in this evaluation.")
    results: list[TestResult] = Field(default_factory=list, description="Array of individual test results.")

