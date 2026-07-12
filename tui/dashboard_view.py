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
    DashboardView {
        padding: 0 1;
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    #dashboard-container {
        layout: vertical;
        height: 100%;
        background: $bg-black;
    }

    .title-label {
        text-style: bold;
        color: $primary-text;
        margin-top: 1;
    }

    .subtitle-label {
        color: $secondary-text;
        margin-bottom: 1;
    }

    Input {
        background: $bg-black;
        color: $primary-text;
        border: solid $border;
    }

    Input:focus {
        border: solid $accent;
        color: $accent;
    }

    #dashboard-tabs {
        margin-top: 1;
        background: $bg-black;
        color: $primary-text;
    }

    Tab {
        background: $bg-black;
        color: $primary-text;
    }

    Tab.-active {
        color: $accent;
        text-style: bold;
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
        background: $bg-black;
        color: $primary-text;
        margin-bottom: 1;
        scrollbar-background: $background;
        scrollbar-background-hover: $background;
        scrollbar-background-active: $background;
        scrollbar-color: $primary;
        scrollbar-color-hover: $accent;
        scrollbar-color-active: $accent;
        scrollbar-corner-color: $background;
    }

    DataTable:focus {
        border: round $accent;
        background-tint: transparent;
    }

    DataTable > .datatable--header {
        color: $secondary-text;
        background: $bg-black;
        text-style: bold;
    }

    DataTable > .datatable--header-hover {
        background: #222222;
    }

    DataTable > .datatable--header-cursor {
        background: $accent;
        color: $bg-black;
    }

    DataTable > .datatable--fixed {
        background: $bg-black;
        color: $secondary-text;
    }

    DataTable > .datatable--odd-row {
        background: $bg-black;
    }

    DataTable > .datatable--even-row {
        background: $bg-black;
    }

    DataTable > .datatable--hover {
        background: #222222;
    }

    DataTable > .datatable--cursor {
        background: #222222;
        text-style: bold;
    }

    DataTable:focus > .datatable--cursor {
        background: #333333;
        text-style: bold;
    }

    DataTable > .datatable--fixed-cursor {
        background: #222222;
    }

    DataTable:focus > .datatable--fixed-cursor {
        background: #333333;
    }

    #dashboard-detail {
        border: round $border;
        background: $bg-black;
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
        self.query_one("#db-title", Label).update(title_text.upper())
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
            diff_str = f"[#00FF00]+{diff_val:,.0f}[/#00FF00]" if diff_val > 0 else f"[#FF0000]{diff_val:,.0f}[/#FF0000]"

            table_changes.add_row(
                Text.from_markup(str(r["SHARE_CODE"])),
                Text.from_markup(str(r["INVESTOR_NAME"])),
                Text.from_markup(f"[#FFFF00]{r['TOTAL_HOLDING_SHARES_prev']:,.0f}[/#FFFF00]"),
                Text.from_markup(f"[#FFFF00]{format_lot_value(float(r['TOTAL_HOLDING_SHARES_prev']))}[/#FFFF00]"),
                Text.from_markup(f"[#FFFF00]{r['TOTAL_HOLDING_SHARES_curr']:,.0f}[/#FFFF00]"),
                Text.from_markup(f"[#FFFF00]{format_lot_value(float(r['TOTAL_HOLDING_SHARES_curr']))}[/#FFFF00]"),
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
                    Text.from_markup(f"[#FFFF00]{r['TOTAL_HOLDING_SHARES_curr']:,.0f}[/#FFFF00]"),
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
        detail.update(Text.from_markup("[#FFA028]Highlight a row in the table above to see details here...[/#FFA028]"))

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

            stock_text = stock.plain if isinstance(stock, Text) else str(stock)
            investor_text = investor.plain if isinstance(investor, Text) else str(investor)

            header = Text.assemble(
                ("Stock: ", "bold #FFA028"),
                Text(stock_text, style="bold #FFFFFF"),
                ("  |  ", "bold #45475a"),
                ("Investor: ", "bold #FFA028"),
                Text(investor_text, style="bold #FFFFFF"),
            )

            grid = Table.grid(expand=False, padding=(0, 4))
            grid.add_column()
            grid.add_column()
            grid.add_column()

            sub1 = Table.grid(padding=(0, 1))
            sub1.add_column(style="bold #FFA028", justify="right", no_wrap=True)
            sub1.add_column(style="bold #FFFF00", no_wrap=True)
            sub1.add_row("Prev Shares:", prev_shares.plain if isinstance(prev_shares, Text) else str(prev_shares))
            sub1.add_row("Prev Lot:", prev_lot.plain if isinstance(prev_lot, Text) else str(prev_lot))

            sub2 = Table.grid(padding=(0, 1))
            sub2.add_column(style="bold #FFA028", justify="right", no_wrap=True)
            sub2.add_column(style="bold #FFFF00", no_wrap=True)
            sub2.add_row("Curr Shares:", curr_shares.plain if isinstance(curr_shares, Text) else str(curr_shares))
            sub2.add_row("Curr Lot:", curr_lot.plain if isinstance(curr_lot, Text) else str(curr_lot))

            sub3 = Table.grid(padding=(0, 1))
            sub3.add_column(style="bold #FFA028", justify="right", no_wrap=True)
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
                ("Stock: ", "bold #FFA028"),
                Text(stock.plain if isinstance(stock, Text) else str(stock), style="bold #FFFFFF"),
                ("  |  ", "bold #45475a"),
                ("Holding Shares: ", "bold #FFA028"),
                Text(shares.plain if isinstance(shares, Text) else str(shares), style="bold #FFFF00"),
            )

            grid = Table.grid(expand=False, padding=(0, 4))
            grid.add_column()
            grid.add_column()

            sub1 = Table.grid(padding=(0, 1))
            sub1.add_column(style="bold #FFA028", justify="right", no_wrap=True)
            sub1.add_column(style="bold #FFFFFF")
            sub1.add_row("Previous Name:", prev_name.plain if isinstance(prev_name, Text) else str(prev_name))

            sub2 = Table.grid(padding=(0, 1))
            sub2.add_column(style="bold #FFA028", justify="right", no_wrap=True)
            sub2.add_column(style="bold #FFFFFF")
            sub2.add_row("Current Name:", curr_name.plain if isinstance(curr_name, Text) else str(curr_name))

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
