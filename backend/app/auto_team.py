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


@dataclass(frozen=True)
class Extra:
    """초안 점수에 더하는 조건: 타입 코어, 랭커 동시 채용 코어, 인기 가중치."""
    core: str = ""
    pairs: tuple = ()  # ((id_a, id_b, 보너스), ...)
    popularity: float = 1.5

    def pair_bonus(self, ids):
        return sum(bonus for a, b, bonus in self.pairs if a in ids and b in ids)


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
            - pressure - 10 * max(0, megas - 1) - 20 * max(0, megas - 2) - conflict)


def _keep_best(options, goals, weights, limit=16, extra=DEFAULT_EXTRA):
    best = {}
    for group in options:
        key = frozenset(c.id for c in group)
        score = _score(group, goals, weights, extra)
        if key not in best or score > best[key][0]:
            best[key] = (score, group)
    return sorted(best.values(), key=lambda row: -row[0])[:limit]


def _draft(pool, fixed, required, goals, weights, limit, extra=DEFAULT_EXTRA):
    current = [tuple(fixed)]
    for variants in required:
        options = (group + (c,) for group in current for c in variants if _eligible(c, group))
        current = [group for _, group in _keep_best(options, goals, weights, limit, extra)]
    while current and len(current[0]) < 6:
        options = (group + (c,) for group in current for c in pool if _eligible(c, group))
        current = [group for _, group in _keep_best(options, goals, weights, limit, extra)]
    return current


def _fit_count(group, roster):
    counts = Counter(key for c in roster for key in c.features)
    return sum(min(counts[key], minimum) for style in group for key, minimum in STYLES[style].requirements)


def _rank_key(report, objective):
    worst = min(row["win"] / row["runs"] for row in report["strategies"])
    total = report["win"] / report["runs"]
    scores = (worst, total) if objective == "stability" else (total, worst)
    return (*scores, report["draw"])


def _shortlist(drafts, fixed_count):
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
                if len(output) == DRAFT_LIMIT:
                    return [(g, r) for g, _, r in output]
    return [(g, r) for g, _, r in output]


def _keep_weather_options(rows, limit, split_weather):
    if not split_weather:
        return rows[:limit]
    groups = set()
    reserved = []
    for row in rows:
        if row[0] not in groups:
            reserved.append(row)
            groups.add(row[0])
    picked = reserved + [row for row in rows if row not in reserved][:max(0, limit - len(reserved))]
    return [row for row in rows if row in picked][:limit]


JOKER_RANK = 40


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


