"""Typer CLI application configuration and command registration."""

import typer
import typer.core

from guard_rail_edge.cli.attacks import register_attacks_commands
from guard_rail_edge.cli.calibrate import register_calibrate_command
from guard_rail_edge.cli.doctor import register_doctor_command
from guard_rail_edge.cli.helpers import version_callback
from guard_rail_edge.cli.init import register_init_command
from guard_rail_edge.cli.models import register_models_command
from guard_rail_edge.cli.run import register_run_command


class DefaultGroup(typer.core.TyperGroup):
    """Custom Typer/Click Group that routes unknown commands or flag-only calls to 'run'."""

    def resolve_command(self, ctx, args):
        if args and args[0] not in self.commands and args[0] not in ("--help", "-h", "--version"):
            return "run", self.commands["run"], args
        return super().resolve_command(ctx, args)


def create_app() -> typer.Typer:
    """Construct and configure the Typer CLI app with all registered commands."""
    app = typer.Typer(
        cls=DefaultGroup,
        name="guard-rail-edge",
        help="CLI tool for automated prompt injection and jailbreak tests against LLM system prompts.",
        add_completion=False,
    )

    @app.callback()
    def main_callback(
        version: bool | None = typer.Option(
            None,
            "--version",
            "-v",
            help="Show guard-rail-edge version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ) -> None:
        """Automated prompt injection & jailbreak testing against LLM system prompts."""

    register_run_command(app)
    register_init_command(app)
    register_attacks_commands(app)
    register_calibrate_command(app)
    register_models_command(app)
    register_doctor_command(app)

    return app


app = create_app()

__all__ = ["DefaultGroup", "app", "create_app", "version_callback"]
