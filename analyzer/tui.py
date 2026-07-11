"""Textual TUI for IDX shareholder data comparison."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, ClassVar

import pandas as pd
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Collapsible,
    ContentSwitcher,
    DataTable,
    Footer,
    Input,
    Label,
    LoadingIndicator,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from analyzer.data_loader import load_excel_file, parse_filename_date
from analyzer.entity_resolver import run_comparison
from analyzer.reporter import (
    format_change_pct,
    format_lot_value,
    format_net_change_lot,
)


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


class LoadingView(Static):
    """A view showing a spinner and a message while loading."""

    def compose(self) -> ComposeResult:
        with Vertical(id="loading-container"):
            yield LoadingIndicator()
            yield Label("Loading shareholder reports...", id="loading-label")

    def update_message(self, message: str) -> None:
        """Update the loading message."""
        self.query_one("#loading-label", Label).update(message)


class DashboardView(Static):
    """Widget for showing a specific period comparison dashboard."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.title_text = ""
        self.subtitle_text = ""
        self.active_stocks = 0
        self.entries = pd.DataFrame()
        self.exits = pd.DataFrame()
        self.increases = pd.DataFrame()
        self.decreases = pd.DataFrame()
        self.transfers = pd.DataFrame()
        self.combined_changes = pd.DataFrame()

    def compose(self) -> ComposeResult:
        with Vertical(id="dashboard-container"):
            yield Label(id="db-title", classes="title-label")
            yield Label(id="db-subtitle", classes="subtitle-label")

            yield Input(placeholder="🔍 Search investor or stock code in this period...", id="dashboard-search")

            with VerticalScroll(id="tables-scroll"):
                yield Label("CONSOLIDATED SHAREHOLDER CHANGES", classes="section-header")
                yield DataTable(id="changes-table")
                yield Label("RESOLVED NAME CHANGES (NO NET CHANGE)", classes="section-header", id="transfers-label")
                yield DataTable(id="transfers-table")

    def on_mount(self) -> None:
        table_changes = self.query_one("#changes-table", DataTable)
        table_changes.cursor_type = "row"
        table_changes.add_columns(
            "Stock",
            "Investor Name",
            "Prev Shares",
            "Prev Lot",
            "Curr Shares",
            "Curr Lot",
            "Net Change",
            "Net Change Lot",
            "% Change",
        )

        table_trans = self.query_one("#transfers-table", DataTable)
        table_trans.cursor_type = "row"
        table_trans.add_columns("Stock", "Previous Name Format", "Current Name Format", "Holding Shares")

    def update_data(
        self,
        title_text: str,
        subtitle_text: str,
        active_stocks: int,
        entries: pd.DataFrame,
        exits: pd.DataFrame,
        increases: pd.DataFrame,
        decreases: pd.DataFrame,
        transfers: pd.DataFrame,
    ) -> None:
        """Update the dashboard data and refresh tables."""
        self.title_text = title_text
        self.subtitle_text = subtitle_text
        self.active_stocks = active_stocks
        self.entries = entries
        self.exits = exits
        self.increases = increases
        self.decreases = decreases
        self.transfers = transfers

        # Build consolidated changes
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
            self.combined_changes = (
                pd.concat(dfs_to_combine).sort_values(by="diff", ascending=False).reset_index(drop=True)
            )
        else:
            self.combined_changes = pd.DataFrame()

        # Update metadata labels
        self.query_one("#db-title", Label).update(title_text)
        self.query_one("#db-subtitle", Label).update(subtitle_text)

        # Reset search input text
        search_input = self.query_one("#dashboard-search", Input)
        search_input.value = ""

        # Populate tables
        self.populate_tables()

    def populate_tables(self, query: str = "") -> None:
        """Filter and populate changes and transfers tables."""
        table_changes = self.query_one("#changes-table", DataTable)
        table_changes.clear()

        filtered_changes = self.combined_changes
        if query.strip() and not filtered_changes.empty:
            needle = query.strip().lower()
            mask = filtered_changes["SHARE_CODE"].astype(str).str.lower().str.contains(
                needle, na=False
            ) | filtered_changes["INVESTOR_NAME"].astype(str).str.lower().str.contains(needle, na=False)
            filtered_changes = filtered_changes[mask]

        for _, r in filtered_changes.iterrows():
            diff_val = float(r["diff"])
            diff_str = f"[green]+{diff_val:,.0f}[/green]" if diff_val > 0 else f"[red]{diff_val:,.0f}[/red]"

            table_changes.add_row(
                Text.from_markup(str(r["SHARE_CODE"])),
                Text.from_markup(str(r["INVESTOR_NAME"])),
                Text.from_markup(f"{r['TOTAL_HOLDING_SHARES_prev']:,.0f}"),
                Text.from_markup(format_lot_value(float(r["TOTAL_HOLDING_SHARES_prev"]))),
                Text.from_markup(f"{r['TOTAL_HOLDING_SHARES_curr']:,.0f}"),
                Text.from_markup(format_lot_value(float(r["TOTAL_HOLDING_SHARES_curr"]))),
                Text.from_markup(diff_str),
                Text.from_markup(format_net_change_lot(diff_val)),
                Text.from_markup(
                    format_change_pct(float(r["TOTAL_HOLDING_SHARES_prev"]), float(r["TOTAL_HOLDING_SHARES_curr"]))
                ),
            )

        # Name format changes table
        table_trans = self.query_one("#transfers-table", DataTable)
        table_trans.clear()

        transfers_no_diff = pd.DataFrame()
        if not self.transfers.empty:
            transfers_no_diff = self.transfers[self.transfers["diff"] == 0]

        transfers_label = self.query_one("#transfers-label", Label)

        if transfers_no_diff.empty:
            transfers_label.display = False
            table_trans.display = False
        else:
            transfers_label.display = True
            table_trans.display = True

            if query.strip():
                needle = query.strip().lower()
                mask = (
                    transfers_no_diff["SHARE_CODE"].astype(str).str.lower().str.contains(needle, na=False)
                    | transfers_no_diff["INVESTOR_NAME_prev"].astype(str).str.lower().str.contains(needle, na=False)
                    | transfers_no_diff["INVESTOR_NAME_curr"].astype(str).str.lower().str.contains(needle, na=False)
                )
                transfers_no_diff = transfers_no_diff[mask]

            top_transfers = transfers_no_diff.sort_values(by="TOTAL_HOLDING_SHARES_curr", ascending=False)
            for _, r in top_transfers.iterrows():
                table_trans.add_row(
                    Text.from_markup(str(r["SHARE_CODE"])),
                    Text.from_markup(str(r["INVESTOR_NAME_prev"])),
                    Text.from_markup(str(r["INVESTOR_NAME_curr"])),
                    Text.from_markup(f"{r['TOTAL_HOLDING_SHARES_curr']:,.0f}"),
                )

    @on(Input.Changed, "#dashboard-search")
    def handle_search_change(self, event: Input.Changed) -> None:
        """Handle search input key changes in real time."""
        self.populate_tables(event.value)


