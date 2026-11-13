"""연구 기반 추천 파티.

1. 랭커 파티(시즌 최종 상위권)에서 자주 함께 쓰인 2·3마리 코어를 뽑는다.
2. 코어, 전략(순풍·트릭룸·날씨 등), 조커 후보를 시작점으로 6마리를 채운다 (auto_team 의 초안 탐색 재사용).
3. 모든 후보를 같은 메타 상대군(전략별 생성 파티)과 같은 랭커 파티 목록에서 같은 난수로 싸우게 해 거른다.
4. 남은 후보를 더 많은 판 수와 고른 CPU 로 다시 검증하고, 랭커 파티별 상대 전적(유리/호각/불리)을 낸다.
"""
from collections import Counter
from functools import lru_cache
from itertools import combinations
from random import Random

from . import auto_team, battle_lab, parallel, simulation
from .engine import Engine, weight
from .parties import RANKERS, _member

JOKER_RANK = 40  # 사용률 순위가 이보다 낮으면 조커로 본다.
# 평가 깊이: (1차 메타 판 수, 1차 랭커 파티당 판 수, 최종 메타 판 수, 최종 랭커 파티당 판 수, 최종 후보 수)
DEPTHS = {"quick": (16, 1, 48, 2, 4), "standard": (24, 1, 96, 4, 6), "deep": (40, 2, 200, 8, 8)}
FAVORED, UNFAVORED = .6, .4


def _rank(e, fmt, pid):
    return e.P[pid]["usage"].get(fmt, {}).get("rank") or 999


def is_joker(e, fmt, pid):
    return _rank(e, fmt, pid) > JOKER_RANK


def rankers(fmt):
    return [r for r in RANKERS if r["format"] == fmt]


@lru_cache(maxsize=4)
def ranker_rosters(e: Engine, fmt: str):
    """랭커 파티의 종 구성에 가장 흔한 세트를 입힌다. 메가스톤은 한 장만, 도구는 겹치지 않게."""
    out = []
    for r in rankers(fmt):
        ids = [pid for pid in r["ids"] if pid in e.P]
        if len(ids) < 4:
            continue
        sets, used, mega = [], set(), False
        for pid in sorted(ids, key=lambda p: _rank(e, fmt, p)):
            s = e.default_set(pid, fmt)
            stone = bool(s.get("mega"))
            if s["item"] in used or (stone and mega):
                rows = e.P[pid]["usage"].get(fmt, {}).get("items", [])
                item = next((row["name"] for row in rows if row["name"] not in used
                             and not e.find_mega(e.P[pid], stone=row["name"])), None)
                s.update(item=item, mega=None)
            mega |= bool(s.get("mega"))
            if s["item"]:
                used.add(s["item"])
            sets.append(s)
        order = {pid: i for i, pid in enumerate(ids)}
        sets.sort(key=lambda s: order[s["id"]])
        out.append((r, tuple(sets)))
    return tuple(out)


@lru_cache(maxsize=4)
def ranker_cores(e: Engine, fmt: str, size: int = 2, top: int = 8):
    """상위 랭커일수록 무겁게 센 동시 채용 빈도. 개별 채용률로 기대되는 빈도 대비 비율(lift)도 함께 낸다."""
    teams = [(r, [pid for pid in r["ids"] if pid in e.P]) for r in rankers(fmt)]
    if not teams:
        return ()
    from .regulation import _season_number, season_weight

    # 시즌 신뢰도: 가진 표본 중 가장 새 시즌을 1로, 한 시즌 전 0.75, 두 시즌 전 0.5
    newest = max((r.get("season") for r, _ in teams), key=lambda s: _season_number(s) or 0, default=None)
    singles, groups, total = Counter(), Counter(), 0.
    for r, ids in teams:
        w = weight(r["rank"]) * season_weight(r.get("season"), reference=newest)
        total += w
        for pid in set(ids):
            singles[pid] += w
        for combo in combinations(sorted(set(ids)), size):
            groups[combo] += w
    rows = []
    for combo, w in groups.items():
        count = sum(1 for _, ids in teams if set(combo) <= set(ids))
        if count < 2:
            continue
        expected = total
        for pid in combo:
            expected *= singles[pid] / total
        rows.append({"ids": combo, "teams": count, "share": round(100 * count / len(teams)),
                     "weight": w, "lift": round(w / expected, 2) if expected else 0})
    rows.sort(key=lambda row: (-row["weight"], -row["lift"]))
    return tuple(rows[:top])


