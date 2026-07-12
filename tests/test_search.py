"""Tests for search functionality across shareholder reports."""

import pandas as pd
import pytest

from analyzer.search import search_dataframes


@pytest.fixture
def sample_dataframes() -> dict[str, pd.DataFrame]:
    """Fixture providing sample current-period shareholder dataframes."""
    df1 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII", "TLKM"],
            "ISSUER_NAME": ["Astra International", "Telkom Indonesia"],
            "INVESTOR_NAME": ["HANS JONATHAN", "PT INVESTAMA"],
            "LOCAL_FOREIGN": ["LOCAL", "FOREIGN"],
            "NATIONALITY": ["IDN", "SGP"],
            "DOMICILE": ["JAKARTA", "SINGAPORE"],
            "TOTAL_HOLDING_SHARES": [5000.0, 10000.0],
        }
    )
    df2 = pd.DataFrame(
        {
            "SHARE_CODE": ["BBCA"],
            "ISSUER_NAME": ["Bank Central Asia"],
            "INVESTOR_NAME": ["HANS SCHMIDT"],
            "LOCAL_FOREIGN": ["LOCAL"],
            "NATIONALITY": ["IDN"],
            "DOMICILE": ["SURABAYA"],
            "TOTAL_HOLDING_SHARES": [2000.0],
        }
    )
    return {"file1.xlsx": df1, "file2.xlsx": df2}


@pytest.fixture
def prior_dataframes() -> dict[str, pd.DataFrame]:
    """Fixture providing sample prior-period shareholder dataframes for enrichment."""
    df1 = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII", "TLKM"],
            "INVESTOR_NAME": ["HANS JONATHAN", "PT INVESTAMA"],
            "TOTAL_HOLDING_SHARES": [4000.0, 12000.0],
        }
    )
    df2 = pd.DataFrame(
        {
            "SHARE_CODE": ["BBCA"],
            "INVESTOR_NAME": ["HANS SCHMIDT"],
            "TOTAL_HOLDING_SHARES": [2000.0],
        }
    )
    return {"file1.xlsx": df1, "file2.xlsx": df2}


def test_search_dataframes_empty_query(sample_dataframes: dict[str, pd.DataFrame]) -> None:
    """Verify that an empty or whitespace-only query returns an empty list."""
    assert search_dataframes(sample_dataframes, "") == []
    assert search_dataframes(sample_dataframes, "   ") == []


def test_search_dataframes_no_matches(sample_dataframes: dict[str, pd.DataFrame]) -> None:
    """Verify search returns empty list if query does not match any fields."""
    assert search_dataframes(sample_dataframes, "XYZ") == []


def test_search_dataframes_matches_substring_case_insensitive(sample_dataframes: dict[str, pd.DataFrame]) -> None:
    """Verify case-insensitivity and substring matching (e.g. 'hans' matches both 'HANS JONATHAN' and 'HANS SCHMIDT')."""
    results = search_dataframes(sample_dataframes, "hans")

    assert len(results) == 2
    # Check results from file1.xlsx
    filenames = [r[0] for r in results]
    assert "file1.xlsx" in filenames
    assert "file2.xlsx" in filenames

    file1_df = next(df for f, df in results if f == "file1.xlsx")
    assert len(file1_df) == 1
    assert file1_df.iloc[0]["SHARE_CODE"] == "ASII"
    assert file1_df.iloc[0]["INVESTOR_NAME"] == "HANS JONATHAN"

    file2_df = next(df for f, df in results if f == "file2.xlsx")
    assert len(file2_df) == 1
    assert file2_df.iloc[0]["SHARE_CODE"] == "BBCA"
    assert file2_df.iloc[0]["INVESTOR_NAME"] == "HANS SCHMIDT"


def test_search_dataframes_searchable_columns(sample_dataframes: dict[str, pd.DataFrame]) -> None:
    """Verify search matches across multiple columns: DOMICILE, NATIONALITY, etc."""
    # Match DOMICILE
    results = search_dataframes(sample_dataframes, "SURABAYA")
    assert len(results) == 1
    assert results[0][0] == "file2.xlsx"

    # Match LOCAL_FOREIGN
    results = search_dataframes(sample_dataframes, "foreign")
    assert len(results) == 1
    assert results[0][1].iloc[0]["SHARE_CODE"] == "TLKM"


def test_search_dataframes_with_enrichment(
    sample_dataframes: dict[str, pd.DataFrame], prior_dataframes: dict[str, pd.DataFrame]
) -> None:
    """Verify search result is enriched with prior period data and calculates differences correctly."""
    results = search_dataframes(sample_dataframes, "hans", previous_periods=prior_dataframes)

    assert len(results) == 2

    # Verify file1.xlsx match (ASII - HANS JONATHAN) increased by 1000 shares
    file1_df = next(df for f, df in results if f == "file1.xlsx")
    assert "TOTAL_HOLDING_SHARES_curr" in file1_df.columns
    assert "TOTAL_HOLDING_SHARES_prev" in file1_df.columns
    assert "diff" in file1_df.columns
    assert file1_df.iloc[0]["TOTAL_HOLDING_SHARES_curr"] == 5000.0
    assert file1_df.iloc[0]["TOTAL_HOLDING_SHARES_prev"] == 4000.0
    assert file1_df.iloc[0]["diff"] == 1000.0

    # Verify file2.xlsx match (BBCA - HANS SCHMIDT) stayed constant
    file2_df = next(df for f, df in results if f == "file2.xlsx")
    assert file2_df.iloc[0]["TOTAL_HOLDING_SHARES_curr"] == 2000.0
    assert file2_df.iloc[0]["TOTAL_HOLDING_SHARES_prev"] == 2000.0
    assert file2_df.iloc[0]["diff"] == 0.0


def test_search_dataframes_empty_df() -> None:
    """Verify that empty dataframes are skipped during search."""
    dfs = {"empty.xlsx": pd.DataFrame()}
    assert search_dataframes(dfs, "test_query") == []


def test_search_dataframes_no_searchable_columns() -> None:
    """Verify that dataframes with no searchable columns are skipped."""
    dfs = {"no_cols.xlsx": pd.DataFrame({"SOME_OTHER_COLUMN": [1, 2, 3]})}
    assert search_dataframes(dfs, "test_query") == []
