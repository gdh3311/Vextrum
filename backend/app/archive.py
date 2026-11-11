"""Closed-season rankings and the last available detailed snapshot per Pokémon."""
from datetime import datetime
from functools import lru_cache
from time import sleep
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import json
import os
import tempfile

from . import collector


@lru_cache(maxsize=1)
def _index(version: str) -> tuple[dict, dict, dict]:
    data = collector.load_json(collector.CACHE / "index.json")
    summaries, names, dates = {}, {}, {}
    for entry in data["pokemon"]:
        pid = entry["showdownId"]
        summaries[pid] = entry["summary"].get("battleSummary", {})
        for name in (entry["name"], entry["battleName"], entry["showdownName"], entry["slug"]):
            names[name] = names[collector.tid(name)] = pid
    for folder in data.get("dailyDataFolders", []):
        season, day = folder.split("/", 1)
        dates.setdefault(season, _date(day))
    return summaries, names, dates


def _date(value: str) -> str:
    return datetime.strptime(value, "%d_%m_%Y").date().isoformat()


def summary(e, season: str, fmt: str, pid: str) -> dict:
    return _index(e.d["dataVersion"])[0].get(pid, {}).get(season, {}).get(fmt, {})


def date(e, season: str) -> str | None:
    return _index(e.d["dataVersion"])[2].get(season)


def rank(p: dict, season: str, fmt: str) -> int | None:
    return p["ranks"].get(season, {}).get(fmt)


@lru_cache(maxsize=256)
def _snapshot(version: str, season: str, fmt: str, pid: str) -> dict | None:
    expected_date = _index(version)[2].get(season, "undated")
    path = collector.CACHE / "seasons" / season / expected_date / fmt / f"{pid}.json"
    if path.exists():
        return collector.load_json(path)
    query = urlencode({"season": season, "days": 1})
    url = f"{collector.BASE}/api/battle/{fmt}/{quote(pid, safe='')}?{query}"
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers=collector.UA), timeout=4) as response:
                data = json.load(response)
            break
        except HTTPError as error:
            if error.code == 404:
                return None
            if error.code < 500 or attempt:
                raise
        except (OSError, ValueError):
            if attempt:
                raise
        sleep(.2)
    snapshot = next((row for row in data["daily"] if row["season"] == season and row["rows"]), None)
    if snapshot:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode="w", encoding="utf-8") as tmp:
            temporary = tmp.name
            json.dump(snapshot, tmp, ensure_ascii=False)
        try:
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return snapshot


def usage(e, season: str, fmt: str, pid: str) -> tuple[dict | None, str | None]:
    snapshot = _snapshot(e.d["dataVersion"], season, fmt, pid)
    if snapshot is None:
        return None, None
    _, names, _ = _index(e.d["dataVersion"])
    return collector.parse_usage(snapshot["rows"], names), _date(snapshot["date"])


def preview(e, season: str, fmt: str, pid: str) -> dict | None:
    """Keep the archive usable offline with the published season summary."""
    data = summary(e, season, fmt, pid)
    _, names, _ = _index(e.d["dataVersion"])
    usage = collector.parse_usage(list(data.get("top", {}).values()), names)
    if usage is None:
        return None
    values = data.get("values", {})
    for category, key in (("move", "moves"), ("held_item", "items"), ("ability", "abilities"),
                          ("stat_alignment", "natures")):
        available = {row["name"]: row for row in usage[key]}
        usage[key] = [available.get(name, {"name": name, "pct": None}) for name in values.get(category, [])]
    usage["teammates"] = [
        matched for name in values.get("teammate", [])
        if (matched := names.get(name) or names.get(collector.tid(name)))
    ]
    return usage