def build(e: Engine, fmt: str, styles: list[str], include: list[str], locked: list[dict], *,
          exclude: Sequence[str] = (), objective: str = "win", depth: str = "standard", cpu: str = "ultra",
          joker: str = "allow", mega: str = "auto", core: str = "", tune: str = "off", rankers: bool = True):
    from . import parallel

    goals = tuple(dict.fromkeys(styles))
    if any(key not in STYLES or (STYLES[key].doubles_only and fmt != "Doubles") for key in goals):
        raise ValueError("현재 배틀 형식에서 사용할 수 있는 전략을 골라 주세요.")
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
    extra = Extra(core=core, pairs=ranker_pairs(e, fmt))
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
    if split_weather:
        groups = [tuple(key for key in goals if key not in WEATHER_STYLES or key == target) for target in weather]
    drafts = []
    for group in groups:
        room = "trickroom" in group
        available = (*pool, *_room_pool(e, fmt)) if room else pool
        target_weather = next((key for key in group if key in WEATHER_STYLES), None)
        conflicting = {f"{key}_set" for key in WEATHER_STYLES - {target_weather}} if target_weather else set()
        available = tuple(c for c in available if c.species not in excluded and not c.features & conflicting)
        wanted = [
            [*rows, *(row for c in rows if (row := _slow_variant(e, fmt, meta, c)) is not None)]
            if room else rows for rows in required
        ]
        if mega == "one":
            available = tuple(c for c in available if not c.resolved["mega"])
        rows = _draft(available, fixed, wanted, group, weights, limit=16 if goals else 9, extra=extra)
        if not rows:
            continue
        best_fit = max(_fit_count(group, roster) for roster in rows)
        drafts.append((group, [roster for roster in rows if _fit_count(group, roster) == best_fit]))
    picks = _shortlist(drafts, len(ids))
    if not picks:
        raise ValueError("이 조건으로 6마리를 구성하기 어렵습니다. 고정 조건을 줄여 보세요.")
    if not goals:
        if not ids and not excluded:
            mapped = {"balanced": "balance", "speed": "tailwind", "trickroom": "trickroom",
                      "cycle": "pivot", "setup": "setup"}
            baselines = [
                ((mapped[party["id"]],), tuple(_candidate(e, fmt, meta, m["set"]) for m in party["members"]))
                for party in recommended(e, fmt) if party["id"] in mapped
            ]
            picks = [*picks[:DRAFT_LIMIT - len(baselines)], *baselines]
        # General recommendations should not repeat the exact same six sets under different names.
        distinct = {}
        for group, roster in picks:
            key = tuple(sorted((c.id, c.set["item"], c.set["ability"], c.set["mega"], c.set["nature"],
                                tuple(c.set["moves"]), tuple(sorted(c.set["points"].items()))) for c in roster))
            distinct.setdefault(key, (group, roster))
        picks = list(distinct.values())

    screen_runs, final_runs = DEPTHS.get(depth, DEPTHS["standard"])

    def assess(picks, runs, seed, difficulty="ultra"):
        results = parallel.compare_teams(e, fmt, [[c.set for c in roster] for _, roster in picks], runs, seed,
                                         difficulty)
        rows = [(group, roster, report) for (group, roster), report in zip(picks, results)]
        return sorted(rows, key=lambda row: _rank_key(row[2], objective), reverse=True)

    # 1차 선별은 빠른 표준 CPU로, 최종 검증은 고른 CPU 수준으로 한다.
    screened = assess(picks, screen_runs, seed=821239)
    finalists = _keep_weather_options(screened, FINAL_LIMIT, split_weather)
    assessed = assess([(group, roster) for group, roster, _ in finalists], final_runs, seed=3146781, difficulty=cpu)
    shown = _keep_weather_options(assessed, max(3, len(weather)), split_weather)

    # 세트 최적화: 도구·특성·기술·능력 포인트를 바꿔 보고 시뮬레이션으로 확인된 변경만 받아들인다.
    tuning = {}
    if tune != "off":
        from .set_tuner import Tuner

        tuner = Tuner(e, fmt)
        keep = {entry["id"] for entry in locked}
        retuned = []
        for group, roster, report in shown:
            sets, changes, info = tuner.tune([c.set for c in roster], tune, locked=keep)
            if changes:
                roster = tuple(_candidate(e, fmt, meta, s) for s in sets)
            tuning[frozenset(c.id for c in roster)] = {"changes": changes, **info}
            retuned.append((group, roster))
        shown = assess(retuned, final_runs, seed=3146781, difficulty=cpu)
    ranker_reports = {}
    if rankers:
        from .recommend import ranker_rosters

        if ranker_rosters(e, fmt):
            games = RANKER_GAMES.get(depth, 2)
            results = parallel.versus_rankers_many(e, fmt, [[c.set for c in roster] for _, roster, _ in shown],
                                                   games, 6151, cpu)
            ranker_reports = {frozenset(c.id for c in roster): r for (_, roster, _), r in zip(shown, results)}
    if objective == "ranker" and ranker_reports:
        def combined(row):
            report = row[2]
            meta_rate = (report["win"] + .5 * report["draw"]) / report["runs"]
            return .5 * meta_rate + .5 * ranker_reports[frozenset(c.id for c in row[1])]["rate"]
        shown.sort(key=combined, reverse=True)
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
    for c, (_, roster, _) in zip(candidates, shown):
        key = frozenset(m.id for m in roster)
        c["rankers"] = ranker_reports.get(key)
        c["tuning"] = tuning.get(key)
        c["jokers"] = [m["ko"] or m["name"] for m in c["members"] if m.get("joker")]
    return {"candidates": candidates, "splitWeather": split_weather,
            "evaluation": {"screened": len(picks), "finalists": len(finalists),
                           "screenRuns": screen_runs, "finalRuns": final_runs,
                           "objective": objective, "depth": depth, "cpu": cpu, "joker": joker,
                           "mega": mega, "core": core, "tune": tune,
                           "rankerGames": RANKER_GAMES.get(depth, 2) if ranker_reports else 0}}


@lru_cache(maxsize=6)
def simulated_recommendations(e, fmt):
    return build(e, fmt, [], [], [])
