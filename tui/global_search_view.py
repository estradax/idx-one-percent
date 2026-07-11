"""Global search view and search helper for historical reports."""

from __future__ import annotations

from typing import Any

import pandas as pd
from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Input, Label, Static
from textual.widgets.data_table import RowKey

from analyzer.data_loader import parse_filename_date


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


class GlobalSearchView(Static):
    """View for searching across all historical reports."""

    DEFAULT_CSS = """
    $accent: #89b4fa;
    $border: #45475a;
    $content-bg: #1e1e2e;
    $title-color: #f5c2e7;
    $subtle: #a6adc8;
    $cyan: #89dceb;

    GlobalSearchView {
        padding: 0 1;
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    #global-search-container {
        layout: vertical;
        height: 100%;
    }

    .title-label {
        text-style: bold;
        color: $title-color;
        margin-top: 1;
    }

    .subtitle-label {
        color: $subtle;
        margin-bottom: 1;
    }

    #global-search-input {
        border: solid $border;
    }

    #global-search-input:focus {
        border: solid $accent;
    }

    #global-search-status {
        margin-bottom: 1;
        color: $cyan;
        text-style: bold;
    }

    #global-search-table {
        height: 1fr;
        max-height: 100%;
    }

    DataTable {
        height: auto;
        max-height: 25;
        border: round $border;
        background: $content-bg;
        margin-bottom: 1;
    }

    DataTable:focus {
        border: round $accent;
    }

    #global-search-detail {
        border: round $border;
        background: $content-bg;
        height: 7;
        padding: 0 2;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="global-search-container"):
            yield Label("GLOBAL SHAREHOLDER DATA SEARCH", classes="title-label")
            yield Label("Search for any investor name or stock code across all periods", classes="subtitle-label")

            yield Input(placeholder="Type keyword and press Enter to search...", id="global-search-input")
            yield Label("Enter a search term above.", id="global-search-status")

            yield DataTable(id="global-search-table")
            yield Static(id="global-search-detail")

    def on_mount(self) -> None:
        table = self.query_one("#global-search-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Period", "Stock", "Investor", "Change %", "Lots Change", "Details")

        detail_box = self.query_one("#global-search-detail", Static)
        detail_box.border_title = "Details"
        self.reset_detail_view()

    def perform_search(self, query: str) -> None:
        """Run global search across loaded dfs and populate search table."""
        table = self.query_one("#global-search-table", DataTable)
        table.clear()
        self.reset_detail_view()

        status_label = self.query_one("#global-search-status", Label)

        if not query.strip():
            status_label.update("Enter a search term above.")
            return

        app = self.app
        # Use local import to avoid circular import issues
        from tui.app import IDXAnalyzerApp

        assert isinstance(app, IDXAnalyzerApp)

        # Check background loading status
        loaded_count = len(app.loaded_dfs)
        total_count = len(app.sorted_files)

        warning_msg = ""
        if loaded_count < total_count:
            warning_msg = f" [yellow](Background loading: {loaded_count}/{total_count} files ready)[/yellow]"

        matches = app.run_global_search(query)

        if not matches:
            status_label.update(Text.from_markup(f"[yellow]No matches found.[/yellow]{warning_msg}"))
            return

        # Sort matches by parsed date from filename descending (newest/highest to oldest/lowest)
        matches.sort(key=lambda x: parse_filename_date(x[0])[0], reverse=True)

        row_count = 0
        for filename, df in matches:
            period_label = filename.replace(".xlsx", "")
            for _, row in df.iterrows():
                prev_shares = float(row.get("TOTAL_HOLDING_SHARES_prev", row.get("TOTAL_HOLDING_SHARES", 0.0)) or 0.0)
                curr_shares = float(row.get("TOTAL_HOLDING_SHARES_curr", row.get("TOTAL_HOLDING_SHARES", 0.0)) or 0.0)
                diff = curr_shares - prev_shares
                pct = ((diff / prev_shares) * 100) if prev_shares else (0.0 if diff == 0 else 100.0)
                lots = diff / 100.0

                change_text = (
                    f"[green]+{pct:,.2f}%[/green]" if pct > 0 else (f"[red]{pct:,.2f}%[/red]" if pct < 0 else "0.00%")
                )
                lots_text = (
                    f"[green]+{lots:,.2f}[/green]" if lots > 0 else (f"[red]{lots:,.2f}[/red]" if lots < 0 else "0")
                )

                if pct == 100.0 and prev_shares == 0:
                    change_text = "[bold green]New[/bold green]"
                    lots_text = f"[green]+{lots:,.2f}[/green]"

                details = f"Prev: {prev_shares:,.0f} | Curr: {curr_shares:,.0f}"

                table.add_row(
                    Text.from_markup(period_label),
                    Text.from_markup(str(row.get("SHARE_CODE", ""))),
                    Text.from_markup(str(row.get("INVESTOR_NAME", row.get("INVESTOR_NAME_prev", "")))),
                    Text.from_markup(change_text),
                    Text.from_markup(lots_text),
                    Text.from_markup(details),
                )
                row_count += 1

        status_label.update(Text.from_markup(f"[green]Found {row_count} matches.[/green]{warning_msg}"))
        self.update_detail_view(table)

    @on(Input.Submitted, "#global-search-input")
    def handle_global_search_submit(self, event: Input.Submitted) -> None:
        """Handle search submit (pressing Enter)."""
        self.perform_search(event.value)

    @on(Input.Changed, "#global-search-input")
    def handle_global_search_change(self, event: Input.Changed) -> None:
        """Handle real-time search typing."""
        if len(event.value) >= 2 or not event.value:
            self.perform_search(event.value)

    @on(DataTable.RowHighlighted)
    def handle_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlighted in global-search-table."""
        if event.data_table.id == "global-search-table":
            self.update_detail_view(event.data_table, row_key=event.row_key)

    def reset_detail_view(self) -> None:
        """Reset the detail view to its default state."""
        detail = self.query_one("#global-search-detail", Static)
        detail.update(Text.from_markup("[dim]Highlight a row in the table above to see details here...[/dim]"))

    def update_detail_view(
        self,
        data_table: DataTable[Any],
        row_key: RowKey | None = None,
        row_index: int | None = None,
    ) -> None:
        """Update the detail view with the contents of the highlighted row."""
        detail = self.query_one("#global-search-detail", Static)

        try:
            if row_key is not None:
                row_values = data_table.get_row(row_key)
            elif row_index is not None:
                row_values = data_table.get_row_at(row_index)
            else:
                if data_table.row_count > 0 and 0 <= data_table.cursor_row < data_table.row_count:
                    row_values = data_table.get_row_at(data_table.cursor_row)
                else:
                    self.reset_detail_view()
                    return
        except Exception:
            self.reset_detail_view()
            return

        # Columns: Period, Stock, Investor, Change %, Lots Change, Details
        if len(row_values) >= 6:
            period = row_values[0]
            stock = row_values[1]
            investor = row_values[2]
            pct_change = row_values[3]
            lots_change = row_values[4]
            details_str = row_values[5]

            header = Text.assemble(
                ("Period: ", "bold #a6adc8"),
                period,
                ("  |  ", "dim"),
                ("Stock: ", "bold #a6adc8"),
                stock,
                ("  |  ", "dim"),
                ("Investor: ", "bold #a6adc8"),
                investor,
            )

            details_plain = details_str.plain if isinstance(details_str, Text) else str(details_str)
            prev_part, curr_part = "—", "—"
            if "|" in details_plain:
                parts = details_plain.split("|")
                prev_part = parts[0].replace("Prev:", "").strip()
                curr_part = parts[1].replace("Curr:", "").strip()

            grid = Table.grid(expand=False, padding=(0, 4))
            grid.add_column()
            grid.add_column()
            grid.add_column()

            sub1 = Table.grid(padding=(0, 1))
            sub1.add_column(style="bold #a6adc8", justify="right", no_wrap=True)
            sub1.add_column(style="default", no_wrap=True)
            sub1.add_row("Prev Shares:", prev_part)
            try:
                prev_val = float(prev_part.replace(",", ""))
                prev_lot_str = f"{prev_val / 100.0:,.2f}"
            except Exception:
                prev_lot_str = "—"
            sub1.add_row("Prev Lot:", prev_lot_str)

            sub2 = Table.grid(padding=(0, 1))
            sub2.add_column(style="bold #a6adc8", justify="right", no_wrap=True)
            sub2.add_column(style="default", no_wrap=True)
            sub2.add_row("Curr Shares:", curr_part)
            try:
                curr_val = float(curr_part.replace(",", ""))
                curr_lot_str = f"{curr_val / 100.0:,.2f}"
            except Exception:
                curr_lot_str = "—"
            sub2.add_row("Curr Lot:", curr_lot_str)

            sub3 = Table.grid(padding=(0, 1))
            sub3.add_column(style="bold #a6adc8", justify="right", no_wrap=True)
            sub3.add_column(style="default", no_wrap=True)
            sub3.add_row("Lots Change:", lots_change)
            sub3.add_row("% Change:", pct_change)

            grid.add_row(sub1, sub2, sub3)

            content = Group(header, Text(""), grid)
            detail.update(content)
