"""Genre presence rules shared with the dashboard's js/genres.js."""

from __future__ import annotations

# Sync with NON_GENRE_TOKENS in js/genres.js (checked by test_library_genres).
NON_GENRE_TOKENS = frozenset({
    "ps3", "ps4", "ps5", "psp", "ps vita", "psvita", "vita",
    "xbox", "xbox 360", "xbox one", "xbox series x", "xbox series s",
    "xbox series x|s", "xbox series x/s", "xbox series",
    "nintendo switch", "switch", "wii", "wii u", "ds", "3ds", "nintendo ds", "nintendo 3ds",
    "pc", "windows", "mac", "macos", "osx", "linux", "steamos",
    "ios", "android", "browser", "stadia", "google stadia",
    "default", "html", "html5", "flash", "java", "unity", "godot",
    "physical_game", "physical game", "assets", "asset_pack", "asset pack",
    "tool", "book", "comic", "soundtrack", "other", "early access", "early-access",
})


def usable_genres(raw: object) -> list[str]:
    """Ignore blanks and platform/classification tokens when checking coverage."""
    if not isinstance(raw, list):
        return []
    return list(dict.fromkeys(
        value.strip() for value in raw
        if isinstance(value, str) and value.strip() and value.strip().lower() not in NON_GENRE_TOKENS
    ))
