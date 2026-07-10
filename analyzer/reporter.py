"""Terminal dashboard rendering for IDX shareholder data comparison."""

import contextlib

import pandas as pd
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

__all__ = [
    "format_change_pct",
    "render_dashboard",
]

# Initialize Console for printing
console = Console()


def format_change_pct(prev: float, curr: float) -> str:
    """Format the change percentage with appropriate styling.

    Args:
        prev: Previous share count.
        curr: Current share count.

    Returns:
        Formatted percentage string (e.g. '+12.4%' or 'New').
    """
    if prev == 0:
        return "[bold green]New[/bold green]"
    if curr == 0:
        return "[bold red]Exited[/bold red]"
    diff = curr - prev
    pct = (diff / prev) * 100
    if pct > 0:
        return f"[green]+{pct:,.2f}%[/green]"
    return f"[red]{pct:,.2f}%[/red]"


def _format_lot_value(shares: float) -> str:
    """Format share count into lot units (1 lot = 100 shares)."""
    lots = shares / 100.0
    if lots.is_integer():
        return f"{lots:,.0f}"
    return f"{lots:,.2f}".rstrip("0").rstrip(".")


def _format_net_change_lot(diff: float) -> str:
    """Format net change in shares to styled lot units."""
    lots = diff / 100.0
    if lots == 0:
        return "0"
    if lots.is_integer():
        formatted = f"{lots:,.0f}"
    else:
        formatted = f"{lots:,.2f}".rstrip("0").rstrip(".")
    if lots > 0:
        return f"[green]+{formatted}[/green]"
    return f"[red]{formatted}[/red]"


def render_dashboard(
    title: str,
    active_stocks_count: int,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    increases: pd.DataFrame,
    decreases: pd.DataFrame,
    transfers: pd.DataFrame,
    new_stocks: set[str],
    removed_stocks: set[str],
    pager: bool = True,
) -> None:
    """Render a beautiful CLI dashboard showing period comparison metrics.

    Args:
        title: Styled header title.
        active_stocks_count: Total stocks in the current period.
        entries: DataFrame of true new shareholder positions.
        exits: DataFrame of true closed shareholder positions.
        increases: DataFrame of increased positions.
        decreases: DataFrame of decreased positions.
        transfers: DataFrame of resolved entity name changes.
        new_stocks: Newly listed stock symbols.
        removed_stocks: Delisted stock symbols.
        pager: Whether to use a terminal pager (scrollable view).
    """
    pager_context = console.pager(styles=True) if pager else contextlib.nullcontext()

    with pager_context:
        console.print(Panel(Align.center(f"[bold white]{title}[/bold white]"), expand=True, border_style="cyan"))

        # Consolidate all changes (entries, exits, increases, decreases, and name changes with non-zero differences)
        dfs_to_combine = []

        if not entries.empty:
            dfs_to_combine.append(
                entries[
                    ["SHARE_CODE", "INVESTOR_NAME", "TOTAL_HOLDING_SHARES_prev", "TOTAL_HOLDING_SHARES_curr", "diff"]
                ]
            )

        if not increases.empty:
            dfs_to_combine.append(
                increases[
                    ["SHARE_CODE", "INVESTOR_NAME", "TOTAL_HOLDING_SHARES_prev", "TOTAL_HOLDING_SHARES_curr", "diff"]
                ]
            )

        if not transfers.empty:
            # Include resolved transfers that have a net holding difference
            df_tr_diff = transfers[transfers["diff"] != 0].copy()
            if not df_tr_diff.empty:
                df_tr_diff["INVESTOR_NAME"] = df_tr_diff.apply(
                    lambda r: f"{r['INVESTOR_NAME_curr']} [dim](formerly {r['INVESTOR_NAME_prev']})[/dim]", axis=1
                )
                dfs_to_combine.append(
                    df_tr_diff[
                        [
                            "SHARE_CODE",
                            "INVESTOR_NAME",
                            "TOTAL_HOLDING_SHARES_prev",
                            "TOTAL_HOLDING_SHARES_curr",
                            "diff",
                        ]
                    ]
                )

        if not decreases.empty:
            dfs_to_combine.append(
                decreases[
                    ["SHARE_CODE", "INVESTOR_NAME", "TOTAL_HOLDING_SHARES_prev", "TOTAL_HOLDING_SHARES_curr", "diff"]
                ]
            )

        if not exits.empty:
            dfs_to_combine.append(
                exits[["SHARE_CODE", "INVESTOR_NAME", "TOTAL_HOLDING_SHARES_prev", "TOTAL_HOLDING_SHARES_curr", "diff"]]
            )

        if dfs_to_combine:
            combined_changes = pd.concat(dfs_to_combine)
            # Sort from most added shares (largest positive diff) to most decreased shares (largest negative diff)
            combined_changes = combined_changes.sort_values(by="diff", ascending=False).reset_index(drop=True)
        else:
            combined_changes = pd.DataFrame()

        # Render Consolidated Table of every change
        if not combined_changes.empty:
            table_changes = Table(
                expand=True,
                title_justify="left",
                border_style="blue",
            )
            table_changes.add_column("Stock", style="cyan", justify="left")
            table_changes.add_column("Investor Name", style="white", justify="left")
            table_changes.add_column("Previous Shares", justify="right")
            table_changes.add_column("Previous Lot", justify="right")
            table_changes.add_column("Current Shares", justify="right")
            table_changes.add_column("Current Lot", justify="right")
            table_changes.add_column("Net Change Shares", justify="right")
            table_changes.add_column("Net Change Lot", justify="right")
            table_changes.add_column("% Change", justify="right")

            for _, r in combined_changes.iterrows():
                diff_val = float(r["diff"])
                diff_str = f"[green]+{diff_val:,.0f}[/green]" if diff_val > 0 else f"[red]{diff_val:,.0f}[/red]"
                table_changes.add_row(
                    str(r["SHARE_CODE"]),
                    str(r["INVESTOR_NAME"]),
                    f"{r['TOTAL_HOLDING_SHARES_prev']:,.0f}",
                    _format_lot_value(float(r["TOTAL_HOLDING_SHARES_prev"])),
                    f"{r['TOTAL_HOLDING_SHARES_curr']:,.0f}",
                    _format_lot_value(float(r["TOTAL_HOLDING_SHARES_curr"])),
                    diff_str,
                    _format_net_change_lot(diff_val),
                    format_change_pct(float(r["TOTAL_HOLDING_SHARES_prev"]), float(r["TOTAL_HOLDING_SHARES_curr"])),
                )
            console.print(table_changes)
            console.print()

        # Render Table for Name Variations with NO net change (pure format changes)
        if not transfers.empty:
            transfers_no_diff = transfers[transfers["diff"] == 0].copy()
            if not transfers_no_diff.empty:
                table_trans = Table(
                    expand=True,
                    title_justify="left",
                    border_style="cyan",
                )
                table_trans.add_column("Stock", style="cyan")
                table_trans.add_column("Previous Name Format", style="dim white")
                table_trans.add_column("Current Name Format", style="white")
                table_trans.add_column("Holding Shares", justify="right")

                # Sort by holding size to show most prominent ones
                top_transfers = transfers_no_diff.sort_values(by="TOTAL_HOLDING_SHARES_curr", ascending=False)
                for _, r in top_transfers.iterrows():
                    table_trans.add_row(
                        str(r["SHARE_CODE"]),
                        str(r["INVESTOR_NAME_prev"]),
                        str(r["INVESTOR_NAME_curr"]),
                        f"{r['TOTAL_HOLDING_SHARES_curr']:,.0f}",
                    )
                console.print(table_trans)
                console.print()
