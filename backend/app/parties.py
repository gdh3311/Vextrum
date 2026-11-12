"""Published ladder reports and locally generated party recommendations."""
from functools import lru_cache

from .engine import Engine, weight
from .typechart import STAT_KEYS, TYPES, type_multiplier


def _set(pid, item, ability, nature, points, moves, mega=None):
    return {"id": pid, "item": item, "ability": ability, "nature": nature,
            "points": dict(zip(STAT_KEYS, points)), "moves": moves.split("|"), "mega": mega}


_REPORTS = [
    {
        "id": "m7-s-4", "season": "M7", "format": "Singles", "rank": 4, "player": "Virtus",
        "name": "하마돈 · 메가보만다",
        "source": "https://yinyangpoke.hatenablog.com/entry/2026/11/07/171953",
        "note": "하마돈으로 상대를 깎거나 교체를 유도한 뒤 보만다와 타부자고로 마무리합니다. 상대에 따라 메가 드닐레이브나 메가 갑주무사로 선출을 바꿉니다.",
        "sets": [
            _set("hippowdon", "Sitrus Berry", "Sand Stream", "Impish", [32,0,2,0,32,0], "Earthquake|Stealth Rock|Yawn|Whirlwind"),
            _set("salamence", "Salamencite", "Intimidate", "Adamant", [1,32,1,0,0,32], "Thrash|Earthquake|Dragon Dance|Substitute", "Mega Salamence"),
            _set("gholdengo", "Choice Scarf", "Good as Gold", "Timid", [1,0,1,32,0,32], "Flash Cannon|Shadow Ball|Thunderbolt|Trick"),
            _set("primarina", "Leftovers", "Liquid Voice", "Modest", [32,0,6,4,0,24], "Moonblast|Psychic Noise|Aqua Jet|Encore"),
            _set("baxcalibur", "Baxcalibrite", "Thermal Exchange", "Adamant", [17,32,0,0,0,17], "Icicle Crash|Ice Shard|Earthquake|Swords Dance", "Mega Baxcalibur"),
            _set("golisopod", "Golisopite", "Emergency Exit", "Adamant", [31,32,0,0,3,0], "First Impression|Iron Head|Close Combat|Payback", "Mega Golisopod"),
        ],
    },
    {
        "id": "m6-s-11", "season": "M6", "format": "Singles", "rank": 11, "rating": 2528, "player": "モーガン",
        "name": "메가메타그로스 · 메가한카리아스Z",
        "source": "https://note.com/pokemons2/n/n1ec6963deb17",
        "note": "기본 선출은 하마돈·타부자고·한카리아스입니다. 정면 승부가 유리할 때는 누리레느·메타그로스·따라큐를 냅니다.",
        "sets": [
            _set("metagross", "Metagrossite", "Clear Body", "Adamant", [10,25,0,8,0,23], "Psychic Fangs|Bullet Punch|Earthquake|Grass Knot", "Mega Metagross"),
            _set("garchomp", "Garchompite Z", "Rough Skin", "Timid", [0,0,2,32,0,32], "Draco Meteor|Flamethrower|Poison Jab|Stealth Rock", "Mega Garchomp Z"),
            _set("primarina", "Sitrus Berry", "Torrent", "Modest", [32,0,10,14,0,10], "Moonblast|Surf|Aqua Jet|Encore"),
            _set("mimikyu", "Life Orb", "Disguise", "Adamant", [27,32,0,0,2,5], "Play Rough|Drain Punch|Shadow Sneak|Swords Dance"),
            _set("gholdengo", "Leftovers", "Good as Gold", "Calm", [32,0,0,0,24,10], "Shadow Ball|Make It Rain|Nasty Plot|Recover"),
            _set("hippowdon", "Rocky Helmet", "Sand Stream", "Impish", [32,0,32,0,2,0], "Earthquake|Ice Fang|Yawn|Slack Off"),
        ],
    },
    {
        "id": "m7-d-765", "season": "M7", "format": "Doubles", "rank": 765, "rating": 2057.590, "player": "pukuff",
        "name": "카디나르마 트릭룸 · 비",
        "source": "https://pukuff.hatenablog.com/entry/2026/11/04/175934",
        "note": "카디나르마와 메가곤율거니로 트릭룸을 전개하거나, 패리퍼와 메가대짱이로 비를 활용합니다.",
        "sets": [
            _set("armarouge", "Life Orb", "Weak Armor", "Modest", [9,0,0,32,12,13], "Expanding Force|Armor Cannon|Trick Room|Protect"),
            _set("indeedeef", "Sitrus Berry", "Psychic Surge", "Relaxed", [32,0,32,0,2,0], "Psychic|Follow Me|Helping Hand|Trick Room"),
            _set("scrafty", "Scraftinite", "Intimidate", "Brave", [29,32,0,0,5,0], "Close Combat|Knock Off|Fake Out|Detect", "Mega Scrafty"),
            _set("pelipper", "Choice Scarf", "Drizzle", "Timid", [14,0,3,18,0,31], "Hurricane|Weather Ball|Ice Beam|U-turn"),
            _set("archaludon", "Leftovers", "Stamina", "Modest", [12,0,0,25,21,8], "Flash Cannon|Aura Sphere|Electro Shot|Protect"),
            _set("swampert", "Swampertite", "Torrent", "Adamant", [8,32,0,0,0,26], "Wave Crash|Earthquake|Ice Punch|Protect", "Mega Swampert"),
        ],
    },
]

