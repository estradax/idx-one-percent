"""IDX One Percent Shareholder Data Analyzer Main Entrypoint.

This script coordinates scanning the 'onepercent-data' directory, sorting
the files chronologically, comparing consecutive periods using the entity
resolution engine, and rendering the results in the terminal.
"""

from datetime import datetime
import os
from typing import Dict, List, Tuple

import pandas as pd
from rich.console import Console
from rich.panel import Panel

from analyzer import load_excel_file, parse_filename_date, render_dashboard, run_comparison

console = Console()


def main() -> None:
    """Find, sort, and process all shareholder reports chronologically."""
    # Find files relative to script or standard workspace
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "onepercent-data")

    if not os.path.exists(data_dir):
        # Fallback to local execution directory
        data_dir = "./onepercent-data"

    if not os.path.exists(data_dir):
        console.print(
            f"[bold red]Error: Directory '{data_dir}' not found.[/bold red]")
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

    # Cache loaded dataframes to avoid re-reading files multiple times
    loaded_dfs: Dict[str, pd.DataFrame] = {}

    for idx in range(len(sorted_files) - 1):
        dt1, file1, m1 = sorted_files[idx]
        dt2, file2, m2 = sorted_files[idx + 1]

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
            continue

        # Run comparison and entity resolution
        entries, exits, increases, decreases, transfers, new_stocks, removed_stocks = run_comparison(
            df1, df2)

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


if __name__ == "__main__":
    main()
