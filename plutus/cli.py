"""CLI interface — the main entry point for Plutus.

Provides:
  - `plutus start` — launch the web interface + API server
  - `plutus chat` — interactive terminal REPL for direct agent conversation
  - `plutus run <prompt>` — run a single prompt and exit
  - `plutus setup` — interactive setup wizard
  - `plutus status` — show current configuration
  - `plutus tools` — list available tools
  - `plutus set-tier` — change guardrail tier
  - `plutus audit` — show audit log
  - `plutus update` — update to the latest version
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import webbrowser
from pathlib import Path

import click
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.spinner import Spinner
from rich.syntax import Syntax

from plutus import __version__
from plutus.config import PlutusConfig, config_path, plutus_dir

console = Console()

BANNER = r"""
[bold cyan]
    ____  __      __
   / __ \/ /_  __/ /___  _______
  / /_/ / / / / / __/ / / / ___/
 / ____/ / /_/ / /_/ /_/ (__  )
/_/   /_/\__,_/\__/\__,_/____/
[/bold cyan]
[dim]  Autonomous AI Agent with Subprocess Orchestration[/dim]
"""

CHAT_HELP = """
[bold]Commands:[/bold]
  /help     — Show this help
  /tools    — List available tools
  /plan     — Show current plan
  /clear    — Clear conversation
  /tier     — Show/change guardrail tier
  /workers  — Show active subprocesses
  /exit     — Exit the chat
"""


@click.group(invoke_without_command=True)
@click.version_option(__version__)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Plutus — Autonomous AI agent with subprocess orchestration."""
    if ctx.invoked_subcommand is None:
        console.print(BANNER)
        console.print(f"  v{__version__}\n")
        console.print("  [bold]plutus start[/bold]   — Launch web interface")
        console.print("  [bold]plutus chat[/bold]    — Interactive terminal chat")
        console.print("  [bold]plutus run[/bold]     — Run a single prompt")
        console.print("  [bold]plutus setup[/bold]   — Setup wizard")
        console.print("  [bold]plutus --help[/bold]  — All commands\n")


@main.command()
@click.option("--host", default=None, help="Host to bind to (default: 127.0.0.1)")
@click.option("--port", default=None, type=int, help="Port to bind to (default: 7777)")
@click.option("--dev", is_flag=True, help="Run in development mode (auto-reload)")
@click.option("--no-browser", is_flag=True, help="Don't open the browser automatically")
@click.option("--force", is_flag=True, help="Kill any existing instance on the same port")
def start(
    host: str | None,
    port: int | None,
    dev: bool,
    no_browser: bool,
    force: bool,
) -> None:
    """Launch the Plutus agent and web interface."""
    import uvicorn

    config = PlutusConfig.load()
    bind_host = host or config.gateway.host
    bind_port = port or config.gateway.port

    # Check if port is already in use and handle it
    if _port_in_use(bind_host, bind_port):
        if force:
            console.print(
                f"  [yellow]Port {bind_port} in use — killing existing process...[/yellow]"
            )
            _kill_port(bind_port)
            import time
            time.sleep(1)
        else:
            console.print(
                f"\n  [red bold]Port {bind_port} is already in use.[/red bold]\n"
                f"  Plutus may already be running at http://{bind_host}:{bind_port}\n\n"
                f"  Options:\n"
                f"    plutus start --force      Kill the existing instance and restart\n"
                f"    plutus start --port 7778  Start on a different port\n"
                f"    plutus stop               Stop the running instance\n"
            )
            sys.exit(1)

    console.print(BANNER)

    # Show current configuration
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Tier", f"[bold]{config.guardrails.tier}[/bold]")
    table.add_row("Model", f"{config.model.provider}/{config.model.model}")
    table.add_row("Interface", f"http://{bind_host}:{bind_port}")
    console.print(Panel(table, title="Configuration", border_style="cyan"))
    console.print()

    # Write PID file for stop command
    _write_pid_file(bind_port)

    if not no_browser and not dev:
        import threading

        def _open():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://{bind_host}:{bind_port}")

        threading.Thread(target=_open, daemon=True).start()

    try:
        uvicorn.run(
            "plutus.gateway.server:create_app",
            host=bind_host,
            port=bind_port,
            reload=dev,
            factory=True,
            log_level="info",
            ws_ping_interval=20,   # Send WS ping frame every 20s
            ws_ping_timeout=20,    # Close if no pong within 20s
        )
    finally:
        _remove_pid_file(bind_port)


