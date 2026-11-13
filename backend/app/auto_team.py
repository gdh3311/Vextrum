"""Build editable six-Pokémon drafts around selected play styles and fixed sets."""
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from .engine import ROLE_MOVES, Engine, weight
from .parties import _member, recommended
from .typechart import TYPES, type_multiplier


@dataclass(frozen=True)
class Style:
    label: str
    features: tuple[str, ...]
    doubles_only: bool = False
    minimum: tuple[int, ...] = ()

    @property
    def requirements(self):
        return zip(self.features, self.minimum or (1,) * len(self.features))


STYLES = {
    "balance": Style("균형형", ("physical", "special", "bulky")),
    "speed": Style("스피드 중심", ("fast_attacker",), minimum=(3,)),
    "physical": Style("물리 중심", ("physical", "special"), minimum=(3, 1)),
    "special": Style("특수 중심", ("special", "physical"), minimum=(3, 1)),
    "bulky": Style("내구 중심", ("bulky", "recovery"), minimum=(3, 1)),
    "tailwind": Style("순풍", ("tailwind", "fast_attacker"), True),
    "trickroom": Style("트릭룸", ("trickroom", "slow_attacker"), True, (1, 2)),
    "rain": Style("비", ("rain_set", "rain_core")),
    "sun": Style("쾌청", ("sun_set", "sun_core")),
    "sand": Style("모래바람", ("sand_set", "sand_core")),
    "snow": Style("눈", ("snow_set", "snow_core")),
    "psychic": Style("사이코필드", ("psychic_set", "psychic_attack"), True),
    "setup": Style("랭크업", ("setup_attacker",)),
    "pivot": Style("교체 운영", ("pivot", "bulky")),
}
FEATURE_NAMES = {
    "physical": "물리 화력", "special": "특수 화력", "bulky": "내구", "tailwind": "순풍 시동",
    "attacker": "화력", "trickroom": "트릭룸 시동", "slow_attacker": "저속 화력",
    "rain_set": "비 시동", "rain_attack": "비를 활용하는 기술·특성", "sun_set": "쾌청 시동",
    "sun_attack": "쾌청을 활용하는 기술·특성", "psychic_set": "사이코메이커",
    "psychic_attack": "와이드포스", "setup_attacker": "랭크업 기술과 화력", "pivot": "교체 기술",
    "fast_attacker": "빠른 공격수", "recovery": "회복 기술",
    "rain_core": "비를 활용하는 공격수", "sun_core": "쾌청을 활용하는 공격수",
    "sand_set": "모래바람 시동", "sand_core": "모래바람을 활용하는 공격수",
    "snow_set": "눈 시동", "snow_core": "눈을 활용하는 공격수",
}
STYLE_MOVES = {"Tailwind", "Trick Room", "Rain Dance", "Sunny Day", "Expanding Force"} | ROLE_MOVES["setup"] | ROLE_MOVES["pivot"]
STYLE_ABILITIES = {"Drizzle", "Swift Swim", "Drought", "Chlorophyll", "Solar Power", "Psychic Surge"}
DRAFT_MOVES = STYLE_MOVES | {"Sandstorm", "Snowscape"} | ROLE_MOVES["recovery"]
DRAFT_ABILITIES = STYLE_ABILITIES | {"Sand Stream", "Sand Rush", "Snow Warning", "Slush Rush"}
WEATHER_STYLES = {"rain", "sun", "sand", "snow"}
DISCOVERY_STYLES = ("balance", "speed", "physical", "special", "bulky", "rain", "sun", "tailwind", "trickroom")
SCREEN_RUNS = 30
FINAL_RUNS = 80
# 평가 깊이: (1차 선별 판 수, 최종 검증 판 수)
DEPTHS = {"quick": (16, 40), "standard": (SCREEN_RUNS, FINAL_RUNS), "deep": (48, 160)}
RANKER_GAMES = {"quick": 1, "standard": 2, "deep": 4}
DRAFT_LIMIT = 20
FINAL_LIMIT = 6


@dataclass
class Candidate:
    set: dict
    resolved: dict
    species: str
    features: frozenset[str]
    matchups: tuple[float, ...]
    weak: tuple[bool, ...]
    resist: tuple[bool, ...]
    popularity: float
    teammates: frozenset[str]

    @property
    def id(self):
        return self.set["id"]


def species(e, pid):
    return e.P[pid]["name"].split("-", 1)[0]


def _candidate(e, fmt, meta, s):
    r = e.resolve(s, fmt)
    moves = set(r["moves"])
    features = set(e.roles(r, fmt))
    if "mixed" in features:
        features.update(("physical", "special"))
    attacker = bool(features & {"physical", "special"})
    ability = r["ability"]
    for key, condition in {
        "attacker": attacker,
        "fast_attacker": attacker and "fast" in features,
        "slow_attacker": attacker and r["speed"] <= 95 and "trickroom" not in features,
        "setup_attacker": attacker and "setup" in features,
        "rain_set": ability == "Drizzle" or "Rain Dance" in moves,
        "rain_attack": attacker and (ability == "Swift Swim" or "Electro Shot" in moves
                                     or ("Hurricane" in moves and ability != "Drizzle")),
        "sun_set": ability == "Drought" or "Sunny Day" in moves,
        "sun_attack": attacker and (ability in {"Chlorophyll", "Solar Power"}
                                    or bool(moves & {"Solar Beam", "Solar Blade"}) and ability != "Drought"),
        "psychic_set": ability == "Psychic Surge",
        "psychic_attack": "Expanding Force" in moves and "Flying" not in r["types"] and ability != "Levitate",
        "other_weather": ability in {"Sand Stream", "Snow Warning"} or bool(moves & {"Sandstorm", "Snowscape"}),
        "sand_set": ability == "Sand Stream" or "Sandstorm" in moves,
        "snow_set": ability == "Snow Warning" or "Snowscape" in moves,
    }.items():
        if condition:
            features.add(key)
    attack_types = {e.M[m]["type"] for m in moves if e.M[m]["power"] >= 65}
    for key, payoff in {
        "rain": "rain_attack" in features or ("Water" in r["types"] and "Water" in attack_types) or "Weather Ball" in moves,
        "sun": "sun_attack" in features or ("Fire" in r["types"] and "Fire" in attack_types) or "Weather Ball" in moves,
        "sand": ability == "Sand Rush" or "Rock" in r["types"] and "bulky" in features,
        "snow": ability == "Slush Rush" or ("Ice" in r["types"] and ("Blizzard" in moves or "bulky" in features)),
    }.items():
        if attacker and payoff and f"{key}_set" not in features:
            features.add(f"{key}_core")
    modifiers = [type_multiplier(t, r["types"], ability) for t in TYPES]
    u = e.P[s["id"]]["usage"].get(fmt, {})
    return Candidate(s, r, species(e, s["id"]), frozenset(features),
                     tuple(e.matchup(r, f, fmt)["score"] for f in meta),
                     tuple(m >= 2 for m in modifiers), tuple(m <= .5 for m in modifiers),
                     weight(u.get("rank", 250)), frozenset(u.get("teammates", [])[:8]))


def _generated_sets(e, fmt, pid, *, required=False, draft=False):
    p = e.P[pid]
    base = e.default_set(pid, fmt)
    usage = p["usage"].get(fmt, {})
    style_moves = DRAFT_MOVES if draft else STYLE_MOVES
    style_abilities = DRAFT_ABILITIES if draft else STYLE_ABILITIES
    items = list(dict.fromkeys([base["item"], *(row["name"] for row in usage.get("items", [])[:4 if required else 2])]))
    if required and None not in items:
        items.append(None)
    for form in p["megas"]:
        if form["stone"] and form["stone"] in e.d["items"] and form["stone"] not in items:
            if set(form["abilities"]) & style_abilities:
                items.append(form["stone"])
    seen = set()
    for item in items:
        mega = e.find_mega(p, stone=item)
        chosen_ability = base["ability"] if base["ability"] in p["abilities"] else next(iter(p["abilities"]), None)
        alternatives = [chosen_ability]
        if not mega:
            alternatives += [a["name"] for a in usage.get("abilities", [])
                             if a["name"] in style_abilities and a["name"] in p["abilities"] and a["pct"] >= 12]

        def usable(move):
            m = e.M.get(move)
            if not m or m.get("unknown") or m.get("selfdestruct"):
                return False
            if m["category"] == "Status":
                if item == "Assault Vest":
                    return False
                if item in {"Choice Band", "Choice Specs", "Choice Scarf"}:
                    return move in {"Trick", "Switcheroo"}
            return True

        preferred = [r["name"] for r in usage.get("moves", [])]
        fallback = sorted(p["learnset"], key=lambda m: (
            e.M[m]["type"] in p["types"], e.M[m]["power"], e.M[m]["accuracy"]), reverse=True)
        moves = list(dict.fromkeys(m for m in [*base["moves"], *preferred, *fallback] if usable(m)))[:4]
        if not any(e.M[m]["power"] for m in moves):
            attack = next((m for m in fallback if usable(m) and e.M[m]["power"]), None)
            if attack:
                moves = moves[:3] + [attack]
        if not moves:
            continue
        variants = [moves]
        # A used support move may sit just outside the four most common moves.
        for row in usage.get("moves", [])[:10]:
            mv = row["name"]
            if row["pct"] < 15 or mv not in style_moves or mv in moves or not usable(mv):
                continue
            drop = next((i for i in range(len(moves) - 1, -1, -1) if moves[i] not in style_moves), None)
            if drop is not None and (e.M[mv]["power"] or any(e.M[m]["power"] for i, m in enumerate(moves) if i != drop)):
                variants.append(moves[:drop] + [mv] + moves[drop + 1:])
        for ability in dict.fromkeys(alternatives):
            for variant in variants:
                key = item, ability, tuple(variant)
                if key in seen:
                    continue
                seen.add(key)
                yield {**base, "item": item, "mega": mega["name"] if mega else None, "ability": ability, "moves": variant}


