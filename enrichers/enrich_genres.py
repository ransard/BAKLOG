"""Fill missing library genres using public Steam metadata, without credentials.

Reuse direct Steam IDs and the Reviews mapping before searching by title. Cache
matches and confirmed misses per profile; transient errors stay retryable.
Only genre fields are written. Existing usable store genres always win.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from clients.itch_game import itch_is_videogame
from clients.steam_client import SteamClient
from clients.steam_metadata import enrichment_from_appdetails
from fetchers._base import catalog_file, configure_stdout, write_catalog_text
from fetchers._progress import HeartbeatTimer, RunStats, started
from fetchers.registry import LIBRARY_JSON_BY_KEY
from shared.library_genres import usable_genres
from shared.profile_paths import cache_json_path
from shared.safe_write import atomic_write_text
from shared.steam_match import appid_from_steam_url, pick_appid

SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
SEARCH_DELAY_SEC = 0.4
SAVE_EVERY = 25


def load_cache(filename: str) -> dict:
    try:
        data = json.loads(cache_json_path(filename).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def positive_appid(raw: object) -> int | None:
    if isinstance(raw, bool):
        return None
    try:
        value = int(raw)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def direct_appid(store: str, game: dict) -> int | None:
    if store == "steam":
        return positive_appid(game.get("id"))
    for field in ("steam_app_id", "humble_steam_app_id", "steam_appid"):
        if appid := positive_appid(game.get(field)):
            return appid
    return appid_from_steam_url(game.get("steam_url")) or appid_from_steam_url(game.get("store_url"))


def search_appid(name: str) -> int | None:
    """A successful empty result is a miss; HTTP/parse errors must propagate."""
    time.sleep(SEARCH_DELAY_SEC)
    response = requests.get(
        SEARCH_URL,
        params={"term": name, "l": "english", "cc": "us"},
        headers={"User-Agent": "Mozilla/5.0 backlog/1.0"},
        timeout=20,
    )
    response.raise_for_status()
    items = response.json().get("items")
    if not isinstance(items, list):
        raise ValueError("Steam search did not return an items list")
    return pick_appid(items, name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill missing library genres from Steam metadata.")
    parser.add_argument("--stores", nargs="+", choices=sorted(LIBRARY_JSON_BY_KEY))
    parser.add_argument("--retry-misses", action="store_true", help="Retry cached unmatched titles or missing genres.")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch metadata for games still missing genres.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing catalogs or genre cache")
    args = parser.parse_args(argv)
    configure_stdout()
    t0 = started("enrich_genres")
    stats = RunStats()
    cache = load_cache("genres_map.json")
    matches = cache.setdefault("by_key", {})
    if not isinstance(matches, dict):
        matches = cache["by_key"] = {}
    review_map = load_cache("steam_review_map.json")
    steam = SteamClient(api_key="", steam_id="")
    hb = HeartbeatTimer(25.0)
    details_by_appid: dict[int, list[str]] = {}
    searches: dict[str, int | None] = {}

    def save_cache() -> None:
        if not args.dry_run:
            cache["fetched_at"] = datetime.now(UTC).isoformat()
            cache["rows_updated"] = stats.ok
            atomic_write_text(cache_json_path("genres_map.json"), json.dumps(cache, indent=2, ensure_ascii=False))

    for store, filename in LIBRARY_JSON_BY_KEY.items():
        if args.stores and store not in args.stores:
            continue
        rel = Path(filename)
        path = catalog_file(rel)
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        games = data.get("games", [])
        updated = 0
        checked = 0
        print(f"\n=== {filename} ({len(games)} rows) ===", flush=True)
        for i, game in enumerate(games, 1):
            hb.tick_progress(i, len(games), f"genres {filename}", f"{updated} updated")
            if store == "itch" and not itch_is_videogame(game):
                continue
            if usable_genres(game.get("genres")):
                continue
            key = f"{store}:{game.get('id')}"
            cached = matches.get(key)
            appid = direct_appid(store, game) or positive_appid(review_map.get(key))
            if not appid and isinstance(cached, dict):
                appid = positive_appid(cached.get("appid"))
            # A newly available direct/review match supersedes an old search miss.
            if cached is False and not appid and not args.retry_misses:
                continue
            checked += 1
            try:
                if not appid:
                    if store == "steam":
                        continue  # Never search for a replacement for an invalid Steam ID.
                    name = str(game.get("name") or "").strip()
                    if not name:
                        continue
                    if name not in searches:
                        searches[name] = search_appid(name)
                    appid = searches[name]
                if not appid:
                    matches[key] = False
                else:
                    if (
                        isinstance(cached, dict) and cached.get("appid") == appid
                        and not args.refresh and (cached.get("genres") or not args.retry_misses)
                    ):
                        genres = usable_genres(cached.get("genres"))
                    else:
                        if appid not in details_by_appid:
                            result = steam.get_app_details(appid, refresh=args.refresh or args.retry_misses)
                            if not isinstance(result, dict) or "success" not in result:
                                raise ValueError("Steam returned no app details")
                            details = result.get("data") if result.get("success") else None
                            if result.get("success") and not isinstance(details, dict):
                                raise ValueError("Steam returned malformed app details")
                            details_by_appid[appid] = usable_genres(enrichment_from_appdetails(details)["genres"])
                        genres = details_by_appid[appid]
                    matches[key] = {"appid": appid, "genres": genres}
                    if genres:
                        game["genres"] = genres
                        updated += 1
                        stats.ok += 1
            except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
                stats.warn(f"Genre lookup failed for {game.get('name')}: {exc}")
                continue
            if checked % SAVE_EVERY == 0:
                if updated and not args.dry_run:
                    write_catalog_text(rel, json.dumps(data, indent=2, ensure_ascii=False))
                save_cache()
                print(f"  [{i}/{len(games)}] {updated} genres filled", flush=True)
        if updated and not args.dry_run:
            write_catalog_text(rel, json.dumps(data, indent=2, ensure_ascii=False))
        save_cache()
        print(f"  genres filled: {updated}" + (" [dry run]" if args.dry_run else ""), flush=True)
    save_cache()
    return stats.finish("enrich_genres", t0, exit_code=0, extra=f"{stats.ok} rows updated")


if __name__ == "__main__":
    raise SystemExit(main())
