"""Champions Meta Lab API.

    uvicorn app.main:app --port 8000
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import archive, battle_lab, collector, parties, season_notice, simulation
from .engine import ROLE_LABELS, Engine, weight

Format = Literal["Doubles", "Singles"]

app = FastAPI(title="Champions Meta Lab")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_name_tables: dict | None = None


@app.middleware("http")
async def localize_names(request, call_next):
    """X-Lang: en|ja 요청이면 응답 JSON의 한국어 이름을 그 언어 이름으로 바꾼다 (app/names.py)."""
    global _name_tables
    lang = request.headers.get("x-lang", "ko")
    response = await call_next(request)
    if lang not in ("en", "ja") or not response.headers.get("content-type", "").startswith("application/json"):
        return response
    from fastapi.responses import Response

    from . import names

    body = b"".join([chunk async for chunk in response.body_iterator])
    try:
        if _name_tables is None:
            _name_tables = names.build(engine().d)
        body = names.translate_body(body, _name_tables[lang])
    except Exception:  # 변환에 실패해도 원래 응답은 보낸다
        pass
    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    return Response(content=body, status_code=response.status_code, headers=headers, media_type="application/json")

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


def selected_season(e: Engine, season: str | None) -> tuple[str | None, list[str]]:
    seasons = [s for s in e.d["seasons"] if s != "Current"]
    if season and season not in seasons:
        raise HTTPException(404, "unknown season")
    return season or (seasons[0] if seasons else None), seasons


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
def meta(format: Format = "Doubles", top: int = Query(50, ge=5, le=300), season: str | None = None):
    e = engine()
    d = e.d
    season, seasons = selected_season(e, season)
    historical = bool(seasons and season != seasons[0])
    index = seasons.index(season) if season else -1
    prev_season = seasons[index + 1] if index + 1 < len(seasons) else None
    week = {} if historical else past_ranks(format, 7)
    ranked = (sorted((p for p in e.P.values() if archive.rank(p, season, format)),
                     key=lambda p: archive.rank(p, season, format)) if historical else e.ranked(format))
    rows = []
    for p in ranked:
        prev = p["ranks"].get(prev_season, {}).get(format) if prev_season else None
        if historical:
            rank = archive.rank(p, season, format)
            values = archive.summary(e, season, format, p["id"]).get("values", {})
            item = next(iter(values.get("held_item", [])), None)
            moves = values.get("move", [])[:4]
        else:
            rank = p["usage"][format]["rank"]
            s = e.default_set(p["id"], format)
            item, moves = s["item"], s["moves"]
        mega = e.find_mega(p, stone=item)
        rows.append({**brief(e, p, format), "rank": rank, "prevRank": prev, "delta": (prev - rank) if prev else None,
                     "weekDelta": (week[p["id"]] - rank) if p["id"] in week else None,
                     "isNew": prev is None, "topItem": item,
                     "topItemKo": (d["items"].get(item) or {}).get("ko"),
                     "topMoves": [{"name": m, "ko": d["moves"][m]["ko"], "type": d["moves"][m]["type"]}
                                  for m in moves if m in d["moves"]],
                     "megaSprite": mega["sprite"] if mega else None,
                     "megaName": mega["name"] if mega else None, "megaKo": mega["ko"] if mega else None})
    movers = [r for r in rows if r["delta"] is not None and r["rank"] <= 80]
    rising = sorted([r for r in movers if r["delta"] >= 5], key=lambda r: -r["delta"] / (r["rank"] ** 0.5))[:8]
    falling = sorted([r for r in movers if r["delta"] <= -5], key=lambda r: r["delta"] / (r["rank"] ** 0.5))[:8]
    result = {"format": format, "season": season, "seasons": seasons, "historical": historical,
              "officialSeason": season_notice.active_notice(e),
              "prevSeason": prev_season, "generatedAt": archive.date(e, season) if historical else d["generatedAt"],
              "attribution": d["attribution"], "source": d["source"], "total": len(rows), "hasWeekTrend": bool(week),
              "ranking": rows[:top], "rising": rising, "falling": falling}
    if historical:
        return {**result, "topMegas": [], "topMoves": [], "topItems": [], "topAbilities": []}

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

    return {**result, "topMegas": megas[:10], "topMoves": aggregate("moves"),
            "topItems": aggregate("items"), "topAbilities": aggregate("abilities", 10)}


@app.get("/api/pokemon")
def pokemon_list():
    e = engine()
    out = []
    for p in e.P.values():
        out.append({"id": p["id"], "name": p["name"], "ko": p["ko"], "sprite": p["sprite"], "types": p["types"],
                    "ranks": {f: u["rank"] for f, u in p["usage"].items()},
                    "megas": [{"name": m["name"], "ko": m["ko"], "sprite": m["sprite"], "stone": m["stone"]}
                              for m in p["megas"]]})
    return out


@app.get("/api/pokemon/{pid}")
def pokemon_detail(pid: str, format: Format = "Doubles", season: str | None = None):
    e = engine()
    p = e.P.get(pid)
    if not p:
        raise HTTPException(404, "unknown pokemon")
    d = e.d
    season, seasons = selected_season(e, season)
    historical = bool(seasons and season != seasons[0])
    snapshot_date = None
    preview_only = False
    rank = archive.rank(p, season, format) if historical else e.rank(pid, format)
    if historical and rank:
        try:
            u, snapshot_date = archive.usage(e, season, format, pid)
        except (OSError, ValueError):
            u = None
        if u is None:
            u = archive.preview(e, season, format, pid)
            preview_only = u is not None
            snapshot_date = archive.date(e, season)
    else:
        u = None if historical else p["usage"].get(format)

    def named(rows, table):
        return [{**r, "ko": (table.get(r["name"]) or {}).get("ko")} for r in rows]

    usage = None
    if u:
        usage = {
            "rank": rank,
            "moves": [{**r, **{key: d["moves"].get(r["name"], {}).get(key) for key in ("ko", "type", "category", "power")}}
                      for r in u["moves"]],
            "items": named(u["items"], d["items"]), "abilities": named(u["abilities"], d["abilities"]),
            "natures": [{**r, "ko": d["natures"].get(r["name"])} for r in u["natures"]],
            "spreads": u["spreads"],
            "teammates": [{**brief(e, e.P[t], format),
                           "rank": archive.rank(e.P[t], season, format) if historical else e.rank(t, format)}
                          for t in u["teammates"] if t in e.P],
        }
    seasons = [s for s in reversed(d["seasons"]) if s != "Current"]
    return {
        **brief(e, p, format), "rank": rank, "season": season, "snapshotDate": snapshot_date, "previewOnly": preview_only,
        "abilities": [{"name": a, "ko": (d["abilities"].get(a) or {}).get("ko")}
                                             for a in p["abilities"]],
        "stats": p["stats"],
        "megas": [{**m, "abilities": [{"name": a, "ko": (d["abilities"].get(a) or {}).get("ko")}
                                      for a in m["abilities"]]} for m in p["megas"]],
        "usage": usage,
        "history": [{"season": s, "rank": p["ranks"].get(s, {}).get(format)} for s in seasons],
        "learnset": [{"name": m, **{k: d["moves"][m][k] for k in ("ko", "type", "category", "power", "accuracy",
                                                                   "priority")}} for m in p["learnset"]],
        "defaultSet": None if historical else e.default_set(pid, format),
        "resolved": None if historical else e.describe(e.default_resolved(pid, format), format),
        **(e.counters_and_targets(pid, format) if u and not historical else {"counters": [], "targets": []}),
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


class AutoTeamRequest(BaseModel):
    format: Format = "Doubles"
    styles: list[str] = Field(default_factory=list, max_length=8)
    include: list[str] = Field(default_factory=list, max_length=5)
    locked: list[TeamSet] = Field(default_factory=list, max_length=5)
    exclude: list[str] = Field(default_factory=list, max_length=12)
    objective: Literal["win", "stability", "ranker"] = "win"
    depth: Literal["quick", "standard", "deep"] = "standard"
    cpu: Literal["ultra", "master", "champion"] = "ultra"
    joker: Literal["off", "allow", "force"] = "allow"
    mega: Literal["auto", "one", "none"] = "auto"
    core: Literal["", "fwg", "dsf", "resist"] = ""
    tune: Literal["off", "quick", "standard", "deep"] = "standard"
    rankers: bool = True


@app.post("/api/team/build")
def auto_team(req: AutoTeamRequest):
    from . import auto_team as builder

    locked = [s.model_dump(exclude_unset=True) for s in req.locked]
    try:
        return builder.build(engine(), req.format, req.styles, req.include, locked,
                             exclude=req.exclude, objective=req.objective, depth=req.depth, cpu=req.cpu,
                             joker=req.joker, mega=req.mega, core=req.core, tune=req.tune, rankers=req.rankers)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/parties")
def party_list(format: Format = "Doubles"):
    e = engine()
    season, seasons = selected_season(e, None)
    return {"season": season, "seasons": seasons, "published": parties.published(e, format),
            "recommended": parties.recommended(e, format)}


@app.get("/api/parties/simulated")
def simulated_parties(format: Format = "Doubles", joker: Literal["off", "allow", "force"] = "allow",
                      depth: Literal["quick", "standard", "deep"] = "standard",
                      cpu: Literal["ultra", "master", "champion"] = "ultra",
                      styles: str = "", rankerWeight: float = Query(.5, ge=0, le=1)):
    """랭커 코어·전략·조커를 시작점으로 만든 후보를 메타 상대군과 랭커 파티 상대로 검증한 추천."""
    from . import recommend

    keys = tuple(k for k in styles.split(",") if k)
    try:
        return recommend.cached(engine(), format, joker, depth, cpu, keys, round(rankerWeight, 2))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/parties/research")
def party_research(format: Format = "Doubles"):
    from . import recommend

    e = engine()
    return {"rankers": len(recommend.ranker_rosters(e, format)),
            "cores": [{"ids": list(r["ids"]), "names": [e.P[p]["ko"] or e.P[p]["name"] for p in r["ids"]],
                       "sprites": [e.P[p]["sprite"] for p in r["ids"]], "teams": r["teams"],
                       "share": r["share"], "lift": r["lift"]}
                      for r in [*recommend.ranker_cores(e, format, 3, 6)[:3], *recommend.ranker_cores(e, format, 2, 10)[:6]]],
            "jokerRank": recommend.JOKER_RANK}


class BattleRequest(BaseModel):
    format: Format = "Doubles"
    team: list[TeamSet] = Field(min_length=1, max_length=6)
    seed: int | None = Field(default=None, ge=0, lt=2 ** 31)


class BattleStart(BattleRequest):
    selection: list[str] | None = Field(default=None, min_length=1, max_length=4)
    difficulty: simulation.Difficulty = "ultra"
    manual: bool = False


class BatchRequest(BattleRequest):
    runs: int = Field(default=50, ge=1, le=200)
    difficulty: simulation.Difficulty = "ultra"


class MoveAction(BaseModel):
    slot: int
    kind: Literal["move"]
    move: str
    target: int | None = None


class SwitchAction(BaseModel):
    slot: int
    kind: Literal["switch"]
    target: int


class WaitAction(BaseModel):
    slot: int
    kind: Literal["wait"]


class BattleTurn(BaseModel):
    turn: int = Field(ge=1, le=simulation.MAX_TURNS)
    actions: list[Annotated[MoveAction | SwitchAction | WaitAction, Field(discriminator="kind")]] | None = Field(
        default=None, max_length=2)


class BattleReplacement(BaseModel):
    turn: int = Field(ge=1, le=simulation.MAX_TURNS)
    choices: dict[int, int] = Field(min_length=1, max_length=2)
    phase: int | None = Field(default=None, ge=1)


_battles = simulation.Sessions()


def battle_team(e: Engine, req: BattleRequest) -> list[dict]:
    ids = {s.id for s in req.team}
    if not ids <= e.P.keys() or len(ids) != len(req.team):
        raise HTTPException(422, "팀에 서로 다른 포켓몬을 넣어 주세요.")
    return [s.model_dump(exclude_unset=True) for s in req.team]


def battle_seed(req: BattleRequest) -> int:
    return req.seed if req.seed is not None else secrets.randbelow(2 ** 31)


@app.post("/api/battle/scout")
def scout_battle(req: BattleRequest):
    e = engine()
    try:
        return battle_lab.scout(e, req.format, battle_team(e, req), battle_seed(req))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/battle/start")
def start_battle(req: BattleStart):
    e = engine()
    try:
        return _battles.start(battle_lab.start(e, req.format, battle_team(e, req), battle_seed(req), req.selection,
                                              req.difficulty, manual=req.manual))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/battle/{battle_id}/turn")
def battle_turn(battle_id: str, req: BattleTurn):
    actions = [a.model_dump() for a in req.actions] if req.actions is not None else None
    try:
        return _battles.advance(battle_id, req.turn, actions)
    except KeyError as error:
        raise HTTPException(404, "battle expired") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/battle/batch")
def simulate_battles(req: BatchRequest):
    e = engine()
    try:
        return battle_lab.batch(e, req.format, battle_team(e, req), req.runs, battle_seed(req), req.difficulty)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/battle/{battle_id}/replace")
def replace_battle_member(battle_id: str, req: BattleReplacement):
    try:
        return _battles.replace(battle_id, req.turn, req.choices, req.phase)
    except KeyError as error:
        raise HTTPException(404, "battle expired") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/team/analyze")
def analyze(req: TeamRequest):
    e = engine()
    from . import guide

    sets = [s.model_dump(exclude_unset=True) for s in req.team[:6]]
    top_n = max(5, min(50, req.topN))
    res = e.analyze_team(sets, req.format, top_n)
    res["guide"] = guide.team_guide(e, sets, req.format, top_n)
    res["warnings"] = rule_warnings(res.get("members", [])) + res.get("warnings", [])
    return res


def rule_warnings(members: list[dict]) -> list[dict]:
    """대전 규칙에 걸리는 구성: 같은 포켓몬·같은 도구 중복, 기술이 4개 미만."""
    out = []

    def dup(values):
        seen, d = set(), []
        for v in values:
            if v and v in seen and v not in d:
                d.append(v)
            seen.add(v)
        return d

    name = {m["baseName"]: m["ko"] or m["name"] for m in members}
    species = dup([m["baseName"].split("-")[0] for m in members])
    if species:
        out.append({"kind": "rule", "severity": "high", "text": "같은 포켓몬이 두 번 들어 있습니다",
                    "detail": "한 팀에 같은 종류는 한 마리만 넣을 수 있습니다: " + ", ".join(name.get(s, s) for s in species)})
    items = dup([m["item"] for m in members])
    if items:
        ko = {m["item"]: m.get("itemKo") or m["item"] for m in members}
        out.append({"kind": "rule", "severity": "high", "text": "같은 도구를 두 마리가 지니고 있습니다",
                    "detail": "도구는 팀 안에서 겹칠 수 없습니다: " + ", ".join(ko[i] for i in items)})
    short = [m["ko"] or m["name"] for m in members if len(m["moves"]) < 4]
    if short:
        out.append({"kind": "rule", "severity": "mid", "text": "기술이 4개 미만인 포켓몬이 있습니다",
                    "detail": ", ".join(short)})
    return out


class EnemyRequest(BaseModel):
    format: Format = "Doubles"
    enemy: list[str]
    team: list[TeamSet] = []
    enemyLead: list[str] = Field(default_factory=list, max_length=2)
    lockedBring: list[str] = Field(default_factory=list, max_length=4)


@app.post("/api/enemy/analyze")
def analyze_enemy(req: EnemyRequest):
    from . import enemy as enemy_mod

    sets = [s.model_dump(exclude_unset=True) for s in req.team[:6]]
    return enemy_mod.analyze_enemy(engine(), req.enemy[:6], sets, req.format, req.enemyLead, req.lockedBring)


class LabRequest(BaseModel):
    format: Format = "Doubles"
    id: str
    set: TeamSet | None = None
    topN: int = 20


@app.post("/api/lab")
def lab_view(req: LabRequest):
    """한 포켓몬의 세트 기준 메타 상성표·파트너·운용법."""
    from . import lab

    e = engine()
    if req.id not in e.P:
        raise HTTPException(404, "unknown pokemon")
    s = req.set.model_dump(exclude_unset=True) if req.set else None
    return lab.lab(e, req.id, s, req.format, max(5, min(60, req.topN)))


class DuelRequest(BaseModel):
    format: Format = "Doubles"
    me: TeamSet
    foe: TeamSet


@app.post("/api/duel")
def duel_view(req: DuelRequest):
    """두 세트의 1:1 상세: 기술별 데미지 범위, 확정수, 스피드."""
    from . import lab

    e = engine()
    if req.me.id not in e.P or req.foe.id not in e.P:
        raise HTTPException(404, "unknown pokemon")
    a = e.resolve(req.me.model_dump(exclude_unset=True), req.format)
    foe = req.foe.model_dump(exclude_unset=True)
    base = e.default_set(req.foe.id, req.format)
    if "item" in foe and "mega" not in foe:  # 도구만 바꿔 보면 메가 여부도 따라간다
        m = e.find_mega(e.P[req.foe.id], stone=foe["item"])
        foe["mega"] = m["name"] if m else None
    b = e.resolve({**base, **foe}, req.format)
    return lab.duel(e, a, b, req.format)


class SpeedRequest(BaseModel):
    format: Format = "Doubles"
    topN: int = 60
    team: list[TeamSet] = []


@app.post("/api/speed")
def speed_tiers(req: SpeedRequest):
    """메타 상위권의 실전 스피드 분포와 내 팀 스피드"""
    from . import speed

    e = engine()
    return {"format": req.format,
            "meta": speed.meta_rows(e, req.format, max(10, min(150, req.topN))),
            "team": speed.team_rows(e, req.format, [s.model_dump(exclude_unset=True) for s in req.team[:6]])}


class PasteRequest(BaseModel):
    url: str


@app.post("/api/pokepaste")
def pokepaste(req: PasteRequest):
    """pokepast.es 링크의 팀 텍스트를 가져온다 (앱의 Showdown 가져오기로 넘긴다)."""
    import urllib.request

    m = re.match(r"^https?://(?:www\.)?pokepast\.es/([0-9a-fA-F]{8,32})(?:/raw)?/?$", req.url.strip())
    if not m:
        raise HTTPException(400, "pokepast.es 링크가 아닙니다")
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://pokepast.es/{m.group(1)}/raw", headers=collector.UA), timeout=15) as r:
            text = r.read(200_000).decode("utf-8", "replace")
    except Exception:
        raise HTTPException(502, "팀을 불러오지 못했습니다")
    return {"text": text}


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
    global _engine, _name_tables
    collector.collect()
    _name_tables = None
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