def _port_in_use(host: str, port: int) -> bool:
    """Check if a port is already bound."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def _kill_port(port: int) -> None:
    """Kill any process listening on the given port."""
    import signal
    try:
        import psutil
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.pid:
                try:
                    os.kill(conn.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
    except Exception:
        # Fallback: try lsof
        import subprocess
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in result.stdout.strip().split():
                try:
                    os.kill(int(pid_str), signal.SIGTERM)
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
        except Exception:
            pass


def _pid_file_path(port: int) -> Path:
    return plutus_dir() / f"plutus_{port}.pid"


def _write_pid_file(port: int) -> None:
    """Write the current PID to a file."""
    try:
        _pid_file_path(port).write_text(str(os.getpid()))
    except OSError:
        pass


def _remove_pid_file(port: int) -> None:
    """Remove the PID file."""
    try:
        path = _pid_file_path(port)
        if path.exists():
            path.unlink()
    except OSError:
        pass


@main.command()
@click.option("--port", default=None, type=int, help="Port of the instance to stop")
def stop(port: int | None) -> None:
    """Stop a running Plutus instance."""
    import signal

    config = PlutusConfig.load()
    target_port = port or config.gateway.port

    pid_file = _pid_file_path(target_port)
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            console.print(f"  [green]Sent stop signal to Plutus (PID {pid})[/green]")
            _remove_pid_file(target_port)
            return
        except (ValueError, ProcessLookupError):
            _remove_pid_file(target_port)
        except PermissionError:
            console.print(f"  [red]Permission denied killing PID from {pid_file}[/red]")
            return

    # Fallback: kill by port
    if _port_in_use("127.0.0.1", target_port):
        _kill_port(target_port)
        console.print(f"  [green]Stopped process on port {target_port}[/green]")
    else:
        console.print(f"  [dim]No Plutus instance found on port {target_port}[/dim]")


@main.command(name="restart")
@click.option("--port", default=None, type=int, help="Port to restart on")
def restart_cmd(port: int | None) -> None:
    """Restart Plutus (stop + start)."""
    import subprocess
    import time

    config = PlutusConfig.load()
    target_port = port or config.gateway.port

    # Stop existing instance
    if _port_in_use("127.0.0.1", target_port):
        console.print(f"  [yellow]Stopping existing instance on port {target_port}...[/yellow]")
        _kill_port(target_port)
        time.sleep(1.5)

    # Start new instance
    console.print("  [green]Starting Plutus...[/green]")
    subprocess.Popen(
        [sys.executable, "-m", "plutus.cli", "start", "--port", str(target_port)],
        start_new_session=True,
    )
    console.print(f"  [green]Plutus restarting on port {target_port}[/green]")


@main.command()
@click.option("--model", default=None, help="Override model (e.g., claude-sonnet-4-6)")
@click.option("--tier", default=None, help="Override tier (observer/assistant/operator/autonomous)")
def chat(model: str | None, tier: str | None) -> None:
    """Interactive terminal chat with the Plutus agent."""
    asyncio.run(_chat_loop(model, tier))


async def _chat_loop(model_override: str | None, tier_override: str | None) -> None:
    """Main interactive chat loop."""
    from plutus.config import SecretsStore
    from plutus.core.agent import AgentRuntime
    from plutus.guardrails.engine import GuardrailEngine
    from plutus.core.memory import MemoryStore
    from plutus.tools.registry import create_default_registry

    config = PlutusConfig.load()

    # Apply overrides
    if model_override:
        config.model.model = model_override
    if tier_override:
        config.guardrails.tier = tier_override

    console.print(BANNER)
    console.print(f"  Model: [bold]{config.model.provider}/{config.model.model}[/bold]")
    console.print(f"  Tier:  [bold]{config.guardrails.tier}[/bold]")
    console.print(f"  Type [bold]/help[/bold] for commands, [bold]/exit[/bold] to quit.\n")

    # Initialize components
    secrets = SecretsStore()
    secrets.inject_all()

    memory = MemoryStore(db_path=config.resolve_memory_db())
    guardrails = GuardrailEngine(config.guardrails)
    registry = create_default_registry()

    agent = AgentRuntime(
        config=config,
        guardrails=guardrails,
        memory=memory,
        tool_registry=registry,
        secrets=secrets,
    )
    await agent.initialize()

    if not agent.key_configured:
        console.print(
            "\n  [red bold]No API key configured![/red bold]\n"
            "  Run [bold]plutus setup[/bold] or set the environment variable.\n"
        )
        return

    console.print("  [green]Agent ready.[/green] Start chatting!\n")
    console.print("─" * 60)

    try:
        while True:
            try:
                user_input = console.input("\n[bold cyan]You:[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n\n  [dim]Goodbye![/dim]\n")
                break

            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith("/"):
                handled = await _handle_slash_command(user_input, agent, registry, config)
                if handled == "exit":
                    break
                continue

            # Process the message through the agent
            console.print()
            current_text = ""

            async for event in agent.process_message(user_input):
                etype = event.type

                if etype == "thinking":
                    console.print(f"  [dim]{event.data.get('message', 'Thinking...')}[/dim]")

                elif etype == "text":
                    content = event.data.get("content", "")
                    if content:
                        current_text += content

                elif etype == "tool_call":
                    tool_name = event.data.get("tool", "")
                    args = event.data.get("arguments", {})
                    _print_tool_call(tool_name, args)

                elif etype == "tool_result":
                    tool_name = event.data.get("tool", "")
                    result = event.data.get("result", "")
                    denied = event.data.get("denied", False)
                    rejected = event.data.get("rejected", False)
                    _print_tool_result(tool_name, result, denied, rejected)

                elif etype == "tool_approval_needed":
                    tool_name = event.data.get("tool", "")
                    reason = event.data.get("reason", "")
                    console.print(
                        f"\n  [yellow bold]Approval needed:[/yellow bold] {tool_name}"
                    )
                    console.print(f"  [dim]{reason}[/dim]")
                    # In CLI mode, auto-approve for operator/autonomous tiers
                    # For assistant tier, prompt user
                    if config.guardrails.tier in ("operator", "autonomous"):
                        console.print("  [green]Auto-approved (tier: {config.guardrails.tier})[/green]")

                elif etype == "plan_update":
                    result = event.data.get("result", "")
                    console.print(f"\n  [blue]Plan updated:[/blue] {result[:100]}")

                elif etype == "error":
                    msg = event.data.get("message", "Unknown error")
                    console.print(f"\n  [red bold]Error:[/red bold] {msg}")

                elif etype == "done":
                    if current_text:
                        console.print(f"\n[bold green]Plutus:[/bold green]")
                        # Render as markdown
                        try:
                            md = Markdown(current_text)
                            console.print(md)
                        except Exception:
                            console.print(current_text)
                        current_text = ""
                    console.print("\n" + "─" * 60)

    finally:
        await agent.shutdown()


def _print_tool_call(tool_name: str, args: dict) -> None:
    """Pretty-print a tool call."""
    # Compact display
    args_str = json.dumps(args, indent=None)
    if len(args_str) > 120:
        args_str = args_str[:117] + "..."
    console.print(f"\n  [yellow]▶ {tool_name}[/yellow] {args_str}")


def _print_tool_result(tool_name: str, result: str, denied: bool, rejected: bool) -> None:
    """Pretty-print a tool result."""
    if denied:
        console.print(f"  [red]✗ {tool_name}: DENIED[/red]")
        return
    if rejected:
        console.print(f"  [red]✗ {tool_name}: REJECTED[/red]")
        return

    # Truncate long results
    display = result
    if len(display) > 500:
        display = display[:497] + "..."

    # Color based on success/failure
    if "[ERROR]" in display:
        console.print(f"  [red]✗ {tool_name}:[/red] {display}")
    else:
        console.print(f"  [green]✓ {tool_name}:[/green] {display[:200]}")


async def _handle_slash_command(
    cmd: str, agent: any, registry: any, config: PlutusConfig
) -> str | None:
    """Handle slash commands in the chat. Returns 'exit' to quit."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ("/exit", "/quit", "/q"):
        console.print("\n  [dim]Goodbye![/dim]\n")
        return "exit"

    elif command == "/help":
        console.print(CHAT_HELP)

    elif command == "/tools":
        tools = registry.list_tools()
        table = Table(title="Available Tools", show_header=True, header_style="bold cyan")
        table.add_column("Tool", style="bold")
        table.add_column("Description", max_width=60)
        for name in tools:
            tool = registry.get(name)
            desc = tool.description[:60] + "..." if len(tool.description) > 60 else tool.description
            table.add_row(name, desc)
        console.print(table)

    elif command == "/plan":
        plan = await agent.planner.get_active_plan(
            agent.conversation.conversation_id
        )
        if plan:
            console.print(Markdown(agent.planner.format_plan_for_context(plan)))
        else:
            console.print("  [dim]No active plan.[/dim]")

    elif command == "/clear":
        await agent.conversation.start_conversation(title="New conversation")
        console.print("  [dim]Conversation cleared.[/dim]")

    elif command == "/tier":
        if arg:
            valid_tiers = ["observer", "assistant", "operator", "autonomous"]
            if arg in valid_tiers:
                config.guardrails.tier = arg
                config.save()
                console.print(f"  Tier set to [bold]{arg}[/bold]")
            else:
                console.print(f"  [red]Invalid tier. Choose: {', '.join(valid_tiers)}[/red]")
        else:
            console.print(f"  Current tier: [bold]{config.guardrails.tier}[/bold]")

    elif command == "/workers":
        from plutus.tools.subprocess_tool import SubprocessTool
        sub_tool = registry.get("subprocess")
        if sub_tool:
            active = sub_tool._manager.list_active()
            if active:
                table = Table(title="Active Workers", show_header=True)
                table.add_column("ID")
                table.add_column("PID")
                table.add_column("Status")
                table.add_column("Elapsed")
                for w in active:
                    table.add_row(w["id"], str(w["pid"]), w["status"], f"{w['elapsed']}s")
                console.print(table)
            else:
                console.print("  [dim]No active workers.[/dim]")
        else:
            console.print("  [dim]Subprocess tool not available.[/dim]")

    else:
        console.print(f"  [red]Unknown command: {command}[/red]")
        console.print("  Type [bold]/help[/bold] for available commands.")

    return None


