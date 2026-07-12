"""Loading view for the Textual TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, LoadingIndicator, Static


class LoadingView(Static):
    """A view showing a spinner and a message while loading."""

    DEFAULT_CSS = """
    LoadingView {
        padding: 0 1;
        layout: vertical;
        height: 100%;
        width: 100%;
        background: $bg-black;
    }

    #loading-container {
        align: center middle;
        height: 1fr;
        layout: vertical;
        background: $bg-black;
    }

    LoadingIndicator {
        color: $primary-text;
    }

    #loading-label {
        margin-top: 1;
        color: $primary-text;
        text-align: center;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="loading-container"):
            yield LoadingIndicator()
            yield Label("Loading shareholder reports...", id="loading-label")

    def update_message(self, message: str) -> None:
        """Update the loading message."""
        self.query_one("#loading-label", Label).update(message)