# 랭커 파티 (종 구성만 공개). 출처: 리버티노트 시즌 최종 순위 정리. 세트는 각 포켓몬의 가장 흔한 세트로 채운다.
M7_TOP = """
1 2418 ナーク charizard garchomp rillaboom milotic incineroar sneasler
3 2370 まりるり charizard floetteeternal whimsicott garchomp kingambit basculegion
4 2354 Online archaludon armarouge charizard pelipper swampert indeedeef
5 2353 じゅんや charizard aerodactyl kingambit garchomp sylveon farigiraf
6 2349 Me dragonite kingambit basculegion mudsdale weavile sylveon
7 2347 キム staraptor indeedeef farigiraf kingambit basculegion raichu
9 2338 MOTOTE gholdengo floetteeternal incineroar charizard sneasler rillaboom
10 2337 ヤシの木 gengar dragonite garchomp sneasler basculegion kingambit
13 2329 アーニャ incineroar garchomp sneasler floetteeternal rillaboom aegislash
15 2319 justing_tang floetteeternal delphox sinistcha sneasler kingambit incineroar
18 2309 いしろ gengar dragonite rillaboom sneasler basculegion kingambit
19 2309 わらびもち salamence sylveon basculegion kingambit sneasler raichu
20 2308 ショコラ gengar garchomp vivillonfancy rillaboom incineroar primarina
21 2308 MeLuCa salamence froslass rillaboom basculegion kingambit sneasler
22 2308 Yuyuvgc rillaboom milotic ceruledge incineroar ninetalesalola floetteeternal
24 0 Lorenzo dragonite rillaboom incineroar gengar hippowdon kingambit
25 2304 ちゃっぴー charizard venusaur basculegion indeedeef kingambit sylveon
26 2304 ゆー floetteeternal talonflame garchomp rillaboom kingambit basculegion
27 2303 HRK pelipper basculegionf sneasler archaludon raichu golisopod
28 2303 ゆヌ floetteeternal garchomp dragonite sneasler kingambit basculegion
30 2293 アル scovillain raichu ninetalesalola kingambit basculegion sneasler
34 2287 じーん sneasler dragonite basculegion kingambit rillaboom incineroar
35 2285 りょうたろう floetteeternal mausholdfour basculegion talonflame garchomp gardevoir
36 2285 ユウキ gengar incineroar rillaboom kommoo blastoise indeedeef
37 2282 ゆうき raichu sneasler rillaboom incineroar primarina garchomp
39 2275 Mitsu charizard garchomp farigiraf floetteeternal basculegion whimsicott
"""
M7_SOURCE = "https://liberty-note.com/2026/11/04/champions-seasonm7-top100/"
RANKERS = []
for line in M7_TOP.strip().splitlines():
    rank, rating, player, *ids = line.split()
    RANKERS.append({"id": f"m7-d-{rank}", "season": "M7", "format": "Doubles", "rank": int(rank),
                    "rating": int(rating) or None, "player": player.replace("_", " "),
                    "name": f"{player.replace('_', ' ')}의 파티", "source": M7_SOURCE, "ids": ids})
for row in [
    ("M6", "2026/10/07", 1, 2500, "なま", "garchomp sneasler kingambit delphox dragonite basculegion"),
    ("M6", "2026/10/07", 2, 2490, "Paul", "charizard garchomp venusaur sylveon toxapex incineroar"),
    ("M6", "2026/10/07", 3, 2478, "ヤシの木🌴", "gengar dragonite garchomp sneasler basculegion kingambit"),
]:
    season, source, rank, rating, player, ids = row
    RANKERS.append({"id": f"{season.lower()}-d-{rank}", "season": season, "format": "Doubles", "rank": rank,
                    "rating": rating, "player": player, "name": f"{player}의 파티",
                    "source": f"https://liberty-note.com/{source}/champions-season{season.lower()}-top100/",
                    "ids": ids.split()})
_detailed = {r["id"] for r in _REPORTS}
for ranker in RANKERS:
    if ranker["id"] not in _detailed:
        _REPORTS.append({**{k: v for k, v in ranker.items() if k != "ids"},
                         "sets": [{"id": pid} for pid in ranker["ids"]]})


def _member(e: Engine, s: dict, fmt: str) -> dict:
    p = e.P[s["id"]]
    mega = e.find_mega(p, name=s.get("mega"))
    form = mega or p
    return {"id": p["id"], "name": form["name"], "ko": form["ko"], "sprite": form["sprite"],
            "types": form["types"], "set": s,
            "itemKo": e.d["items"].get(s.get("item"), {}).get("ko"),
            "abilityKo": e.d["abilities"].get(s.get("ability"), {}).get("ko"),
            "megaAbility": (mega["abilities"] or [None])[0] if mega else None,
            "natureKo": e.d["natures"].get(s.get("nature")),
            "moveInfo": [{"name": m, "ko": e.M.get(m, {}).get("ko"), "type": e.M.get(m, {}).get("type")}
                         for m in s.get("moves", [])],
            "roles": e.describe(e.resolve(s, fmt), fmt)["roles"] if "moves" in s else []}


