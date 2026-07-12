"""Tests for data loading, parsing, and cleaning logic."""

from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from analyzer.data_loader import clean_dataframe, load_excel_file, parse_filename_date


def test_parse_filename_date_valid() -> None:
    """Verify that valid filenames are parsed correctly into dates."""
    date_val, month_str = parse_filename_date("12-January-2026.xlsx")
    assert date_val == datetime(2026, 1, 12)
    assert month_str == "January"

    date_val, month_str = parse_filename_date("01-December-2025.xlsx")
    assert date_val == datetime(2025, 12, 1)
    assert month_str == "December"


def test_parse_filename_date_invalid() -> None:
    """Verify that invalid filenames return datetime.min and empty string."""
    date_val, month_str = parse_filename_date("invalid-filename.xlsx")
    assert date_val == datetime.min
    assert month_str == ""

    date_val, month_str = parse_filename_date("12-Jan-2026.csv")
    assert date_val == datetime.min
    assert month_str == ""


def test_clean_dataframe_headers_and_rename() -> None:
    """Verify headers are normalized and INVESTOR_CLASSIFICATION is renamed."""
    df = pd.DataFrame(
        {
            " share_code ": ["ASII", "BBCA"],
            "investor_classification": ["IB", "CP"],
            "total_holding_shares": ["1000", "2000"],
        }
    )
    cleaned = clean_dataframe(df)

    assert "SHARE_CODE" in cleaned.columns
    assert "INVESTOR_TYPE" in cleaned.columns
    assert "INVESTOR_CLASSIFICATION" not in cleaned.columns
    assert "TOTAL_HOLDING_SHARES" in cleaned.columns


def test_clean_dataframe_string_coercion() -> None:
    """Verify boolean and NaN values are correctly coerced into standardized strings."""
    df = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII", True, False, None],
            "INVESTOR_NAME": ["PT Astra", "PT Bank Central", None, "   PT Telkom   "],
        }
    )
    cleaned = clean_dataframe(df)

    assert cleaned["SHARE_CODE"].tolist() == ["ASII", "TRUE", "FALSE", ""]
    assert cleaned["INVESTOR_NAME"].tolist() == ["PT Astra", "PT Bank Central", "", "PT Telkom"]


def test_clean_dataframe_numeric_conversion() -> None:
    """Verify numeric columns are coerced to floats, replacing NaNs with 0.0."""
    df = pd.DataFrame(
        {
            "SHARE_CODE": ["ASII", "BBCA", "TLKM"],
            "TOTAL_HOLDING_SHARES": ["1000", "invalid_number", None],
            "PERCENTAGE": [1.5, "2.3", "abc"],
        }
    )
    cleaned = clean_dataframe(df)

    assert cleaned["TOTAL_HOLDING_SHARES"].tolist() == [1000.0, 0.0, 0.0]
    assert cleaned["PERCENTAGE"].tolist() == [1.5, 2.3, 0.0]


@pytest.fixture
def temp_excel_file(tmp_path: Path) -> Path:
    """Fixture that creates a temporary valid Excel file with custom data."""
    file_path = tmp_path / "12-January-2026.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None

    # Write headers and rows
    ws.append(
        [
            "share_code",
            "issuer_name",
            "investor_name",
            "total_holding_shares",
            "investor_classification",
        ]
    )
    ws.append(["ASII", "Astra International", "PT Danantara", 500000, "IB"])
    ws.append(["BBCA", "Bank Central Asia", True, "1234.5", "CP"])

    wb.save(file_path)
    return file_path


def test_load_excel_file(temp_excel_file: Path) -> None:
    """Verify that load_excel_file properly loads and cleans data from a file."""
    df = load_excel_file(str(temp_excel_file))

    assert not df.empty
    assert len(df) == 2
    assert list(df.columns) == ["SHARE_CODE", "ISSUER_NAME", "INVESTOR_NAME", "TOTAL_HOLDING_SHARES", "INVESTOR_TYPE"]
    assert df.loc[0, "SHARE_CODE"] == "ASII"
    assert df.loc[0, "TOTAL_HOLDING_SHARES"] == 500000.0
    assert df.loc[1, "INVESTOR_NAME"] == "TRUE"
    assert df.loc[1, "TOTAL_HOLDING_SHARES"] == 1234.5


def test_load_excel_file_empty(tmp_path: Path) -> None:
    """Verify loading an empty Excel sheet returns an empty DataFrame."""
    file_path = tmp_path / "empty.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    wb.save(file_path)

    df = load_excel_file(str(file_path))
    assert df.empty
