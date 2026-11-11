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
SCREEN_RUNS = 21
FINAL_RUNS = 56
DRAFT_LIMIT = 12
FINAL_LIMIT = 5


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


def _score(chosen, goals, weights):
    counts = Counter(key for c in chosen for key in c.features)
    features = counts.keys()
    coverage = sum(w * max(c.matchups[i] for c in chosen) for i, w in enumerate(weights))
    pressure = 0
    for i in range(len(TYPES)):
        weak = sum(c.weak[i] for c in chosen)
        resist = sum(c.resist[i] for c in chosen)
        pressure += 1.4 * max(0, weak - 1 - resist) + 2.5 * (weak >= 3 and not resist)
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
    return (coverage * .55 + goal_points + variety * 1.25 + teammates * .4
            + 3.5 * sum(c.popularity for c in chosen) - pressure - 4 * max(0, megas - 1) - conflict)


def _keep_best(options, goals, weights, limit=16):
    best = {}
    for group in options:
        key = frozenset(c.id for c in group)
        score = _score(group, goals, weights)
        if key not in best or score > best[key][0]:
            best[key] = (score, group)
    return sorted(best.values(), key=lambda row: -row[0])[:limit]


def _draft(pool, fixed, required, goals, weights, limit):
    current = [tuple(fixed)]
    for variants in required:
        options = (group + (c,) for group in current for c in variants if _eligible(c, group))
        current = [group for _, group in _keep_best(options, goals, weights, limit)]
    while current and len(current[0]) < 6:
        options = (group + (c,) for group in current for c in pool if _eligible(c, group))
        current = [group for _, group in _keep_best(options, goals, weights, limit)]
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


def build(e: Engine, fmt: str, styles: list[str], include: list[str], locked: list[dict], *,
          exclude: Sequence[str] = (), objective: str = "win"):
    from . import battle_lab

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
        rows = _draft(available, fixed, wanted, group, weights, limit=16 if goals else 9)
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

    def assess(picks, runs, seed):
        results = battle_lab.compare_teams(e, fmt, [[c.set for c in roster] for _, roster in picks], runs, seed)
        rows = [(group, roster, report) for (group, roster), report in zip(picks, results)]
        return sorted(rows, key=lambda row: _rank_key(row[2], objective), reverse=True)

    screened = assess(picks, SCREEN_RUNS, seed=821239)
    finalists = _keep_weather_options(screened, FINAL_LIMIT, split_weather)
    assessed = assess([(group, roster) for group, roster, _ in finalists], FINAL_RUNS, seed=3146781)
    shown = _keep_weather_options(assessed, max(3, len(weather)), split_weather)
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
        candidates.append({"id": f"auto-{index}", "name": name, "format": fmt, "complete": True,
                           "members": [_member(e, s, fmt) for s in sets], "metaScore": analysis["metaScore"],
                           "warnings": analysis["warnings"][:3], "fit": fit, "fixedIds": ids,
                           "simulation": report, "profile": profile})
    return {"candidates": candidates, "splitWeather": split_weather,
            "evaluation": {"screened": len(picks), "finalists": len(finalists),
                           "screenRuns": SCREEN_RUNS, "finalRuns": FINAL_RUNS,
                           "objective": objective}}


@lru_cache(maxsize=6)
def simulated_recommendations(e, fmt):
    return build(e, fmt, [], [], [])
