"""IDX One Percent Shareholder Data Analyzer Main Entrypoint.

This script coordinates scanning the 'onepercent-data' directory, sorting
the files chronologically, comparing consecutive periods using the entity
resolution engine, and rendering the results in the terminal.
"""

import os
from collections.abc import Iterable
from datetime import datetime

import pandas as pd
from rich.align import Align
from rich.panel import Panel
from rich.table import Table

from analyzer import (
    load_excel_file,
    parse_filename_date,
    render_dashboard,
    run_comparison,
)
from analyzer.reporter import console


def search_dataframes(
    dfs: dict[str, pd.DataFrame],
    query: str,
    previous_periods: dict[str, pd.DataFrame] | None = None,
) -> list[tuple[str, pd.DataFrame]]:
    """Search loaded dataframes across common shareholder columns for a keyword and enrich them with prior-period values."""
    if not query.strip():
        return []

    needle = query.strip().lower()
    matches: list[tuple[str, pd.DataFrame]] = []
    searchable_columns = ["SHARE_CODE", "ISSUER_NAME", "INVESTOR_NAME", "LOCAL_FOREIGN", "NATIONALITY", "DOMICILE"]

    for filename, df in dfs.items():
        if df.empty:
            continue

        candidate_columns = [col for col in searchable_columns if col in df.columns]
        if not candidate_columns:
            continue

        mask = pd.Series(False, index=df.index)
        for column in candidate_columns:
            values = df[column].fillna("")
            mask |= values.astype(str).str.lower().str.contains(needle, na=False, regex=False)

        if mask.any():
            matched_df = df.loc[mask].copy()
            prev_df = previous_periods.get(filename) if previous_periods else None
            if prev_df is not None and not prev_df.empty:
                matched_df = matched_df.copy()
                current_shares = pd.to_numeric(matched_df.get("TOTAL_HOLDING_SHARES", 0), errors="coerce").fillna(0.0)
                matched_df["TOTAL_HOLDING_SHARES_curr"] = current_shares

                prev_lookup = prev_df[["SHARE_CODE", "INVESTOR_NAME", "TOTAL_HOLDING_SHARES"]].copy()
                prev_lookup = prev_lookup.groupby(["SHARE_CODE", "INVESTOR_NAME"], as_index=False)[
                    "TOTAL_HOLDING_SHARES"
                ].sum()
                prev_lookup = prev_lookup.rename(columns={"TOTAL_HOLDING_SHARES": "TOTAL_HOLDING_SHARES_prev"})
                matched_df = matched_df.merge(prev_lookup, on=["SHARE_CODE", "INVESTOR_NAME"], how="left")
                matched_df["TOTAL_HOLDING_SHARES_prev"] = pd.to_numeric(
                    matched_df.get("TOTAL_HOLDING_SHARES_prev", 0), errors="coerce"
                ).fillna(0.0)
                matched_df["TOTAL_HOLDING_SHARES_curr"] = pd.to_numeric(
                    matched_df.get("TOTAL_HOLDING_SHARES_curr", 0), errors="coerce"
                ).fillna(0.0)
                matched_df["diff"] = matched_df["TOTAL_HOLDING_SHARES_curr"] - matched_df["TOTAL_HOLDING_SHARES_prev"]

            matches.append((filename, matched_df))

    return matches


def render_search_results(matches: Iterable[tuple[str, pd.DataFrame]]) -> None:
    """Render search results in a terminal table with period, change, and lot details."""
    matches_list = list(matches)
    if not matches_list:
        console.print("[bold yellow]No matches found.[/bold yellow]")
        return

    table = Table(title="Search Results", expand=True, border_style="magenta")
    table.add_column("Period", style="cyan")
    table.add_column("Stock", style="white")
    table.add_column("Investor", style="white")
    table.add_column("Change %", justify="right")
    table.add_column("Lots", justify="right")
    table.add_column("Details", style="dim")

    for filename, df in matches_list:
        for _, row in df.iterrows():
            period_label = filename.replace(".xlsx", "")
            prev_shares = float(row.get("TOTAL_HOLDING_SHARES_prev", row.get("TOTAL_HOLDING_SHARES", 0.0)) or 0.0)
            curr_shares = float(row.get("TOTAL_HOLDING_SHARES_curr", row.get("TOTAL_HOLDING_SHARES", 0.0)) or 0.0)
            diff = curr_shares - prev_shares
            pct = ((diff / prev_shares) * 100) if prev_shares else (0.0 if diff == 0 else 100.0)
            lots = diff / 100.0

            change_text = f"[green]+{pct:,.2f}%[/green]" if pct > 0 else f"[red]{pct:,.2f}%[/red]"
            lots_text = f"[green]+{lots:,.2f}[/green]" if lots > 0 else f"[red]{lots:,.2f}[/red]"

            details = f"Prev: {prev_shares:,.0f} | Curr: {curr_shares:,.0f}"
            table.add_row(
                period_label,
                str(row.get("SHARE_CODE", "")),
                str(row.get("INVESTOR_NAME", row.get("INVESTOR_NAME_prev", ""))),
                change_text,
                lots_text,
                details,
            )

    console.print(table)