def published(e: Engine, fmt: str) -> list[dict]:
    return [{**{k: v for k, v in report.items() if k != "sets"},
             "members": [_member(e, s, fmt) for s in report["sets"] if s["id"] in e.P],
             "complete": all(s["id"] in e.P and "moves" in s for s in report["sets"])}
            for report in sorted(_REPORTS, key=lambda r: (-int(r["season"][1:]), r["rank"]))
            if report["format"] == fmt]


@lru_cache(maxsize=8)
def recommended(e: Engine, fmt: str) -> list[dict]:
    """Fill six slots by balancing matchup coverage, complementary roles and teammate frequency."""
    ranked = e.ranked(fmt)[:80]
    meta = e.meta(fmt, 20)
    if len(ranked) < 6 or not meta:
        return []
    defaults = {p["id"]: e.default_resolved(p["id"], fmt) for p in ranked}
    roles = {pid: set(e.roles(r, fmt)) for pid, r in defaults.items()}
    by_role = lambda role: next((p["id"] for p in ranked if role in roles[p["id"]]), None)
    styles = [
        ("balanced", "균형형", ranked[0]["id"], {"physical", "special", "pivot", "priority"}),
        ("speed", "순풍형", by_role("tailwind"), {"tailwind", "special", "physical", "fakeout"}),
        ("trickroom", "트릭룸형", by_role("trickroom"), {"trickroom", "physical", "special", "redirect"}),
    ] if fmt == "Doubles" else [
        ("balanced", "균형형", ranked[0]["id"], {"physical", "special", "priority", "pivot"}),
        ("cycle", "교체 운영형", by_role("hazard"), {"hazard", "pivot", "wall", "special"}),
        ("setup", "랭크업형", by_role("setup"), {"setup", "physical", "special", "priority"}),
    ]
    matchups = {pid: [e.matchup(r, foe, fmt)["score"] for foe in meta] for pid, r in defaults.items()}
    weights = [weight(e.rank(r["id"], fmt)) for r in meta]
    resistance = {pid: [type_multiplier(t, r["types"], r["ability"]) for t in TYPES]
                  for pid, r in defaults.items()}
    candidates = {p["id"]: p for p in ranked}
    results, seen = [], set()
    for key, label, anchor, wanted in styles:
        if anchor is None:
            continue
        chosen = [anchor]
        while len(chosen) < 6:
            filled = set.union(*(roles[pid] for pid in chosen))
            mates = {pid for member in chosen for pid in candidates[member]["usage"][fmt]["teammates"][:8]}
            best = [max(matchups[pid][i] for pid in chosen) for i in range(len(meta))]

            def score(p):
                pid = p["id"]
                coverage = sum(w * max(0, s - b) for w, s, b in zip(weights, matchups[pid], best)) / sum(weights)
                overlap = sum(
                    1 for i, m in enumerate(resistance[pid])
                    if m >= 2 and sum(resistance[c][i] >= 2 for c in chosen) >= 2
                )
                roles_added = len((wanted - filled) & roles[pid])
                tempo = (max(0, 105 - defaults[pid]["speed"]) / 30) if key == "trickroom" else 0
                return (coverage * 1.7 + roles_added * 1.8 + (pid in mates) * 1.0
                        + weight(p["usage"][fmt]["rank"]) * 6 + tempo - overlap * 2.3)

            species = {candidates[pid]["name"].split("-")[0] for pid in chosen}
            eligible = [p for p in ranked if p["name"].split("-")[0] not in species]
            if not eligible:
                break
            chosen.append(max(eligible, key=score)["id"])
        signature = frozenset(chosen)
        if len(chosen) != 6 or signature in seen:
            continue
        seen.add(signature)
        used, sets = set(), []
        for pid in chosen:
            s = e.default_set(pid, fmt)
            if s["item"] in used:
                item = next((r["name"] for r in e.P[pid]["usage"][fmt]["items"] if r["name"] not in used), None)
                mega = e.find_mega(e.P[pid], stone=item)
                s.update(item=item, mega=mega["name"] if mega else None)
            if s["item"]:
                used.add(s["item"])
            sets.append(s)
        analysis = e.analyze_team(sets, fmt)
        results.append({"id": key, "name": label, "format": fmt, "complete": True,
                        "members": [_member(e, s, fmt) for s in sets], "metaScore": analysis["metaScore"],
                        "warnings": analysis["warnings"][:3],
                        "note": (f"중심 포켓몬은 {e.P[anchor]['ko'] or e.P[anchor]['name']}입니다. "
                                 "메타 상위 20마리 대응, 역할 분담과 동료 채용을 평가했습니다.")})
    return results
