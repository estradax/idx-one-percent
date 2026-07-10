"""Data loading, parsing, and cleaning logic for IDX shareholder data."""

import re
from datetime import datetime

import openpyxl
import pandas as pd

from analyzer.config import MONTHS_MAP

__all__ = [
    "parse_filename_date",
    "clean_dataframe",
    "load_excel_file",
]


def parse_filename_date(filename: str) -> tuple[datetime, str]:
    """Parse the date from filename in the format 'DD-Month-YYYY.xlsx'.

    Args:
        filename: Name of the excel file.

    Returns:
        A tuple of (parsed datetime, month name string).
    """
    match = re.match(r"(\d+)-([A-Za-z]+)-(\d+)\.xlsx", filename)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        year = int(match.group(3))
        month = MONTHS_MAP.get(month_str, 1)
        return datetime(year, month, day), month_str
    return datetime.min, ""


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize headers and clean datatypes to handle Excel anomalies.

    Args:
        df: The raw pandas DataFrame.

    Returns:
        A cleaned and typed pandas DataFrame.
    """
    cleaned = df.copy()

    # Normalize header names to uppercase and strip whitespace
    cleaned.columns = [str(c).strip().upper() for c in cleaned.columns]

    # Map INVESTOR_CLASSIFICATION to INVESTOR_TYPE for consistency
    if "INVESTOR_CLASSIFICATION" in cleaned.columns and "INVESTOR_TYPE" not in cleaned.columns:
        cleaned.rename(columns={"INVESTOR_CLASSIFICATION": "INVESTOR_TYPE"}, inplace=True)

    # Standardize string fields and prevent boolean coercions
    string_cols = ["SHARE_CODE", "ISSUER_NAME", "INVESTOR_NAME", "LOCAL_FOREIGN", "NATIONALITY", "DOMICILE"]
    for col in string_cols:
        if col in cleaned.columns:
            cleaned[col] = cleaned[col].apply(
                lambda x: "TRUE" if x is True else ("FALSE" if x is False else str(x).strip() if pd.notna(x) else "")
            )

    # Standardize numeric fields
    numeric_cols = ["HOLDINGS_SCRIPLESS", "HOLDINGS_SCRIP", "TOTAL_HOLDING_SHARES", "PERCENTAGE"]
    for col in numeric_cols:
        if col in cleaned.columns:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce").fillna(0.0)

    return cleaned


def load_excel_file(filepath: str) -> pd.DataFrame:
    """Load and clean an Excel file from disk.

    Args:
        filepath: Absolute or relative path to the Excel file.

    Returns:
        A cleaned pandas DataFrame.
    """
    wb = openpyxl.load_workbook(filepath, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))

    if not rows:
        return pd.DataFrame()

    headers = rows[0]
    data = [dict(zip(headers, r, strict=False)) for r in rows[1:] if any(r is not None for r in r)]
    df = pd.DataFrame(data)
    return clean_dataframe(df)
