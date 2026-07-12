"""Tests for the configuration constants."""

from analyzer.config import MONTHS_MAP, STOP_WORDS


def test_months_map() -> None:
    """Verify that MONTHS_MAP contains all 12 months with correct mappings."""
    assert len(MONTHS_MAP) == 12
    assert MONTHS_MAP["January"] == 1
    assert MONTHS_MAP["December"] == 12
    assert MONTHS_MAP["July"] == 7


def test_stop_words() -> None:
    """Verify key corporate prefixes and abbreviations are in STOP_WORDS."""
    assert "PT" in STOP_WORDS
    assert "TBK" in STOP_WORDS
    assert "LTD" in STOP_WORDS
    assert "CO" in STOP_WORDS
