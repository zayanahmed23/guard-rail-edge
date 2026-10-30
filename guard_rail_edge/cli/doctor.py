"""Doctor diagnostic command checking system readiness and configuration."""

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from guard_rail_edge import __version__
from guard_rail_edge.config import ConfigError, resolve_merged_config
from guard_rail_edge.render import console

KNOWN_CALIBRATION_RESULTS: dict[str, dict[str, str]] = {
    "qwen/qwen3.8-27b": {
        "status": "PASS",
        "detail": "Passed calibration as TRUSTWORTHY on 50-case benchmark (100% recall, 5% false alarms).",
    },
    "llama-3.3-70b-versatile": {
        "status": "PASS",
        "detail": "Passed calibration as TRUSTWORTHY on 50-case benchmark (100% recall, 5% false alarms).",
    },
    "llama-3.1-8b-instant": {
        "status": "FAIL",
        "detail": "Did NOT pass calibration (False alarms 20.0% > 15.0%).",
    },
    "qwen2.5:7b": {
        "status": "FAIL",
        "detail": "Did NOT pass calibration (Holdout Recall 75.0% < 80.0%). Recommend Groq qwen/qwen3.8-27b.",
    },
    "mistral:7b": {
        "status": "FAIL",
        "detail": "Did NOT pass calibration (Holdout Recall 62.5% < 80.0%).",
    },
    "llama3:8b": {
        "status": "FAIL",
        "detail": "Did NOT pass calibration (Holdout Recall 62.5% < 80.0%).",
    },
    "deepseek-r1:7b": {
        "status": "FAIL",
        "detail": "Did NOT pass calibration (False alarms 25.0% > 15.0%).",
    },
    "qwen2.5:0.5b": {
        "status": "FAIL",
        "detail": "Did NOT pass calibration (High false alarms 85.0% > 15.0%).",
    },
    "gemma:2b": {
        "status": "FAIL",
        "detail": "Did NOT pass calibration (Recall 10.0% < 80.0%).",
    },
}

SUPPORTED_API_KEYS: list[tuple[str, str]] = [
    ("GROQ_API_KEY", "Groq (Recommended Free Tier)"),
    ("OPENROUTER_API_KEY", "OpenRouter"),
    ("GEMINI_API_KEY", "Google Gemini"),
    ("GITHUB_MODELS_TOKEN", "GitHub Models"),
    ("OPENAI_API_KEY", "OpenAI / Compatible"),
]


def _probe_ollama_host(host: str) -> tuple[bool, list[str]]:
    """Check if Ollama server is responding and return pulled model list."""
    url = f"{host.rstrip('/')}/api/tags"
    req = urllib.request.Request(url, headers={"User-Agent": "guard-rail-edge-doctor"})
    try:
        import json

        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [str(m.get("name")) for m in data.get("models", []) if isinstance(m, dict) and m.get("name")]
            return True, models
    except Exception:
        return False, []


