"""Dashboard view for consecutive period comparisons."""

from __future__ import annotations

from typing import Any

import pandas as pd
from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import ContentSwitcher, DataTable, Input, Label, Static, Tab, Tabs
from textual.widgets.data_table import RowKey

from analyzer.reporter import (
    format_change_pct,
    format_lot_value,
    format_net_change_lot,
)


class DashboardView(Static):
    """Widget for showing a specific period comparison dashboard."""

    DEFAULT_CSS = """
    $accent: #89b4fa;
    $border: #45475a;
    $content-bg: #1e1e2e;
    $title-color: #f5c2e7;
    $subtle: #a6adc8;

    DashboardView {
        padding: 0 1;
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    #dashboard-container {
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

    #dashboard-search {
        border: solid $border;
    }

    #dashboard-search:focus {
        border: solid $accent;
    }

    #dashboard-tabs {
        margin-top: 1;
    }

    #dashboard-switcher {
        height: 1fr;
    }

    #dashboard-switcher DataTable {
        height: 100%;
        max-height: 100%;
        margin-bottom: 0;
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

    #dashboard-detail {
        border: round $border;
        background: $content-bg;
        height: 7;
        padding: 0 2;
        margin-top: 1;
    }
    """

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

            yield Input(placeholder="Search investor or stock code in this period...", id="dashboard-search")

            yield Tabs(
                Tab("Consolidated Shareholder Changes", id="tab-changes"),
                Tab("Resolved Name Changes (No Net Change)", id="tab-transfers"),
                id="dashboard-tabs",
            )

            with ContentSwitcher(id="dashboard-switcher", initial="changes-table"):
                yield DataTable(id="changes-table")
                yield DataTable(id="transfers-table")

            yield Static(id="dashboard-detail")

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

        detail_box = self.query_one("#dashboard-detail", Static)
        detail_box.border_title = "Details"

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

        tabs = self.query_one("#dashboard-tabs", Tabs)

        if transfers_no_diff.empty:
            tabs.display = False
            tabs.active = "tab-changes"
            self.query_one("#dashboard-switcher", ContentSwitcher).current = "changes-table"
        else:
            tabs.display = True

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

        # Update detail view based on active tab
        tabs = self.query_one("#dashboard-tabs", Tabs)
        active_tab = tabs.active if tabs else "tab-changes"
        if active_tab == "tab-changes":
            self.update_detail_view(self.query_one("#changes-table", DataTable))
        elif active_tab == "tab-transfers":
            self.update_detail_view(self.query_one("#transfers-table", DataTable))

    @on(Tabs.TabActivated, "#dashboard-tabs")
    def handle_tab_activated(self, event: Tabs.TabActivated) -> None:
        """Handle dashboard tab switches."""
        switcher = self.query_one("#dashboard-switcher", ContentSwitcher)
        if event.tab and event.tab.id == "tab-changes":
            switcher.current = "changes-table"
            self.update_detail_view(self.query_one("#changes-table", DataTable))
        elif event.tab and event.tab.id == "tab-transfers":
            switcher.current = "transfers-table"
            self.update_detail_view(self.query_one("#transfers-table", DataTable))

    @on(Input.Changed, "#dashboard-search")
    def handle_search_change(self, event: Input.Changed) -> None:
        """Handle search input key changes in real time."""
        self.populate_tables(event.value)

    @on(DataTable.RowHighlighted)
    def handle_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlighted in changes-table or transfers-table."""
        tabs = self.query_one("#dashboard-tabs", Tabs)
        active_tab = tabs.active if tabs else "tab-changes"
        active_table_id = "changes-table" if active_tab == "tab-changes" else "transfers-table"

        if event.data_table.id == active_table_id:
            self.update_detail_view(event.data_table, row_key=event.row_key)

    def reset_detail_view(self) -> None:
        """Reset the detail view to its default state."""
        detail = self.query_one("#dashboard-detail", Static)
        detail.update(Text.from_markup("[dim]Highlight a row in the table above to see details here...[/dim]"))

    def update_detail_view(
        self,
        data_table: DataTable[Any],
        row_key: RowKey | None = None,
        row_index: int | None = None,
    ) -> None:
        """Update the detail view with the contents of the highlighted row."""
        detail = self.query_one("#dashboard-detail", Static)

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

        columns = data_table.ordered_columns

        # Build custom styled layout for each table type to make it look premium
        if data_table.id == "changes-table" and len(row_values) >= 9:
            stock = row_values[0]
            investor = row_values[1]
            prev_shares = row_values[2]
            prev_lot = row_values[3]
            curr_shares = row_values[4]
            curr_lot = row_values[5]
            net_change = row_values[6]
            net_change_lot = row_values[7]
            pct_change = row_values[8]

            header = Text.assemble(
                ("Stock: ", "bold #a6adc8"), stock, ("  |  ", "dim"), ("Investor: ", "bold #a6adc8"), investor
            )

            grid = Table.grid(expand=False, padding=(0, 4))
            grid.add_column()
            grid.add_column()
            grid.add_column()

            sub1 = Table.grid(padding=(0, 1))
            sub1.add_column(style="bold #a6adc8", justify="right", no_wrap=True)
            sub1.add_column(style="default", no_wrap=True)
            sub1.add_row("Prev Shares:", prev_shares)
            sub1.add_row("Prev Lot:", prev_lot)

            sub2 = Table.grid(padding=(0, 1))
            sub2.add_column(style="bold #a6adc8", justify="right", no_wrap=True)
            sub2.add_column(style="default", no_wrap=True)
            sub2.add_row("Curr Shares:", curr_shares)
            sub2.add_row("Curr Lot:", curr_lot)

            sub3 = Table.grid(padding=(0, 1))
            sub3.add_column(style="bold #a6adc8", justify="right", no_wrap=True)
            sub3.add_column(style="default", no_wrap=True)
            sub3.add_row("Net Change:", net_change)
            sub3.add_row("Net Change Lot:", net_change_lot)
            sub3.add_row("% Change:", pct_change)

            grid.add_row(sub1, sub2, sub3)

            content = Group(header, Text(""), grid)
            detail.update(content)

        elif data_table.id == "transfers-table" and len(row_values) >= 4:
            stock = row_values[0]
            prev_name = row_values[1]
            curr_name = row_values[2]
            shares = row_values[3]

            header = Text.assemble(
                ("Stock: ", "bold #a6adc8"), stock, ("  |  ", "dim"), ("Holding Shares: ", "bold #a6adc8"), shares
            )

            grid = Table.grid(expand=False, padding=(0, 4))
            grid.add_column()
            grid.add_column()

            sub1 = Table.grid(padding=(0, 1))
            sub1.add_column(style="bold #a6adc8", justify="right", no_wrap=True)
            sub1.add_column(style="default")
            sub1.add_row("Previous Name:", prev_name)

            sub2 = Table.grid(padding=(0, 1))
            sub2.add_column(style="bold #a6adc8", justify="right", no_wrap=True)
            sub2.add_column(style="default")
            sub2.add_row("Current Name:", curr_name)

            grid.add_row(sub1, sub2)

            content = Group(header, Text(""), grid)
            detail.update(content)

        else:
            # Fallback for any other table structure
            grid = Table.grid(expand=True, padding=(0, 2))
            pairs = []
            for col, val in zip(columns, row_values, strict=True):
                label = col.label.plain if isinstance(col.label, Text) else str(col.label)
                pairs.append((label, val))

            num_pairs = len(pairs)
            cols_count = 3 if num_pairs >= 6 else 2

            for _ in range(cols_count):
                grid.add_column(style="bold #a6adc8", justify="right")
                grid.add_column(style="default", justify="left")

            for i in range(0, num_pairs, cols_count):
                row_cells = []
                for j in range(cols_count):
                    if i + j < num_pairs:
                        label, val = pairs[i + j]
                        row_cells.extend([f"{label}:", val])
                    else:
                        row_cells.extend(["", ""])
                grid.add_row(*row_cells)

            detail.update(grid)