class CompareAllView(Static):
    """View showing all comparisons stacked using Collapsible widgets."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.comparisons_data: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="compare-all-scroll"):
            yield Label("ALL HISTORICAL PERIODS COMPARISON", classes="section-header")
            yield Container(id="collapsible-container")

    def update_data(self, comparisons_data: list[dict[str, Any]]) -> None:
        """Update comparisons data and rebuild Collapsibles."""
        self.comparisons_data = comparisons_data
        container = self.query_one("#collapsible-container")

        # Remove existing children safely
        for child in list(container.children):
            child.remove()

        if not comparisons_data:
            container.mount(Label("No comparison data loaded.", id="compare-all-empty"))
            return

        for idx, data in enumerate(comparisons_data):
            title = f"📅 {data['m1']} {data['dt1'].year} ➔ {data['m2']} {data['dt2'].year}"

            combined = data["combined_changes"]

            table: DataTable[Any] = DataTable(id=f"all-table-{idx}")
            table.cursor_type = "row"
            table.add_columns(
                "Stock",
                "Investor Name",
                "Prev Shares",
                "Prev Lot",
                "Curr Shares",
                "Curr Lot",
                "Net Change",
                "Net Change Lot",
                "% Change",
            )

            # Add top rows
            for _, r in combined.iterrows():
                diff_val = float(r["diff"])
                diff_str = f"[green]+{diff_val:,.0f}[/green]" if diff_val > 0 else f"[red]{diff_val:,.0f}[/red]"
                table.add_row(
                    Text.from_markup(str(r["SHARE_CODE"])),
                    Text.from_markup(str(r["INVESTOR_NAME"])),
                    Text.from_markup(f"{r['TOTAL_HOLDING_SHARES_prev']:,.0f}"),
                    Text.from_markup(format_lot_value(float(r["TOTAL_HOLDING_SHARES_prev"]))),
                    Text.from_markup(f"{r['TOTAL_HOLDING_SHARES_curr']:,.0f}"),
                    Text.from_markup(format_lot_value(float(r["TOTAL_HOLDING_SHARES_curr"]))),
                    Text.from_markup(diff_str),
                    Text.from_markup(format_net_change_lot(diff_val)),
                    Text.from_markup(
                        format_change_pct(float(r["TOTAL_HOLDING_SHARES_prev"]), float(r["TOTAL_HOLDING_SHARES_curr"]))
                    ),
                )

            collapsible = Collapsible(
                table,
                title=title,
                id=f"collapse-{idx}",
                collapsed=(idx > 0),  # Expand only the first (newest) transition by default
            )
            container.mount(collapsible)


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
        # Use simple type checking casting
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


class IDXAnalyzerApp(App[int]):
    """Main Textual TUI Application for IDX One Percent Shareholder Analyzer."""

    CSS_PATH: ClassVar[str] = "styles.tcss"
    BINDINGS: ClassVar[list[Any]] = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Toggle Dark"),
        ("s", "focus_search", "Focus Search"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.data_dir: str = ""
        self.files: list[str] = []
        self.sorted_files: list[tuple[datetime, str, str]] = []
        self.transitions: list[tuple[int, tuple[datetime, str, str], tuple[datetime, str, str]]] = []
        self.loaded_dfs: dict[str, pd.DataFrame] = {}
        self.loading_in_progress: set[str] = set()
        self.current_view: str = "loading"

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static(id="sidebar-spacer")
                yield OptionList(id="sidebar-menu")
            with ContentSwitcher(id="content-area", initial="loading"):
                yield LoadingView(id="loading")
                yield DashboardView(id="dashboard")
                yield CompareAllView(id="compare_all")
                yield GlobalSearchView(id="global_search")
        yield Footer(id="footer")

    def on_mount(self) -> None:
        self.title = "IDX One Percent Shareholder Analyzer"
        self.theme = "textual-dark"

        # Locate project paths
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(project_dir, "onepercent-data")
        if not os.path.exists(self.data_dir):
            self.data_dir = "./onepercent-data"

        if not os.path.exists(self.data_dir):
            self.notify("Error: 'onepercent-data' directory not found.", severity="error")
            self.exit(1)
            return

        self.files = [f for f in os.listdir(self.data_dir) if f.endswith(".xlsx")]
        if len(self.files) < 2:
            self.notify("Error: Need at least 2 Excel files to perform comparisons.", severity="error")
            self.exit(1)
            return

        # Parse and sort chronologically
        self.sorted_files = []
        for f in self.files:
            dt, month_name = parse_filename_date(f)
            if dt != datetime.min:
                self.sorted_files.append((dt, f, month_name))
        self.sorted_files.sort(key=lambda x: x[0])

        # Build consecutive transitions
        self.transitions = []
        for idx in range(len(self.sorted_files) - 1):
            self.transitions.append((idx, self.sorted_files[idx], self.sorted_files[idx + 1]))
        # Reverse to show newest first
        self.transitions.reverse()

        self.populate_sidebar_menu()

        # Start background preloading
        self.load_all_files_background()

        # Select first transition by default
        if self.transitions:
            self.select_transition(0)

    def populate_sidebar_menu(self) -> None:
        """Build the sidebar menu items."""
        option_list = self.query_one("#sidebar-menu", OptionList)
        option_list.clear_options()

        # Add comparisons list
        for i, (_, (_dt1, _, m1), (dt2, _, m2)) in enumerate(self.transitions):
            label = f"{m2} {dt2.year} (from {m1})"
            option_list.add_option(Option(label, id=f"t_{i}"))

        option_list.add_option(None)
        option_list.add_option(Option("Compare All Periods", id="action_all"))
        option_list.add_option(Option("Global Search", id="action_search"))
        option_list.add_option(Option("Exit App", id="action_exit"))

    def show_view(self, view_name: str) -> None:
        """Switch current content view."""
        self.current_view = view_name
        switcher = self.query_one("#content-area", ContentSwitcher)
        switcher.current = view_name

    def update_loading_message(self, message: str) -> None:
        """Update loading indicator description."""
        try:
            self.query_one("#loading", LoadingView).update_message(message)
        except Exception:
            pass

    def load_file_sync(self, filename: str) -> pd.DataFrame:
        """Read Excel file cleanly. Concurrency-safe for background worker."""
        if filename in self.loaded_dfs:
            return self.loaded_dfs[filename]

        while filename in self.loading_in_progress:
            time.sleep(0.1)
            if filename in self.loaded_dfs:
                return self.loaded_dfs[filename]

        self.loading_in_progress.add(filename)
        try:
            filepath = os.path.join(self.data_dir, filename)
            df = load_excel_file(filepath)
            self.loaded_dfs[filename] = df
            return df
        finally:
            self.loading_in_progress.discard(filename)

    @work(thread=True)
    def load_transition_files(self, idx: int, file1: str, file2: str) -> None:
        """Worker thread to load files and compare them, updating the dashboard."""
        self.call_from_thread(self.show_view, "loading")
        self.call_from_thread(self.update_loading_message, f"Loading periods data...\n{file1} ➔ {file2}")

        df1 = self.load_file_sync(file1)
        df2 = self.load_file_sync(file2)

        # Run resolution and comparisons
        entries, exits, increases, decreases, transfers, new_stocks, removed_stocks = run_comparison(df1, df2)

        # Setup dashboard details
        dt1, _, m1 = self.transitions[idx][1]
        dt2, _, m2 = self.transitions[idx][2]
        title_text = f"{m1} {dt1.year} ➔ {m2} {dt2.year}"
        subtitle_text = f"Comparing {file1} and {file2}"
        active_stocks = len(df2["SHARE_CODE"].dropna().unique())

        self.call_from_thread(
            self.display_dashboard,
            title_text,
            subtitle_text,
            active_stocks,
            entries,
            exits,
            increases,
            decreases,
            transfers,
        )

    def display_dashboard(
        self,
        title_text: str,
        subtitle_text: str,
        active_stocks: int,
        entries: pd.DataFrame,
        exits: pd.DataFrame,
        increases: pd.DataFrame,
        decreases: pd.DataFrame,
        transfers: pd.DataFrame,
    ) -> None:
        """Switch view to dashboard and populate values (must run on main thread)."""
        self.show_view("dashboard")
        dashboard = self.query_one("#dashboard", DashboardView)
        dashboard.update_data(
            title_text=title_text,
            subtitle_text=subtitle_text,
            active_stocks=active_stocks,
            entries=entries,
            exits=exits,
            increases=increases,
            decreases=decreases,
            transfers=transfers,
        )

    @work(thread=True)
    def load_all_files_background(self) -> None:
        """Worker to load all Excel sheets in the background."""
        all_files = [item[1] for item in self.sorted_files]
        for f in all_files:
            if f not in self.loaded_dfs:
                self.load_file_sync(f)
                # Refresh search UI if currently visible to show new results reactively
                self.call_from_thread(self._refresh_global_search_if_active)

    def _refresh_global_search_if_active(self) -> None:
        if self.current_view == "global_search":
            try:
                search_view = self.query_one("#global_search", GlobalSearchView)
                input_val = self.query_one("#global-search-input", Input).value
                if input_val:
                    search_view.perform_search(input_val)
            except Exception:
                pass

    @work(thread=True)
    def load_and_compare_all(self) -> None:
        """Worker thread to run all comparisons and populate CompareAll view."""
        self.call_from_thread(self.show_view, "loading")
        self.call_from_thread(self.update_loading_message, "Comparing all periods... please wait")

        comparisons_data = []
        for _idx, period1, period2 in sorted(self.transitions, key=lambda x: x[0]):
            dt1, file1, m1 = period1
            dt2, file2, m2 = period2

            df1 = self.load_file_sync(file1)
            df2 = self.load_file_sync(file2)

            entries, exits, increases, decreases, transfers, new_stocks, removed_stocks = run_comparison(df1, df2)

            dfs_to_combine = []
            if not entries.empty:
                dfs_to_combine.append(
                    entries[
                        [
                            "SHARE_CODE",
                            "INVESTOR_NAME",
                            "TOTAL_HOLDING_SHARES_prev",
                            "TOTAL_HOLDING_SHARES_curr",
                            "diff",
                        ]
                    ]
                )
            if not increases.empty:
                dfs_to_combine.append(
                    increases[
                        [
                            "SHARE_CODE",
                            "INVESTOR_NAME",
                            "TOTAL_HOLDING_SHARES_prev",
                            "TOTAL_HOLDING_SHARES_curr",
                            "diff",
                        ]
                    ]
                )
            if not transfers.empty:
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
                        [
                            "SHARE_CODE",
                            "INVESTOR_NAME",
                            "TOTAL_HOLDING_SHARES_prev",
                            "TOTAL_HOLDING_SHARES_curr",
                            "diff",
                        ]
                    ]
                )
            if not exits.empty:
                dfs_to_combine.append(
                    exits[
                        [
                            "SHARE_CODE",
                            "INVESTOR_NAME",
                            "TOTAL_HOLDING_SHARES_prev",
                            "TOTAL_HOLDING_SHARES_curr",
                            "diff",
                        ]
                    ]
                )

            if dfs_to_combine:
                combined_changes = (
                    pd.concat(dfs_to_combine).sort_values(by="diff", ascending=False).reset_index(drop=True)
                )
            else:
                combined_changes = pd.DataFrame()

            comparisons_data.append(
                {
                    "dt1": dt1,
                    "file1": file1,
                    "m1": m1,
                    "dt2": dt2,
                    "file2": file2,
                    "m2": m2,
                    "combined_changes": combined_changes,
                }
            )

        comparisons_data.reverse()
        self.call_from_thread(self.display_compare_all, comparisons_data)

    def display_compare_all(self, comparisons_data: list[dict[str, Any]]) -> None:
        """Show CompareAll view (runs on main thread)."""
        self.show_view("compare_all")
        compare_all = self.query_one("#compare_all", CompareAllView)
        compare_all.update_data(comparisons_data)

    def select_transition(self, idx: int) -> None:
        """Load files and show comparison for selected transition index."""
        if idx < 0 or idx >= len(self.transitions):
            return
        _, period1, period2 = self.transitions[idx]
        file1 = period1[1]
        file2 = period2[1]
        self.load_transition_files(idx, file1, file2)

    def select_compare_all(self) -> None:
        """Trigger loading and show CompareAll view."""
        self.load_and_compare_all()

    def select_global_search(self) -> None:
        """Show GlobalSearch view."""
        self.show_view("global_search")
        try:
            self.query_one("#global-search-input", Input).focus()
        except Exception:
            pass

    def run_global_search(self, query: str) -> list[tuple[str, pd.DataFrame]]:
        """Run keyword search over all loaded DataFrames."""
        previous_periods = {}
        sorted_file_names = [item[1] for item in self.sorted_files]
        for idx, file_name in enumerate(sorted_file_names):
            if idx == 0:
                continue
            previous_periods[file_name] = self.loaded_dfs.get(sorted_file_names[idx - 1], pd.DataFrame())

        return search_dataframes(self.loaded_dfs, query, previous_periods=previous_periods)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle Sidebar option selection."""
        option_id = event.option_id
        if option_id is None:
            return

        if option_id.startswith("t_"):
            idx = int(option_id.split("_")[1])
            self.select_transition(idx)
        elif option_id == "action_all":
            self.select_compare_all()
        elif option_id == "action_search":
            self.select_global_search()
        elif option_id == "action_exit":
            self.exit()

    def action_focus_search(self) -> None:
        """Focus the search input in the active view."""
        if self.current_view == "dashboard":
            try:
                self.query_one("#dashboard-search", Input).focus()
            except Exception:
                pass
        elif self.current_view == "global_search":
            try:
                self.query_one("#global-search-input", Input).focus()
            except Exception:
                pass

    def action_toggle_dark(self) -> None:
        """Toggle dark mode theme."""
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"


if __name__ == "__main__":
    app = IDXAnalyzerApp()
    app.run()
