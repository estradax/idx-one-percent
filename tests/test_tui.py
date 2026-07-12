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

            # The active selection should default to "t_0"
            assert app.active_selection_id == "t_0"

            # The first option should have the arrow prefix
            opt_0 = menu.get_option_at_index(0)
            assert "➤" in str(opt_0.prompt)

            # Transition to All Periods and check highlight
            app.select_compare_all()
            await pilot.pause()
            assert app.active_selection_id == "action_all"

            # Recheck options to ensure the arrow transitioned
            opt_0_updated = menu.get_option_at_index(0)
            assert "➤" not in str(opt_0_updated.prompt)

            # Find the option with id "action_all"
            opt_all = None
            for idx in range(menu.option_count):
                opt = menu.get_option_at_index(idx)
                if opt.id == "action_all":
                    opt_all = opt
                    break
            assert opt_all is not None
            assert "➤" in str(opt_all.prompt)

            # Assert we transitioned to the dashboard view or compare all view
            assert app.current_view in ["loading", "dashboard", "compare_all"]

            # Terminate app cleanly
            app.exit(0)
