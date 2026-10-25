"""Inspect and list built-in adversarial attack library."""

import sys

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from guard_rail_edge.attacks import list_available_packs, load_attacks
from guard_rail_edge.render import console


def register_attacks_commands(app: typer.Typer) -> typer.Typer:
    """Register the attacks sub-command group onto the Typer application."""
    attacks_app = typer.Typer(
        name="attacks",
        help="Manage and inspect built-in adversarial attack library.",
        no_args_is_help=True,
    )
    app.add_typer(attacks_app, name="attacks")

    @attacks_app.command(name="list")
    def attacks_list(
        pack: str | None = typer.Option(None, "--pack", "-p", help="Filter attacks by pack name."),
        category: str | None = typer.Option(None, "--category", "-c", help="Filter attacks by category (alias for --pack)."),
    ) -> None:
        """List built-in attacks in a formatted table."""
        target_pack = pack or category
        available = list_available_packs()
        if target_pack:
            if target_pack not in available:
                console.print(
                    f"[bold red]Error:[/bold red] Unknown attack pack '{target_pack}'. "
                    f"Available packs: {', '.join(available)}"
                )
                sys.exit(2)
            packs_to_load = [target_pack]
        else:
            packs_to_load = available

        attacks = load_attacks(packs=packs_to_load, min_severity="low")

        table = Table(
            title="Built-In Adversarial Attack Library",
            title_style="bold magenta",
            header_style="bold bright_white on grey23",
            border_style="bright_blue",
        )
        table.add_column("ID", style="bold yellow", width=12, justify="center")
        table.add_column("Pack", style="bold cyan", width=22)
        table.add_column("Severity", justify="center", width=12)
        table.add_column("Name", style="white", min_width=30)

        for atk in attacks:
            if atk.severity == "high":
                sev_badge = Text("HIGH", style="bold red")
            elif atk.severity == "medium":
                sev_badge = Text("MEDIUM", style="bold yellow")
            else:
                sev_badge = Text("LOW", style="bold green")

            table.add_row(atk.id, atk.category, sev_badge, atk.name)

        console.print(table)
        console.print(f"\n[dim]Total Attacks: [bold]{len(attacks)}[/bold] across {len(packs_to_load)} pack(s)[/dim]")

    @attacks_app.command(name="show")
    def attacks_show(
        attack_id: str = typer.Argument(..., help="The attack ID to inspect (e.g. PE-001)."),
    ) -> None:
        """Display the full details of a specific attack by ID."""
        all_attacks = load_attacks(packs=["all"], min_severity="low")
        target = None
        for atk in all_attacks:
            if atk.id.upper() == attack_id.upper():
                target = atk
                break

        if target is None:
            console.print(f"[bold red]Error:[/bold red] Unknown attack ID '{attack_id}'.")
            sys.exit(2)

        sev_color = "red" if target.severity == "high" else ("yellow" if target.severity == "medium" else "green")
        details = (
            f"[bold cyan]ID:[/bold cyan] {target.id}\n"
            f"[bold cyan]Name:[/bold cyan] {target.name}\n"
            f"[bold cyan]Category / Pack:[/bold cyan] {target.category}\n"
            f"[bold cyan]Severity:[/bold cyan] [{sev_color} bold]{target.severity.upper()}[/{sev_color} bold]\n"
            f"[bold cyan]Input:[/bold cyan]\n[white]{target.input}[/white]\n"
        )
        if target.references:
            details += "\n[bold cyan]References / Techniques:[/bold cyan]\n" + "\n".join(f"  • {r}" for r in target.references)
        if target.decoded_hint:
            details += f"\n[bold cyan]Decoded Hint:[/bold cyan] {target.decoded_hint}"

        console.print(
            Panel(
                details,
                title=f"[bold magenta]Attack Specification: {target.id}[/bold magenta]",
                border_style="magenta",
                padding=(1, 2),
            )
        )

    return attacks_app
