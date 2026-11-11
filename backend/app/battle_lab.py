"""Seeded Champions opponent drafts, matchup-aware lineups and battle observations."""
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from random import Random

from . import auto_team, simulation
from .engine import Engine
from .parties import _member
from .typechart import TYPES

PLAYBOOKS = {
    "balance": ("물리와 특수 화력을 분산해 한쪽 공격만 막히는 상황을 줄입니다.", ("physical", "special")),
    "tailwind": ("순풍으로 행동 순서를 앞당기고 공격으로 초반을 압박합니다.", ("tailwind", "attacker")),
    "trickroom": ("트릭룸으로 행동 순서를 뒤집고 느린 공격수를 먼저 움직입니다.", ("trickroom", "slow_attacker")),
    "rain": ("비를 전개해 물 화력, 날씨 기술 또는 쓱쓱을 살립니다.", ("rain_set", "rain_attack")),
    "sun": ("쾌청을 전개해 불 화력, 날씨 기술 또는 엽록소를 살립니다.", ("sun_set", "sun_attack")),
    "psychic": ("사이코필드로 지상 상대에게 쓰는 선제기를 막고 와이드포스를 강화합니다.", ("psychic_set", "psychic_attack")),
    "setup": ("랭크업 공격수가 강화할 기회를 만들고 내구형 포켓몬으로 빈틈을 메웁니다.", ("setup_attacker", "bulky")),
}
COUNTERPLAY = {
    "balance": "한쪽 화력에만 맞춘 선출을 피하고, 물리와 특수 공격을 각각 받아줄 포켓몬을 남겨 보세요.",
    "tailwind": "순풍 턴에 정면으로 속도를 겨루기 어렵다면 방어·교체로 버티고, 순풍이 끝난 뒤 화력을 내보세요.",
    "trickroom": "설치 포켓몬을 첫 턴에 압박해 보세요. 트릭룸이 열리면 느린 포켓몬을 활용하거나 방어로 남은 턴을 줄이세요.",
    "rain": "물 공격을 반감하는 포켓몬을 후발에 남기세요. 날씨를 바꿀 수 있다면 상대의 비 전개 뒤에 내보내 보세요.",
    "sun": "불 공격을 받아줄 후발을 남기고, 날씨를 덮거나 엽록소 포켓몬을 먼저 압박해 보세요.",
    "psychic": "선제기에 의존하는 선출을 피하세요. 에스퍼 공격을 무효화하는 악 타입이나 반감하는 교체 자원을 고려하세요.",
    "setup": "랭크업 공격수를 초반에 압박하고, 상대가 강화를 쌓기 전에 집중 공격으로 교체를 유도해 보세요.",
}
FIELD_ROLES = {
    "rain": {"rain_set", "rain_attack", "other_weather"},
    "sun": {"sun_set", "sun_attack", "other_weather"},
    "psychic": {"psychic_set", "psychic_attack"},
    "tailwind": {"tailwind", "attacker"},
    "trickroom": {"trickroom", "slow_attacker"},
}


def limit(fmt):
    return 4 if fmt == "Doubles" else 3


def _brief(mon):
    return {k: mon[k] for k in ("id", "name", "ko", "sprite", "types")}


def _compatible(candidate, chosen):
    return auto_team._eligible(candidate, chosen) and (
        not candidate.resolved["mega"] or not any(c.resolved["mega"] for c in chosen))


def _fits_style(candidate, style):
    weather = candidate.features & {"rain_set", "sun_set", "other_weather"}
    return weather <= ({f"{style}_set"} if style in {"rain", "sun"} else set())


@lru_cache(maxsize=6)
def _draft_pools(e, fmt):
    candidates = {}
    for entry in auto_team.candidate_sets(e, fmt):
        moves = [m for m in entry["moves"] if m in simulation.SUPPORT or e.M[m]["power"]]
        if not any(e.M[m]["power"] and m not in simulation.FIRST_TURN for m in moves):
            continue
        key = entry["id"], entry["item"], entry["ability"], tuple(moves)
        if key not in candidates:
            candidate = auto_team._candidate(e, fmt, (), {**entry, "moves": moves})
            if "setup_attacker" in candidate.features and not any(
                stat in simulation.BOOSTS.get(move, {}) and role in candidate.features
                for move in moves for stat, role in (("atk", "physical"), ("spa", "special"))
            ):
                candidate.features -= {"setup_attacker"}
            candidates[key] = candidate
    pools = {}
    for style, (_, roles) in PLAYBOOKS.items():
        if auto_team.STYLES[style].doubles_only and fmt != "Doubles":
            continue
        pool = tuple(c for c in candidates.values() if _fits_style(c, style))
        starters = [c for c in pool if roles[0] in c.features]
        partners = [c for c in pool if roles[1] in c.features]
        cores = [(a, b) for a in starters for b in partners if _compatible(b, (a,))]
        if cores and len({c.species for c in pool}) >= 6:
            pools[style] = pool, cores, [_core_weight(a, b) for a, b in cores]
    return pools


