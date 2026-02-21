"""CLI interface — the main entry point for Plutus."""

from __future__ import annotations

import json
import os
import webbrowser

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from plutus import __version__
from plutus.config import PlutusConfig, config_path, plutus_dir

console = Console()

BANNER = r"""
    ____  __      __
   / __ \/ /_  __/ /___  _______
  / /_/ / / / / / __/ / / / ___/
 / ____/ / /_/ / /_/ /_/ (__  )
/_/   /_/\__,_/\__/\__,_/____/
"""


@click.group(invoke_without_command=True)
@click.version_option(__version__)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Plutus — Autonomous AI agent with configurable guardrails."""
    if ctx.invoked_subcommand is None:
        console.print(BANNER, style="bold cyan")
        console.print(f"  v{__version__} — Local-first AI agent with guardrails\n", style="dim")
        console.print("  Run [bold]plutus start[/bold] to launch, or [bold]plutus --help[/bold] for commands.\n")


@main.command()
@click.option("--host", default=None, help="Host to bind to (default: 127.0.0.1)")
@click.option("--port", default=None, type=int, help="Port to bind to (default: 7777)")
@click.option("--dev", is_flag=True, help="Run in development mode (auto-reload)")
@click.option("--no-browser", is_flag=True, help="Don't open the browser automatically")
def start(host: str | None, port: int | None, dev: bool, no_browser: bool) -> None:
    """Launch the Plutus agent and web interface."""
    import uvicorn

    config = PlutusConfig.load()
    bind_host = host or config.gateway.host
    bind_port = port or config.gateway.port

    console.print(BANNER, style="bold cyan")
    console.print(f"  Starting Plutus v{__version__}...\n", style="bold")

    # Show current configuration
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Tier", f"[bold]{config.guardrails.tier}[/bold]")
    table.add_row("Model", f"{config.model.provider}/{config.model.model}")
    table.add_row("Interface", f"http://{bind_host}:{bind_port}")
    console.print(Panel(table, title="Configuration", border_style="cyan"))
    console.print()

    if not no_browser and not dev:
        import threading

        def _open():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://{bind_host}:{bind_port}")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "plutus.gateway.server:create_app",
        host=bind_host,
        port=bind_port,
        reload=dev,
        factory=True,
        log_level="info",
    )


@main.command()
def setup() -> None:
    """Interactive setup wizard for Plutus."""
    console.print(BANNER, style="bold cyan")
    console.print("  Welcome to Plutus setup!\n", style="bold")

    config = PlutusConfig.load()

    # Provider
    console.print("[bold]1. LLM Provider[/bold]")
    provider = click.prompt(
        "  Choose provider",
        type=click.Choice(["anthropic", "openai", "ollama", "custom"]),
        default=config.model.provider,
    )
    config.model.provider = provider

    # Model
    default_models = {
        "anthropic": "claude-sonnet-4-6-20250514",
        "openai": "gpt-5.2",
        "ollama": "llama3.2",
        "custom": "gpt-5.2",
    }
    model = click.prompt(
        "  Model name", default=default_models.get(provider, config.model.model)
    )
    config.model.model = model

    # API key
    if provider not in ("ollama",):
        from plutus.config import SecretsStore, PROVIDER_ENV_VARS

        secrets = SecretsStore()
        default_env = PROVIDER_ENV_VARS.get(provider, f"{provider.upper()}_API_KEY")
        config.model.api_key_env = default_env

        has_key = secrets.has_key(provider)
        if has_key:
            console.print(f"  [green]API key already configured for {provider}[/green]")
            change_key = click.confirm("  Change it?", default=False)
        else:
            console.print(f"\n  [yellow]No API key found for {provider}[/yellow]")
            change_key = True

        if change_key:
            api_key = click.prompt(
                f"  Enter your {provider} API key",
                hide_input=True,
                default="",
                show_default=False,
            )
            if api_key.strip():
                secrets.set_key(provider, api_key.strip())
                console.print(f"  [green]API key saved securely[/green]")
            else:
                console.print(
                    f"  [dim]Skipped. You can set it later via the web UI or "
                    f"by setting the {default_env} environment variable.[/dim]"
                )

    if provider == "custom":
        base_url = click.prompt("  Base URL", default=config.model.base_url or "")
        config.model.base_url = base_url or None

    # Tier
    console.print("\n[bold]2. Guardrail Tier[/bold]")
    console.print("  observer   — Read-only, AI can only observe")
    console.print("  assistant  — Every action requires your approval")
    console.print("  operator   — Pre-approved actions run autonomously")
    console.print("  autonomous — Full control, no restrictions")
    tier = click.prompt(
        "\n  Choose tier",
        type=click.Choice(["observer", "assistant", "operator", "autonomous"]),
        default=config.guardrails.tier,
    )
    config.guardrails.tier = tier

    # Port
    console.print("\n[bold]3. Gateway[/bold]")
    port = click.prompt("  Port", default=config.gateway.port, type=int)
    config.gateway.port = port

    config.save()
    console.print(f"\n  [green]Configuration saved to {config_path()}[/green]")
    console.print("  Run [bold]plutus start[/bold] to launch!\n")


@main.command()
def status() -> None:
    """Show current Plutus configuration and status."""
    config = PlutusConfig.load()

    table = Table(title="Plutus Status", show_header=True, header_style="bold cyan")
    table.add_column("Setting", style="bold")
    table.add_column("Value")

    table.add_row("Version", __version__)
    table.add_row("Config", str(config_path()))
    table.add_row("Data Dir", str(plutus_dir()))
    table.add_row("Model", f"{config.model.provider}/{config.model.model}")
    table.add_row("Tier", config.guardrails.tier)
    table.add_row("Port", str(config.gateway.port))
    table.add_row("Memory DB", config.resolve_memory_db())
    table.add_row("Skills Dir", str(config.resolve_skills_dir()))

    from plutus.config import SecretsStore

    secrets = SecretsStore()
    key_available = secrets.has_key(config.model.provider)
    table.add_row(
        "API Key",
        f"[green]configured[/green]"
        if key_available
        else f"[red]not set[/red] — run `plutus setup` or use the web UI",
    )

    console.print()
    console.print(table)
    console.print()


@main.command()
@click.argument("tier", type=click.Choice(["observer", "assistant", "operator", "autonomous"]))
def set_tier(tier: str) -> None:
    """Change the guardrail tier."""
    config = PlutusConfig.load()
    config.guardrails.tier = tier
    config.save()
    console.print(f"  Tier set to [bold]{tier}[/bold]")


@main.command()
def audit() -> None:
    """Show recent audit log entries."""
    from plutus.guardrails.audit import AuditLogger

    logger = AuditLogger()
    entries = logger.recent(limit=20)

    if not entries:
        console.print("  No audit entries yet.")
        return

    table = Table(title="Recent Audit Entries", show_header=True, header_style="bold cyan")
    table.add_column("Time", width=20)
    table.add_column("Tool")
    table.add_column("Operation")
    table.add_column("Decision")
    table.add_column("Reason", max_width=40)

    import datetime

    for entry in entries:
        dt = datetime.datetime.fromtimestamp(entry.timestamp)
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        decision_style = {
            "allowed": "green",
            "denied": "red",
            "pending_approval": "yellow",
            "approved": "green",
            "rejected": "red",
        }.get(entry.decision, "white")

        table.add_row(
            time_str,
            entry.tool_name,
            entry.operation or "-",
            f"[{decision_style}]{entry.decision}[/{decision_style}]",
            entry.reason[:40],
        )

    console.print()
    console.print(table)
    console.print(f"\n  Total entries: {logger.count()}")
    console.print()


@main.command()
def config_show() -> None:
    """Display the current configuration as JSON."""
    config = PlutusConfig.load()
    console.print_json(json.dumps(config.model_dump(), indent=2))