def candidate_sets(e: Engine, fmt: str, *, draft=False):
    ranked = e.ranked(fmt)
    # Look beyond the top 80 for weather/field starters and dedicated speed control.
    species_ids = [p["id"] for p in ranked[:90]]
    abilities = {"Drizzle", "Drought", "Psychic Surge", "Swift Swim", "Chlorophyll"}
    if draft:
        abilities |= {"Sand Stream", "Snow Warning", "Sand Rush", "Slush Rush"}
    for p in ranked[90:]:
        usage = p["usage"].get(fmt, {})
        if (any(row["name"] in abilities
                and row["pct"] >= 25 for row in usage.get("abilities", []))
                or any(row["name"] in {"Trick Room", "Expanding Force"} and row["pct"] >= 35
                       for row in usage.get("moves", []))):
            species_ids.append(p["id"])
    for pid in species_ids:
        yield from _generated_sets(e, fmt, pid, draft=draft)


@lru_cache(maxsize=6)
def _pool(e: Engine, fmt: str):
    meta = e.meta(fmt, 20)
    return meta, tuple(_candidate(e, fmt, meta, s) for s in candidate_sets(e, fmt, draft=True))


def _slow_variant(e, fmt, meta, candidate):
    r = candidate.resolved
    if (r["item"] == "Choice Scarf" or r["speed"] > 140
            or not candidate.features & {"attacker", "trickroom"}):
        return None
    s = candidate.set
    physical = "physical" in candidate.features and "special" not in candidate.features
    nature = "Brave" if physical else "Quiet"
    points = r["points"].copy()
    spare = points["spe"]
    points["spe"] = 0
    for stat in ("hp", "def", "spd"):
        extra = min(spare, 32 - points[stat])
        points[stat] += extra
        spare -= extra
    points["spe"] = spare
    if s["nature"] == nature and points == r["points"]:
        return None
    alternative = _candidate(e, fmt, meta, {**s, "nature": nature, "points": points})
    return alternative if alternative.resolved["speed"] <= 95 else None


@lru_cache(maxsize=6)
def _room_pool(e, fmt):
    meta, pool = _pool(e, fmt)
    return tuple(row for c in pool if (row := _slow_variant(e, fmt, meta, c)) is not None)


def _eligible(c, chosen):
    item = c.set.get("item")
    return all(c.species != m.species and (not item or item != m.set.get("item")) for m in chosen)


TYPE_CORES = {
    "fwg": ({"Fire", "Water", "Grass"}, "불·물·풀"),
    "dsf": ({"Dragon", "Steel", "Fairy"}, "드래곤·강철·페어리"),
}


# 독창성: (사용률 가중치, 랭커 동시 채용 보너스 배율, 랭커 파티와 4마리 이상 겹칠 때 감점, 보여 줄 팀끼리 달라야 할 마릿수,
#          초안 시작점으로 쓸 '에이스' 수, 에이스 후보에서 뺄 사용률 상위 종 수)
ORIGINALITY = {
    "meta": (1.5, 1.0, 0., 1, 0, 0),
    "balanced": (0., .4, 7., 2, 3, 3),
    "unique": (-1.2, .2, 12., 3, 3, 8),
}
# 최종 순위에서 랭커 파티와 4마리 이상 겹칠 때 승률에서 빼는 값 (겹치는 마릿수 - 3 마다)
COPY_RATE = {"meta": 0., "balanced": 0., "unique": 0.}
# 랭커 파티와 겹쳐도 되는 최대 마릿수 (넘으면 후보에서 뺀다). 이 안에서는 승률만 본다.
OVERLAP_CAP = {"meta": 6, "balanced": 3, "unique": 2}
# 깊이별: 전략마다 추가로 만드는 에이스 초안 수, 후보 수, 경주 단계 [(판 수, 남길 팀 수), ...]
SEARCH = {
    "quick": (4, 36, [(10, 14), (20, 6)]),
    "standard": (6, 56, [(12, 22), (24, 10), (32, 6)]),
    "deep": (9, 90, [(14, 34), (28, 14), (48, 8)]),
}


@dataclass(frozen=True)
class Extra:
    """초안 점수에 더하는 조건: 타입 코어, 랭커 동시 채용 코어, 인기 가중치, 랭커 파티 베끼기 감점."""
    core: str = ""
    pairs: tuple = ()  # ((id_a, id_b, 보너스), ...)
    popularity: float = 1.5
    ranker_teams: tuple = ()  # 랭커 파티의 종 집합들
    overlap: float = 0.

    def pair_bonus(self, ids):
        return sum(bonus for a, b, bonus in self.pairs if a in ids and b in ids)

    def copy_penalty(self, chosen):
        if not self.overlap or not self.ranker_teams or len(chosen) < 4:
            return 0.
        names = {c.species for c in chosen}
        worst = max(len(names & team) for team in self.ranker_teams)
        return self.overlap * max(0, worst - 3) ** 1.5


DEFAULT_EXTRA = Extra(popularity=3.5)


def ranker_pairs(e, fmt):
    """랭커 파티에서 기대보다 자주 함께 쓰인 쌍 → 보너스 (팀 수와 배율에 비례)."""
    from .recommend import ranker_cores

    return tuple((*row["ids"], round(.9 * min(row["teams"], 9) ** .5 * min(row["lift"], 2.5), 2))
                 for row in ranker_cores(e, fmt, 2, 80) if row["lift"] >= .9)


def _score(chosen, goals, weights, extra=DEFAULT_EXTRA):
    counts = Counter(key for c in chosen for key in c.features)
    features = counts.keys()
    coverage = sum(w * max(c.matchups[i] for c in chosen) for i, w in enumerate(weights))
    pressure = 0
    for i in range(len(TYPES)):
        weak = sum(c.weak[i] for c in chosen)
        resist = sum(c.resist[i] for c in chosen)
        pressure += 1.4 * max(0, weak - 1 - resist) + 2.5 * (weak >= 3 and not resist)
    if extra.core == "resist":
        pressure *= 1.8
    goal_points = 0
    for goal in goals:
        needed = tuple(STYLES[goal].requirements)
        hits = sum(min(counts[key], minimum) for key, minimum in needed)
        goal_points += 8 * hits + 7 * (hits == sum(minimum for _, minimum in needed))
    variety = len(features & {"physical", "special", "bulky", "priority", "pivot", "speedcontrol", "hazard", "redirect"})
    ids = {c.id for c in chosen}
    teammates = sum(len(c.teammates & ids) for c in chosen)
    megas = sum(bool(c.resolved["mega"]) for c in chosen)
    weather = next((goal for goal in goals if goal in WEATHER_STYLES), None)
    conflict = 0
    if weather:
        conflicting = {f"{other}_set" for other in WEATHER_STYLES - {weather}}
        conflict = 12 * sum(bool(c.features & conflicting) for c in chosen)
    if "trickroom" in goals:
        variety += min(3, sum("slow_attacker" in c.features for c in chosen))
    core = 0
    if extra.core in TYPE_CORES:
        types = {t for c in chosen for t in c.resolved["types"]}
        core = 3 * len(TYPE_CORES[extra.core][0] & types)
    return (coverage * .55 + goal_points + variety * 1.25 + teammates * .4 + core
            + extra.popularity * sum(c.popularity for c in chosen) + extra.pair_bonus(ids)
            - extra.copy_penalty(chosen)
            - pressure - 10 * max(0, megas - 1) - 20 * max(0, megas - 2) - conflict)