def _core_weight(a, b):
    teammates = int(a.id in b.teammates) + int(b.id in a.teammates)
    return (.1 + a.popularity) ** 1.4 * (.1 + b.popularity) ** 1.4 * (1 + .35 * teammates)


def _fill_weights(pool, roster, style):
    covered = set().union(*(m.features for m in roster))
    missing = {"physical", "special", "bulky", "priority", "fast", "fakeout"} - covered
    weak_counts = [sum(m.weak[i] for m in roster) for i in range(len(TYPES))]
    uncovered = [i for i, n in enumerate(weak_counts) if n and not any(m.resist[i] for m in roster)]
    crowded = [i for i, n in enumerate(weak_counts) if n >= 2]
    preferred = FIELD_ROLES.get(style, set())
    weights = []
    for c in pool:
        variety = len(c.features & missing)
        synergy = sum(c.id in m.teammates or m.id in c.teammates for m in roster)
        cover = sum(c.resist[i] for i in uncovered)
        overlap = sum(c.weak[i] for i in crowded)
        fit = bool(c.features & preferred)
        weights.append((.16 + c.popularity) ** 1.5 * (1 + .4 * variety + .25 * synergy + .35 * cover + .15 * fit)
                       / (1 + .65 * overlap))
    return weights


def _draft(e, fmt, seed, rng):
    pools = _draft_pools(e, fmt)
    if not pools:
        raise ValueError("이 배틀 형식의 상대 파티를 구성할 메타 데이터가 부족합니다.")
    style = tuple(pools)[seed % len(pools)]
    pool, cores, weights = pools[style]
    for _ in range(12):
        roster = list(rng.choices(cores, weights)[0])
        while len(roster) < 6:
            eligible = [c for c in pool if _compatible(c, roster)]
            if not eligible:
                break
            roster.append(rng.choices(eligible, _fill_weights(eligible, roster, style))[0])
        if len(roster) == 6:
            return style, roster
    raise ValueError("상대 파티를 구성할 수 없습니다. 상대를 다시 뽑아 주세요.")


def _resolve(e, fmt, sets):
    return [e.resolve({**e.default_set(s["id"], fmt), **s}, fmt) for s in sets]


def _choose(e, fmt, own, opponents, rng, *, style=None, core=()):
    """Score coverage across the full opposing roster, then score the opening."""
    width = 2 if fmt == "Doubles" else 1
    count = min(limit(fmt), len(own))
    matrix = [[e.matchup(m, f, fmt)["score"] for f in opponents] for m in own]
    columns = range(len(opponents))
    roles = [set(e.roles(m, fmt)) for m in own]
    candidates = []
    for group in combinations(range(len(own)), count):
        coverage = []
        for j in columns:
            values = sorted((matrix[i][j] for i in group), reverse=True)
            coverage.append(.76 * values[0] + .24 * values[min(1, len(values) - 1)])
        megas = sum(bool(own[i]["mega"]) for i in group)
        score = .79 * sum(coverage) / len(coverage) + .21 * min(coverage) - 6 * max(0, megas - 1)
        if core:
            score += 7 * sum(i in group for i in core)
        for leads in combinations(group, min(width, count)):
            pressure = sum(max(matrix[i][j] for i in leads) for j in columns) / len(opponents)
            tempo = sum(bool(roles[i] & {"fakeout", "tailwind", "trickroom"}) for i in leads)
            entry = 0
            if core and style in FIELD_ROLES and core[0] in leads:
                entry = 7 + 5 * (core[1] in leads)
            order = (*leads, *(i for i in group if i not in leads))
            candidates.append((.72 * score + .28 * pressure + 1.4 * tempo + entry + rng.uniform(0, 2), order))
    return max(candidates)[1], matrix


