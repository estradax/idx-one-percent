"""Tests for terminal dashboard rendering and styling functions."""

import pandas as pd
import pytest

from analyzer.reporter import (
    console,
    format_change_pct,
    format_lot_value,
    format_net_change_lot,
    render_dashboard,
)


def test_format_change_pct() -> None:
    """Verify change percentage formatting under different conditions."""
    assert format_change_pct(0, 100) == "[bold #00FF00]New[/bold #00FF00]"
    assert format_change_pct(100, 0) == "[bold #FF0000]Exited[/bold #FF0000]"
    assert format_change_pct(100, 150) == "[#00FF00]+50.00%[/#00FF00]"
    assert format_change_pct(100, 50) == "[#FF0000]-50.00%[/#FF0000]"


def test_format_lot_value() -> None:
    """Verify share count is formatted correctly into lot units (1 lot = 100 shares)."""
    assert format_lot_value(0) == "0"
    assert format_lot_value(10000) == "100"
    assert format_lot_value(12345) == "123.45"
    assert format_lot_value(500) == "5"


def test_format_net_change_lot() -> None:
    """Verify net change is formatted correctly into styled lot units."""
    assert format_net_change_lot(0) == "0"
    assert format_net_change_lot(10000) == "[#00FF00]+100[/#00FF00]"
    assert format_net_change_lot(-5000) == "[#FF0000]-50[/#FF0000]"
    assert format_net_change_lot(12345) == "[#00FF00]+123.45[/#00FF00]"


def test_render_dashboard_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify render_dashboard runs without errors and outputs a title block when data is empty."""
    entries = pd.DataFrame()
    exits = pd.DataFrame()
    increases = pd.DataFrame()
    decreases = pd.DataFrame()
    transfers = pd.DataFrame()

    original_width = console.width
    console.width = 200
    try:
        render_dashboard(
            title="Test Period Comparison",
            active_stocks_count=5,
            entries=entries,
            exits=exits,
            increases=increases,
            decreases=decreases,
            transfers=transfers,
            new_stocks=set(),
            removed_stocks=set(),
            pager=False,
        )
    finally:
        console.width = original_width

    captured = capsys.readouterr()
    assert "Test Period Comparison" in captured.out


def test_render_dashboard_with_data(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify render_dashboard prints consolidated changes, headings, and name variations correctly."""
    entries = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII"],
            "INVESTOR_NAME": ["Investor A"],
            "TOTAL_HOLDING_SHARES_prev": [0.0],
            "TOTAL_HOLDING_SHARES_curr": [1000.0],
            "diff": [1000.0],
        }
    )
    exits = pd.DataFrame(
        {
            "SHARE_CODE": ["TLKM"],
            "INVESTOR_NAME": ["Investor B"],
            "TOTAL_HOLDING_SHARES_prev": [2000.0],
            "TOTAL_HOLDING_SHARES_curr": [0.0],
            "diff": [-2000.0],
        }
    )
    increases = pd.DataFrame(
        {
            "SHARE_CODE": ["BBCA"],
            "INVESTOR_NAME": ["Investor C"],
            "TOTAL_HOLDING_SHARES_prev": [5000.0],
            "TOTAL_HOLDING_SHARES_curr": [7000.0],
            "diff": [2000.0],
        }
    )
    decreases = pd.DataFrame(
        {
            "SHARE_CODE": ["BBRI"],
            "INVESTOR_NAME": ["Investor D"],
            "TOTAL_HOLDING_SHARES_prev": [5000.0],
            "TOTAL_HOLDING_SHARES_curr": [3000.0],
            "diff": [-2000.0],
        }
    )
    # Transfers: one with a diff (which should be combined) and one with 0 diff (which should go to name variation table)
    transfers = pd.DataFrame(
        {
            "SHARE_CODE": ["ADRO", "KLBF"],
            "INVESTOR_NAME_prev": ["PT OLD ADRO", "PT OLD KLBF"],
            "INVESTOR_NAME_curr": ["PT NEW ADRO", "PT NEW KLBF"],
            "TOTAL_HOLDING_SHARES_prev": [1000.0, 5000.0],
            "TOTAL_HOLDING_SHARES_curr": [1200.0, 5000.0],
            "diff": [200.0, 0.0],
        }
    )

    original_width = console.width
    console.width = 200
    try:
        render_dashboard(
            title="Comparison January vs February",
            active_stocks_count=10,
            entries=entries,
            exits=exits,
            increases=increases,
            decreases=decreases,
            transfers=transfers,
            new_stocks={"ASII"},
            removed_stocks={"TLKM"},
            pager=False,
        )
    finally:
        console.width = original_width

    captured = capsys.readouterr()
    output = captured.out

    # Verify everything renders
    assert "Comparison January vs February" in output
    assert "ASII" in output
    assert "Investor A" in output
    assert "TLKM" in output
    assert "Investor B" in output
    assert "BBCA" in output
    assert "Investor C" in output
    assert "BBRI" in output
    assert "Investor D" in output
    assert "ADRO" in output
    assert "PT NEW ADRO" in output
    assert "KLBF" in output
    assert "PT NEW KLBF" in output