@main.command()
@click.argument("prompt")
@click.option("--model", default=None, help="Override model")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def run(prompt: str, model: str | None, json_output: bool) -> None:
    """Run a single prompt and exit."""
    asyncio.run(_run_single(prompt, model, json_output))


async def _run_single(prompt: str, model_override: str | None, json_output: bool) -> None:
    """Execute a single prompt."""
    from plutus.config import SecretsStore
    from plutus.core.agent import AgentRuntime
    from plutus.guardrails.engine import GuardrailEngine
    from plutus.core.memory import MemoryStore
    from plutus.tools.registry import create_default_registry

    config = PlutusConfig.load()
    if model_override:
        config.model.model = model_override

    secrets = SecretsStore()
    secrets.inject_all()

    memory = MemoryStore(db_path=config.resolve_memory_db())
    guardrails = GuardrailEngine(config.guardrails)
    registry = create_default_registry()

    agent = AgentRuntime(
        config=config,
        guardrails=guardrails,
        memory=memory,
        tool_registry=registry,
        secrets=secrets,
    )
    await agent.initialize()

    if not agent.key_configured:
        if json_output:
            print(json.dumps({"error": "No API key configured"}))
        else:
            console.print("[red]No API key configured. Run plutus setup.[/red]")
        return

    events = []
    final_text = ""

    async for event in agent.process_message(prompt):
        events.append(event.to_dict())
        if event.type == "text":
            final_text += event.data.get("content", "")
        elif event.type == "error":
            if not json_output:
                console.print(f"[red]Error: {event.data.get('message')}[/red]")

    if json_output:
        print(json.dumps({
            "response": final_text,
            "events": events,
        }, indent=2))
    else:
        if final_text:
            console.print(Markdown(final_text))

    await agent.shutdown()


