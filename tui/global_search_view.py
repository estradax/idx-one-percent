"""Global search view and search helper for historical reports."""

from __future__ import annotations

import pandas as pd
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Input, Label, Static


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

    def compose(self) -> ComposeResult:
        with Vertical(id="global-search-container"):
            with Vertical(classes="title-card"):
                yield Label("Global Shareholder Data Search", classes="title-label")
                yield Label("Search for any investor name or stock code across all periods", classes="subtitle-label")

            yield Input(placeholder="🔍 Type keyword and press Enter to search...", id="global-search-input")
            yield Label("Enter a search term above.", id="global-search-status")

            yield DataTable(id="global-search-table")

    def on_mount(self) -> None:
        table = self.query_one("#global-search-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Period", "Stock", "Investor", "Change %", "Lots Change", "Details")

    def perform_search(self, query: str) -> None:
        """Run global search across loaded dfs and populate search table."""
        table = self.query_one("#global-search-table", DataTable)
        table.clear()

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

        status_label.update(
            Text.from_markup(f"[green]Found {row_count} matches across all loaded periods.[/green]{warning_msg}")
        )

    @on(Input.Submitted, "#global-search-input")
    def handle_global_search_submit(self, event: Input.Submitted) -> None:
        """Handle search submit (pressing Enter)."""
        self.perform_search(event.value)

    @on(Input.Changed, "#global-search-input")
    def handle_global_search_change(self, event: Input.Changed) -> None:
        """Handle real-time search typing."""
        if len(event.value) >= 2 or not event.value:
            self.perform_search(event.value)