@dataclass(frozen=True)
class Matchup:
    style: str
    roster: list[auto_team.Candidate]
    player: list[dict]
    ours: tuple[int, ...]
    theirs: tuple[int, ...]
    scores: list[list[float]]
    battle_seed: int


def matchup(e: Engine, fmt: str, team: list[dict], seed: int) -> Matchup:
    rng = Random(seed)
    style, roster = _draft(e, fmt, seed, rng)
    return _match_against(e, fmt, _resolve(e, fmt, team), style, roster, rng)


def _match_against(e, fmt, player, style, roster, rng):
    opponents = [c.resolved for c in roster]
    ours, matrix = _choose(e, fmt, player, opponents, rng)
    preview = [e.default_resolved(p["id"], fmt) for p in player]
    their, _ = _choose(e, fmt, opponents, preview, rng, style=style, core=(0, 1))
    return Matchup(style, roster, player, ours, their, matrix, rng.randrange(2 ** 31))


def _opponent(e, fmt, style, roster):
    plan, roles = PLAYBOOKS[style]
    members = []
    for i, c in enumerate(roster):
        covered = []
        if i < 2:
            why = auto_team.FEATURE_NAMES[roles[i]]
        else:
            covered = [t for j, t in enumerate(TYPES) if c.resist[j] and any(m.weak[j] for m in roster[:i])]
            if covered:
                why = "공격을 받아줄 교대 자원"
            else:
                why = " · ".join(row["label"] for row in e.describe(c.resolved, fmt)["roles"][:2]) or "공격 범위 보강"
        members.append({**_member(e, c.set, fmt), "why": why, "covers": covered[:2]})
    return {"style": style, "label": auto_team.STYLES[style].label, "plan": plan, "members": members}


def scout(e, fmt, team, seed):
    match = matchup(e, fmt, team, seed)
    threat_index = min(range(len(match.roster)), key=lambda j: max(row[j] for row in match.scores))
    counter_index = max(match.ours, key=lambda i: match.scores[i][threat_index])
    return {"seed": seed, "opponent": _opponent(e, fmt, match.style, match.roster),
            "selection": [match.player[i]["id"] for i in match.ours],
            "player": [_brief(m) for m in match.player],
            "threat": {"foe": _brief(match.roster[threat_index].resolved), "counter": _brief(match.player[counter_index]),
                       "score": match.scores[counter_index][threat_index]}}


def start(e, fmt, team, seed, selection, difficulty: simulation.Difficulty = "ultra", *, manual=False):
    match = matchup(e, fmt, team, seed)
    ours = match.ours
    if selection is not None:
        index = {m["id"]: i for i, m in enumerate(match.player)}
        if len(selection) != len(ours) or len(set(selection)) != len(ours) or not set(selection) <= index.keys():
            raise ValueError("팀에서 필요한 수만큼 서로 다른 포켓몬을 선출해 주세요.")
        ours = tuple(index[pid] for pid in selection)
    return simulation.Battle(
        e, fmt, [team[i] for i in ours], [match.roster[i].set for i in match.theirs], match.battle_seed,
        context={"seed": seed, "opponent": _opponent(e, fmt, match.style, match.roster)},
        foe_strategy=match.style, difficulty=difficulty, manual=manual)


def _results():
    return dict.fromkeys(("win", "loss", "draw"), 0)


def wilson(wins: float, runs: int, z: float = 1.96) -> list[float]:
    """승률의 95% 신뢰 구간 (Wilson). 판 수가 적을수록 범위가 넓다."""
    if not runs:
        return [0., 0.]
    phat = wins / runs
    denom = 1 + z * z / runs
    center = (phat + z * z / (2 * runs)) / denom
    margin = z * ((phat * (1 - phat) + z * z / (4 * runs)) / runs) ** .5 / denom
    return [round(100 * max(0., center - margin), 1), round(100 * min(1., center + margin), 1)]


