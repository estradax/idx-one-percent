"""Search functionality for shareholder reports."""

from __future__ import annotations

import pandas as pd

__all__ = [
    "search_dataframes",
]


def search_dataframes(
    dfs: dict[str, pd.DataFrame],
    query: str,
    previous_periods: dict[str, pd.DataFrame] | None = None,
) -> list[tuple[str, pd.DataFrame]]:
    """Search loaded dataframes across common shareholder columns for a keyword and enrich them with prior-period values.

    Args:
        dfs: A dictionary mapping filenames to pandas DataFrames.
        query: The search term.
        previous_periods: Optional dictionary mapping filenames to prior-period pandas DataFrames for enrichment.

    Returns:
        A list of tuples containing the filename and the matching DataFrame.
    """
    if not query.strip():
        return []

    needle = query.strip().lower()
    matches: list[tuple[str, pd.DataFrame]] = []
    searchable_columns = ["SHARE_CODE", "ISSUER_NAME", "INVESTOR_NAME", "LOCAL_FOREIGN", "NATIONALITY", "DOMICILE"]

    for filename, df in dfs.items():
        if df.empty:
            continue

        candidate_columns = [col for col in searchable_columns if col in df.columns]
        if not candidate_columns:
            continue

        mask = pd.Series(False, index=df.index)
        for column in candidate_columns:
            values = df[column].fillna("")
            mask |= values.astype(str).str.lower().str.contains(needle, na=False, regex=False)

        if mask.any():
            matched_df = df.loc[mask].copy()
            prev_df = previous_periods.get(filename) if previous_periods else None
            if prev_df is not None and not prev_df.empty:
                matched_df = matched_df.copy()
                current_shares = pd.to_numeric(matched_df.get("TOTAL_HOLDING_SHARES", 0), errors="coerce").fillna(0.0)
                matched_df["TOTAL_HOLDING_SHARES_curr"] = current_shares

                prev_lookup = prev_df[["SHARE_CODE", "INVESTOR_NAME", "TOTAL_HOLDING_SHARES"]].copy()
                prev_lookup = prev_lookup.groupby(["SHARE_CODE", "INVESTOR_NAME"], as_index=False)[
                    "TOTAL_HOLDING_SHARES"
                ].sum()
                prev_lookup = prev_lookup.rename(columns={"TOTAL_HOLDING_SHARES": "TOTAL_HOLDING_SHARES_prev"})
                matched_df = matched_df.merge(prev_lookup, on=["SHARE_CODE", "INVESTOR_NAME"], how="left")
                matched_df["TOTAL_HOLDING_SHARES_prev"] = pd.to_numeric(
                    matched_df.get("TOTAL_HOLDING_SHARES_prev", 0), errors="coerce"
                ).fillna(0.0)
                matched_df["TOTAL_HOLDING_SHARES_curr"] = pd.to_numeric(
                    matched_df.get("TOTAL_HOLDING_SHARES_curr", 0), errors="coerce"
                ).fillna(0.0)
                matched_df["diff"] = matched_df["TOTAL_HOLDING_SHARES_curr"] - matched_df["TOTAL_HOLDING_SHARES_prev"]

            matches.append((filename, matched_df))

    return matches
