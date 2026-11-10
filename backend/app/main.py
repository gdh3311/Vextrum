"""Champions Meta Lab API.

    uvicorn app.main:app --port 8000
"""
from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import collector
from .engine import ROLE_LABELS, Engine, weight

Format = Literal["Doubles", "Singles"]

app = FastAPI(title="Champions Meta Lab")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_engine: Engine | None = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        if not collector.DATASET.exists():
            collector.collect()
        _engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
    return _engine


def brief(e: Engine, p: dict, fmt: str) -> dict:
    u = p["usage"].get(fmt)
    return {"id": p["id"], "name": p["name"], "ko": p["ko"], "sprite": p["sprite"], "types": p["types"],
            "rank": u["rank"] if u else None}


def past_ranks(fmt: str, days: int) -> dict[str, int]:
    """자체 스냅샷에서 N일 전(또는 그 이전 가장 가까운 날)의 순위."""
    if not collector.HISTORY_DB.exists():
        return {}
    con = sqlite3.connect(collector.HISTORY_DB)
    try:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        row = con.execute("SELECT MAX(day) FROM rank_snapshots WHERE format=? AND day<=?", (fmt, cutoff)).fetchone()
        if not row or not row[0]:
            return {}
        return dict(con.execute("SELECT pokemon_id, rank FROM rank_snapshots WHERE format=? AND day=?",
                                (fmt, row[0])).fetchall())
    finally:
        con.close()


@app.get("/api/info")
def info():
    e = engine()
    d = e.d
    seasons = [s for s in d["seasons"] if s != "Current"]
    return {"generatedAt": d["generatedAt"], "dataVersion": d["dataVersion"], "seasons": seasons,
            "currentSeason": seasons[0] if seasons else None, "formats": d["formats"],
            "attribution": d["attribution"], "source": d["source"], "roles": ROLE_LABELS,
            "natures": {n: {"ko": d["natures"].get(n), "up": collector_nature(n)[0], "down": collector_nature(n)[1]}
                        for n in sorted(d["natures"])}}


def collector_nature(n: str):
    from .typechart import NATURES
    return NATURES.get(n, (None, None))


@app.get("/api/meta")
def meta(format: Format = "Doubles", top: int = Query(50, ge=5, le=300)):
    e = engine()
    d = e.d
    seasons = [s for s in d["seasons"] if s != "Current"]
    prev_season = seasons[1] if len(seasons) > 1 else None
    week = past_ranks(format, 7)
    ranked = e.ranked(format)
    rows = []
    for p in ranked:
        u = p["usage"][format]
        prev = p["ranks"].get(prev_season, {}).get(format) if prev_season else None
        s = e.default_set(p["id"], format)
        r = e.default_resolved(p["id"], format)
        rows.append({**brief(e, p, format), "prevRank": prev, "delta": (prev - u["rank"]) if prev else None,
                     "weekDelta": (week[p["id"]] - u["rank"]) if p["id"] in week else None,
                     "isNew": prev is None, "topItem": s["item"],
                     "topItemKo": (d["items"].get(s["item"]) or {}).get("ko"),
                     "topMoves": [{"name": m, "ko": d["moves"][m]["ko"], "type": d["moves"][m]["type"]}
                                  for m in s["moves"] if m in d["moves"]],
                     "megaSprite": r["sprite"] if r["mega"] else None,
                     "megaName": r["name"] if r["mega"] else None, "megaKo": r["ko"] if r["mega"] else None})
    movers = [r for r in rows if r["delta"] is not None and r["rank"] <= 80]
    rising = sorted([r for r in movers if r["delta"] >= 5], key=lambda r: -r["delta"] / (r["rank"] ** 0.5))[:8]
    falling = sorted([r for r in movers if r["delta"] <= -5], key=lambda r: r["delta"] / (r["rank"] ** 0.5))[:8]

    def aggregate(kind: str, n: int = 12, scope: int = 50):
        acc: dict[str, float] = {}
        wsum = 0.0
        for p in ranked[:scope]:
            u = p["usage"][format]
            w = weight(u["rank"])
            wsum += w
            for x in u[kind]:
                acc[x["name"]] = acc.get(x["name"], 0) + w * x["pct"]
        ko = d["moves"] if kind == "moves" else d["items"] if kind == "items" else d["abilities"]
        return [{"name": k, "ko": (ko.get(k) or {}).get("ko"), "share": round(v / wsum, 1),
                 **({"type": d["moves"][k]["type"]} if kind == "moves" and k in d["moves"] else {})}
                for k, v in sorted(acc.items(), key=lambda kv: -kv[1])[:n]]

    megas = []
    for p in ranked[:120]:
        u = p["usage"][format]
        for it in u["items"]:
            m = e.find_mega(p, stone=it["name"])
            if m and it["pct"] >= 10:
                megas.append({"id": p["id"], "name": m["name"], "ko": m["ko"], "sprite": m["sprite"],
                              "types": m["types"], "rank": u["rank"], "pct": it["pct"], "stone": it["name"],
                              "_s": weight(u["rank"]) * it["pct"]})
    megas.sort(key=lambda m: -m.pop("_s"))

    return {"format": format, "season": seasons[0] if seasons else None, "prevSeason": prev_season,
            "generatedAt": d["generatedAt"], "attribution": d["attribution"], "source": d["source"],
            "total": len(rows), "hasWeekTrend": bool(week), "ranking": rows[:top], "rising": rising,
            "falling": falling, "topMegas": megas[:10], "topMoves": aggregate("moves"),
            "topItems": aggregate("items"), "topAbilities": aggregate("abilities", 10)}


