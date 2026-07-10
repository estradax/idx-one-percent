"""IDX One Percent Shareholder Data Analyzer Package."""

from analyzer.data_loader import load_excel_file, parse_filename_date
from analyzer.entity_resolver import run_comparison
from analyzer.reporter import render_dashboard

__all__ = [
    "load_excel_file",
    "parse_filename_date",
    "run_comparison",
    "render_dashboard",
]

__version__ = "0.1.0"
