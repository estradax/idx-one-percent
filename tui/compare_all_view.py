"""Compare All view showing all consecutive comparisons."""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Collapsible, DataTable, Label, Static

from analyzer.reporter import (
    format_change_pct,
    format_lot_value,
    format_net_change_lot,
)


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