def _matches(e, fmt, team, rosters, games, seed):
    """각 랭커 파티와 games 판. 양쪽 모두 상대 6마리를 보고 4마리를 고른다 (같은 seed 면 같은 판)."""
    player = battle_lab._resolve(e, fmt, team)
    for index, (ranker, sets) in enumerate(rosters):
        opponents = battle_lab._resolve(e, fmt, list(sets))
        for game in range(games):
            rng = Random(seed * 7919 + index * 104729 + game)
            ours, _ = battle_lab._choose(e, fmt, player, opponents, rng)
            theirs, _ = battle_lab._choose(e, fmt, opponents, player, rng)
            yield index, ours, theirs, rng.randrange(2 ** 31)


def versus_rankers(e: Engine, fmt: str, team: list[dict], games: int, seed: int,
                   difficulty: simulation.Difficulty = "ultra"):
    rosters = ranker_rosters(e, fmt)
    rows = [{"win": 0, "loss": 0, "draw": 0} for _ in rosters]
    for index, ours, theirs, battle_seed in _matches(e, fmt, team, rosters, games, seed):
        battle = simulation.Battle(e, fmt, [team[i] for i in ours], [rosters[index][1][i] for i in theirs],
                                   battle_seed, log=False, difficulty=difficulty)
        while not battle.winner:
            battle.advance()
        rows[index][battle.winner] += 1
    total = {k: sum(r[k] for r in rows) for k in ("win", "loss", "draw")}
    runs = sum(total.values())
    teams = []
    for (ranker, sets), row in zip(rosters, rows):
        n = sum(row.values())
        rate = (row["win"] + .5 * row["draw"]) / n if n else 0
        teams.append({"id": ranker["id"], "rank": ranker["rank"], "season": ranker["season"],
                      "player": ranker["player"], "rating": ranker.get("rating"), **row, "runs": n,
                      "rate": round(rate, 3),
                      "verdict": "favored" if rate >= FAVORED else "unfavored" if rate <= UNFAVORED else "even",
                      "members": [battle_lab._brief(e.resolve(s, fmt)) for s in sets]})
    counts = Counter(t["verdict"] for t in teams)
    return {**total, "runs": runs, "ci": battle_lab.wilson(total["win"] + .5 * total["draw"], runs),
            "rate": round((total["win"] + .5 * total["draw"]) / max(1, runs), 3),
            "favored": counts["favored"], "even": counts["even"], "unfavored": counts["unfavored"],
            "teams": sorted(teams, key=lambda t: (t["rate"], t["rank"]))}


def _variants(e, fmt, meta, pid):
    return [auto_team._candidate(e, fmt, meta, s)
            for s in auto_team._generated_sets(e, fmt, pid, required=True, draft=True)]


def _goals_for(e, fmt, meta, ids):
    """코어가 순풍·트릭룸·날씨 시동을 갖고 있으면 그 전략 조건을 함께 채운다."""
    features = set()
    for pid in ids:
        features |= auto_team._candidate(e, fmt, meta, e.default_set(pid, fmt)).features
    goals = []
    for key, feature in (("tailwind", "tailwind"), ("trickroom", "trickroom"), ("rain", "rain_set"),
                         ("sun", "sun_set"), ("sand", "sand_set"), ("snow", "snow_set")):
        if feature in features and (fmt == "Doubles" or not auto_team.STYLES[key].doubles_only):
            goals.append(key)
    return tuple(goals[:1])


def _label(e, pid):
    return e.P[pid]["ko"] or e.P[pid]["name"]