@app.get("/api/pokemon")
def pokemon_list():
    e = engine()
    out = []
    for p in e.P.values():
        out.append({"id": p["id"], "name": p["name"], "ko": p["ko"], "sprite": p["sprite"], "types": p["types"],
                    "ranks": {f: u["rank"] for f, u in p["usage"].items()},
                    "megas": [{"name": m["name"], "ko": m["ko"], "sprite": m["sprite"]} for m in p["megas"]]})
    return out


@app.get("/api/pokemon/{pid}")
def pokemon_detail(pid: str, format: Format = "Doubles"):
    e = engine()
    p = e.P.get(pid)
    if not p:
        raise HTTPException(404, "unknown pokemon")
    d = e.d
    u = p["usage"].get(format)

    def named(rows, table):
        return [{**r, "ko": (table.get(r["name"]) or {}).get("ko")} for r in rows]

    usage = None
    if u:
        usage = {
            "rank": u["rank"],
            "moves": [{**r, "ko": d["moves"][r["name"]]["ko"], "type": d["moves"][r["name"]]["type"],
                       "category": d["moves"][r["name"]]["category"], "power": d["moves"][r["name"]]["power"]}
                      for r in u["moves"] if r["name"] in d["moves"]],
            "items": named(u["items"], d["items"]), "abilities": named(u["abilities"], d["abilities"]),
            "natures": [{**r, "ko": d["natures"].get(r["name"])} for r in u["natures"]],
            "spreads": u["spreads"],
            "teammates": [brief(e, e.P[t], format) for t in u["teammates"] if t in e.P],
        }
    seasons = [s for s in reversed(d["seasons"]) if s != "Current"]
    return {
        **brief(e, p, format), "abilities": [{"name": a, "ko": (d["abilities"].get(a) or {}).get("ko")}
                                             for a in p["abilities"]],
        "stats": p["stats"],
        "megas": [{**m, "abilities": [{"name": a, "ko": (d["abilities"].get(a) or {}).get("ko")}
                                      for a in m["abilities"]]} for m in p["megas"]],
        "usage": usage,
        "history": [{"season": s, "rank": p["ranks"].get(s, {}).get(format)} for s in seasons],
        "learnset": [{"name": m, **{k: d["moves"][m][k] for k in ("ko", "type", "category", "power", "accuracy",
                                                                   "priority")}} for m in p["learnset"]],
        "defaultSet": e.default_set(pid, format),
        "resolved": e.describe(e.default_resolved(pid, format), format),
        **(e.counters_and_targets(pid, format) if u else {"counters": [], "targets": []}),
    }


@app.get("/api/items")
def items():
    e = engine()
    stones = {m["stone"] for p in e.P.values() for m in p["megas"] if m["stone"]}
    return [{"name": n, "ko": v["ko"], "stone": n in stones} for n, v in e.d["items"].items()]


class TeamSet(BaseModel):
    id: str
    moves: list[str] | None = None
    item: str | None = None
    ability: str | None = None
    nature: str | None = None
    points: dict[str, int] | None = None
    mega: str | None = None


class TeamRequest(BaseModel):
    format: Format = "Doubles"
    team: list[TeamSet]
    topN: int = 20


@app.post("/api/team/analyze")
def analyze(req: TeamRequest):
    e = engine()
    sets = [s.model_dump(exclude_unset=True) for s in req.team[:6]]
    return e.analyze_team(sets, req.format, max(5, min(50, req.topN)))


class EnemyRequest(BaseModel):
    format: Format = "Doubles"
    enemy: list[str]
    team: list[TeamSet] = []


@app.post("/api/enemy/analyze")
def analyze_enemy(req: EnemyRequest):
    from . import enemy as enemy_mod

    sets = [s.model_dump(exclude_unset=True) for s in req.team[:6]]
    return enemy_mod.analyze_enemy(engine(), req.enemy[:6], sets, req.format)


@app.get("/api/jokers")
def jokers(format: Format = "Doubles", minRank: int = Query(50, ge=10, le=260), topN: int = Query(20, ge=5, le=50),
           role: str | None = None, type: str | None = None):
    e = engine()
    return {"format": format, "minRank": minRank, "topN": topN, "total": len(e.ranked(format)),
            "meta": [brief(e, e.P[b["id"]], format) for b in e.meta(format, topN)],
            "jokers": e.jokers(format, minRank, topN, role or None, type or None)}


@app.post("/api/refresh")
def refresh():
    """원본 사이트에서 새 데이터를 받아 다시 계산한다."""
    global _engine
    collector.collect()
    _engine = None
    return {"dataVersion": engine().d["dataVersion"]}


# ---------- 이미지 프록시 (디스크 캐시) ----------
IMG_DIRS = {"pokemon": "pokemon", "item": "items", "type": "types"}
SAFE_NAME = re.compile(r"^[\w .'’:%\-éÉ]+$")


@app.get("/img/{kind}/{name}")
def image(kind: str, name: str):
    name = name.removesuffix(".png")
    if kind not in IMG_DIRS or not SAFE_NAME.match(name) or ".." in name:
        raise HTTPException(404)
    path = collector.CACHE / "img" / kind / f"{name}.png"
    if not path.exists():
        url = f"{collector.BASE}/pokemon_champions_assets/{IMG_DIRS[kind]}/{urllib.parse.quote(name)}.png"
        try:
            collector.fetch(url, path, retries=1)
        except Exception:
            raise HTTPException(404)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})


# ---------- Flutter 웹 빌드가 있으면 같은 서버에서 서빙 ----------
WEB_DIR = collector.DATA_DIR.parent.parent / "app" / "build" / "web"
if WEB_DIR.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
