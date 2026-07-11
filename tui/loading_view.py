"""Loading view for the Textual TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, LoadingIndicator, Static


class LoadingView(Static):
    """A view showing a spinner and a message while loading."""

    def compose(self) -> ComposeResult:
        with Vertical(id="loading-container"):
            yield LoadingIndicator()
            yield Label("Loading shareholder reports...", id="loading-label")

    def update_message(self, message: str) -> None:
        """Update the loading message."""
        self.query_one("#loading-label", Label).update(message)
