"""IDX One Percent Shareholder Data Analyzer Main Entrypoint.

This script coordinates launching the Textual TUI application for
scanning, comparing, and tracking IDX shareholder reports.
"""

import sys

from analyzer.tui import IDXAnalyzerApp


def main() -> None:
    """Launch the Textual TUI Application."""
    app = IDXAnalyzerApp()
    exit_code = app.run()
    if exit_code is not None:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
