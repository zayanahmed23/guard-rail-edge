"""Models CLI command listing available model IDs from backend."""

import typer
from rich.table import Table

from guard_rail_edge.backends import get_backend
from guard_rail_edge.evaluator import EvaluatorConnectionError
from guard_rail_edge.render import console


def register_models_command(app: typer.Typer) -> None:
    """Register the models command onto the Typer application."""

    @app.command(name="models")
    def list_models(
        backend: str = typer.Option(
            "groq",
            "--backend",
            "-b",
            help="Backend or provider preset to query ('groq', 'openrouter', 'gemini', 'github', 'openai', 'ollama').",
        ),
        base_url: str | None = typer.Option(None, "--base-url", help="Override base URL."),
        api_key_env: str = typer.Option("OPENAI_API_KEY", "--api-key-env", help="Env var name containing API key."),
        host: str = typer.Option("http://localhost:11434", "--host", help="Ollama host URL."),
        timeout: float = typer.Option(30.0, "--timeout", help="Timeout in seconds."),
    ) -> None:
        """List available model IDs from a target or judge LLM provider (never prints API keys)."""
        b_clean = (backend or "groq").lower().strip()
        client = get_backend(
            backend_type=b_clean,
            model="default",
            base_url=base_url,
            host=host,
            timeout=timeout,
            api_key_env=api_key_env,
        )

        try:
            if hasattr(client, "list_models"):
                model_ids = client.list_models()
            else:
                import ollama

                raw = ollama.Client(host=host, timeout=timeout).list()
                if hasattr(raw, "models"):
                    model_ids = [getattr(m, "model", "") for m in raw.models if getattr(m, "model", "")]
                elif isinstance(raw, dict) and "models" in raw:
                    model_ids = [m.get("name") or m.get("model", "") for m in raw["models"]]
                else:
                    model_ids = []
        except EvaluatorConnectionError as exc:
            console.print(f"[bold red]Authentication / Connection Error:[/bold red] {exc}")
            raise typer.Exit(code=2)
        except Exception as exc:
            console.print(f"[bold red]Failed to retrieve models from backend '{b_clean}':[/bold red] {exc}")
            raise typer.Exit(code=2)

        cleaned_ids = [m for m in model_ids if m]
        if not cleaned_ids:
            console.print(f"[dim]No models returned from backend '{b_clean}'.[/dim]")
            raise typer.Exit(code=0)

        table = Table(
            title=f"Available Models ({b_clean})",
            title_style="bold magenta",
            header_style="bold bright_white on grey23",
            border_style="bright_blue",
        )
        table.add_column("No.", justify="right", style="dim", width=6)
        table.add_column("Model ID", style="bold cyan")

        for idx, m_id in enumerate(sorted(cleaned_ids), start=1):
            table.add_row(str(idx), m_id)

        console.print(table)
