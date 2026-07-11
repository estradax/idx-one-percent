"""Main Textual TUI Application for IDX One Percent Shareholder Analyzer."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, ClassVar

import pandas as pd
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import ContentSwitcher, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from analyzer.data_loader import load_excel_file, parse_filename_date
from analyzer.entity_resolver import run_comparison
from tui.compare_all_view import CompareAllView
from tui.dashboard_view import DashboardView
from tui.global_search_view import GlobalSearchView, search_dataframes
from tui.loading_view import LoadingView


class IDXAnalyzerApp(App[int]):
    """Main Textual TUI Application for IDX One Percent Shareholder Analyzer."""

    CSS: ClassVar[str] = """
    $border: #45475a;
    $sidebar-bg: #11111b;
    $content-bg: #1e1e2e;
    $subtle: #a6adc8;
    $cyan: #89dceb;

    Screen {
        background: $content-bg;
    }

    #footer {
        background: $sidebar-bg;
        color: $subtle;
    }

    /* Sidebar Styling */
    #sidebar {
        width: 32;
        height: 100%;
        background: $sidebar-bg;
        border-right: solid $border;
        layout: vertical;
    }

    #sidebar-spacer {
        height: 1;
        background: transparent;
    }

    .sidebar-heading {
        padding: 1 2 0 2;
        color: $cyan;
        text-style: bold;
        background: transparent;
    }

    #sidebar-menu {
        background: transparent;
        border: none;
        height: 1fr;
    }

    /* Main Content Layout */
    #content-area {
        layout: vertical;
        background: $content-bg;
        width: 1fr;
        height: 100%;
    }
    """
    BINDINGS: ClassVar[list[Any]] = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("d", "toggle_dark", "Toggle Dark", show=False),
        Binding("s", "focus_search", "Focus Search", show=False),
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
        yield Footer(id="footer", show_command_palette=False)

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
                    "transfers": transfers,
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