def register_doctor_command(app: typer.Typer) -> None:
    """Register the doctor CLI command onto the Typer application."""

    @app.command()
    def doctor(
        config: Path | None = typer.Option(None, "--config", "-c", help="Path to custom config file to check."),
    ) -> None:
        """Inspect environment, configuration, API credentials, and engine connectivity."""
        console.print(
            Panel(
                "[bold bright_white]guard-rail-edge doctor — System Diagnostics & Readiness Checklist[/bold bright_white]",
                border_style="magenta",
                padding=(0, 2),
            )
        )

        table = Table(
            title="System Diagnostics Checklist",
            title_style="bold magenta",
            header_style="bold bright_white on grey23",
            border_style="bright_blue",
        )
        table.add_column("Category", style="bold cyan", width=22)
        table.add_column("Item", style="bold bright_white", width=28)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Details & Recommendations", width=48)

        blocking_errors: list[str] = []

        # 1. Python Version
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if sys.version_info >= (3, 11):
            table.add_row("Runtime", "Python Version", "[bold green]OK[/bold green]", f"Python {py_ver} (>= 3.11)")
        else:
            table.add_row("Runtime", "Python Version", "[bold red]FAIL[/bold red]", f"Python {py_ver} < 3.11. Upgrade required.")
            blocking_errors.append("Python 3.11+ is required.")

        # 2. Package Version
        table.add_row("Runtime", "Package Version", "[bold green]OK[/bold green]", f"guard-rail-edge v{__version__}")

        # 3. Configuration File
        cfg: dict[str, Any] = {}
        cfg_path: str | None = None
        try:
            cfg, cfg_path = resolve_merged_config(custom_config_path=config)
            if cfg_path:
                table.add_row("Configuration", "Config File", "[bold green]OK[/bold green]", f"Loaded '{cfg_path}' (valid)")
            else:
                table.add_row("Configuration", "Config File", "[bold blue]INFO[/bold blue]", "None found; using CLI defaults")
        except ConfigError as exc:
            table.add_row("Configuration", "Config File", "[bold red]FAIL[/bold red]", f"{exc}")
            blocking_errors.append(str(exc))

        # 4. API Key Environment Variables (NEVER PRINT KEY VALUES)
        for env_var, desc in SUPPORTED_API_KEYS:
            is_set = bool(os.environ.get(env_var, "").strip())
            status_text = "[bold green]SET[/bold green]" if is_set else "[dim]NOT SET[/dim]"
            detail = f"{desc} ({'Ready' if is_set else 'Not configured'})"
            table.add_row("Credentials", env_var, status_text, detail)

        # 5. Configured Backends & Connectivity
        target_backend = str(cfg.get("target_backend", "ollama")).lower()
        judge_backend = str(cfg.get("judge_backend", "ollama")).lower()
        model_name = str(cfg.get("model", "gemma:2b"))
        judge_model_name = str(cfg.get("judge_model") or model_name)
        host = str(cfg.get("host", "http://localhost:11434"))
        is_mock = bool(cfg.get("mock", False))

        if is_mock:
            table.add_row("Engine", "Target & Judge", "[bold yellow]MOCK[/bold yellow]", "Mock mode enabled (no network required)")
        else:
            # Check backend keys if hosted
            for b_name, b_val in [("Target", target_backend), ("Judge", judge_backend)]:
                if b_val == "groq" and not os.environ.get("GROQ_API_KEY", "").strip():
                    table.add_row("Engine", f"{b_name} Backend ({b_val})", "[bold red]FAIL[/bold red]", "GROQ_API_KEY not set in environment.")
                    blocking_errors.append(f"{b_name} uses Groq but GROQ_API_KEY is not set.")
                elif b_val == "openrouter" and not os.environ.get("OPENROUTER_API_KEY", "").strip():
                    table.add_row("Engine", f"{b_name} Backend ({b_val})", "[bold red]FAIL[/bold red]", "OPENROUTER_API_KEY not set.")
                    blocking_errors.append(f"{b_name} uses OpenRouter but OPENROUTER_API_KEY is not set.")
                elif b_val in ("groq", "openrouter", "gemini", "github", "openai"):
                    table.add_row("Engine", f"{b_name} Backend ({b_val})", "[bold green]OK[/bold green]", f"Configured for hosted provider: {b_val}")

            # Check Ollama if either uses ollama
            if target_backend == "ollama" or judge_backend == "ollama":
                is_ready, pulled_models = _probe_ollama_host(host)
                if is_ready:
                    table.add_row("Engine", "Ollama Daemon", "[bold green]OK[/bold green]", f"Reachable at {host} ({len(pulled_models)} models pulled)")
                else:
                    table.add_row("Engine", "Ollama Daemon", "[bold red]FAIL[/bold red]", f"Unreachable at {host}. Start with 'ollama serve'.")
                    blocking_errors.append(f"Ollama server is unreachable at {host}.")

        # 6. Test Suite File
        suite_path = Path(str(cfg.get("suite", "tests.json")))
        if suite_path.is_file():
            try:
                from guard_rail_edge.runner import load_suite

                suite_obj, _ = load_suite(suite_path)
                table.add_row("Test Suite", "Suite File", "[bold green]OK[/bold green]", f"'{suite_path}' ({len(suite_obj.tests)} tests, format: {suite_obj.expected_output_format})")
            except Exception as exc:
                table.add_row("Test Suite", "Suite File", "[bold red]FAIL[/bold red]", f"Error loading '{suite_path}': {exc}")
                blocking_errors.append(f"Test suite '{suite_path}' is invalid.")
        else:
            table.add_row("Test Suite", "Suite File", "[bold yellow]WARN[/bold yellow]", f"'{suite_path}' not found. Run 'guard-rail-edge init'.")

        # 7. Judge vs Target Independence Check
        if not is_mock and judge_model_name == model_name:
            table.add_row("Judge Selection", "Judge Independence", "[bold yellow]WARN[/bold yellow]", f"Judge equals target ('{model_name}'). May cause bias.")
        elif not is_mock:
            table.add_row("Judge Selection", "Judge Independence", "[bold green]OK[/bold green]", f"Target: '{model_name}' != Judge: '{judge_model_name}'")

        # 8. Judge Calibration Benchmark Status
        cal_info = KNOWN_CALIBRATION_RESULTS.get(judge_model_name)
        if cal_info is not None:
            c_status = cal_info["status"]
            status_badge = "[bold green]PASS[/bold green]" if c_status == "PASS" else "[bold red]FAIL[/bold red]"
            table.add_row("Calibration", judge_model_name, status_badge, cal_info["detail"])
            if c_status != "PASS" and not is_mock:
                console.print(f"[dim][INFO] Judge '{judge_model_name}' did not pass calibration. Run `guard-rail-edge calibrate` to evaluate.[/dim]")
        else:
            table.add_row("Calibration", judge_model_name, "[dim]UNKNOWN[/dim]", "Untested judge model. Run `guard-rail-edge calibrate` first.")

        console.print(table)
        console.print()

        if blocking_errors:
            console.print(
                Panel(
                    "[bold red]System has blocking issues. Please resolve the errors above before running evaluations.[/bold red]",
                    border_style="red",
                    padding=(0, 2),
                )
            )
            raise typer.Exit(code=1)

        console.print(
            Panel(
                "[bold green]All pre-flight checks passed! Your environment is ready to run guard-rail-edge.[/bold green]",
                border_style="green",
                padding=(0, 2),
            )
        )
        raise typer.Exit(code=0)

