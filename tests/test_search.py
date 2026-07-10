import pandas as pd

from main import filter_comparison_frames, search_dataframes


def test_search_dataframes_matches_partial_text_across_columns() -> None:
    df = pd.DataFrame(
        [
            {"SHARE_CODE": "BBCA", "INVESTOR_NAME": "Alice Investor", "ISSUER_NAME": "Bank ABC"},
            {"SHARE_CODE": "TLKM", "INVESTOR_NAME": "Bob Holder", "ISSUER_NAME": "Telkom"},
        ]
    )

    results = search_dataframes({"sample.xlsx": df}, "alice")

    assert len(results) == 1
    assert results[0][0] == "sample.xlsx"
    assert results[0][1].iloc[0]["SHARE_CODE"] == "BBCA"


def test_search_dataframes_uses_previous_period_for_change_values() -> None:
    current_df = pd.DataFrame(
        [{"SHARE_CODE": "BBCA", "INVESTOR_NAME": "Alice Investor", "TOTAL_HOLDING_SHARES": 100.0}]
    )
    previous_df = pd.DataFrame(
        [{"SHARE_CODE": "BBCA", "INVESTOR_NAME": "Alice Investor", "TOTAL_HOLDING_SHARES": 50.0}]
    )

    results = search_dataframes(
        {"2024.xlsx": current_df},
        "alice",
        previous_periods={"2024.xlsx": previous_df},
    )

    assert len(results) == 1
    assert results[0][1].iloc[0]["TOTAL_HOLDING_SHARES_prev"] == 50.0
    assert results[0][1].iloc[0]["TOTAL_HOLDING_SHARES_curr"] == 100.0
    assert results[0][1].iloc[0]["diff"] == 50.0


def test_filter_comparison_frames_matches_keyword() -> None:
    entries = pd.DataFrame(
        [{"SHARE_CODE": "BBCA", "INVESTOR_NAME": "Alice Investor", "TOTAL_HOLDING_SHARES_prev": 0, "TOTAL_HOLDING_SHARES_curr": 100, "diff": 100}]
    )
    exits = pd.DataFrame(
        [{"SHARE_CODE": "TLKM", "INVESTOR_NAME": "Bob Holder", "TOTAL_HOLDING_SHARES_prev": 50, "TOTAL_HOLDING_SHARES_curr": 0, "diff": -50}]
    )

    filtered_entries, filtered_exits, filtered_increases, filtered_decreases, filtered_transfers = filter_comparison_frames(
        entries,
        exits,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        "alice",
    )

    assert filtered_entries.shape[0] == 1
    assert filtered_exits.shape[0] == 0
    assert filtered_entries.iloc[0]["INVESTOR_NAME"] == "Alice Investor"