class _Detail:
    """한 팀의 반복 배틀 상세 집계: 포켓몬별 기여, 위협적인 상대, 선봉 조합별 승률, 턴 분포."""

    def __init__(self, width):
        self.width = width
        self.members, self.foes, self.leads = {}, {}, {}
        self.turns = Counter()
        self.games = 0

    def add(self, battle, result):
        self.games += 1
        turns = battle.turn - 1
        self.turns[min(12, max(1, turns))] += 1
        for i, f in enumerate(battle.teams[0]):
            row = self.members.setdefault(f.mon["id"], {
                **_brief(f.mon), "picked": 0, "leads": 0, "survived": 0, "wins": 0,
                "dealt": 0, "taken": 0, "kos": 0, "hpLeft": 0.})
            row["picked"] += 1
            row["leads"] += i < self.width
            row["survived"] += f.hp > 0
            row["wins"] += result == "win"
            row["dealt"] += f.dealt
            row["taken"] += f.taken
            row["kos"] += f.kos
            row["hpLeft"] += f.hp / f.max_hp
        for f in battle.teams[1]:
            row = self.foes.setdefault(f.mon["id"], {**_brief(f.mon), "faced": 0, "kos": 0, "dealt": 0,
                                                     "losses": 0})
            row["faced"] += 1
            row["kos"] += f.kos
            row["dealt"] += f.dealt
            row["losses"] += result == "loss"
        lead = tuple(sorted(f.mon["id"] for f in battle.teams[0][:self.width]))
        line = self.leads.setdefault(lead, {"ids": list(lead), "runs": 0, **_results()})
        line["runs"] += 1
        line[result] += 1

    def report(self):
        members = []
        for row in self.members.values():
            n = row["picked"]
            members.append({**row, "pickRate": round(100 * n / self.games, 1),
                            "surviveRate": round(100 * row["survived"] / n, 1),
                            "winRate": round(100 * row["wins"] / n, 1),
                            "avgDealt": round(row["dealt"] / n), "avgTaken": round(row["taken"] / n),
                            "koPerGame": round(row["kos"] / n, 2), "hpLeft": round(100 * row["hpLeft"] / n)})
        members.sort(key=lambda r: -r["picked"])
        foes = [{**r, "koPerGame": round(r["kos"] / r["faced"], 2), "avgDealt": round(r["dealt"] / r["faced"])}
                for r in self.foes.values() if r["faced"] >= max(2, self.games // 20)]
        foes.sort(key=lambda r: (-r["koPerGame"], -r["avgDealt"]))
        leads = sorted(self.leads.values(), key=lambda r: -r["runs"])[:5]
        for r in leads:
            r["winRate"] = round(100 * r["win"] / r["runs"], 1)
            r["ci"] = wilson(r["win"], r["runs"])
        return {"memberStats": members, "threats": foes[:6], "leadStats": leads,
                "turnHistogram": [{"turns": t, "games": self.turns[t]} for t in sorted(self.turns)]}


def _member_stats(mon):
    return {**_brief(mon), "rostered": 0, "picked": 0, "leads": 0,
            "dealt": 0, "taken": 0, "kos": 0, "victims": Counter(), **_results()}


def _observe(rows, roster, fighters, width, outcome):
    for mon in roster:
        row = rows.setdefault(mon["id"], _member_stats(mon))
        row["rostered"] += 1
    for i, fighter in enumerate(fighters):
        row = rows[fighter.mon["id"]]
        row["picked"] += 1
        row["leads"] += i < width
        row[outcome] += 1
        row["dealt"] += fighter.dealt
        row["taken"] += fighter.taken
        row["kos"] += fighter.kos
        row["victims"].update(fighter.victims)


def _style_stats(style):
    return {"style": style, "label": auto_team.STYLES[style].label, "plan": PLAYBOOKS[style][0],
            "counterplay": COUNTERPLAY[style],
            "runs": 0, "turns": 0, "activated": None if style == "balance" else 0,
            **_results(), "members": {}, "foes": {}, "lineups": {},
            "example": None}


def _match_seeds(e, fmt, runs, seed):
    rng = Random(seed)
    count = len(_draft_pools(e, fmt))
    if not count:
        raise ValueError("이 배틀 형식의 상대 파티를 구성할 메타 데이터가 부족합니다.")
    order = []
    for _ in range(runs):
        if not order:
            order = list(range(count))
            rng.shuffle(order)
        yield rng.randrange((2 ** 31 - count) // count) * count + order.pop()


def _play(e, fmt, team, match, difficulty):
    battle = simulation.Battle(e, fmt, [team[i] for i in match.ours],
                               [match.roster[i].set for i in match.theirs], match.battle_seed,
                               log=False, foe_strategy=match.style, difficulty=difficulty)
    while not battle.winner:
        battle.advance()
    return battle


def compare_teams(e, fmt, teams, runs, seed, difficulty: simulation.Difficulty = "ultra"):
    """Use the same six opponents and RNG for every team; each still gets its own preview."""
    standings = [{**_results(), "runs": runs, "strategies": {}, "leads": Counter(),
                  "activations": Counter(), "turns": 0} for _ in teams]
    details = [_Detail(2 if fmt == "Doubles" else 1) for _ in teams]
    resolved = [_resolve(e, fmt, team) for team in teams]
    width = 2 if fmt == "Doubles" else 1
    for match_seed in _match_seeds(e, fmt, runs, seed):
        rng = Random(match_seed)
        style, roster = _draft(e, fmt, match_seed, rng)
        state = rng.getstate()
        for team, player, row, detail in zip(teams, resolved, standings, details):
            rng.setstate(state)
            match = _match_against(e, fmt, player, style, roster, rng)
            battle = _play(e, fmt, team, match, difficulty)
            row[battle.winner] += 1
            row["turns"] += battle.turn - 1
            detail.add(battle, battle.winner)
            row["activations"].update(sorted(battle.activated[0]))
            strategy = row["strategies"].setdefault(style, {
                "style": style, "label": auto_team.STYLES[style].label,
                "counterplay": COUNTERPLAY[style], "runs": 0, **_results(),
            })
            strategy["runs"] += 1
            strategy[battle.winner] += 1
            lead = tuple(sorted(f.mon["id"] for f in battle.teams[0][:width]))
            row["leads"][lead] += 1
    for row, detail in zip(standings, details):
        row["avgTurns"] = round(row.pop("turns") / max(1, runs), 1)
        row["ci"] = wilson(row["win"], runs)
        row["difficulty"] = difficulty
        row.update(detail.report())
        for block in row["strategies"].values():
            block["ci"] = wilson(block["win"], block["runs"])
        row["strategies"] = sorted(row["strategies"].values(), key=lambda block: (
            block["win"] / block["runs"], -block["loss"], block["style"]))
        lead, appearances = row.pop("leads").most_common(1)[0]
        row["lead"] = {"ids": lead, "runs": appearances}
    return standings


def batch(e, fmt, team, runs, seed, difficulty: simulation.Difficulty = "ultra"):
    width = 2 if fmt == "Doubles" else 1
    totals = _results()
    breakdown, overall = {}, {}
    turns = 0
    detail = _Detail(width)
    for match_seed in _match_seeds(e, fmt, runs, seed):
        match = matchup(e, fmt, team, match_seed)
        battle = _play(e, fmt, team, match, difficulty)
        result, turn_count = battle.winner, battle.turn - 1
        totals[result] += 1
        turns += turn_count
        detail.add(battle, result)
        block = breakdown.setdefault(match.style, _style_stats(match.style))
        block["runs"] += 1
        block[result] += 1
        block["turns"] += turn_count
        if block["activated"] is not None:
            block["activated"] += match.style in battle.activated[1]
        _observe(overall, match.player, battle.teams[0], width, result)
        _observe(block["members"], match.player, battle.teams[0], width, result)
        _observe(block["foes"], [e.P[c.id] for c in match.roster], battle.teams[1], width, result)
        mine, foe = [[f.mon["id"] for f in side] for side in battle.teams]
        lead, back = tuple(sorted(mine[:width])), tuple(sorted(mine[width:]))
        line = block["lineups"].setdefault((lead, back), {"lead": lead, "back": back, "runs": 0, **_results()})
        line["runs"] += 1
        line[result] += 1
        if not block["example"] or result == "loss" and block["example"]["result"] != "loss":
            block["example"] = {"seed": match_seed, "result": result, "turns": turn_count, "leadSize": width,
                                "mine": mine, "foe": foe, "opponent": [_brief(c.resolved) for c in match.roster]}
    for block in breakdown.values():
        block["ci"] = wilson(block["win"], block["runs"])
        block["avgTurns"] = round(block.pop("turns") / block["runs"], 1)
        block["members"] = list(block["members"].values())
        block["foes"] = sorted(block["foes"].values(), key=lambda row: (-row["loss"], -row["picked"], row["id"]))
        block["lineups"] = sorted(block["lineups"].values(), key=lambda row: -row["runs"])[:5]
    return {"runs": runs, **totals, "avgTurns": round(turns / runs, 1), "seed": seed, "difficulty": difficulty,
            "ci": wilson(totals["win"], runs), **detail.report(),
            "dataset": {"season": next((s for s in e.d["seasons"] if s != "Current"), None),
                        "generatedAt": e.d["generatedAt"]},
            "members": list(overall.values()), "strategies": sorted(breakdown.values(), key=lambda b: b["win"] / b["runs"])}
