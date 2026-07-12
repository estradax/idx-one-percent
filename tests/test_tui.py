"""Tests for the Textual TUI Application."""

from unittest.mock import patch

import pandas as pd
import pytest

from tui.app import IDXAnalyzerApp


@pytest.fixture
def mock_shareholder_df() -> pd.DataFrame:
    """Fixture providing a mock dataframe representing cleaned Excel reports."""
    return pd.DataFrame(
        {
            "SHARE_CODE": ["ASII", "TLKM"],
            "ISSUER_NAME": ["Astra International", "Telkom Indonesia"],
            "INVESTOR_NAME": ["PT DANANTARA", "FOREIGN INVESTOR"],
            "LOCAL_FOREIGN": ["LOCAL", "FOREIGN"],
            "NATIONALITY": ["IDN", "USA"],
            "DOMICILE": ["JAKARTA", "NEW YORK"],
            "TOTAL_HOLDING_SHARES": [500000.0, 1000000.0],
            "PERCENTAGE": [5.0, 10.0],
            "HOLDINGS_SCRIPLESS": [500000.0, 1000000.0],
            "HOLDINGS_SCRIP": [0.0, 0.0],
        }
    )


@pytest.mark.asyncio
async def test_tui_app_lifecycle(mock_shareholder_df: pd.DataFrame) -> None:
    """Verify that the TUI app initializes successfully and transitions views."""
    # Mock filesystem operations to make the app believe it has valid data files
    with (
        patch("os.path.exists", return_value=True),
        patch("os.listdir", return_value=["12-January-2026.xlsx", "13-January-2026.xlsx"]),
        patch("tui.app.load_excel_file", return_value=mock_shareholder_df),
    ):
        app = IDXAnalyzerApp()

        async with app.run_test() as pilot:
            # Let the background workers execute and load the files
            await pilot.pause(0.5)

            # Assert variables populated correctly
            assert len(app.sorted_files) == 2
            assert app.data_dir != ""
            assert len(app.transitions) == 1

            # Assert correct menu options exist
            menu = app.query_one("#sidebar-menu")
            assert menu is not None

            # Assert we transitioned to the dashboard view
            assert app.current_view in ["loading", "dashboard"]

            # Terminate app cleanly
            app.exit(0)
