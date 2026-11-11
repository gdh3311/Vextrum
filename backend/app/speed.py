"""스피드 티어: 메타 상위권의 실전 스피드(채용 통계 기반)와 내 팀의 스피드를 한 줄에 놓고 비교한다.

레퍼런스(Game8 스피드 체커, Pikalytics 스피드 티어)처럼 한 포켓몬의 대표 스피드 여러 개를 보여 주되,
"가장 많이 쓰는 분배·성격"으로 계산한 주력 세트 스피드를 정렬 기준으로 삼는다.
"""
from __future__ import annotations

from .engine import Engine
from .typechart import NATURES


def _speed(e: Engine, base: dict, fmt: str, nature: str, spe: int) -> int:
    points = {**(base.get("points") or {}), "spe": spe}
    return e.resolve({**base, "nature": nature, "points": points}, fmt)["stats"]["spe"]


def meta_rows(e: Engine, fmt: str, top_n: int) -> list[dict]:
    rows = []
    for p in e.ranked(fmt)[:top_n]:
        u = p["usage"][fmt]
        base = e.default_set(p["id"], fmt)
        r = e.resolve(base, fmt)
        natures = {n["name"]: n["pct"] for n in u.get("natures", [])}
        spreads = u.get("spreads", [])
        plus = sum(pct for n, pct in natures.items() if NATURES.get(n, (None, None))[0] == "spe")
        minus = sum(pct for n, pct in natures.items() if NATURES.get(n, (None, None))[1] == "spe")
        invested = sum(s["pct"] for s in spreads if s.get("spe", 0) >= 28)
        scarf = next((i["pct"] for i in u.get("items", []) if i["name"] == "Choice Scarf"), 0)
        rows.append({
            "id": p["id"], "name": r["name"], "ko": r["ko"], "sprite": r["sprite"], "types": r["types"],
            "rank": u["rank"], "mega": r["mega"],
            "common": r["stats"]["spe"],
            "max": _speed(e, base, fmt, "Jolly" if r["stats"]["atk"] >= r["stats"]["spa"] else "Timid", 32),
            "neutral": _speed(e, base, fmt, "Hardy", 32),
            "uninvested": _speed(e, base, fmt, "Hardy", 0),
            "min": _speed(e, base, fmt, "Brave" if r["stats"]["atk"] >= r["stats"]["spa"] else "Quiet", 0),
            "plusPct": round(plus, 1), "minusPct": round(minus, 1), "investedPct": round(invested, 1),
            "scarfPct": round(scarf, 1),
        })
    rows.sort(key=lambda x: -x["common"])
    return rows


def team_rows(e: Engine, fmt: str, sets: list[dict]) -> list[dict]:
    out = []
    for s in sets:
        if s.get("id") not in e.P:
            continue
        r = e.resolve(s, fmt)
        out.append({"id": r["id"], "name": r["name"], "ko": r["ko"], "sprite": r["sprite"], "types": r["types"],
                    "speed": round(r["speed"]), "stat": r["stats"]["spe"], "item": r["item"],
                    "scarf": r["item"] == "Choice Scarf"})
    return out