def _seeds(e, fmt, meta, joker, styles):
    """(출처 정보, 필수 포켓몬 id, 전략 목표) 목록."""
    seeds = []
    pairs, triples = ranker_cores(e, fmt, 2, 10), ranker_cores(e, fmt, 3, 6)
    goals = tuple(styles)
    for row in [*triples[:4], *pairs[:6]]:
        seeds.append(({"kind": "core", "label": "랭커 코어 · " + " + ".join(_label(e, p) for p in row["ids"]),
                       "detail": f"랭커 파티 {row['teams']}개에서 함께 채용"}, row["ids"], goals or _goals_for(
                           e, fmt, meta, row["ids"])))
    if not pairs:  # 싱글처럼 랭커 표본이 없으면 상위권 동료 채용 1순위로 코어를 만든다.
        for p in e.ranked(fmt)[:6]:
            mate = next((m for m in p["usage"][fmt].get("teammates", []) if m in e.P), None)
            if mate:
                ids = (p["id"], mate)
                seeds.append(({"kind": "core", "label": "동료 채용 코어 · " + " + ".join(_label(e, i) for i in ids),
                               "detail": "상위권 포켓몬과 가장 자주 함께 쓰인 동료"}, ids, goals))
    for key in (styles and [] or auto_team.DISCOVERY_STYLES):
        if auto_team.STYLES[key].doubles_only and fmt != "Doubles":
            continue
        seeds.append(({"kind": "style", "label": "전략 · " + auto_team.STYLES[key].label,
                       "detail": "전략 조건을 먼저 채우고 메타 상성으로 나머지를 고름"}, (), (key,)))
    if styles:
        seeds.append(({"kind": "style", "label": "전략 · " + " · ".join(auto_team.STYLES[k].label for k in styles),
                       "detail": "고른 전략 조건을 먼저 채움"}, (), goals))
    if joker != "off":
        picks = [j for j in e.jokers(fmt, JOKER_RANK + 1, 20) if j["set"]["id"] in e.P][:6 if joker == "force" else 4]
        anchors = [row["ids"] for row in pairs[:2]] or [()]
        for j in picks:
            jid = j["set"]["id"]
            for anchor in anchors[:2 if joker == "force" else 1]:
                ids = (jid, *[a for a in anchor if a != jid])
                seeds.append(({"kind": "joker", "jokerSet": j["set"], "label": f"조커 · {_label(e, jid)}" + (
                    " + " + " + ".join(_label(e, a) for a in anchor) if anchor else ""),
                               "detail": f"사용률 {_rank(e, fmt, jid)}위 · 조커 점수 {j.get('score', 0):.0f}"},
                              ids, goals or _goals_for(e, fmt, meta, ids)))
    return seeds


def _signature(roster):
    return frozenset(c.species for c in roster)


def _combined(meta_rate, ranker_rate, ranker_weight):
    return (1 - ranker_weight) * meta_rate + ranker_weight * ranker_rate


