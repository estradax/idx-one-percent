"""Compare All view showing all consecutive comparisons."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd
from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import ContentSwitcher, DataTable, Input, Label, Static, Tab, Tabs
from textual.widgets.data_table import RowKey

from analyzer.entity_resolver import normalize_name_sorted_tokens
from analyzer.reporter import (
    format_lot_value,
)

if TYPE_CHECKING:
    from tui.app import IDXAnalyzerApp


class NameResolver:
    """Helper class to build chain of name changes and resolve canonical names."""

    def __init__(self) -> None:
        self.links: dict[tuple[str, str], str] = {}

    def add_link(self, share_code: str, name_prev: str, name_curr: str) -> None:
        self.links[(share_code, name_prev)] = name_curr

    def resolve(self, share_code: str, name: str) -> str:
        visited = {name}
        curr = name
        while (share_code, curr) in self.links:
            next_name = self.links[(share_code, curr)]
            if next_name in visited:  # avoid infinite loops
                break
            curr = next_name
            visited.add(curr)
        return curr


def format_holding_with_change(prev_val: float, curr_val: float, is_first: bool = False) -> str:
    """Format holding and its change compared to the previous period in lots."""
    if is_first:
        if curr_val == 0:
            return "—"
        return f"[#FFFF00]{format_lot_value(curr_val)}[/#FFFF00]"

    if curr_val == 0 and prev_val == 0:
        return "—"

    curr_lots_str = format_lot_value(curr_val)
    prev_lots_str = format_lot_value(prev_val)
    diff_val = curr_val - prev_val
    diff_lots_str = format_lot_value(abs(diff_val))

    if curr_val == 0 and prev_val > 0:
        return f"[#FFFF00]0[/#FFFF00] [#FF0000](-{prev_lots_str})[/#FF0000]"

    if curr_val > 0 and prev_val == 0:
        return f"[#FFFF00]{curr_lots_str}[/#FFFF00] [#00FF00](+{curr_lots_str})[/#00FF00]"

    if diff_val > 0:
        return f"[#FFFF00]{curr_lots_str}[/#FFFF00] [#00FF00](+{diff_lots_str})[/#00FF00]"
    elif diff_val < 0:
        return f"[#FFFF00]{curr_lots_str}[/#FFFF00] [#FF0000](-{diff_lots_str})[/#FF0000]"
    else:
        return f"[#FFFF00]{curr_lots_str}[/#FFFF00]"


class CompareAllView(Static):
    """View showing all comparisons combined in a single dashboard layout without collapsibles."""

    if TYPE_CHECKING:
        app: IDXAnalyzerApp

    DEFAULT_CSS = """
    $primary: #FFA028;
    $accent: #FFFF00;
    $background: #000000;
    $surface: #000000;
    $panel: #000000;
    $text: #FFA028;
    $border: #45475a;
    $bg-black: #000000;
    $primary-text: #FFA028;
    $secondary-text: #FFFFFF;

    CompareAllView {
        padding: 0 1;
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    #compare-all-container {
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
        border: solid #FFFF00;
        color: #FFFF00;
    }

    #compare-all-tabs {
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

    #compare-all-switcher {
        height: 1fr;
    }

    #compare-all-switcher DataTable {
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
        scrollbar-background: #000000;
        scrollbar-background-hover: #000000;
        scrollbar-background-active: #000000;
        scrollbar-color: #FFA028;
        scrollbar-color-hover: #FFFF00;
        scrollbar-color-active: #FFFF00;
        scrollbar-corner-color: #000000;
    }

    DataTable:focus {
        border: round #FFFF00;
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
        background: #FFFF00;
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
        background: #FFA028;
        color: $bg-black;
        text-style: bold;
    }

    DataTable:focus > .datatable--cursor {
        background: #FFFF00;
        color: $bg-black;
        text-style: bold;
    }

    DataTable > .datatable--fixed-cursor {
        background: #FFA028;
        color: $bg-black;
    }

    DataTable:focus > .datatable--fixed-cursor {
        background: #FFFF00;
        color: $bg-black;
    }

    #compare-all-detail {
        border: round $border;
        background: $bg-black;
        height: 12;
        padding: 0 2;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.comparisons_data: list[dict[str, Any]] = []
        self.combined_changes: pd.DataFrame = pd.DataFrame()
        self.combined_transfers: pd.DataFrame = pd.DataFrame()
        self.master_changes: pd.DataFrame = pd.DataFrame()
        self.sorted_files: list[tuple[Any, str, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="compare-all-container"):
            yield Label("ALL HISTORICAL PERIODS COMPARISON", classes="title-label")
            yield Label(
                "Overview of all period-to-period changes",
                classes="subtitle-label",
            )

            yield Input(placeholder="Search investor, stock, or period across all data...", id="compare-all-search")

            yield Tabs(
                Tab("Consolidated Shareholder Changes", id="tab-changes"),
                Tab("Resolved Name Changes (No Net Change)", id="tab-transfers"),
                id="compare-all-tabs",
            )

            with ContentSwitcher(id="compare-all-switcher", initial="changes-table"):
                yield DataTable(id="changes-table")
                yield DataTable(id="transfers-table")

            yield Static(id="compare-all-detail")

    def on_mount(self) -> None:
        table_trans: DataTable[Any] = self.query_one("#transfers-table", DataTable)
        table_trans.cursor_type = "row"
        table_trans.add_columns(
            "Period",
            "Stock",
            "Previous Name Format",
            "Current Name Format",
            "Holding Shares (Shares)",
        )

        detail_box = self.query_one("#compare-all-detail", Static)
        detail_box.border_title = "Details"
        self.reset_detail_view()

    def update_data(self, comparisons_data: list[dict[str, Any]]) -> None:
        """Update comparisons data and rebuild Master DataFrames."""
        self.comparisons_data = comparisons_data

        # Get sorted files list from the app
        self.sorted_files = self.app.sorted_files

        # 1. Build NameResolver from transitions
        resolver = NameResolver()
        for data in reversed(comparisons_data):
            transfers = data.get("transfers", pd.DataFrame())
            if not transfers.empty:
                for _, r in transfers.iterrows():
                    resolver.add_link(
                        str(r["SHARE_CODE"]),
                        str(r["INVESTOR_NAME_prev"]),
                        str(r["INVESTOR_NAME_curr"]),
                    )

        # 2. Build master holdings map
        holdings_map: dict[tuple[str, str], list[float]] = {}
        canonical_names: dict[tuple[str, str], str] = {}

        for t, (_dt, file, _m) in enumerate(self.sorted_files):
            df = self.app.loaded_dfs.get(file, pd.DataFrame())
            if df.empty:
                continue

            # Group by SHARE_CODE and INVESTOR_NAME to get total shares
            grp = df.groupby(["SHARE_CODE", "INVESTOR_NAME"])["TOTAL_HOLDING_SHARES"].sum().reset_index()

            for _, r in grp.iterrows():
                code = str(r["SHARE_CODE"])
                raw_name = str(r["INVESTOR_NAME"])
                shares = float(r["TOTAL_HOLDING_SHARES"])

                # Resolve name to its canonical name
                resolved_name = resolver.resolve(code, raw_name)
                norm_name = normalize_name_sorted_tokens(resolved_name)

                key = (code, norm_name)
                if key not in holdings_map:
                    holdings_map[key] = [0.0] * len(self.sorted_files)
                holdings_map[key][t] = shares

                # Keep the latest name as the canonical name
                canonical_names[key] = resolved_name

        # 3. Create master changes DataFrame
        rows = []
        for (code, norm_name), shares_list in holdings_map.items():
            display_name = canonical_names.get((code, norm_name), norm_name)

            total_change = shares_list[-1] - shares_list[0]

            row_dict = {
                "SHARE_CODE": code,
                "INVESTOR_NAME": display_name,
                "shares_history": shares_list,
                "total_change": total_change,
            }
            rows.append(row_dict)

        self.master_changes = pd.DataFrame(rows)
        if not self.master_changes.empty:
            self.master_changes["abs_change"] = self.master_changes["total_change"].abs()
            self.master_changes = self.master_changes.sort_values(by="abs_change", ascending=False).reset_index(
                drop=True
            )
        else:
            self.master_changes = pd.DataFrame()

        # 4. Build combined transfers DataFrame
        all_trans_list = []
        for data in comparisons_data:
            period_str = f"{data['m1']} {data['dt1'].year} ➔ {data['m2']} {data['dt2'].year}"
            transfers = data.get("transfers", pd.DataFrame())
            if not transfers.empty:
                transfers_no_diff = transfers[transfers["diff"] == 0].copy()
                if not transfers_no_diff.empty:
                    transfers_no_diff["PERIOD"] = period_str
                    all_trans_list.append(transfers_no_diff)

        if all_trans_list:
            self.combined_transfers = pd.concat(all_trans_list).reset_index(drop=True)
        else:
            self.combined_transfers = pd.DataFrame()

        # Reset search input text
        search_input = self.query_one("#compare-all-search", Input)
        search_input.value = ""

        # Populate tables
        self.populate_tables()

    def populate_tables(self, query: str = "") -> None:
        """Filter and populate changes and transfers tables for all period comparisons."""
        # 1. Populate changes table
        table_changes = self.query_one("#changes-table", DataTable)

        # Re-add columns dynamically based on the current sorted_files
        table_changes.clear(columns=True)
        table_changes.cursor_type = "row"
        table_changes.add_column("Stock")
        table_changes.add_column("Investor Name")
        for dt, _, m in self.sorted_files:
            table_changes.add_column(f"{m} {dt.year} (Lot)")
        table_changes.add_column("Net Change (Lot)")

        filtered_changes = self.master_changes
        if query.strip() and not filtered_changes.empty:
            needle = query.strip().lower()
            mask = filtered_changes["SHARE_CODE"].astype(str).str.lower().str.contains(
                needle, na=False
            ) | filtered_changes["INVESTOR_NAME"].astype(str).str.lower().str.contains(needle, na=False)
            filtered_changes = filtered_changes[mask]

        if not filtered_changes.empty:
            for _, r in filtered_changes.iterrows():
                shares_list = r["shares_history"]

                row_cells = [
                    Text.from_markup(str(r["SHARE_CODE"])),
                    Text.from_markup(str(r["INVESTOR_NAME"])),
                ]

                # Format period columns
                for t in range(len(shares_list)):
                    prev_val = shares_list[t - 1] if t > 0 else 0.0
                    curr_val = shares_list[t]
                    cell_str = format_holding_with_change(prev_val, curr_val, is_first=(t == 0))
                    row_cells.append(Text.from_markup(cell_str))

                # Net Change column
                diff_val = float(r["total_change"])
                diff_str = (
                    f"[#00FF00]+{format_lot_value(diff_val)}[/#00FF00]"
                    if diff_val > 0
                    else (f"[#FF0000]-{format_lot_value(abs(diff_val))}[/#FF0000]" if diff_val < 0 else "0")
                )
                row_cells.append(Text.from_markup(diff_str))

                table_changes.add_row(*row_cells)

        # 2. Populate transfers table
        table_trans = self.query_one("#transfers-table", DataTable)
        table_trans.clear()

        filtered_trans = self.combined_transfers
        if query.strip() and not filtered_trans.empty:
            needle = query.strip().lower()
            mask = (
                filtered_trans["PERIOD"].astype(str).str.lower().str.contains(needle, na=False)
                | filtered_trans["SHARE_CODE"].astype(str).str.lower().str.contains(needle, na=False)
                | filtered_trans["INVESTOR_NAME_prev"].astype(str).str.lower().str.contains(needle, na=False)
                | filtered_trans["INVESTOR_NAME_curr"].astype(str).str.lower().str.contains(needle, na=False)
            )
            filtered_trans = filtered_trans[mask]

        if not filtered_trans.empty:
            for _, r in filtered_trans.iterrows():
                table_trans.add_row(
                    Text.from_markup(str(r["PERIOD"])),
                    Text.from_markup(str(r["SHARE_CODE"])),
                    Text.from_markup(str(r["INVESTOR_NAME_prev"])),
                    Text.from_markup(str(r["INVESTOR_NAME_curr"])),
                    Text.from_markup(f"[#FFFF00]{r['TOTAL_HOLDING_SHARES_curr']:,.0f}[/#FFFF00]"),
                )

        # Update the detail view after populating
        self.update_active_detail()

    @on(Tabs.TabActivated, "#compare-all-tabs")
    def handle_tab_activated(self, event: Tabs.TabActivated) -> None:
        """Handle global tab switch."""
        switcher = self.query_one("#compare-all-switcher", ContentSwitcher)
        if event.tab and event.tab.id == "tab-changes":
            switcher.current = "changes-table"
            self.update_detail_view(self.query_one("#changes-table", DataTable))
        elif event.tab and event.tab.id == "tab-transfers":
            switcher.current = "transfers-table"
            self.update_detail_view(self.query_one("#transfers-table", DataTable))

    @on(Input.Changed, "#compare-all-search")
    def handle_search_change(self, event: Input.Changed) -> None:
        """Handle search input key changes in real time."""
        self.populate_tables(event.value)

    @on(DataTable.RowHighlighted)
    def handle_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlighted in changes-table or transfers-table."""
        tabs = self.query_one("#compare-all-tabs", Tabs)
        active_tab = tabs.active if tabs else "tab-changes"
        active_table_id = "changes-table" if active_tab == "tab-changes" else "transfers-table"

        if event.data_table.id == active_table_id:
            self.update_detail_view(event.data_table, row_key=event.row_key)

    def reset_detail_view(self) -> None:
        """Reset the detail view to its default state."""
        detail = self.query_one("#compare-all-detail", Static)
        detail.update(Text.from_markup("[#FFA028]Highlight a row in the table above to see details here...[/#FFA028]"))

    def update_active_detail(self) -> None:
        """Find the active/focused table and update the detail view."""
        tabs = self.query_one("#compare-all-tabs", Tabs)
        active_tab = tabs.active if tabs else "tab-changes"
        active_table_id = "changes-table" if active_tab == "tab-changes" else "transfers-table"
        try:
            active_table = self.query_one(f"#{active_table_id}", DataTable)
            self.update_detail_view(active_table)
        except Exception:
            self.reset_detail_view()

    def update_detail_view(
        self,
        data_table: DataTable[Any],
        row_key: RowKey | None = None,
        row_index: int | None = None,
    ) -> None:
        """Update the detail view with the contents of the highlighted row."""
        detail = self.query_one("#compare-all-detail", Static)

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
        if data_table.id == "changes-table" and len(row_values) >= 3:
            stock = row_values[0]
            investor = row_values[1]
            net_change = row_values[-1]

            stock_text = stock.plain if isinstance(stock, Text) else str(stock)
            investor_text = investor.plain if isinstance(investor, Text) else str(investor)

            header = Text.assemble(
                ("Stock: ", "bold #FFA028"),
                Text(stock_text, style="bold #FFFFFF"),
                ("  |  ", "bold #45475a"),
                ("Investor: ", "bold #FFA028"),
                Text(investor_text, style="bold #FFFFFF"),
                ("  |  ", "bold #45475a"),
                ("Total Net Change: ", "bold #FFA028"),
                net_change,
                (" Lot", "bold #FFA028"),
            )

            # Build timeline/history
            grid = Table.grid(expand=False, padding=(0, 4))
            grid.add_column(style="bold #FFA028", justify="right")
            grid.add_column(style="default")

            # Period columns are at indices 2 to len(row_values)-2
            period_cols = data_table.ordered_columns[2:-1]
            for col_idx, col in enumerate(period_cols):
                col_name = col.label.plain if isinstance(col.label, Text) else str(col.label)
                cell_value = row_values[2 + col_idx]
                grid.add_row(f"{col_name}:", cell_value)

            content = Group(header, Text(""), grid)
            detail.update(content)

        elif data_table.id == "transfers-table" and len(row_values) >= 5:
            period = row_values[0]
            stock = row_values[1]
            prev_name = row_values[2]
            curr_name = row_values[3]
            shares = row_values[4]

            header = Text.assemble(
                ("Period: ", "bold #FFA028"),
                Text(period.plain if isinstance(period, Text) else str(period), style="bold #FFFFFF"),
                ("  |  ", "bold #45475a"),
                ("Stock: ", "bold #FFA028"),
                Text(stock.plain if isinstance(stock, Text) else str(stock), style="bold #FFFFFF"),
                ("  |  ", "bold #45475a"),
                ("Holding Shares: ", "bold #FFA028"),
                Text(shares.plain if isinstance(shares, Text) else str(shares), style="bold #FFFF00"),
                (" Shares", "bold #FFA028"),
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
