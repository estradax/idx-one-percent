"""Tests for entity resolution and shareholder comparison logic."""

import pandas as pd

from analyzer.entity_resolver import get_tokens, normalize_name_sorted_tokens, run_comparison


def test_get_tokens() -> None:
    """Verify get_tokens cleans punctuation, tokenizes, and removes stop words."""
    assert get_tokens("") == []
    assert get_tokens("PT. DANANTARA ASSET MANAGEMENT (PERSERO)") == ["DANANTARA", "ASSET", "MANAGEMENT"]
    assert get_tokens("Astra-International, Co. Ltd.") == ["ASTRA", "INTERNATIONAL"]


def test_normalize_name_sorted_tokens() -> None:
    """Verify that normalize_name_sorted_tokens normalizes and sorts name tokens."""
    name1 = "PT DANANTARA ASSET MANAGEMENT (PERSERO)"
    name2 = "PERUSAHAAN PERSEROAN (PERSERO) PT DANANTARA ASSET MANAGEMENT"
    normalized = normalize_name_sorted_tokens(name1)

    assert normalized == "ASSET DANANTARA MANAGEMENT"
    assert normalize_name_sorted_tokens(name2) == normalized


def test_run_comparison_new_and_removed_stocks() -> None:
    """Verify detection of newly listed and delisted stock codes."""
    df1 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII", "TLKM"],
            "INVESTOR_NAME": ["Investor A", "Investor B"],
            "TOTAL_HOLDING_SHARES": [100.0, 200.0],
            "PERCENTAGE": [1.0, 2.0],
        }
    )
    df2 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII", "BBCA"],
            "INVESTOR_NAME": ["Investor A", "Investor C"],
            "TOTAL_HOLDING_SHARES": [100.0, 300.0],
            "PERCENTAGE": [1.0, 3.0],
        }
    )

    _, _, _, _, _, new_stocks, removed_stocks = run_comparison(df1, df2)

    assert new_stocks == {"BBCA"}
    assert removed_stocks == {"TLKM"}


def test_run_comparison_increases_decreases() -> None:
    """Verify detection of increased and decreased holding positions for same investor."""
    df1 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII", "ASII"],
            "INVESTOR_NAME": ["Investor A", "Investor B"],
            "TOTAL_HOLDING_SHARES": [100.0, 200.0],
            "PERCENTAGE": [1.0, 2.0],
        }
    )
    df2 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII", "ASII"],
            "INVESTOR_NAME": ["Investor A", "Investor B"],
            "TOTAL_HOLDING_SHARES": [150.0, 120.0],
            "PERCENTAGE": [1.5, 1.2],
        }
    )

    entries, exits, increases, decreases, transfers, _, _ = run_comparison(df1, df2)

    assert entries.empty
    assert exits.empty
    assert len(increases) == 1
    assert increases.iloc[0]["INVESTOR_NAME"] == "Investor A"
    assert increases.iloc[0]["diff"] == 50.0

    assert len(decreases) == 1
    assert decreases.iloc[0]["INVESTOR_NAME"] == "Investor B"
    assert decreases.iloc[0]["diff"] == -80.0

    assert transfers.empty


def test_run_comparison_pass1_token_sorted_match() -> None:
    """Verify name change resolution when names normalize to identical sorted tokens."""
    df1 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII"],
            "INVESTOR_NAME": ["PT DANANTARA ASSET MANAGEMENT"],
            "TOTAL_HOLDING_SHARES": [1000.0],
            "PERCENTAGE": [1.0],
        }
    )
    df2 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII"],
            "INVESTOR_NAME": ["DANANTARA ASSET MANAGEMENT PT"],
            "TOTAL_HOLDING_SHARES": [1050.0],
            "PERCENTAGE": [1.05],
        }
    )

    entries, exits, increases, decreases, transfers, _, _ = run_comparison(df1, df2)

    assert entries.empty
    assert exits.empty
    assert increases.empty
    assert decreases.empty
    assert len(transfers) == 1
    assert transfers.iloc[0]["INVESTOR_NAME_prev"] == "PT DANANTARA ASSET MANAGEMENT"
    assert transfers.iloc[0]["INVESTOR_NAME_curr"] == "DANANTARA ASSET MANAGEMENT PT"
    assert transfers.iloc[0]["diff"] == 50.0


def test_run_comparison_pass2_share_and_token_overlap_match() -> None:
    """Verify name change resolution when share count matches and tokens overlap."""
    df1 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII"],
            "INVESTOR_NAME": ["HANS JONATHAN SCHMIDT"],
            "TOTAL_HOLDING_SHARES": [5000.0],
            "PERCENTAGE": [5.0],
        }
    )
    df2 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII"],
            "INVESTOR_NAME": ["HANS JONATHAN"],
            "TOTAL_HOLDING_SHARES": [5000.0],
            "PERCENTAGE": [5.0],
        }
    )

    entries, exits, increases, decreases, transfers, _, _ = run_comparison(df1, df2)

    assert entries.empty
    assert exits.empty
    assert increases.empty
    assert decreases.empty
    assert len(transfers) == 1
    assert transfers.iloc[0]["INVESTOR_NAME_prev"] == "HANS JONATHAN SCHMIDT"
    assert transfers.iloc[0]["INVESTOR_NAME_curr"] == "HANS JONATHAN"
    assert transfers.iloc[0]["diff"] == 0.0


def test_run_comparison_no_match() -> None:
    """Verify distinct investors are treated as true entries and exits."""
    df1 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII"],
            "INVESTOR_NAME": ["Alice"],
            "TOTAL_HOLDING_SHARES": [5000.0],
            "PERCENTAGE": [5.0],
        }
    )
    df2 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII"],
            "INVESTOR_NAME": ["Bob"],
            "TOTAL_HOLDING_SHARES": [5000.0],
            "PERCENTAGE": [5.0],
        }
    )

    entries, exits, increases, decreases, transfers, _, _ = run_comparison(df1, df2)

    assert len(entries) == 1
    assert entries.iloc[0]["INVESTOR_NAME"] == "Bob"
    assert len(exits) == 1
    assert exits.iloc[0]["INVESTOR_NAME"] == "Alice"
    assert transfers.empty