def filter_comparison_frames(
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    increases: pd.DataFrame,
    decreases: pd.DataFrame,
    transfers: pd.DataFrame,
    query: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Filter comparison frames by a keyword across common investor and stock columns."""
    if not query.strip():
        return entries, exits, increases, decreases, transfers

    needle = query.strip().lower()

    def _filter_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame

        columns = [
            col
            for col in ["SHARE_CODE", "INVESTOR_NAME", "INVESTOR_NAME_prev", "INVESTOR_NAME_curr", "ISSUER_NAME"]
            if col in frame.columns
        ]
        if not columns:
            return frame.iloc[0:0].copy()

        mask = pd.Series(False, index=frame.index)
        for column in columns:
            values = frame[column].fillna("")
            mask |= values.astype(str).str.lower().str.contains(needle, na=False, regex=False)
        return frame.loc[mask].copy()

    return (
        _filter_frame(entries),
        _filter_frame(exits),
        _filter_frame(increases),
        _filter_frame(decreases),
        _filter_frame(transfers),
    )


def compare_and_render(
    period1: tuple[datetime, str, str],
    period2: tuple[datetime, str, str],
    data_dir: str,
    loaded_dfs: dict[str, pd.DataFrame],
    pager: bool = True,
) -> None:
    """Run comparison between two periods and render the dashboard.

    Args:
        period1: Start period tuple (datetime, filename, month_name).
        period2: End period tuple (datetime, filename, month_name).
        data_dir: Directory containing the excel files.
        loaded_dfs: Cached dataframes mapping filename to DataFrame.
        pager: Whether to use a terminal pager (scrollable view).
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
        console.print(f"[bold red]Skipping comparison: Failed to load data from {file1} or {file2}[/bold red]")
        return

    # Run comparison and entity resolution
    entries, exits, increases, decreases, transfers, new_stocks, removed_stocks = run_comparison(df1, df2)

    console.print("[bold cyan]Search inside this monthly view?[/bold cyan] (press Enter to skip)")
    search_query = console.input("[bold green]Keyword: [/bold green]").strip()
    if search_query:
        entries, exits, increases, decreases, transfers = filter_comparison_frames(
            entries,
            exits,
            increases,
            decreases,
            transfers,
            search_query,
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
        pager=pager,
    )


def main() -> None:
    """Find, sort, and process all shareholder reports chronologically, prompting the user for selection."""
    # Ensure terminal pager (e.g. less) renders colors correctly
    if "LESS" in os.environ:
        if "R" not in os.environ["LESS"]:
            os.environ["LESS"] += "R"
    else:
        os.environ["LESS"] = "-R"

    if "PAGER" not in os.environ and "MANPAGER" not in os.environ:
        os.environ["PAGER"] = "less -R"

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
        console.print("[bold red]Error: Need at least 2 Excel files to perform comparisons.[/bold red]")
        return

    # Parse and sort chronologically
    sorted_files: list[tuple[datetime, str, str]] = []
    for f in files:
        dt, month_name = parse_filename_date(f)
        if dt != datetime.min:
            sorted_files.append((dt, f, month_name))

    sorted_files.sort(key=lambda x: x[0])

    # Build the list of consecutive transitions
    transitions: list[tuple[int, tuple[datetime, str, str], tuple[datetime, str, str]]] = []
    for idx in range(len(sorted_files) - 1):
        transitions.append((idx, sorted_files[idx], sorted_files[idx + 1]))

    # Reverse transitions to list them in reverse chronological order
    transitions.reverse()

    # Cache loaded dataframes to avoid re-reading files multiple times
    loaded_dfs: dict[str, pd.DataFrame] = {}

    console.print(
        Panel(
            Align.center("[bold green]IDX Shareholder Data Analyzer[/bold green]"),
            border_style="green",
        )
    )

    console.print("[bold cyan]Available Periods to Compare:[/bold cyan]")
    for i, (_, (dt1, _, m1), (dt2, _, m2)) in enumerate(transitions, start=1):
        console.print(f"[bold yellow][{i}][/bold yellow] {m1} {dt1.year} ➔ {m2} {dt2.year}")

    console.print(f"[bold yellow][{len(transitions) + 1}][/bold yellow] Compare All Periods")
    console.print(f"[bold yellow][{len(transitions) + 2}][/bold yellow] Search Data")
    console.print(f"[bold yellow][{len(transitions) + 3}][/bold yellow] Exit")

    try:
        choice_str = console.input(f"\n[bold green]Select option (1-{len(transitions) + 3}): [/bold green]").strip()
        if choice_str:
            choice = int(choice_str)

            if 1 <= choice <= len(transitions):
                idx, period1, period2 = transitions[choice - 1]
                compare_and_render(period1, period2, data_dir, loaded_dfs, pager=True)
            elif choice == len(transitions) + 1:
                # Compare all chronologically
                with console.pager(styles=True):
                    for _, period1, period2 in sorted(transitions, key=lambda x: x[0]):
                        compare_and_render(period1, period2, data_dir, loaded_dfs, pager=False)
            elif choice == len(transitions) + 2:
                query = console.input("[bold green]Search keyword: [/bold green]").strip()
                if not query:
                    console.print("[bold yellow]No keyword entered.[/bold yellow]")
                    return

                if not loaded_dfs:
                    for file_name in files:
                        loaded_dfs[file_name] = load_excel_file(os.path.join(data_dir, file_name))

                previous_periods: dict[str, pd.DataFrame] = {}
                sorted_file_names = [item[1] for item in sorted_files]
                for idx, file_name in enumerate(sorted_file_names):
                    if idx == 0:
                        continue
                    previous_periods[file_name] = loaded_dfs.get(sorted_file_names[idx - 1], pd.DataFrame())

                matches = search_dataframes(loaded_dfs, query, previous_periods=previous_periods)
                render_search_results(matches)
            elif choice == len(transitions) + 3:
                console.print("[bold green]Goodbye![/bold green]")
            else:
                console.print(f"[bold red]Please enter a valid option between 1 and {len(transitions) + 3}.[/bold red]")
    except ValueError:
        console.print("[bold red]Invalid input. Please enter a valid number.[/bold red]")


if __name__ == "__main__":
    main()
