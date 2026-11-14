"""Keep genre-presence semantics aligned with dashboard filtering."""

import json
import re
from pathlib import Path

from shared.library_genres import NON_GENRE_TOKENS, usable_genres


def test_non_genre_tokens_match_frontend():
    source = (Path(__file__).resolve().parents[1] / "js/genres.js").read_text(encoding="utf-8")
    body = source.split("new Set([", 1)[1].split("]);", 1)[0]
    tokens = {json.loads(token) for token in re.findall(r'"[^"\n]+"', body)}
    assert tokens == NON_GENRE_TOKENS


def test_usable_genres():
    assert usable_genres([None, " ", "Windows", "Early Access", "Action", " Action "]) == ["Action"]
    assert usable_genres(None) == []
    assert usable_genres("Action") == []
