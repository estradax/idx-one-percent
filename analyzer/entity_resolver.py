"""Entity resolution and shareholder comparison logic."""

import re
from typing import Any

import pandas as pd

from analyzer.config import STOP_WORDS

__all__ = [
    "get_tokens",
    "normalize_name_sorted_tokens",
    "run_comparison",
]


def get_tokens(name: str) -> list[str]:
    """Extract and clean name tokens, removing common stop words.

    Args:
        name: The raw entity name.

    Returns:
        A list of cleaned token strings.
    """
    if not name:
        return []
    n = name.upper()
    n = re.sub(r"[.,()\-]", " ", n)
    words = n.split()
    return [w for w in words if w not in STOP_WORDS]


def normalize_name_sorted_tokens(name: str) -> str:
    """Normalize names by sorting tokens to resolve word transpositions.

    For example, 'PT DANANTARA ASSET MANAGEMENT (PERSERO)' and
    'PERUSAHAAN PERSEROAN (PERSERO) PT DANANTARA ASSET MANAGEMENT'
    both normalize to 'ASSET DANANTARA MANAGEMENT'.

    Args:
        name: The raw investor name.

    Returns:
        The normalized, sorted token string.
    """
    tokens = get_tokens(name)
    return " ".join(sorted(tokens))


def run_comparison(
    df1: pd.DataFrame, df2: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, set[str], set[str]]:
    """Compare two DataFrames, applying entity resolution to find true changes.

    Args:
        df1: Cleansed DataFrame from the previous period.
        df2: Cleansed DataFrame from the current period.

    Returns:
        A tuple containing:
          - df_entries: Unresolved new investor positions.
          - df_exits: Unresolved closed investor positions.
          - df_increases: Current positions that increased shares.
          - df_decreases: Current positions that decreased shares.
          - df_transfers: Resolved entity name changes / transfers.
          - new_stocks: Newly listed stocks.
          - removed_stocks: Delisted stocks.
    """
    # Exclude empty rows or codes
    codes1 = set(df1["SHARE_CODE"].unique()) - {""}
    codes2 = set(df2["SHARE_CODE"].unique()) - {""}

    new_stocks = codes2 - codes1
    removed_stocks = codes1 - codes2

    # Group duplicate entries for the same investor in a stock
    grp1 = df1.groupby(["SHARE_CODE", "INVESTOR_NAME"])[["TOTAL_HOLDING_SHARES", "PERCENTAGE"]].sum().reset_index()
    grp2 = df2.groupby(["SHARE_CODE", "INVESTOR_NAME"])[["TOTAL_HOLDING_SHARES", "PERCENTAGE"]].sum().reset_index()

    # Pre-calculate normalized names
    grp1["NORM_NAME"] = grp1["INVESTOR_NAME"].apply(normalize_name_sorted_tokens)
    grp2["NORM_NAME"] = grp2["INVESTOR_NAME"].apply(normalize_name_sorted_tokens)

    # Perform outer join on exact stock and investor name
    merged = pd.merge(grp1, grp2, on=["SHARE_CODE", "INVESTOR_NAME"], how="outer", suffixes=("_prev", "_curr"))
    merged["TOTAL_HOLDING_SHARES_prev"] = merged["TOTAL_HOLDING_SHARES_prev"].fillna(0.0)
    merged["TOTAL_HOLDING_SHARES_curr"] = merged["TOTAL_HOLDING_SHARES_curr"].fillna(0.0)
    merged["PERCENTAGE_prev"] = merged["PERCENTAGE_prev"].fillna(0.0)
    merged["PERCENTAGE_curr"] = merged["PERCENTAGE_curr"].fillna(0.0)
    merged["diff"] = merged["TOTAL_HOLDING_SHARES_curr"] - merged["TOTAL_HOLDING_SHARES_prev"]

    # Separate raw exits and entries
    exited_raw = (
        merged[(merged["TOTAL_HOLDING_SHARES_prev"] > 0) & (merged["TOTAL_HOLDING_SHARES_curr"] == 0)]
        .copy()
        .reset_index(drop=True)
    )
    entered_raw = (
        merged[(merged["TOTAL_HOLDING_SHARES_prev"] == 0) & (merged["TOTAL_HOLDING_SHARES_curr"] > 0)]
        .copy()
        .reset_index(drop=True)
    )

    # Keep track of matched row indexes to avoid double counting
    matched_idx_prev: set[int] = set()
    matched_idx_curr: set[int] = set()

    # Store resolved name transitions
    name_changes: list[dict[str, Any]] = []

    # --- Pass 1: Token-Sorted Name Resolution ---
    # Index exited candidates by (SHARE_CODE, NORM_NAME)
    exits_by_code_norm: dict[tuple[str, str], list[tuple[int, str, float, float]]] = {}
    for idx, r in exited_raw.iterrows():
        code = str(r["SHARE_CODE"])
        norm = normalize_name_sorted_tokens(str(r["INVESTOR_NAME"]))
        exits_by_code_norm.setdefault((code, norm), []).append(
            (idx, str(r["INVESTOR_NAME"]), float(r["TOTAL_HOLDING_SHARES_prev"]), float(r["PERCENTAGE_prev"]))
        )

    for idx, r in entered_raw.iterrows():
        code = str(r["SHARE_CODE"])
        norm = normalize_name_sorted_tokens(str(r["INVESTOR_NAME"]))
        curr_shares = float(r["TOTAL_HOLDING_SHARES_curr"])
        curr_pct = float(r["PERCENTAGE_curr"])

        candidates = exits_by_code_norm.get((code, norm), [])
        best_cand = None
        for c_idx, c_name, c_shares, c_pct in candidates:
            if c_idx not in matched_idx_prev:
                best_cand = (c_idx, c_name, c_shares, c_pct)
                break

        if best_cand:
            c_idx, c_name, c_shares, c_pct = best_cand
            matched_idx_prev.add(c_idx)
            matched_idx_curr.add(idx)
            name_changes.append(
                {
                    "SHARE_CODE": code,
                    "INVESTOR_NAME_prev": c_name,
                    "INVESTOR_NAME_curr": r["INVESTOR_NAME"],
                    "TOTAL_HOLDING_SHARES_prev": c_shares,
                    "TOTAL_HOLDING_SHARES_curr": curr_shares,
                    "PERCENTAGE_prev": c_pct,
                    "PERCENTAGE_curr": curr_pct,
                    "diff": curr_shares - c_shares,
                }
            )

    # --- Pass 2: Share Count + Token Overlap Resolution ---
    remaining_exited = exited_raw[~exited_raw.index.isin(matched_idx_prev)].copy()
    remaining_entered = entered_raw[~entered_raw.index.isin(matched_idx_curr)].copy()

    # Index remaining exited candidates by (SHARE_CODE, shares)
    exits_by_code_shares: dict[tuple[str, float], list[tuple[int, str, float]]] = {}
    for idx, r in remaining_exited.iterrows():
        code = str(r["SHARE_CODE"])
        shares = float(r["TOTAL_HOLDING_SHARES_prev"])
        exits_by_code_shares.setdefault((code, shares), []).append(
            (idx, str(r["INVESTOR_NAME"]), float(r["PERCENTAGE_prev"]))
        )

    for idx, r in remaining_entered.iterrows():
        code = str(r["SHARE_CODE"])
        shares = float(r["TOTAL_HOLDING_SHARES_curr"])
        curr_pct = float(r["PERCENTAGE_curr"])
        curr_name = str(r["INVESTOR_NAME"])
        curr_tokens = set(get_tokens(curr_name))

        share_candidates = exits_by_code_shares.get((code, shares), [])
        best_share_cand = None
        for c_idx, c_name, c_pct in share_candidates:
            if c_idx not in matched_idx_prev:
                # Check for token overlap (at least 1 word overlaps)
                c_tokens = set(get_tokens(c_name))
                overlap = curr_tokens & c_tokens
                if overlap:
                    best_share_cand = (c_idx, c_name, c_pct)
                    break

        if best_share_cand:
            c_idx, c_name, c_pct = best_share_cand
            matched_idx_prev.add(c_idx)
            matched_idx_curr.add(idx)
            name_changes.append(
                {
                    "SHARE_CODE": code,
                    "INVESTOR_NAME_prev": c_name,
                    "INVESTOR_NAME_curr": curr_name,
                    "TOTAL_HOLDING_SHARES_prev": shares,
                    "TOTAL_HOLDING_SHARES_curr": shares,
                    "PERCENTAGE_prev": c_pct,
                    "PERCENTAGE_curr": curr_pct,
                    "diff": 0.0,
                }
            )

    # Filter out matched items from raw lists to get true entries and exits
    true_exits = exited_raw[~exited_raw.index.isin(matched_idx_prev)].copy()
    true_entries = entered_raw[~entered_raw.index.isin(matched_idx_curr)].copy()

    # Get positions with changed holdings (present in both, but shares changed)
    common = merged[(merged["TOTAL_HOLDING_SHARES_prev"] > 0) & (merged["TOTAL_HOLDING_SHARES_curr"] > 0)]
    common = common[common["diff"] != 0].copy()

    increases = common[common["diff"] > 0].copy()
    decreases = common[common["diff"] < 0].copy()

    df_transfers = pd.DataFrame(name_changes)

    return (
        true_entries,
        true_exits,
        increases,
        decreases,
        df_transfers,
        new_stocks,
        removed_stocks,
    )
