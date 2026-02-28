"""Theme definitions for Claude Chic.

Custom themes can be defined in ~/.claude/.claudechic.yaml:

    themes:
      moonfly:
        primary: "#80a0ff"
        secondary: "#ae81ff"
        accent: "#36c692"
        background: "#080808"
        surface: "#121212"
        panel: "#323437"
        success: "#8cc85f"
        warning: "#e3c78a"
        error: "#ff5d5d"

    theme: moonfly  # Set as active theme

Use /theme to search and switch between available themes.
"""

from textual.theme import BUILTIN_THEMES, Theme

from claudechic.config import CONFIG

# Default Claude Chic theme - orange accent, dark background
CHIC_THEME = Theme(
    name="chic",
    primary="#cc7700",
    secondary="#5599dd",  # Sky blue for syntax highlighting
    accent="#445566",
    background="black",
    surface="#111111",
    panel="#555555",  # Used for borders and subtle UI elements
    success="#5599dd",  # Same as secondary - strings in code
    warning="#aaaa00",  # Yellow - moderate usage/caution
    error="#cc3333",  # Red - high usage/errors
    dark=True,
)

# Light variant - same hues, adjusted for white background
CHIC_LIGHT_THEME = Theme(
    name="chic-light",
    primary="#b56600",  # Darker orange for contrast on white
    secondary="#2277bb",  # Darker blue for readability
    accent="#667788",  # Lighter gray-blue (visible on white)
    background="#ffffff",
    surface="#f0f0f0",  # Light gray for panels
    panel="#cccccc",  # Light gray for borders
    success="#2277bb",  # Match secondary
    warning="#997700",  # Darker yellow-orange
    error="#cc3333",  # Red works on both
    dark=False,
)


# Fields that custom themes can override
_THEME_FIELDS = (
    "primary",
    "secondary",
    "warning",
    "error",
    "success",
    "accent",
    "foreground",
    "background",
    "surface",
    "panel",
    "boost",
    "dark",
)
_CHIC_DEFAULTS = {f: getattr(CHIC_THEME, f) for f in _THEME_FIELDS}


def get_available_theme_names() -> set[str]:
    """Return names of all available themes (Textual built-in + claudechic + custom)."""
    names = set(BUILTIN_THEMES.keys()) | {"chic", "chic-light"}
    for name, colors in CONFIG.get("themes", {}).items():
        if isinstance(colors, dict):
            names.add(name)
    return names


def load_custom_themes() -> list[Theme]:
    """Load custom themes from config file.

    Returns list of Theme objects defined in ~/.claude/.claudechic.yaml
    Missing values inherit from CHIC_THEME defaults.
    """
    themes_config = CONFIG.get("themes", {})
    custom_themes = []

    for name, colors in themes_config.items():
        if not isinstance(colors, dict):
            continue
        theme = Theme(name=name, **{**_CHIC_DEFAULTS, **colors})
        custom_themes.append(theme)

    return custom_themes
