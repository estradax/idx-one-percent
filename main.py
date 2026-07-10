"""IDX One Percent Shareholder Data Analyzer Main Entrypoint.

This script coordinates scanning the 'onepercent-data' directory, sorting
the files chronologically, comparing consecutive periods using the entity
resolution engine, and rendering the results in the terminal.
"""

from datetime import datetime
import os
from typing import Dict, List, Tuple

import pandas as pd
from rich.align import Align
from rich.console import Console
from rich.panel import Panel

from analyzer import (
    load_excel_file,
    parse_filename_date,
    render_dashboard,
    run_comparison,
)

console = Console()


def compare_and_render(
    period1: Tuple[datetime, str, str],
    period2: Tuple[datetime, str, str],
    data_dir: str,
    loaded_dfs: Dict[str, pd.DataFrame],
) -> None:
    """Run comparison between two periods and render the dashboard.

    Args:
        period1: Start period tuple (datetime, filename, month_name).
        period2: End period tuple (datetime, filename, month_name).
        data_dir: Directory containing the excel files.
        loaded_dfs: Cached dataframes mapping filename to DataFrame.
    """
    dt1, file1, m1 = period1
    dt2, file2, m2 = period2

    # Use cache or load file
    if file1 not in loaded_dfs:
        loaded_dfs[file1] = load_excel_file(os.path.join(data_dir, file1))
    if file2 not in loaded_dfs:
        loaded_dfs[file2] = load_excel_file(os.path.join(data_dir, file2))

    df1 = loaded_dfs[file1]
    df2 = loaded_dfs[file2]

    if df1.empty or df2.empty:
        console.print(
            f"[bold red]Skipping comparison: Failed to load data from {file1} or {file2}[/bold red]"
        )
        return

    # Run comparison and entity resolution
    entries, exits, increases, decreases, transfers, new_stocks, removed_stocks = (
        run_comparison(df1, df2)
    )

    # Render dashboard for the period
    title = f"IDX SHAREHOLDER MOVEMENT: {m1} {dt1.year} ➔ {m2} {dt2.year}"
    active_stocks_count = len(df2["SHARE_CODE"].dropna().unique())

    render_dashboard(
        title=title,
        active_stocks_count=active_stocks_count,
        entries=entries,
        exits=exits,
        increases=increases,
        decreases=decreases,
        transfers=transfers,
        new_stocks=new_stocks,
        removed_stocks=removed_stocks,
    )


def main() -> None:
    """Find, sort, and process all shareholder reports chronologically, prompting the user for selection."""
    # Find files relative to script or standard workspace
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "onepercent-data")

    if not os.path.exists(data_dir):
        # Fallback to local execution directory
        data_dir = "./onepercent-data"

    if not os.path.exists(data_dir):
        console.print(f"[bold red]Error: Directory '{data_dir}' not found.[/bold red]")
        return

    files = [f for f in os.listdir(data_dir) if f.endswith(".xlsx")]
    if len(files) < 2:
        console.print(
            "[bold red]Error: Need at least 2 Excel files to perform comparisons.[/bold red]"
        )
        return

    # Parse and sort chronologically
    sorted_files: List[Tuple[datetime, str, str]] = []
    for f in files:
        dt, month_name = parse_filename_date(f)
        if dt != datetime.min:
            sorted_files.append((dt, f, month_name))

    sorted_files.sort(key=lambda x: x[0])

    # Build the list of consecutive transitions
    transitions: List[
        Tuple[int, Tuple[datetime, str, str], Tuple[datetime, str, str]]
    ] = []
    for idx in range(len(sorted_files) - 1):
        transitions.append((idx, sorted_files[idx], sorted_files[idx + 1]))

    # Reverse transitions to list them in reverse chronological order
    transitions.reverse()

    # Cache loaded dataframes to avoid re-reading files multiple times
    loaded_dfs: Dict[str, pd.DataFrame] = {}

    while True:
        console.clear()
        console.print(
            Panel(
                Align.center("[bold green]IDX Shareholder Data Analyzer[/bold green]"),
                border_style="green",
            )
        )

        console.print("[bold cyan]Available Periods to Compare:[/bold cyan]")
        for i, (idx, (dt1, _, m1), (dt2, _, m2)) in enumerate(transitions, start=1):
            console.print(
                f"[bold yellow][{i}][/bold yellow] {m1} {dt1.year} ➔ {m2} {dt2.year}"
            )

        console.print(
            f"[bold yellow][{len(transitions) + 1}][/bold yellow] Compare All Periods"
        )
        console.print(f"[bold yellow][{len(transitions) + 2}][/bold yellow] Exit")

        try:
            choice_str = console.input(
                f"\n[bold green]Select option (1-{len(transitions) + 2}): [/bold green]"
            ).strip()
            if not choice_str:
                continue
            choice = int(choice_str)

            if 1 <= choice <= len(transitions):
                idx, period1, period2 = transitions[choice - 1]
                compare_and_render(period1, period2, data_dir, loaded_dfs)
                console.input(
                    "\n[bold dim]Press Enter to return to the menu...[/bold dim]"
                )
            elif choice == len(transitions) + 1:
                # Compare all chronologically
                for idx, period1, period2 in sorted(transitions, key=lambda x: x[0]):
                    compare_and_render(period1, period2, data_dir, loaded_dfs)
                console.input(
                    "\n[bold dim]Press Enter to return to the menu...[/bold dim]"
                )
            elif choice == len(transitions) + 2:
                console.print("[bold green]Goodbye![/bold green]")
                break
            else:
                console.print(
                    f"[bold red]Please enter a valid option between 1 and {len(transitions) + 2}.[/bold red]"
                )
                console.input("\n[bold dim]Press Enter to continue...[/bold dim]")
        except ValueError:
            console.print(
                "[bold red]Invalid input. Please enter a valid number.[/bold red]"
            )
            console.input("\n[bold dim]Press Enter to continue...[/bold dim]")


if __name__ == "__main__":
    main()