def recommend(e: Engine, fmt: str, *, joker: str = "allow", depth: str = "standard", cpu: str = "ultra",
              styles: tuple[str, ...] = (), ranker_weight: float = .5):
    if joker not in {"off", "allow", "force"}:
        raise ValueError("조커 옵션은 off, allow, force 중 하나입니다.")
    styles = tuple(dict.fromkeys(styles))
    if any(k not in auto_team.STYLES or (auto_team.STYLES[k].doubles_only and fmt != "Doubles") for k in styles):
        raise ValueError("현재 배틀 형식에서 사용할 수 있는 전략을 골라 주세요.")
    screen_meta, screen_rank, final_meta, final_rank, finalists = DEPTHS.get(depth, DEPTHS["standard"])
    rosters = ranker_rosters(e, fmt)
    if not rosters:
        ranker_weight = 0.
    meta, pool = auto_team._pool(e, fmt)
    weights = [weight(e.rank(f["id"], fmt) or 250) for f in meta]
    total = sum(weights) or 1
    weights = [w / total for w in weights]
    if joker == "off":
        pool = tuple(c for c in pool if not is_joker(e, fmt, c.id))
    elif joker == "force":
        pool = tuple(c for c in pool if not is_joker(e, fmt, c.id))

    drafts, seen = [], set()
    for origin, ids, goals in _seeds(e, fmt, meta, joker, styles):
        if joker == "force" and not any(is_joker(e, fmt, pid) for pid in ids):
            continue
        if joker == "off" and any(is_joker(e, fmt, pid) for pid in ids):
            continue
        required = [_variants(e, fmt, meta, pid) for pid in ids]
        if origin.get("jokerSet"):  # 조커 파인더가 메타 상대로 고른 세트도 후보에 넣는다.
            required[0].append(auto_team._candidate(e, fmt, meta, origin.pop("jokerSet")))
        if any(not rows for rows in required):
            continue
        available = pool
        if "trickroom" in goals:
            available = (*pool, *(c for c in auto_team._room_pool(e, fmt)
                                  if joker == "allow" or not is_joker(e, fmt, c.id)))
        rows = auto_team._draft(available, [], required, goals, weights, limit=8)
        kept = 0
        for roster in rows:
            key = _signature(roster)
            if key in seen or sum(bool(c.resolved["mega"]) for c in roster) > 2:
                continue
            seen.add(key)
            drafts.append((origin, goals, roster))
            kept += 1
            if kept == 2:
                break
    if not drafts:
        raise ValueError("이 조건으로 추천 파티를 만들 수 없습니다. 조커나 전략 조건을 바꿔 보세요.")

    teams = [[c.set for c in roster] for _, _, roster in drafts]
    screened = parallel.compare_teams(e, fmt, teams, screen_meta, 515153, "ultra")
    screened_ranks = parallel.versus_rankers_many(e, fmt, teams, screen_rank, 7121, "ultra") if rosters else [None] * len(teams)
    rows = []
    for (origin, goals, roster), team, report, ranks in zip(drafts, teams, screened, screened_ranks):
        meta_rate = (report["win"] + .5 * report["draw"]) / report["runs"]
        rows.append((_combined(meta_rate, ranks["rate"] if ranks else 0, ranker_weight), origin, goals, roster))
    rows.sort(key=lambda row: -row[0])
    # 조커가 들어간 후보와 없는 후보를 비교할 수 있도록 각각 최소 한 팀은 최종 검증에 남긴다.
    chosen = []
    for row in rows:  # 최종 후보끼리는 2마리 이상 달라야 한다.
        if len(chosen) < finalists and all(len(_signature(row[3]) - _signature(c[3])) >= 2 for c in chosen):
            chosen.append(row)
    if joker == "allow":
        for flag in (True, False):
            if not any(any(is_joker(e, fmt, c.id) for c in r[3]) == flag for r in chosen):
                extra = next((r for r in rows if any(is_joker(e, fmt, c.id) for c in r[3]) == flag), None)
                if extra:
                    chosen = [*chosen[:finalists - 1], extra]

    final_teams = [[c.set for c in roster] for _, _, _, roster in chosen]
    reports = parallel.compare_teams(e, fmt, final_teams, final_meta, 9157, cpu)
    final_ranks = (parallel.versus_rankers_many(e, fmt, final_teams, final_rank, 6151, cpu) if rosters
                   else [None] * len(final_teams))
    candidates = []
    for (screen, origin, goals, roster), team, report, ranks in zip(chosen, final_teams, reports, final_ranks):
        meta_rate = (report["win"] + .5 * report["draw"]) / report["runs"]
        score = _combined(meta_rate, ranks["rate"] if ranks else 0, ranker_weight)
        candidates.append((score, origin, goals, roster, team, report, ranks))
    candidates.sort(key=lambda row: -row[0])

    from .guide import team_guide

    out = []
    for index, (score, origin, goals, roster, team, report, ranks) in enumerate(candidates, 1):
        analysis = e.analyze_team(team, fmt)
        guide = team_guide(e, team, fmt) or {}
        members = [_member(e, s, fmt) for s in team]
        jokers = []
        for m, c in zip(members, roster):
            m["speed"] = round(c.resolved["speed"])
            m["usageRank"] = _rank(e, fmt, c.id) if _rank(e, fmt, c.id) < 999 else None
            m["joker"] = is_joker(e, fmt, c.id)
            m["features"] = [auto_team.FEATURE_NAMES[f] for f in sorted(c.features) if f in auto_team.FEATURE_NAMES][:4]
            if m["joker"]:
                jokers.append(m["ko"] or m["name"])
        activations = report.pop("activations")
        report["strategyUse"] = [{"label": auto_team.STYLES[k].label, "runs": activations[k]}
                                 for k in goals if k in auto_team.WEATHER_STYLES | {"tailwind", "trickroom", "psychic"}]
        names = {c.id: c.resolved["ko"] or c.resolved["name"] for c in roster}
        lead = " + ".join(names.get(pid, pid) for pid in report["lead"]["ids"])
        out.append({
            "id": f"lab-{index}", "name": f"{origin['label'].split(' · ', 1)[-1]} · {lead}", "format": fmt,
            "complete": True, "origin": origin, "goals": list(goals),
            "members": members, "jokers": jokers, "metaScore": analysis["metaScore"],
            "warnings": analysis["warnings"][:4], "score": round(score, 3),
            "simulation": report, "rankers": ranks,
            "profile": {k: sum(k in c.features for c in roster) for k in ("fast_attacker", "physical", "special", "bulky")},
            "analysis": {
                "damageSplit": analysis["damageSplit"],
                "weakTypes": [{"type": r["type"], "weak": r["weak"], "resist": r["resist"]}
                              for r in sorted((r for r in analysis["typeRows"] if r["weak"] >= 2),
                                              key=lambda r: r["resist"] - r["weak"])[:4]],
                "roles": [{"label": r["label"], "stars": r["stars"]} for r in analysis["roleCoverage"]],
                "matchups": {k: sum(1 for m in analysis["matchups"] if m["label"] == k) for k in ("GOOD", "EVEN", "BAD")},
                "axes": [{"label": a["label"], "play": a["play"]} for a in guide.get("axes", [])][:4],
                "lead": guide.get("lead"),
            },
        })
    with_joker = [c for c in out if c["jokers"]]
    without = [c for c in out if not c["jokers"]]
    comparison = None
    if with_joker and without:
        comparison = {"withJoker": {"id": with_joker[0]["id"], "name": with_joker[0]["name"],
                                    "score": with_joker[0]["score"], "jokers": with_joker[0]["jokers"]},
                      "without": {"id": without[0]["id"], "name": without[0]["name"], "score": without[0]["score"]}}
    battles = (len(drafts) * (screen_meta + screen_rank * len(rosters))
               + len(chosen) * (final_meta + final_rank * len(rosters)))
    return {
        "candidates": out,
        "research": {
            "rankers": len(rosters),
            "seasons": sorted({r["season"] for r, _ in rosters}),
            "source": rosters[0][0]["source"] if rosters else None,
            "cores": [{"ids": list(r["ids"]), "names": [_label(e, p) for p in r["ids"]], "teams": r["teams"],
                       "share": r["share"], "lift": r["lift"],
                       "sprites": [e.P[p]["sprite"] for p in r["ids"]]}
                      for r in [*ranker_cores(e, fmt, 3, 6)[:3], *ranker_cores(e, fmt, 2, 10)[:6]]],
        },
        "jokerComparison": comparison,
        "evaluation": {"drafts": len(drafts), "finalists": len(chosen), "screenRuns": screen_meta,
                       "screenRankerGames": screen_rank, "finalRuns": final_meta, "finalRankerGames": final_rank,
                       "battles": battles, "cpu": cpu, "depth": depth, "joker": joker,
                       "rankerWeight": ranker_weight, "jokerRank": JOKER_RANK},
    }


@lru_cache(maxsize=24)
def cached(e, fmt, joker, depth, cpu, styles, ranker_weight):
    return recommend(e, fmt, joker=joker, depth=depth, cpu=cpu, styles=styles, ranker_weight=ranker_weight)
