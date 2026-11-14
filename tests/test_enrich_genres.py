"""Offline genre backfill, cache, retry, and profile isolation regressions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from enrichers import enrich_genres as enricher


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from shared import profile_paths

    monkeypatch.setattr(profile_paths, "profile_root", lambda profile_id=None: tmp_path)
    monkeypatch.setattr(enricher, "configure_stdout", lambda: None)
    monkeypatch.setattr(enricher, "search_appid", lambda name: pytest.fail(f"unexpected search: {name}"))
    monkeypatch.setattr(enricher.SteamClient, "get_app_details", lambda *a, **kw: pytest.fail("unexpected details"))
    return tmp_path


def catalog(root: Path, store: str, games: list[dict]) -> Path:
    path = root / f"games_{store}.json"
    path.write_text(json.dumps({"fetched_at": "original", "game_count": len(games), "games": games}), encoding="utf-8")
    return path


def rows(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["games"]


def put_cache(root: Path, name: str, data: dict) -> None:
    (root / "cache").mkdir(exist_ok=True)
    (root / "cache" / name).write_text(json.dumps(data), encoding="utf-8")


def details(genres: list[str]) -> dict:
    return {"success": True, "data": {"genres": [{"description": g} for g in genres], "developers": ["Untouched"]}}


def test_fills_all_stores_without_credentials_and_preserves_populated_genres(workspace, monkeypatch):
    steam = catalog(workspace, "steam", [{"id": 10, "name": "Native", "genres": []}])
    gog = catalog(workspace, "gog", [
        {"id": "mapped", "name": "Mapped", "genres": None},
        {"id": "search", "name": "Search Me"},
        {"id": "keep", "name": "Keep", "genres": ["Puzzle"]},
    ])
    humble = catalog(workspace, "humble", [{"id": "h", "name": "Direct", "humble_steam_app_id": 10}])
    itch = catalog(workspace, "itch", [
        {"id": "game", "name": "Itch", "genres": ["Windows", " ", "html"], "steam_app_id": 10},
        {"id": "tool", "name": "Tool", "classification": "tool"},
    ])
    put_cache(workspace, "steam_review_map.json", {"gog:mapped": 10})
    search_calls = []
    detail_calls = []
    monkeypatch.setattr(enricher, "search_appid", lambda name: search_calls.append(name) or 10)
    monkeypatch.setattr(enricher.SteamClient, "get_app_details",
                        lambda self, appid, refresh=False: detail_calls.append(appid) or details(["Action", "RPG"]))
    assert enricher.main([]) == 0
    for path in (steam, humble):
        assert rows(path)[0]["genres"] == ["Action", "RPG"]
        assert "developers" not in rows(path)[0]
        assert json.loads(path.read_text())["fetched_at"] == "original"
    assert [g["genres"] for g in rows(gog)] == [["Action", "RPG"], ["Action", "RPG"], ["Puzzle"]]
    assert rows(itch)[0]["genres"] == ["Action", "RPG"]
    assert "genres" not in rows(itch)[1]
    assert search_calls == ["Search Me"]
    assert detail_calls == [10]
    assert json.loads((workspace / "cache/genres_map.json").read_text())["rows_updated"] == 5


def test_caches_misses_and_shift_retry_refreshes_missing_only(workspace, monkeypatch):
    path = catalog(workspace, "gog", [
        {"id": "a", "name": "Absent"}, {"id": "b", "name": "No Genres", "steam_app_id": 20},
        {"id": "c", "name": "Keep", "genres": ["Puzzle"]},
    ])
    monkeypatch.setattr(enricher, "search_appid", lambda name: None)
    monkeypatch.setattr(enricher.SteamClient, "get_app_details", lambda *a, **kw: details([]))
    assert enricher.main([]) == 0
    monkeypatch.setattr(enricher, "search_appid", lambda name: pytest.fail("miss must be skipped"))
    monkeypatch.setattr(enricher.SteamClient, "get_app_details", lambda *a, **kw: pytest.fail("cached empty"))
    assert enricher.main([]) == 0
    refreshes = []
    monkeypatch.setattr(enricher, "search_appid", lambda name: 30)
    monkeypatch.setattr(enricher.SteamClient, "get_app_details",
                        lambda self, appid, refresh=False: refreshes.append(refresh) or details(["Action"]))
    assert enricher.main(["--retry-misses", "--refresh"]) == 0
    assert [g["genres"] for g in rows(path)] == [["Action"], ["Action"], ["Puzzle"]]
    assert refreshes == [True, True]


@pytest.mark.parametrize("stage", ["search", "details"])
def test_network_failures_remain_retryable(workspace, monkeypatch, stage):
    path = catalog(workspace, "ea", [{"id": "a", "name": "Retry Me"}])
    monkeypatch.setattr(enricher, "search_appid", lambda name: 10)

    def fail(*args, **kwargs):
        raise requests.ConnectionError("offline")

    if stage == "search":
        monkeypatch.setattr(enricher, "search_appid", fail)
    else:
        monkeypatch.setattr(enricher.SteamClient, "get_app_details", fail)
    assert enricher.main([]) == 0
    assert rows(path) == [{"id": "a", "name": "Retry Me"}]
    cache = json.loads((workspace / "cache/genres_map.json").read_text())
    assert "ea:a" not in cache["by_key"]
    monkeypatch.setattr(enricher, "search_appid", lambda name: 10)
    monkeypatch.setattr(enricher.SteamClient, "get_app_details", lambda *a, **kw: details(["Strategy"]))
    assert enricher.main([]) == 0
    assert rows(path)[0]["genres"] == ["Strategy"]


def test_dry_run_and_store_filter(workspace, monkeypatch):
    path = catalog(workspace, "steam", [{"id": 10, "name": "Native"}])
    other = catalog(workspace, "gog", [{"id": "g", "name": "Excluded"}])
    before = path.read_bytes()
    other_before = other.read_bytes()
    monkeypatch.setattr(enricher.SteamClient, "get_app_details", lambda *a, **kw: details(["Action"]))
    assert enricher.main(["--dry-run", "--stores", "steam"]) == 0
    assert path.read_bytes() == before
    assert other.read_bytes() == other_before
    assert not (workspace / "cache/genres_map.json").exists()


def test_recovers_genres_from_cache_and_new_review_match(workspace, monkeypatch):
    path = catalog(workspace, "xbox", [{"id": "cached", "name": "Cached"}, {"id": "old-miss", "name": "New Map"}])
    put_cache(workspace, "genres_map.json", {"by_key": {
        "xbox:cached": {"appid": 10, "genres": ["RPG"]}, "xbox:old-miss": False,
    }})
    put_cache(workspace, "steam_review_map.json", {"xbox:old-miss": 20})
    monkeypatch.setattr(enricher.SteamClient, "get_app_details", lambda *a, **kw: details(["Action"]))
    assert enricher.main([]) == 0
    assert [g["genres"] for g in rows(path)] == [["RPG"], ["Action"]]


def test_malformed_details_are_not_cached_as_a_miss(workspace, monkeypatch):
    catalog(workspace, "steam", [{"id": 10, "name": "Native"}])
    monkeypatch.setattr(enricher.SteamClient, "get_app_details", lambda *a, **kw: {"success": True, "data": None})
    assert enricher.main([]) == 0
    assert json.loads((workspace / "cache/genres_map.json").read_text())["by_key"] == {}


def test_search_rejects_sequels_and_propagates_http_errors(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"items": [{"id": 20, "name": "Portal 2"}]}

    monkeypatch.setattr(enricher.time, "sleep", lambda _: None)
    monkeypatch.setattr(enricher.requests, "get", lambda *a, **kw: Response())
    assert enricher.search_appid("Portal") is None
    monkeypatch.setattr(Response, "raise_for_status", lambda self: (_ for _ in ()).throw(requests.HTTPError("429")))
    with pytest.raises(requests.HTTPError):
        enricher.search_appid("Portal")
