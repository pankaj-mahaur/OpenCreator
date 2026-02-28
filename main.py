"""
main.py — CLI + Web UI entry point for OpenCreator.

Usage:
    python main.py --topic "Latest AI news"              # Full pipeline
    python main.py --topic "AI news" --dry-run            # Skip publishing
    python main.py --list                                  # List all runs
    python main.py --serve                                 # Start web UI
"""

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

import config

console = Console()


def setup_logging(verbose: bool = False):
    """Configure rich logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def show_banner():
    """Display the agent banner."""
    banner = """
[bold cyan]╔══════════════════════════════════════════════╗
║    🎬 OpenCreator                             ║
║    ─────────────────────────────────────      ║
║    Research → Script → Voice → Video → Edit   ║
║    Local AI • Voice Clone • Open Source        ║
╚══════════════════════════════════════════════╝[/bold cyan]
"""
    console.print(banner)


def run_pipeline(args):
    """Run the full content pipeline."""
    from orchestrator import Orchestrator

    orch = Orchestrator()

    console.print(f"\n[green]Running pipeline for:[/green] {args.topic}")
    console.print(f"[dim]Model: {args.model or config.VIDEO_GEN_MODEL}[/dim]")

    state = orch.run(
        topic=args.topic,
        dry_run=args.dry_run,
        model=args.model,
        voice=args.voice,
    )

    show_run_status(state)
    return state


def list_runs(args):
    """List all pipeline runs."""
    from orchestrator import Orchestrator

    orch = Orchestrator()
    runs = orch.list_runs()

    if not runs:
        console.print("[yellow]No runs found.[/yellow]")
        return

    table = Table(title="Pipeline Runs")
    table.add_column("ID", style="cyan")
    table.add_column("Topic", max_width=30)
    table.add_column("Status", style="bold")
    table.add_column("Created")

    for run in runs[:20]:
        status_color = {
            "pending": "dim",
            "running": "yellow",
            "review": "green",
            "failed": "red",
        }.get(run.status, "white")

        table.add_row(
            run.id,
            run.topic[:30],
            f"[{status_color}]{run.status}[/{status_color}]",
            run.created_at[:19],
        )

    console.print(table)


def show_run_status(state):
    """Display detailed run status."""
    table = Table(title=f"Run: {state.id}")
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    table.add_row("Status", state.status)
    table.add_row("Topic", state.topic)
    table.add_row("Step", state.current_step)
    table.add_row("Progress", f"{state.progress * 100:.0f}%")
    if state.script_title:
        table.add_row("Title", state.script_title)
    if state.final_video_path:
        table.add_row("Video", state.final_video_path)
    if state.error:
        table.add_row("Error", f"[red]{state.error}[/red]")

    console.print(table)


def start_web_ui(args):
    """Start the Flask web UI."""
    from dashboard.app import create_app

    app = create_app()
    console.print(f"\n[bold green]🌐 Web UI starting at http://{config.WEB_HOST}:{config.WEB_PORT}[/bold green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    app.run(
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        debug=args.verbose if hasattr(args, 'verbose') else False,
    )


def main():
    parser = argparse.ArgumentParser(
        description="🎬 OpenCreator — AI Video Content Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --topic "Latest AI tools"           # Full pipeline
  python main.py --topic "AI news" --dry-run          # Skip publish
  python main.py --list                                # List all runs
  python main.py --serve                               # Start web UI
        """,
    )

    parser.add_argument("--topic", type=str, help="Content topic for the Reel")
    parser.add_argument("--model", type=str, choices=["kling-1.6", "wan", "minimax"],
                        help="Video generation model (default: kling-1.6)")
    parser.add_argument("--voice", type=str, help="Edge TTS voice name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run pipeline without publishing")
    parser.add_argument("--list", action="store_true",
                        help="List all pipeline runs")
    parser.add_argument("--serve", action="store_true",
                        help="Start web UI dashboard")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging output")

    args = parser.parse_args()

    setup_logging(args.verbose)
    show_banner()

    if args.serve:
        start_web_ui(args)
    elif args.list:
        list_runs(args)
    elif args.topic:
        run_pipeline(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
