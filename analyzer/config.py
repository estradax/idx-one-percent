"""Configuration constants for the IDX shareholder data analyzer."""

__all__ = [
    "STOP_WORDS",
    "MONTHS_MAP",
]

# Suffixes, prefixes, and common corporate abbreviations to filter out
STOP_WORDS: set[str] = {
    "PT",
    "TBK",
    "PERSERO",
    "LTD",
    "LIMITED",
    "CO",
    "INC",
    "CORP",
    "CORPORATION",
    "PERSEROAN",
    "PERUSAHAAN",
    "Tbk.",
    "PT.",
    "DAN",
    "AND",
    "THE",
    "OF",
}

# Mapping of English month names to integers for date parsing
MONTHS_MAP: dict[str, int] = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}