def _keep_best(options, goals, weights, limit=16, extra=DEFAULT_EXTRA):
    best = {}
    for group in options:
        key = frozenset(c.id for c in group)
        score = _score(group, goals, weights, extra)
        if key not in best or score > best[key][0]:
            best[key] = (score, group)
    return sorted(best.values(), key=lambda row: -row[0])[:limit]


_VARIETY = {"physical", "special", "bulky", "priority", "pivot", "speedcontrol", "hazard", "redirect"}


def _extensions(group, pool, goals, weights, extra):
    """group + (c,) 의 _score 를 모든 후보 c 에 대해 빠르게 계산한다 (팀의 공통 부분은 한 번만 센다).
    결과는 _score(group + (c,)) 와 같다 (tests/test_auto_team_speed.py 에서 확인)."""
    n_types = len(TYPES)
    gmax = [max((c.matchups[i] for c in group), default=0) for i in range(len(weights))]
    weak = [sum(c.weak[i] for c in group) for i in range(n_types)]
    resist = [sum(c.resist[i] for c in group) for i in range(n_types)]
    counts = Counter(key for c in group for key in c.features)
    ids = {c.id for c in group}
    species = {c.species for c in group}
    items = {c.set.get("item") for c in group if c.set.get("item")}
    teammates = sum(len(c.teammates & ids) for c in group)
    megas = sum(bool(c.resolved["mega"]) for c in group)
    popularity = sum(c.popularity for c in group)
    pair_base = extra.pair_bonus(ids)
    partner = {}
    for a, b, bonus in extra.pairs:
        if a in ids and b not in ids:
            partner[b] = partner.get(b, 0) + bonus
        elif b in ids and a not in ids:
            partner[a] = partner.get(a, 0) + bonus
    overlaps = [len(species & team) for team in extra.ranker_teams] if extra.overlap and extra.ranker_teams else None
    weather = next((goal for goal in goals if goal in WEATHER_STYLES), None)
    conflicting = {f"{other}_set" for other in WEATHER_STYLES - {weather}} if weather else set()
    conflict_base = sum(bool(c.features & conflicting) for c in group)
    core_types = TYPE_CORES[extra.core][0] if extra.core in TYPE_CORES else None
    types = {t for c in group for t in c.resolved["types"]}
    needs = [tuple(STYLES[goal].requirements) for goal in goals]
    resist_scale = 1.8 if extra.core == "resist" else 1.
    pairs_w = list(zip(weights, gmax))
    out = []
    for c in pool:
        if c.species in species or (c.set.get("item") and c.set.get("item") in items):
            continue
        coverage = 0.
        for (w, g), m in zip(pairs_w, c.matchups):
            coverage += w * (m if m > g else g)
        pressure = 0.
        for i in range(n_types):
            wk = weak[i] + c.weak[i]
            rs = resist[i] + c.resist[i]
            if wk - 1 - rs > 0:
                pressure += 1.4 * (wk - 1 - rs)
            if wk >= 3 and not rs:
                pressure += 2.5
        pressure *= resist_scale
        feats = c.features
        goal_points = 0
        for needed in needs:
            hits = sum(min(counts[key] + (key in feats), minimum) for key, minimum in needed)
            goal_points += 8 * hits + 7 * (hits == sum(minimum for _, minimum in needed))
        present = (counts.keys() | feats)
        variety = len(present & _VARIETY)
        if "trickroom" in goals:
            variety += min(3, counts["slow_attacker"] + ("slow_attacker" in feats))
        mates = teammates + len(c.teammates & ids) + sum(1 for x in group if c.id in x.teammates) + (c.id in c.teammates)
        mega = megas + bool(c.resolved["mega"])
        conflict = 12 * (conflict_base + bool(feats & conflicting)) if weather else 0
        core = 3 * len(core_types & (types | set(c.resolved["types"]))) if core_types else 0
        copy = 0.
        if overlaps is not None and len(group) + 1 >= 4:
            worst = max(o + (c.species in team) for o, team in zip(overlaps, extra.ranker_teams))
            copy = extra.overlap * max(0, worst - 3) ** 1.5
        score = (coverage * .55 + goal_points + variety * 1.25 + mates * .4 + core
                 + extra.popularity * (popularity + c.popularity) + pair_base + partner.get(c.id, 0) - copy
                 - pressure - 10 * max(0, mega - 1) - 20 * max(0, mega - 2) - conflict)
        out.append((score, group + (c,)))
    return out


def _draft(pool, fixed, required, goals, weights, limit, extra=DEFAULT_EXTRA):
    current = [tuple(fixed)]
    for variants in [*required, *[pool] * 6]:
        if current and len(current[0]) >= 6:
            break
        best = {}
        for group in current:
            for score, option in _extensions(group, variants, goals, weights, extra):
                key = frozenset(c.id for c in option)
                if key not in best or score > best[key][0]:
                    best[key] = (score, option)
        current = [group for _, group in sorted(best.values(), key=lambda row: -row[0])[:limit]]
    return current


def _fit_count(group, roster):
    counts = Counter(key for c in roster for key in c.features)
    return sum(min(counts[key], minimum) for style in group for key, minimum in STYLES[style].requirements)


def _rank_key(report, objective):
    worst = min(row["win"] / row["runs"] for row in report["strategies"])
    total = report["win"] / report["runs"]
    if objective == "ranker" and "rankerRate" in report:
        combined = ((report["win"] + .5 * report["draw"]) / report["runs"] + report["rankerRate"]) / 2
        return combined, total, worst
    scores = (worst, total) if objective == "stability" else (total, worst)
    return (*scores, report["draw"])


def _merge(total, report):
    """같은 팀의 두 성적표를 합친다 (판 수·승패·전략별 성적). 그 밖의 상세는 최근 것을 쓴다."""
    if total is None:
        return report
    merged = {**report}
    for key in ("win", "loss", "draw", "runs"):
        merged[key] = total[key] + report[key]
    old = {row["style"]: row for row in total["strategies"]}
    rows = []
    for row in report["strategies"]:
        prev = old.get(row["style"])
        rows.append({**row, **({k: prev[k] + row[k] for k in ("win", "loss", "draw", "runs")} if prev else {})})
    rows.sort(key=lambda r: (r["win"] / r["runs"], -r["loss"], r["style"]))
    merged["strategies"] = rows
    if "rankerRate" in total and "rankerRate" in report:
        merged["rankerRate"] = (total["rankerRate"] + report["rankerRate"]) / 2
    return merged


