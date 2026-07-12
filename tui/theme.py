"""Bloomberg terminal color theme for the Textual TUI."""

from __future__ import annotations

from textual.theme import Theme

bloomberg_terminal_theme = Theme(
    name="bloomberg-terminal",
    primary="#FFA028",  # Bloomberg Amber
    secondary="#FFFFFF",  # White
    accent="#FFFF00",  # Bloomberg Yellow / highlight
    foreground="#FFA028",  # Amber text
    background="#000000",  # Pure black background
    success="#00FF00",  # Bright green
    warning="#FFFF00",  # Bright yellow
    error="#FF0000",  # Bright red
    surface="#000000",  # Pure black surface
    panel="#000000",  # Pure black panels
    dark=True,
    variables={
        "text": "#FFA028",
        "border": "#555555",
        "border-blurred": "#444444",
        "bg-black": "#000000",
        "primary-text": "#FFA028",
        "secondary-text": "#FFFFFF",
        "block-cursor-background": "#333333",
        "block-cursor-foreground": "#FFFFFF",
        "block-cursor-text-style": "none",
        "block-cursor-blurred-background": "#222222",
        "block-cursor-blurred-foreground": "#FFFFFF",
        "block-cursor-blurred-text-style": "none",
    },
)