@main.command()
def setup() -> None:
    """Interactive setup wizard for Plutus."""
    console.print(BANNER)

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
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4.1",
        "ollama": "llama3.2",
        "custom": "gpt-4.1",
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
                    f"  [dim]Skipped. Set {default_env} env var or use the web UI.[/dim]"
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
    console.print("  Run [bold]plutus start[/bold] to launch the web UI")
    console.print("  Run [bold]plutus chat[/bold] for terminal chat\n")


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
        "[green]configured[/green]"
        if key_available
        else "[red]not set[/red] — run `plutus setup`",
    )

    # Count custom tools
    custom_tools_dir = Path.home() / ".plutus" / "custom_tools"
    custom_count = 0
    if custom_tools_dir.exists():
        custom_count = sum(1 for d in custom_tools_dir.iterdir() if d.is_dir())
    table.add_row("Custom Tools", str(custom_count))

    console.print()
    console.print(table)
    console.print()


@main.command()
def tools() -> None:
    """List all available tools."""
    from plutus.tools.registry import create_default_registry

    registry = create_default_registry()

    table = Table(title="Available Tools", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Description", max_width=70)

    for info in registry.get_tool_info():
        desc = info["description"]
        if len(desc) > 70:
            desc = desc[:67] + "..."
        table.add_row(info["name"], desc)

    console.print()
    console.print(table)
    console.print(f"\n  Total: {len(registry.list_tools())} tools\n")


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
def update() -> None:
    """Update Plutus to the latest version."""
    import subprocess

    from pathlib import Path

    console.print(f"\n  Current version: [bold]{__version__}[/bold]")
    console.print("  Checking for updates...\n")

    # ── Windows workaround: rename locked .exe scripts so pip can overwrite ──
    renamed_scripts: list[tuple[Path, Path]] = []
    if sys.platform == "win32":
        scripts_dir = Path(sys.executable).parent / "Scripts"
        if not scripts_dir.is_dir():
            scripts_dir = Path(sys.executable).parent
        for pattern in ("plutus.exe", "plutus-*.exe"):
            for exe in scripts_dir.glob(pattern):
                bak = exe.with_suffix(".exe.old")
                try:
                    if bak.exists():
                        bak.unlink()
                    exe.rename(bak)
                    renamed_scripts.append((bak, exe))
                except OSError:
                    pass

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "plutus-ai"],
        capture_output=True,
        text=True,
    )

    # ── Windows: clean up .old files ──
    for bak, _orig in renamed_scripts:
        try:
            bak.unlink(missing_ok=True)
        except OSError:
            pass

    if result.returncode != 0:
        console.print(f"  [red bold]Update failed:[/red bold]\n  {result.stderr.strip()[:300]}")
        return

    # Read the new version from a fresh subprocess
    ver_result = subprocess.run(
        [sys.executable, "-c", "import plutus; print(plutus.__version__)"],
        capture_output=True,
        text=True,
    )
    new_version = ver_result.stdout.strip() if ver_result.returncode == 0 else "unknown"

    if new_version == __version__:
        console.print(f"  [green]Already on the latest version (v{__version__})[/green]\n")
    else:
        console.print(f"  [green bold]Updated to v{new_version}[/green bold]")
        console.print("  Restart Plutus to use the new version.\n")


@main.command()
def config_show() -> None:
    """Display the current configuration as JSON."""
    config = PlutusConfig.load()
    console.print_json(json.dumps(config.model_dump(), indent=2))