def _race(picks, stages, measure, rank, track, seed=821239, family=None):
    """후보가 많을 때: 모두 짧게 싸우고, 성적이 좋은 쪽만 더 싸운다 (누적 성적으로 판단).
    단계마다 비슷한 팀(5마리 이상 같음)은 성적이 좋은 하나만 남겨 다양한 후보가 다음 단계로 간다."""
    alive = list(picks)
    totals = {}
    for number, (runs, keep) in enumerate(stages):
        reports = measure(alive, runs, seed + 7_919 * number)
        track.update(done=number + 1, battles=len(alive) * runs)
        for (group, roster), report in zip(alive, reports):
            key = (group, frozenset(c.id for c in roster))
            totals[key] = _merge(totals.get(key), report)
        rows = sorted(((g, r, totals[(g, frozenset(c.id for c in r))]) for g, r in alive),
                      key=lambda row: rank(row[2]), reverse=True)
        kept, names, families = [], [], Counter()
        cap = max(2, -(-keep // 3)) if family else keep  # 한 전략 가족이 남은 자리의 1/3을 넘지 않게
        for row in rows:
            species_set = frozenset(c.species for c in row[1])
            if any(len(species_set & other) >= 5 for other in names):
                continue
            kind = family(row[1]) if family else None
            if family and families[kind] >= cap:
                continue
            kept.append(row)
            names.append(species_set)
            families[kind] += 1
            if len(kept) == keep:
                break
        if len(kept) < keep:  # 다양성 때문에 모자라면 남은 자리를 성적순으로 채운다
            kept += [row for row in rows if row not in kept][:keep - len(kept)]
        if number < len(stages) - 1 and kept:
            from .battle_lab import wilson

            # 적응형 판 수 (명세 7.1): 경계 아래라도 신뢰구간 상한이 경계 팀 승률에 닿는 접전 팀은 더 싸워 본다.
            threshold = 100 * _rate(kept[-1][2])
            extra = [row for row in rows if row not in kept
                     and wilson(row[2]["win"] + .5 * row[2]["draw"], row[2]["runs"])[1] >= threshold][:max(1, keep // 3)]
            # 전략 코어 보호 (명세 5.1): 아직 남지 못한 전략 가족은 가장 좋은 팀 하나를 다음 단계로 보낸다.
            if family:
                have = {family(r[1]) for r in kept + extra}
                for row in rows:
                    kind = family(row[1])
                    if kind not in have and row not in kept and row not in extra:
                        extra.append(row)
                        have.add(kind)
            kept += extra
        alive = [(g, r) for g, r, _ in kept]
        screened = kept
    return screened


def _versions(e):
    from .regulation import versions

    return versions(e.d)


def _rate(report):
    return (report["win"] + .5 * report["draw"]) / max(1, report["runs"])


LEAGUE_RUNS = {"quick": 8, "standard": 16, "deep": 32}
POLICY_TEAMS = 4
SELECT_STYLES = ["balanced", "aggressive", "defensive", "setup", "pivot"]
V6_SELECT_RUNS = {"quick": 48, "standard": 96, "deep": 160}


def _league(report):
    from .battle_lab import wilson

    rate = _rate(report)
    return {"rate": round(rate, 3), "games": report["runs"], "ci": wilson(report["win"] + .5 * report["draw"],
                                                                           report["runs"])}


def _metrics(e, fmt, roster, report, leagues, overlap, strategy, stress=(None, None)):
    """다목적 지표 (명세 7.1): 평균 승률, 하위 꼬리, 랭크 리그 견고성, 선출 다양성, 0선출, 개성, 전략."""
    rates = sorted(r["win"] / r["runs"] for r in report["strategies"])
    tail = sum(rates[:2]) / min(2, len(rates)) if rates else 0
    meta_rate = _rate(report)
    other_rate = min(_rate(leagues["마스터볼"]), _rate(leagues["챔피언"]))
    picked = {m["id"]: m.get("pickRate", 0) for m in report.get("memberStats", ())}
    zero = [c.resolved["ko"] or c.resolved["name"] for c in roster if picked.get(c.id, 0) < 5]
    leads = [r for r in report.get("leadStats", ()) if r["runs"] >= .1 * report["runs"]]
    analysis = strategy.analyze(e, fmt, roster)
    warnings = list(analysis["warnings"])
    champion = _rate(leagues["챔피언"])
    if champion < meta_rate - .15:
        warnings.append("챔피언 리그에서 성적이 크게 떨어집니다. 낮은 랭크 CPU의 실수에 기대는 팀일 수 있습니다.")
    if _rate(leagues["몬스터볼"]) < .8:
        warnings.append("몬스터볼 리그에서도 자주 집니다. 기본 운영에 문제가 있을 수 있습니다.")
    worst, stressed = stress
    plans = []
    for block in report["strategies"]:
        for pick in block.get("picks", [])[:1]:
            name = lambda pid: next((c.resolved["ko"] or c.resolved["name"] for c in roster if c.id == pid), pid)
            plans.append({"against": block["label"], "leads": [name(p) for p in pick["leads"]],
                          "back": [name(p) for p in pick["back"]], "runs": pick["runs"], "win": pick["win"],
                          "opening": pick.get("opening", [])})
    from .battle_lab import wilson

    low, high = (x / 100 for x in wilson(report["win"] + .5 * report["draw"], report["runs"]))
    return {"winRate": round(meta_rate, 3), "winLow": round(low, 3), "winHigh": round(high, 3),
            "lowerTail": round(tail, 3),
            "otherPolicy": round(other_rate, 3),
            "robust": round(min(meta_rate, other_rate), 3), "leadOptions": len(leads), "zeroPick": zero,
            "novelty": 6 - overlap, "family": strategy.family(analysis), "analysis": analysis,
            "warnings": warnings,
            "leagues": {name: _league(r) for name, r in leagues.items()},
            "stress": ({"against": next((b["label"] for b in report["strategies"] if b["style"] == worst), worst),
                        **_league(stressed)} if stressed else None),
            "plans": plans,
            "lossTags": report.get("lossTags", [])}


def _dominates(a, b, keys):
    return all(a[k] >= b[k] for k in keys) and any(a[k] > b[k] for k in keys)


def _pareto(rows, metrics, team_key, limit, objective, distance=1):
    """파레토 + 다양성 선별 (명세 7). 공격형(평균 승률) → 안정형(하위 꼬리·정책 견고성) → 변칙형(개성) 순으로
    서로 다른 전략 가족과 다른 구성(5마리 이상 같지 않음)을 고른다. 각 팀에 성격 라벨을 붙인다."""
    # 최종 우수성은 신뢰구간 하한(winLow)으로, 후보에서 빼는 판단은 상한(winHigh)으로 한다.
    keys = ("winLow", "lowerTail", "robust", "leadOptions", "novelty")
    info = [(row, metrics[team_key(row[0], row[1])]) for row in rows]
    for _, m in info:
        m.setdefault("winLow", m["winRate"])
    front = [x for x in info if not any(_dominates(y[1], x[1], keys) for y in info if y is not x)]
    rest = [x for x in info if x not in front]
    best = max(m["winLow"] for _, m in info)
    picks, families = [], set()

    def distinct(row):
        # 보여 줄 팀끼리는 최소 max(2, 개성 거리)마리가 달라야 한다 (독창적이면 3마리).
        names = {c.species for c in row[1]}
        need = max(2, distance)
        return all(len(names - {c.species for c in r[1]}) >= need for r, _ in picks)

    top_robust = max(m["robust"] for _, m in info)

    def take(pool, key, label, floor=0.):
        # 다른 전략 가족을 선호하되, 성능 하한(평균 승률·정책 견고성)을 넘는 팀 안에서만 고른다.
        # 하한은 신뢰구간 상한으로 판정한다: 표본이 작아 생긴 차이만으로 팀을 떨어뜨리지 않는다 (명세 7.1).
        options = [x for x in pool if x not in picks and distinct(x[0])
                   and x[1].get("winHigh", x[1]["winRate"]) >= floor
                   and x[1]["robust"] >= top_robust - .15]
        if not options:
            return
        best_option = max(options, key=key)
        fresh = [x for x in options if x[1]["family"] not in families
                 and x[1]["winRate"] >= best_option[1]["winRate"] - .06]
        choice = max(fresh or options, key=key)
        choice[1]["profile"] = label
        picks.append(choice)
        families.add(choice[1]["family"])

    first = {"stability": lambda x: (x[1]["lowerTail"], x[1]["robust"]),
             "ranker": lambda x: (x[0][2].get("rankerRate", 0), x[1]["winLow"])}.get(
        objective, lambda x: (x[1]["winLow"], x[1]["robust"]))
    take(front, first, "공격형" if objective == "win" else "안정형" if objective == "stability" else "랭커 대응형")
    take(front + rest, lambda x: (x[1]["lowerTail"] + x[1]["robust"], x[1]["winLow"]), "안정형", best - .08)
    take(front + rest, lambda x: (x[1]["novelty"], x[1]["winLow"]), "변칙형", best - .10)
    for pool in (front, rest):
        while len(picks) < limit:
            before = len(picks)
            take(pool, lambda x: (x[1]["winLow"], x[1]["robust"]), "균형형", best - .10)
            if len(picks) == before:
                break
    # 품질 하한을 넘는 팀만 보여 준다. 2팀뿐이면 2팀만 (명세 10: 구색 맞추기 금지).
    return [row for row, _ in picks][:max(limit, 3)]


def _shortlist(drafts, fixed_count, limit=None):
    """Keep an opening for each style before filling slots with distinct alternatives."""
    seen, output = set(), []
    distance = min(2, 6 - fixed_count)
    for min_changes in (distance, 1):
        for index in range(max((len(rows) for _, rows in drafts), default=0)):
            for group, rows in drafts:
                if index >= len(rows):
                    continue
                roster = rows[index]
                ids = frozenset(c.id for c in roster)
                if (group, ids) in seen:
                    continue
                if index and any(group == g and len(ids - old) < min_changes for g, old, _ in output):
                    continue
                output.append((group, ids, roster))
                seen.add((group, ids))
                if len(output) == (limit or DRAFT_LIMIT):
                    return [(g, r) for g, _, r in output]
    return [(g, r) for g, _, r in output]


def _diverse(rows, limit, split_weather, distance=1):
    signatures = [frozenset(c.species for c in roster) for _, roster, _ in rows]
    chosen = set()
    if split_weather:
        groups = set()
        for i, (group, _, _) in enumerate(rows):
            if group not in groups:
                chosen.add(i)
                groups.add(group)
    for gap in range(distance, 0, -1):
        for i, (group, _, _) in enumerate(rows):
            if len(chosen) >= limit:
                break
            if all(len(signatures[i] - signatures[j]) >= gap
                   for j in chosen if not split_weather or rows[j][0] == group):
                chosen.add(i)
    return [row for i, row in enumerate(rows) if i in chosen][:limit]


JOKER_RANK = 40


def _aces(e, fmt, available, group, weights, count, skip_top, taken):
    """전략의 핵심 역할을 맡을 수 있는 포켓몬 중 메타 상성이 좋은 '에이스' 후보 (사용률 최상위 몇 종은 뺀다)."""
    if not count:
        return []
    top = {species(e, p["id"]) for p in e.ranked(fmt)[:skip_top]}
    keys = {feature for style in group for feature, _ in STYLES[style].requirements} or {"attacker"}
    rows = [c for c in available if c.features & keys and c.species not in top and c.species not in taken]
    rows.sort(key=lambda c: -sum(w * m for w, m in zip(weights, c.matchups)))
    out, seen = [], set()
    for c in rows:
        if c.species not in seen:
            out.append(c)
            seen.add(c.species)
        if len(out) == count:
            break
    return out


def _rank_of(e, fmt, pid):
    return e.P[pid]["usage"].get(fmt, {}).get("rank") or 999


def _joker_candidates(e, fmt, meta, limit=10):
    """조커 파인더가 고른 세트 + 생성 세트 (사용률 40위 밖)."""
    rows = []
    for j in e.jokers(fmt, JOKER_RANK + 1, 20, limit=limit):
        pid = j["set"]["id"]
        if pid not in e.P:
            continue
        rows.append(_candidate(e, fmt, meta, j["set"]))
        rows += [_candidate(e, fmt, meta, s) for s in _generated_sets(e, fmt, pid, draft=True)][:2]
    return rows


def regulation_warnings(e):
    from . import regulation

    return regulation.data_warnings(e.d)


def build(e: Engine, fmt: str, styles: list[str], include: list[str], locked: list[dict], *,
          exclude: Sequence[str] = (), objective: str = "win", depth: str = "standard", cpu: str = "ultra",
          joker: str = "allow", mega: str = "auto", core: str = "", tune: str = "off", rankers: bool = True,
          originality: str = "balanced", engine: str = "v6", progress=None):
    # 엔진: v1(단일 지표) · v2/v3(전략 우선·리그 검증) · v4(+선출 계획 공동 최적화·구조 변경·하한 판단)
    #       v5(+탐색 중 간이 선출 최적화·확률적 상대 전략 열쇠·선출 우선 반사실 비교)
    # 실험용 끄기 스위치: "v5-noquick-noseason-noseed" 처럼 붙인다 (기여도 분해 벤치용).
    engine, *off = engine.split("-")
    off = set(off)
    v5 = engine == "v5"
    # v6: v4 + 평가 편향 제거 — 선별 CPU 스타일 혼합, 최종 선택은 마스터볼 혼합 스타일의 별도 시드,
    #     효과가 확인되지 않은 선출 최적화는 빼고 그 시간을 최종 선택 표본에 쓴다 (진단 보고서 5·7·10장).
    v6 = engine == "v6"
    v4 = engine in ("v4", "v5", "v6")
    label = engine
    if engine in ("v3", "v4", "v5", "v6"):
        engine = "v2"
    from . import parallel, roster_search
    from .progress import Progress
    from .recommend import ranker_rosters

    rosters = ranker_rosters(e, fmt) if rankers else ()
    skip = [stage for stage, enabled in (("tune", tune != "off"), ("rankers", bool(rosters))) if not enabled]
    track = Progress(e, progress, skip=skip)
    track.update("research")

    if any(key not in STYLES for key in styles):
        raise ValueError("현재 배틀 형식에서 사용할 수 있는 전략을 골라 주세요.")
    # 싱글에서 쓸 수 없는 더블 전용 전술(순풍·트릭룸·사이코필드)은 실패시키지 않고 빼고 만든다.
    ignored = [key for key in dict.fromkeys(styles) if STYLES[key].doubles_only and fmt != "Doubles"]
    goals = tuple(key for key in dict.fromkeys(styles) if key not in ignored)
    popularity, pair_scale, overlap, distance, ace_count, skip_top = ORIGINALITY.get(
        originality, ORIGINALITY["balanced"])
    extra_aces, draft_limit, race_stages = SEARCH.get(depth, SEARCH["standard"])
    ace_count += extra_aces if originality != "meta" else extra_aces // 2
    ids = [s["id"] for s in locked] + include
    if len(ids) > 5:
        raise ValueError("자동으로 채울 자리를 위해 고정 포켓몬은 최대 5마리까지 선택할 수 있습니다.")
    if any(pid not in e.P for pid in [*ids, *exclude]):
        raise ValueError("포켓몬 목록에서 찾을 수 없는 항목이 있습니다.")
    if len({species(e, pid) for pid in ids}) != len(ids):
        raise ValueError("같은 종의 포켓몬은 다른 폼을 포함해 한 마리만 고를 수 있습니다.")
    excluded = {species(e, pid) for pid in exclude}
    if any(species(e, pid) in excluded for pid in ids):
        raise ValueError("꼭 넣을 포켓몬이나 고정 세트를 제외 목록에서 빼 주세요.")
    meta, pool = _pool(e, fmt)
    fixed_ids = set(ids)
    from .parties import RANKERS

    # 시즌 신뢰도 가중치는 ranker_cores 에서 랭커 팀마다 (가장 새 표본 시즌 기준) 적용된다.
    extra = Extra(core=core, pairs=tuple((a, b, bonus * pair_scale)
                                         for a, b, bonus in ranker_pairs(e, fmt)),
                  popularity=popularity, overlap=overlap,
                  ranker_teams=tuple(frozenset(species(e, pid) for pid in r["ids"] if pid in e.P)
                                     for r in RANKERS if r["format"] == fmt))
    top_pairs = sorted(extra.pairs, key=lambda row: -row[2])[:6]
    track.update("research", done=1, total=1, spotlight=[pid for a, b, _ in top_pairs[:3] for pid in (a, b)],
                 notes=[f"{track.mon(a)['name']} + {track.mon(b)['name']}" for a, b, _ in top_pairs])
    jokers = ()
    if joker == "off":
        pool = tuple(c for c in pool if c.id in fixed_ids or _rank_of(e, fmt, c.id) <= JOKER_RANK)
    else:
        jokers = tuple(c for c in _joker_candidates(e, fmt, meta) if c.species not in
                       {species(e, pid) for pid in [*exclude, *ids]})
        if joker == "force":
            pool = tuple(c for c in pool if c.id in fixed_ids or _rank_of(e, fmt, c.id) <= JOKER_RANK)
        else:
            pool = (*pool, *jokers)
    if mega == "none":
        pool = tuple(c for c in pool if not c.resolved["mega"])
    weights = [weight(e.rank(f["id"], fmt) or 250) for f in meta]
    total = sum(weights) or 1
    weights = [w / total for w in weights]
    fixed = []
    for entry in locked:
        s = {**e.default_set(entry["id"], fmt), **entry}
        r = e.resolve(s, fmt)
        # A null field requests the same fallback as the regular team analysis.
        for key in ("moves", "nature", "points"):
            if s[key] is None:
                s[key] = r[key]
        c = _candidate(e, fmt, meta, s)
        if not _eligible(c, fixed):
            raise ValueError("고정 세트의 도구가 중복됩니다. 팀 빌더에서 도구를 바꾸거나 한 마리의 고정을 해제해 주세요.")
        fixed.append(c)

    fixed_species = {species(e, pid) for pid in ids}
    overlap_cap = max(OVERLAP_CAP.get(originality, 6),
                      max((len(fixed_species & team) for team in extra.ranker_teams), default=0))

    def copies(roster):
        names = {c.species for c in roster}
        return max((len(names & team) for team in extra.ranker_teams), default=0)

    def set_key(c):
        s = c.set
        return (c.id, s.get("item"), s.get("ability"), s.get("nature"), s.get("mega"), tuple(s.get("moves") or ()),
                tuple(sorted((s.get("points") or {}).items())))

    locked_keys = {set_key(c) for c in fixed}

    def valid(roster):
        megas = sum(bool(c.resolved["mega"]) for c in roster)
        # 고정한 세트는 도구·기술까지 그대로여야 한다 (같은 포켓몬의 다른 세트로 바뀌면 안 된다).
        return (len(roster) == 6 and fixed_ids <= {c.id for c in roster} and copies(roster) <= overlap_cap
                and locked_keys <= {set_key(c) for c in roster}
                and not any(c.species in excluded or not _eligible(c, roster[:i]) for i, c in enumerate(roster))
                and (megas <= 2 if mega == "auto" else megas == (1 if mega == "one" else 0))
                and (joker != "force" or any(_rank_of(e, fmt, c.id) > JOKER_RANK for c in roster))
                and (joker != "off" or all(c.id in fixed_ids or _rank_of(e, fmt, c.id) <= JOKER_RANK for c in roster)))

    if sum(bool(c.resolved["mega"]) for c in fixed) > {"auto": 2, "one": 1, "none": 0}[mega]:
        raise ValueError("고정 세트와 메가진화 조건이 충돌합니다.")
    required = [[_candidate(e, fmt, meta, s) for s in _generated_sets(e, fmt, pid, required=True, draft=True)]
                for pid in include]
    if mega == "none":
        required = [[c for c in rows if not c.resolved["mega"]] or rows for rows in required]
    has_joker = any(_rank_of(e, fmt, pid) > JOKER_RANK for pid in ids)
    if joker == "force" and not has_joker and jokers:
        required.append(list(jokers))
    has_mega = any(c.resolved["mega"] for c in fixed) or any(
        all(c.resolved["mega"] for c in rows) for rows in required if rows)
    if mega == "one" and not has_mega:
        megas = [c for c in pool if c.resolved["mega"]]
        megas.sort(key=lambda c: -c.popularity)
        required.append(megas[:40])
    weather = [key for key in goals if key in WEATHER_STYLES]
    split_weather = len(weather) > 1
    groups = [goals] if goals else [(style,) for style in DISCOVERY_STYLES
                                    if fmt == "Doubles" or not STYLES[style].doubles_only]
    if not goals and engine == "v2":
        # 전략 우선: 주 전략 + 보조 전략을 함께 갖춘 하이브리드 블루프린트도 초안을 만든다.
        from . import strategy

        groups += [group for group in strategy.blueprint_groups(fmt) if group not in groups]
    if split_weather:
        groups = [tuple(key for key in goals if key not in WEATHER_STYLES or key == target) for target in weather]
    drafts = []
    track.update("draft", total=len(groups))
    def weather_conflicts(group):
        target_weather = next((key for key in group if key in WEATHER_STYLES), None)
        return {f"{key}_set" for key in WEATHER_STYLES - {target_weather}} if target_weather else set()

    def available_for(group):
        available = (*pool, *_room_pool(e, fmt)) if "trickroom" in group else pool
        conflicting = weather_conflicts(group)
        return tuple(c for c in available if c.species not in excluded and not c.features & conflicting
                     and (mega != "none" or not c.resolved["mega"])
                     and (joker == "allow" or _rank_of(e, fmt, c.id) <= JOKER_RANK))

    search_pools = {}
    for step, group in enumerate(groups, 1):
        available = available_for(group)
        search_pools[group] = (*available, *(c for c in jokers if joker == "force"
                                            and not c.features & weather_conflicts(group)))
        room = "trickroom" in group
        wanted = [
            [*rows, *(row for c in rows if (row := _slow_variant(e, fmt, meta, c)) is not None)]
            if room else rows for rows in required
        ]
        if mega == "one":
            available = tuple(c for c in available if not c.resolved["mega"])
        rows = _draft(available, fixed, wanted, group, weights, limit=16 if goals else 9, extra=extra)
        # 같은 전략이라도 서로 다른 에이스에서 출발한 초안을 만든다 (사용률 최상위에만 몰리지 않게).
        for ace in _aces(e, fmt, available, group, weights, ace_count if len(group) == 1 or goals else 2, skip_top,
                         {c.species for c in fixed}):
            rows += _draft(available, fixed, [[ace], *wanted], group, weights, limit=6, extra=extra)[:2]
        rows = [roster for roster in rows if valid(roster)]
        if not rows:
            continue
        best_fit = max(_fit_count(group, roster) for roster in rows)
        drafts.append((group, [roster for roster in rows if _fit_count(group, roster) == best_fit]))
        track.update(done=step, spotlight=[c.id for c in drafts[-1][1][0]],
                     notes=[" · ".join(STYLES[key].label for key in group)])
    picks = _shortlist(drafts, len(ids), draft_limit)
    if not picks:
        raise ValueError("이 조건으로 6마리를 구성하기 어렵습니다. 고정 조건을 줄여 보세요.")
    if not goals:
        if not ids and not excluded and mega == "auto" and joker == "allow":
            mapped = {"balanced": "balance", "speed": "tailwind", "trickroom": "trickroom",
                      "cycle": "pivot", "setup": "setup"}
            baselines = [
                ((mapped[party["id"]],), tuple(_candidate(e, fmt, meta, m["set"]) for m in party["members"]))
                for party in recommended(e, fmt) if party["id"] in mapped
            ]
            baselines = [(group, roster) for group, roster in baselines if valid(roster)]
            picks = [*picks[:draft_limit - len(baselines)], *baselines]
        # General recommendations should not repeat the exact same six sets under different names.
        distinct = {}
        for group, roster in picks:
            key = tuple(sorted((c.id, c.set["item"], c.set["ability"], c.set["mega"], c.set["nature"],
                                tuple(c.set["moves"]), tuple(sorted(c.set["points"].items()))) for c in roster))
            distinct.setdefault(key, (group, roster))
        picks = list(distinct.values())

    # 자동 연구가 지금까지 찾은 팀 중 조건에 맞는 것을 출발점으로 더한다 (오래 연구할수록 좋아진다).
    from .research import LAB

    researched = set()
    needed = sum(minimum for style in goals for _, minimum in STYLES[style].requirements)
    seed_plans = {}
    for archetype, roster, seed_plan in LAB.seeds(e, fmt, valid, limit=12,
                                                  originality=originality if v5 and "noseed" not in off else None,
                                                  with_policy=True):
        if seed_plan and v5:
            seed_plans[roster_search.signature(roster)] = {k: tuple(v) for k, v in seed_plan.items()}
        if goals:
            if _fit_count(goals, roster) < needed:
                continue
            group = goals
        else:
            group = (archetype,) if fmt == "Doubles" or not STYLES[archetype].doubles_only else ("balance",)
        picks.append((group, roster))
        researched.add(roster_search.signature(roster))

    screen_runs, final_runs = DEPTHS.get(depth, DEPTHS["standard"])
    search_depth = depth if depth in roster_search.BUDGETS else "standard"
    for group, _ in picks:
        if group not in search_pools:
            search_pools[group] = available_for(group)

    def rank(report):
        return _rank_key(report, objective)

    # 탐색 중 찾은 선출 계획 (v5): 팀 → {미리보기 열쇠: 선출}. 멤버를 바꾼 변형은 가장 닮은 부모의 계획을 물려받는다
    # (계획에 없는 포켓몬이 들어 있으면 apply_policy 가 그 열쇠를 무시한다).
    plans = dict(seed_plans)  # 자동 연구가 팀과 함께 찾아 둔 선출 계획

    def plan_for(roster):
        sig = roster_search.signature(roster)
        if sig in plans:
            return plans[sig]
        best = max(plans, key=lambda k: len(k & sig), default=None)
        return plans[best] if best is not None and len(best & sig) >= 4 else None

    def measure(picks, runs, seed, difficulty="ultra", *, search=True):
        teams = [[c.set for c in roster] for _, roster in picks]
        policies = [plan_for(roster) for _, roster in picks] if plans else None
        # v6: 하이퍼볼 '균형형' 한 가지(방어를 거의 안 쓰는 CPU)에 맞춘 팀이 뽑히지 않도록 스타일을 판마다 돌린다.
        reports = parallel.compare_teams(e, fmt, teams, runs, seed, difficulty, policies=policies,
                                         cpu_styles=SELECT_STYLES if v6 else None)
        if search and objective == "ranker" and rosters:
            ranks = parallel.versus_rankers_many(e, fmt, teams, 1, seed, difficulty)
            for report, ranker_result in zip(reports, ranks):
                report["rankerRate"] = ranker_result["rate"]
            track.update(battles=len(teams) * len(rosters))
        return reports

    def assess(picks, runs, seed, difficulty="ultra", *, search=True):
        results = measure(picks, runs, seed, difficulty, search=search)
        return sorted(((group, roster, report) for (group, roster), report in zip(picks, results)),
                      key=lambda row: rank(row[2]), reverse=True)

    # 1차 선별은 빠른 표준 CPU로, 최종 검증은 고른 CPU 수준으로 한다.
    track.update("screen", total=len(race_stages), spotlight=[c.id for c in picks[0][1]],
                 notes=[" · ".join(STYLES[key].label for key in group) for group, _ in picks])
    family_cache = {}

    def family_of(roster):
        key = frozenset(c.id for c in roster)
        if key not in family_cache:
            from . import strategy

            family_cache[key] = strategy.family(strategy.analyze(e, fmt, roster))
        return family_cache[key]

    screened = _race(picks, race_stages, measure, rank, track, family=family_of if engine == "v2" else None)
    screen_runs = sum(runs for runs, _ in race_stages)
    anchor_limit = max(len(weather), roster_search.BUDGETS[search_depth][1])
    anchors = _diverse(screened, anchor_limit, split_weather, distance=2)
    from concurrent.futures import ThreadPoolExecutor

    from . import policy as pick_policy

    def policy_first(rows):
        """반사실 비교 1단계 (v5): 같은 6마리로 선출만 바꿔 본다. 멤버 교체는 이 계획을 깔고 비교한다."""
        todo = [(g, r, rep_) for g, r, rep_ in rows if roster_search.signature(r) not in plans]
        if not todo:
            return
        track.update(notes=["선출 먼저 바꿔 보기"])
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(todo)))) as threads:
            found = list(threads.map(lambda row: pick_policy.quick(e, fmt, [c.set for c in row[1]], row[2]), todo))
        for (g, r, _), plan in zip(todo, found):
            plans[roster_search.signature(r)] = plan
        track.update(battles=sum(10 * 3 * 3 for _ in todo))

    quick_policy = v5 and "noquick" not in off
    if quick_policy:
        policy_first(anchors)
    def structural(branch):
        """코어 변경: 주 전략의 시동·수혜 2~3마리를 남기고 나머지를 다시 짠다.
        전략 변경: 가장 많이 선출된 에이스를 남기고 다른 블루프린트(주·보조 전략)로 다시 짠다."""
        from . import strategy

        out = []
        roster = branch.roster
        name = lambda c: c.resolved["ko"] or c.resolved["name"]
        analysis = strategy.analyze(e, fmt, roster)
        main = analysis["tags"][0]
        core_names = set(main["setters"]) | set(main["payoffs"][:2])
        core = [c for c in roster if name(c) in core_names][:3]
        keep = list({id(c): c for c in [*fixed, *core]}.values())
        if 2 <= len(keep) < 6:
            rows = _draft(search_pools[branch.group], keep, [], branch.group, weights, limit=4, extra=extra)
            fresh = next((r for r in rows if roster_search.signature(r) != roster_search.signature(roster)), None)
            if fresh:
                out.append((fresh, "core"))
        picked = {m["id"]: m.get("pickRate", 0) for m in branch.report.get("memberStats", ())}
        ace = max(roster, key=lambda c: picked.get(c.id, 0))
        family = strategy.family(analysis)
        alternatives = [g for g in strategy.blueprint_groups(fmt) if g[0] != family and (not goals or g == goals)]
        if alternatives and not goals:
            group = alternatives[(branch.__dict__.setdefault("turns", 0)) % len(alternatives)]
            branch.turns += 1
            pool_for = available_for(group)
            rows = _draft(pool_for, list({id(c): c for c in [*fixed, ace]}.values()), [], group, weights, limit=4,
                          extra=extra)
            if rows:
                out.append((rows[0], "strategy"))
        return out

    branches, refinement = roster_search.refine(
        e, fmt, anchors, screened, search_pools, fixed_ids, valid, weights, extra, search_depth, measure, rank, track,
        structural=structural if v4 else None, policy_first=policy_first if quick_policy else None)
    histories = {(b.group, roster_search.signature(b.roster)): b.history for b in branches if b.history}
    changed = [(b.group, b.roster, b.report) for b in branches if b.history]
    finalists = _diverse([screened[0], *changed, *screened[1:]], FINAL_LIMIT, split_weather, distance=distance)
    if engine == "v2":
        # 최종 후보도 전략 가족별로 고르게: 가족마다 가장 좋은 팀부터 돌아가며 채운다.
        pool_rows = [screened[0], *changed, *screened[1:]]
        by_family = {}
        for row in pool_rows:
            by_family.setdefault(family_of(row[1]), []).append(row)
        ordered = []
        for depth_i in range(max(len(v) for v in by_family.values())):
            for rows_f in by_family.values():
                if depth_i < len(rows_f):
                    ordered.append(rows_f[depth_i])
        finalists = _diverse(ordered, FINAL_LIMIT + 2, split_weather, distance=distance)

    def team_key(group, roster):
        return group, roster_search.signature(roster)

    # 세트 최적화: 도구·특성·기술·능력 포인트를 바꿔 보고 시뮬레이션으로 확인된 변경만 받아들인다.
    tuning = {}
    if tune != "off":
        from .set_tuner import Tuner

        tuner = Tuner(e, fmt)
        keep = {entry["id"] for entry in locked}
        tune_limit = max(3, len(weather))
        tune_teams = _diverse([*changed, *finalists], tune_limit, split_weather)
        retuned = {}
        track.update("tune", total=len(tune_teams) * 3)
        for index, (group, roster, report) in enumerate(tune_teams):
            def step(phase, notes, battles, index=index, roster=roster):
                track.update(done=index * 3 + phase, spotlight=[c.id for c in roster], notes=notes, battles=battles)

            sets, changes, info = tuner.tune([c.set for c in roster], tune, locked=keep, progress=step)
            if changes:
                tuned = tuple(_candidate(e, fmt, meta, s) for s in sets)
                if valid(tuned) and _fit_count(group, tuned) >= _fit_count(group, roster):
                    retuned[team_key(group, roster)] = tuned
                else:
                    changes = []
            tuning[team_key(group, roster)] = {"changes": changes, **info}
            track.update(done=(index + 1) * 3)
        finalists = [(g, retuned.get(team_key(g, r), r), report) for g, r, report in finalists]
    track.update("final", total=1, spotlight=[c.id for c in finalists[0][1]], notes=[])
    race_reports = {team_key(g, r): rep_ for g, r, rep_ in finalists}
    if v6:
        # 최종 선택: 탐색에 쓰지 않은 시드, 마스터볼 CPU 스타일 혼합, 더 많은 판
        assessed = assess([(group, roster) for group, roster, _ in finalists], V6_SELECT_RUNS.get(depth, 64),
                          seed=9_031_777, difficulty="master", search=False)
    else:
        assessed = assess([(group, roster) for group, roster, _ in finalists], final_runs, seed=3146781,
                          difficulty=cpu, search=False)
    copy_rate = COPY_RATE.get(originality, 0.)

    def overlap(roster):
        names = {c.species for c in roster}
        return max((len(names & team) for team in extra.ranker_teams), default=0)

    def final_key(row):
        key = rank(row[2])
        return (key[0] - copy_rate * max(0, overlap(row[1]) - 3), *key[1:])

    if copy_rate:
        assessed.sort(key=final_key, reverse=True)
    track.update(done=1, battles=len(finalists) * final_runs)
    metrics = {}
    if engine == "v2":
        # 랭크 리그 검증 (명세 6.4): 탐색에 쓰지 않은 난수·상대로
        #   마스터볼 리그(검증) · 챔피언 리그(보류 상대) · 스트레스 리그(가장 약한 상대 전략 집중) · 몬스터볼 리그(기본 점검)
        team_sets = [[c.set for c in r] for _, r, _ in assessed]
        # 선출 계획 공동 최적화 (v4): 팀을 고치기 전에 상대 전략별 선봉·후발을 직접 바꿔 보고,
        # 새 상대군의 같은 판에서 확실히 나아진 선출만 계획으로 채택한다. 리그 검증은 이 계획으로 싸운다.
        from concurrent.futures import ThreadPoolExecutor

        from . import policy as pick_policy

        track.update(notes=["선출 계획 최적화"])
        # 비용 때문에 상위 후보만 (나머지는 기본 선출). v6 은 보류 효과가 없어서(진단 5.1·7장) 생략한다.
        tuned_rows = assessed[:POLICY_TEAMS] if v4 and not v6 else []
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(tuned_rows)))) as pool_threads:
            final_plans = list(pool_threads.map(
                lambda row: pick_policy.optimize(e, fmt, [c.set for c in row[1]], row[2], depth,
                                                 start=plan_for(row[1]) if v5 else None), tuned_rows))
        final_plans += [({}, [])] * (len(assessed) - len(final_plans))
        policies = [p for p, _ in final_plans]
        runs_master = max(16, final_runs // 2)
        runs_champion = LEAGUE_RUNS.get(depth, LEAGUE_RUNS["standard"])
        # 마스터볼 리그는 공격·수비·전개·피벗 스타일을 돌아가며, 카운터형은 스트레스 리그에서 따로.
        master = parallel.compare_teams(e, fmt, team_sets, runs_master, 5_512_901, "master", policies=policies,
                                        cpu_styles=["aggressive", "defensive", "setup", "pivot"])
        champion = parallel.compare_teams(e, fmt, team_sets, runs_champion, 7_331_117, "champion", policies=policies)
        sanity = parallel.compare_teams(e, fmt, team_sets, 12, 4_441_001, "poke", policies=policies)
        stress = []
        for (group, roster, report), sets, plan in zip(assessed, team_sets, policies):
            worst = report["strategies"][0]["style"] if report["strategies"] else None
            stress.append((worst, parallel.compare_teams(e, fmt, [sets], runs_champion, 6_220_013, "master",
                                                         styles={worst}, policies=[plan],
                                                         cpu_styles=["counter"])[0] if worst else None))
        track.update(battles=len(assessed) * (runs_master + runs_champion * 2 + 12))
        from . import strategy

        for (group, roster, report), m, c, p, (worst, st), (plan, proof) in zip(
                assessed, master, champion, sanity, stress, final_plans):
            leagues = {"하이퍼볼": race_reports.get(team_key(group, roster), report) if v6 else report,
                       "마스터볼": m, "챔피언": c, "몬스터볼": p}
            metrics[team_key(group, roster)] = _metrics(e, fmt, roster, report, leagues, overlap(roster), strategy,
                                                        stress=(worst, st))
            name = lambda pid: next((x.resolved["ko"] or x.resolved["name"] for x in roster if x.id == pid), pid)
            width = 2 if fmt == "Doubles" else 1
            metrics[team_key(group, roster)]["policy"] = [
                {**row, "leads": [name(pid) for pid in row["pick"][:width]],
                 "back": [name(pid) for pid in row["pick"][width:]]} for row in proof]
            metrics[team_key(group, roster)]["policyMap"] = {k: list(v) for k, v in plan.items()}
            from .simulation import STYLE_LABELS

            metrics[team_key(group, roster)]["cpuStyles"] = [
                {"style": k, "label": STYLE_LABELS.get(k, k), "runs": v["runs"], "rate": round(v["score"] / v["runs"], 3)}
                for k, v in m.get("cpuStyles", {}).items()]
        if not v4:  # v3: 평균 승률(점추정)로 판단
            for m in metrics.values():
                m["winLow"] = m["winRate"]
        shown = _pareto(assessed, metrics, team_key, max(3, len(weather)), objective, distance)
    else:
        shown = _diverse(assessed, max(3, len(weather)), split_weather, distance=distance)
    ranker_reports = {}
    if rosters:
        tested = assessed if objective == "ranker" else shown
        games = RANKER_GAMES.get(depth, 2)
        track.update("rankers", total=1, spotlight=[s["id"] for s in rosters[0][1]],
                     notes=[f"{r['season']} {r['rank']}위 {r['player']}" for r, _ in rosters[:8]])
        results = parallel.versus_rankers_many(e, fmt, [[c.set for c in roster] for _, roster, _ in tested],
                                               games, 6151, cpu)
        ranker_reports = {team_key(group, roster): r for (group, roster, _), r in zip(tested, results)}
        track.update(done=1, battles=len(tested) * len(rosters) * games)
        if objective == "ranker":
            for group, roster, report in assessed:
                report["rankerRate"] = ranker_reports[team_key(group, roster)]["rate"]
            assessed.sort(key=final_key, reverse=True)
            shown = (_pareto(assessed, metrics, team_key, max(3, len(weather)), objective, distance) if metrics
                     else _diverse(assessed, max(3, len(weather)), split_weather, distance=distance))
    track.update("report", total=1, spotlight=[c.id for c in shown[0][1]])
    candidates = []
    names_seen = set()
    for index, (group, roster, report) in enumerate(shown, 1):
        sets = [c.set for c in roster]
        analysis = e.analyze_team(sets, fmt)
        fit = []
        for key in group:
            style = STYLES[key]
            evidence = []
            for feature, minimum in style.requirements:
                names = [c.resolved["ko"] or c.resolved["name"] for c in roster if feature in c.features]
                evidence.append({"role": FEATURE_NAMES[feature], "members": names[:max(3, minimum)],
                                 "count": len(names), "minimum": minimum})
            fit.append({"name": style.label, "evidence": evidence,
                        "complete": all(row["count"] >= row["minimum"] for row in evidence)})
        title = " · ".join(STYLES[key].label for key in group)
        names = {c.id: c.resolved["ko"] or c.resolved["name"] for c in roster}
        lead = " + ".join(names[pid] for pid in report["lead"]["ids"])
        name = f"{title} · {lead}"
        if name in names_seen:
            name = f"{name} ({index}안)"
        names_seen.add(name)
        activations = report.pop("activations")
        report["strategyUse"] = [
            {"label": STYLES[key].label, "runs": activations[key]}
            for key in group if key in WEATHER_STYLES | {"tailwind", "trickroom", "psychic", "setup"}
        ]
        profile = {key: sum(key in c.features for c in roster)
                   for key in ("fast_attacker", "physical", "special", "bulky")}
        from .guide import team_guide

        guide = team_guide(e, sets, fmt) or {}
        weak = sorted((r for r in analysis["typeRows"] if r["weak"] >= 2), key=lambda r: (r["resist"] - r["weak"]))
        members = [_member(e, s, fmt) for s in sets]
        for m, c in zip(members, roster):
            m["speed"] = round(c.resolved["speed"])
            m["fixed"] = c.id in ids
            m["usageRank"] = None if _rank_of(e, fmt, c.id) >= 999 else _rank_of(e, fmt, c.id)
            m["joker"] = _rank_of(e, fmt, c.id) > JOKER_RANK
            m["features"] = [FEATURE_NAMES[f] for f in sorted(c.features) if f in FEATURE_NAMES][:4]
        candidates.append({"id": f"auto-{index}", "name": name, "format": fmt, "complete": True,
                           "members": members, "metaScore": analysis["metaScore"],
                           "warnings": analysis["warnings"][:4], "fit": fit, "fixedIds": ids,
                           "simulation": report, "profile": profile,
                           "analysis": {
                               "damageSplit": analysis["damageSplit"],
                               "weakTypes": [{"type": r["type"], "weak": r["weak"], "resist": r["resist"]}
                                             for r in weak[:4]],
                               "roles": [{"label": r["label"], "stars": r["stars"]} for r in analysis["roleCoverage"]],
                               "matchups": {k: sum(1 for m in analysis["matchups"] if m["label"] == k)
                                            for k in ("GOOD", "EVEN", "BAD")},
                               "axes": [{"label": a["label"], "play": a["play"]} for a in guide.get("axes", [])][:4],
                               "lead": guide.get("lead"),
                           }})
    for c, (group, roster, report) in zip(candidates, shown):
        key = team_key(group, roster)
        c["rankers"] = ranker_reports.get(key)
        c["tuning"] = tuning.get(key)
        c["rosterSearch"] = histories.get(key, [])
        c["jokers"] = [m["ko"] or m["name"] for m in c["members"] if m.get("joker")]
        c["fromResearch"] = roster_search.signature(roster) in researched
        if key in metrics:
            m = metrics[key]
            c["strategy"] = m.pop("analysis")
            c["metrics"] = m
            c["lossCauses"] = report.get("lossCauses", [])
            if v5:
                from . import novelty

                m["originality"] = novelty.measure(
                    e, fmt, roster, family=m["family"], policy_keys=len(m.get("policyMap") or {}),
                    champion_rate=m["leagues"]["챔피언"]["rate"])
                c["counterfactual"] = novelty.counterfactual(m.get("policy"), tuning.get(key), histories.get(key, []))
        # 가장 많이 겹치는 랭커 파티 (그대로 베낀 팀인지 보여 준다)
        names = {r.species for r in roster}
        closest = max(((len(names & team), r) for team, r in zip(extra.ranker_teams, (
            x for x in RANKERS if x["format"] == fmt))), key=lambda row: row[0], default=(0, None))
        c["rankerOverlap"] = ({"count": closest[0], "player": closest[1]["player"], "rank": closest[1]["rank"],
                               "season": closest[1]["season"]} if closest[1] else None)
    track.update(done=1)
    return {"candidates": candidates, "splitWeather": split_weather,
            "evaluation": {"screened": len(picks), "finalists": len(finalists),
                           "screenRuns": screen_runs, "finalRuns": final_runs,
                           "objective": objective, "depth": depth, "cpu": cpu, "joker": joker,
                           "mega": mega, "core": core, "tune": tune, "originality": originality,
                           "ignored": [STYLES[key].label for key in ignored],
                           "rosterSearch": refinement, "engine": label if label in ("v3", "v4", "v5", "v6") else engine, "versions": _versions(e),
                           "rankerGames": RANKER_GAMES.get(depth, 2) if ranker_reports else 0,
                           "dataWarnings": regulation_warnings(e)}}


@lru_cache(maxsize=6)
def simulated_recommendations(e, fmt):
    return build(e, fmt, [], [], [])
