"""Export a local, source-labelled Vextrum Doubles knowledge base."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from subprocess import check_output, SubprocessError
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import collector, mechanics, regulation, simulation  # noqa: E402
from app.engine import ROLE_LABELS, SPREAD_TARGETS, Engine  # noqa: E402

ROSTER = "https://web-view.app.pokemonchampions.jp/battle/pages/events/rs178713870219xeaaio/ko/pokemon.html"
SHOWDOWN = "https://play.pokemonshowdown.com/data/"
MOD = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/mods/champions/moves.ts"
STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")
FORM_ORDER = {
    26: ("raichu", "raichualola"), 38: ("ninetales", "ninetalesalola"),
    53: ("persian", "persianalola"), 59: ("arcanine", "arcaninehisui"),
    80: ("slowbro", "slowbrogalar"),
    128: ("tauros", "taurospaldeacombat", "taurospaldeablaze", "taurospaldeaaqua"),
    157: ("typhlosion", "typhlosionhisui"), 199: ("slowking", "slowkinggalar"),
    479: ("rotom", "rotomheat", "rotomwash", "rotomfrost", "rotomfan", "rotommow"),
    503: ("samurott", "samurotthisui"), 571: ("zoroark", "zoroarkhisui"),
    618: ("stunfisk", "stunfiskgalar"), 678: ("meowstic", "meowsticf"),
    706: ("goodra", "goodrahisui"), 711: ("gourgeist", "gourgeistsmall", "gourgeistlarge", "gourgeistsuper"),
    713: ("avalugg", "avalugghisui"), 724: ("decidueye", "decidueyehisui"),
    745: ("lycanroc", "lycanrocmidnight", "lycanrocdusk"), 849: ("toxtricity", "toxtricitylowkey"),
    876: ("indeedee", "indeedeef"), 902: ("basculegion", "basculegionf"),
    925: ("mausholdfour",), 931: ("squawkabilly", "squawkabillyyellow"),
}
REQUIRED_ABILITIES = {
    "Intimidate", "Prankster", "Inner Focus", "Mold Breaker", "Levitate", "Lightning Rod", "Storm Drain",
    "Regenerator", "Unaware", "Stamina", "Speed Boost", "Swift Swim", "Chlorophyll", "Sand Rush",
    "Slush Rush", "Magic Bounce", "Contrary",
}
M_C_MEGAS = {"Mega Absol Z", "Mega Salamence", "Mega Garchomp Z", "Mega Lucario Z", "Mega Golisopod",
             "Mega Baxcalibur"}


def fetch(url):
    with urlopen(url, timeout=20) as response:
        return response.read()


def cached_reference(filename):
    path = collector.CACHE / filename
    return path.read_bytes() if path.is_file() else fetch(SHOWDOWN + filename)


def list_official(raw, indexed):
    match = re.search(r"const pokemons\s*=\s*(\[\[.*?\]\]);", raw.decode())
    if not match:
        raise ValueError("공식 참가 목록 구조가 바뀌었습니다.")
    groups = defaultdict(list)
    for code, _, name in json.loads(match.group(1)):
        groups[int(code.split("-")[0])].append((code, name))
    official = {}
    for number, rows in groups.items():
        ids = FORM_ORDER.get(number, indexed.get(number, []))
        if len(ids) != len(rows):
            raise ValueError(f"공식 폼 매핑 확인 필요: {number}, {rows}, {ids}")
        official.update({pid: {"code": code, "ko": name, "nationalDex": number, "status": "확인됨"}
                         for pid, (code, name) in zip(ids, rows, strict=True)})
    return official


def moves_table(engine, base, patch):
    overrides = dict(re.findall(r"^\t([a-z0-9]+): \{\n(.*?)^\t\},", patch.decode(), re.M | re.S))
    if "protect" not in overrides or "wish" not in overrides:
        raise ValueError("Showdown 챔피언스 기술 표의 PP 구조를 확인하세요.")
    names = {m for p in engine.P.values() for m in p.get("learnset", ())}
    rows = {}
    for name, meta in engine.M.items():
        key = engine.move_ids[name]
        source = base.get(key, {})
        block = overrides.get(key, "")
        flags = source.get("flags", {})
        patched_flags = re.search(r"^\t\tflags: \{([^}]+)\}", block, re.M)
        if patched_flags:
            flags = dict.fromkeys(re.findall(r"(\w+): 1", patched_flags[1]), 1)
        reference = {"power": source.get("basePower"), "accuracy": source.get("accuracy"),
                     "type": source.get("type"), "target": source.get("target"), "priority": source.get("priority")}
        for field, key_in_mod in (("power", "basePower"), ("accuracy", "accuracy"), ("type", "type"),
                                  ("target", "target"), ("priority", "priority")):
            override = re.search(rf'^\t\t{key_in_mod}: (-?\d+|true|false|"[A-Za-z]+"),', block, re.M)
            if override:
                reference[field] = json.loads(override[1])
        diffs = {k: {"app": meta.get(k), "showdownChampions": value, "comparison":
                     "고정/가변 피해 내부 표기" if k == "power" and (meta.get("fixed") or meta.get("variable"))
                     else "수치 또는 타깃 불일치"} for k, value in reference.items()
                 if value is not None and (100 if value is True else value) != meta.get(k)}
        pp = re.search(r"^\t\tpp: (\d+),", block, re.M)
        value = int(pp[1]) if pp else source.get("pp")
        no_boost = "noPPBoosts: true" in block or source.get("noPPBoosts")
        max_pp = (min(value, 20) if no_boost else (min(value, 20) // 5 + 1) * 4) if value else None
        if name in {"Wish", "Strength Sap"}:
            max_pp = 8
        rows[key] = {
            "en": name, "ko": meta.get("ko") or name,
            **{k: meta.get(k) for k in ("type", "category", "power", "accuracy", "priority", "target")},
            "spread": "필드에 있는 모든 인접 포켓몬" if meta.get("target") == "allAdjacent" else
                      "상대 인접 포켓몬" if meta.get("target") in SPREAD_TARGETS else
                      "접지한 사용자가 사이코필드에서 쓰면 상대 전체" if name == "Expanding Force" else None,
            "canAffectAllyByTarget": None if not source else reference.get("target") in {
                "allAdjacent", "adjacentAlly", "adjacentAllyOrSelf", "allySide", "allies", "any", "normal"},
            "protectFlagShowdown": bool(flags.get("protect")) if source else None,
            "protectExceptions": "방어 제거" if name == "Feint" else
                                 "접촉 관통 특성·와이드가드·퍼스트가드 별도 평가" if flags.get("protect") else None,
            "showdownEffectId": source.get("volatileStatus") or source.get("sideCondition") or source.get("status"),
            "appEffects": {k: v for k, v in {
                "secondaryStatus": mechanics.SECONDARY_STATUS.get(name), "flinchPct": mechanics.FLINCH.get(name),
                "targetStages": mechanics.TARGET_STAGES.get(name), "selfStages": mechanics.SELF_STAGES.get(name),
                "recoilFraction": mechanics.RECOIL.get(name), "boost": simulation.BOOSTS.get(name) or
                mechanics.EXTRA_BOOSTS.get(name), "pivot": name in simulation.PIVOT or None,
                "reactive": name in simulation.REACTIVE or None,
            }.items() if v is not None},
            "championsMaxPp": max_pp, "ppStatus": "공식 확인" if name in {"Wish", "Strength Sap"} else
                      "Showdown 챔피언스 참조" if max_pp is not None else "미확인", "appTracksPp": False,
            "inAppLearnset": name in names, "appEligibility": "처리 대상" if simulation.move_supported(engine, name)
                          else "미구현", "appChampionsOverrides": mechanics.CHAMPIONS_MOVES.get(name),
            "showdownChampionsDifferences": diffs,
            "sourceIds": ["VX", "PS", "PATCH"] if name in {"Wish", "Strength Sap"} else ["VX", "PS"],
        }
    return rows


def combat_readout(engine, pokemon, own, legal, strengths):
    foes = [engine.default_resolved(f["id"], "Doubles") for f in engine.ranked("Doubles")[:20]
            if f["id"] in legal and f["id"] != pokemon["id"]]
    matchups = sorted(((engine.matchup(own, foe, "Doubles")["score"], foe["id"]) for foe in foes), reverse=True)
    explicit = set(own["moves"])
    category = set(strengths) & {"physical", "special", "mixed"}
    type_set = set(own["types"])
    attrs = set(pokemon["abilities"]) | {own["ability"]}
    tools = {
        "fakeOut": [*sorted(type_set & {"Ghost"}), *sorted(attrs & {"Inner Focus", "Armor Tail", "Shield Dust"})],
        "intimidate": sorted(attrs & {"Inner Focus", "Defiant", "Competitive", "Contrary", "Clear Body",
                                       "Hyper Cutter", "White Smoke", "Guard Dog", "Mirror Armor", "Scrappy",
                                       "Oblivious", "Own Tempo", "Full Metal Body"}),
        "burn": [*sorted(type_set & {"Fire"}), *sorted(attrs & {"Guts", "Water Veil", "Water Bubble",
                                                               "Thermal Exchange", "Purifying Salt"})],
    }
    has_attack = any(engine.M[move]["category"] != "Status" for move in own["moves"])
    support_roles = {"support", "fakeout", "speedcontrol", "redirect", "screens", "wideguard", "pivot", "disrupt"}
    return {
        "favorableStatic": [{"id": pid, "score": score} for score, pid in matchups if score >= 62][:3],
        "unfavorableStatic": [{"id": pid, "score": score} for score, pid in reversed(matchups) if score < 50][:3],
        "potentialResistanceOrPunish": tools,
        "physicalBurnImpact": bool(category & {"physical", "mixed"}) and "Guts" != own["ability"],
        "partnerIdsM7Snapshot": [pid for pid in pokemon["usage"].get("Doubles", {}).get("teammates", ())
                                 if pid in legal][:3],
        "bulkyAttacker": has_attack and "bulky" in strengths,
        "supportRoleTags": sorted(support_roles.intersection(strengths)),
        "antiMetaStaticCandidate": sum(score >= 62 for score, _ in matchups) >= 3,
        "hasTrickRoom": "Trick Room" in explicit, "hasTailwind": "Tailwind" in explicit,
        "effectiveSpeedNeutralField": own["speed"], "effectiveSpeedUnderTailwind": own["speed"] * 2,
        "speedWithZeroInvestmentLoweringNature": int(pokemon["stats"]["spe"] * .9),
        "roleCompression": [r for r in strengths if r not in {"physical", "special", "mixed", "fast", "bulky", "mega"}],
        "assessmentStatus": "추정", "tier": None,
    }


def main():
    output = ROOT / "backend" / "data" / "competitive-kb"
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot = collector.DATASET.read_bytes()
    engine = Engine(json.loads(snapshot))
    dex_bytes, moves_bytes = [cached_reference(name) for name in ("pokedex.json", "moves.json")]
    roster_bytes, mod_bytes = fetch(ROSTER), fetch(MOD)
    dex = json.loads(dex_bytes)
    indexed = defaultdict(list)
    for pid in engine.P:
        indexed[dex[pid]["num"]].append(pid)
    official = list_official(roster_bytes, indexed)
    moves = moves_table(engine, json.loads(moves_bytes), mod_bytes)
    m8_evidence = ROOT / "docs" / "competitive-knowledge-base" / "m8-public-evidence.json"
    m8 = json.loads(m8_evidence.read_text(encoding="utf-8"))
    species, megas = {}, []
    mega_dex = {collector.tid(f"Mega {row['baseSpecies']} {row['forme'][4:]}"): row
                for row in dex.values() if row.get("forme", "").startswith("Mega") and row.get("baseSpecies")}
    season = next((s for s in engine.d["seasons"] if s != "Current"), None)
    for pid in sorted(engine.P, key=lambda key: (dex[key]["num"], key)):
        p, reference = engine.P[pid], dex[pid]
        set_ = engine.default_set(pid, "Doubles")
        resolved = engine.resolve(set_, "Doubles")
        roles = engine.roles(resolved, "Doubles")
        usage = p["usage"].get("Doubles", {})
        base_form = engine.resolve({**set_, "mega": None, "item": None}, "Doubles")
        base_roles = set(engine.roles(base_form, "Doubles"))
        for form in p.get("megas", ()):
            variant = dex["meowsticmmega"] if form["name"] == "Mega Meowstic" else mega_dex.get(collector.tid(form["name"]), {})
            delta_stats = {key: form["stats"][key] - p["stats"][key] for key in STAT_KEYS}
            final = engine.resolve({**set_, "item": form["stone"], "mega": form["name"]}, "Doubles")
            final_roles = engine.roles(final, "Doubles")
            megas.append({"speciesId": pid, "en": form["name"], "ko": form["ko"], "stone": form["stone"],
                          "stoneKo": engine.d["items"].get(form["stone"], {}).get("ko"),
                          "typesBefore": p["types"], "typesAfter": form["types"], "abilitiesBefore": p["abilities"],
                          "abilitiesAfter": form["abilities"], "baseStatsBeforeShowdown": reference["baseStats"],
                          "baseStatsAfterShowdown": variant.get("baseStats"), "appLevel50NeutralZeroSpAfter": form["stats"],
                          "statGain": delta_stats, "defaultSetRolesWithStone": final_roles,
                          "statisticRoleChangesVsBaseWithoutItem": {"gained": sorted(set(final_roles) - base_roles),
                                                                    "lost": sorted(base_roles - set(final_roles))},
                          "setAssessment": combat_readout(engine, p, final, official, final_roles),
                          "requiresMegaSlot": True, "slotOpportunityCost": "다른 메가진화 및 같은 자리에 쓸 지닌 도구",
                          "conditionalMoveCandidates": final["moves"], "regulation": "M-C",
                          "eligibility": "공식 M-C 신규 허용" if form["name"] in M_C_MEGAS else "앱 데이터 수록",
                          "sourceIds": ["VX", "PS", "OFF-MC"] if form["name"] in M_C_MEGAS else ["VX", "PS"]})
        aliases = [name for name in p.get("learnset", ()) if name in engine.move_ids]
        species[pid] = {"en": p["name"], "ko": official.get(pid, {}).get("ko", p["ko"]), "appKo": p["ko"],
                        "nationalDex": reference["num"], "officialRoster": official.get(pid),
                        "inVextrumCatalog": True, "types": p["types"],
                        "baseStatsShowdown": reference["baseStats"], "appLevel50NeutralZeroSp": p["stats"],
                        "statDifferencesFromShowdownBaseline": {k: p["stats"][k] - reference["baseStats"][k]
                            - (75 if k == "hp" else 20) for k in STAT_KEYS
                            if p["stats"][k] != reference["baseStats"][k] + (75 if k == "hp" else 20)},
                        "abilitiesInAppData": p["abilities"], "normalAbilitiesShowdown": [a for k, a in
                            reference["abilities"].items() if k in {"0", "1"}],
                        "hiddenAbilityShowdown": reference["abilities"].get("H"),
                        "learnsetIdsFromApp": [engine.move_ids[m] for m in aliases],
                        "moveAcquisitionMethod": None, "megaNames": [form["name"] for form in p.get("megas", ())],
                        "publishedDoublesRankBySeason": {key: p["ranks"][key].get("Doubles")
                            for key in engine.d["seasons"] if key != "Current" and key in p["ranks"]},
                        "m8Stats": m8["rankedPokemon"].get(pid), "snapshotSeasonLabel": season,
                        "snapshotDoublesSetApproximation": set_ if usage else None,
                        "snapshotSetComponentRatesPct": {k: usage.get(k, [])[:3] for k in ("moves", "items", "abilities", "natures")} if usage else None,
                        "snapshotDoublesSetRoles": roles if usage else [],
                        "snapshotSetSimulatorIssues": simulation.rules_report(engine, "Doubles", [set_])["issues"] if usage else [],
                        "competitiveAssessment": combat_readout(engine, p, resolved, official, roles) if usage else None,
                        "sourceIds": ["VX", "PS", "CBD", "OFF-ROSTER"] + (["M8-PUBLIC"] if pid in m8["rankedPokemon"] else [])}

    ability_names = set(engine.d["abilities"]) | {a for row in species.values() for a in row["abilitiesInAppData"]} | REQUIRED_ABILITIES
    special_names = {"Storm Drain": "마중물"}
    official_names = {"Aura Guard": ("파동의방호", "https://pokemonkorea.co.kr/pokedex/view/573"),
                      "Eelevate": ("천정부지", "https://pokemonkorea.co.kr/pokedex/view/770"),
                      "Fire Mane": ("불꽃의갈기", "https://pokemonkorea.co.kr/pokedex/view/850")}
    abilities = {name: {"ko": engine.d["abilities"].get(name, {}).get("ko") or special_names.get(name),
                        "inVextrumAbilityDictionary": name in engine.d["abilities"],
                        "appCoverage": "미구현" if name in simulation.UNIMPLEMENTED_ABILITIES else
                          "미확인" if name in simulation.RULE_UNVERIFIED_ABILITIES else
                          "효과 코드 확인·상호작용 일부" if name in REQUIRED_ABILITIES else "개별 검증 전",
                        "holders": [pid for pid, p in species.items() if name in p["abilitiesInAppData"]],
                        "megaHolders": [m["en"] for m in megas if name in m["abilitiesAfter"]]}
                 for name in sorted(ability_names)}
    for name, (ko, url) in official_names.items():
        abilities[name].update(ko=ko, nameSource=url, appCoverage="전용 효과 미구현")
    items = {name: {"ko": row.get("ko"), "appCoverage": "미구현" if name in simulation.UNIMPLEMENTED_ITEMS else
                       "개별 검증 전", "megaForms": [m["en"] for m in megas if m["stone"] == name]}
             for name, row in engine.d["items"].items()}
    tables = {"pokemon": species, "moves": moves, "abilities": abilities, "items": items,
              "megas": megas, "official-roster": official}
    app_version = re.search(r"^version:\s*([^+\s]+)", (ROOT / "app/pubspec.yaml").read_text(), re.M)[1]
    try:
        revision = check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, SubprocessError):
        revision = None
    manifest = {"schemaVersion": 1, "exportedAtUtc": stamp, "appVersion": app_version, "appGitHead": revision,
                "officialRankedSeason": "M8",
                "regulation": "M-C", "snapshotSeasonLabel": season, "snapshotAt": engine.d["generatedAt"],
                "versions": regulation.versions(engine.d), "roleLabels": ROLE_LABELS,
                "counts": {**{key: len(table) for key, table in tables.items()},
                           "officialSpecies": len({row["nationalDex"] for row in official.values()}),
                           "formsWithoutExactOfficialMatch": len(species.keys() - official.keys()),
                           "m8PublicRankRows": len(m8["rankedPokemon"]),
                           "showdownChampionsMoveDifferences": sum(bool(row["showdownChampionsDifferences"]) for row in moves.values()),
                           "showdownChampionsValueMismatches": sum(any(
                               diff["comparison"] == "수치 또는 타깃 불일치" for diff in row["showdownChampionsDifferences"].values()
                           ) for row in moves.values())},
                "sources": {
                    "OFF-ROSTER": {"url": ROSTER, "sha256": sha256(roster_bytes).hexdigest()},
                    "OFF-MC": {"url": "https://champions-news.pokemon-home.com/ko/page/816.html"},
                    "PATCH": {"url": "https://champions-news.pokemon-home.com/en/page/817.html"},
                    "CBD": {"url": engine.d["source"], "attribution": engine.d["attribution"]},
                    "M8-PUBLIC": {"path": m8_evidence.relative_to(ROOT).as_posix(), "url": m8["source"],
                                  "checkedAt": m8["checkedAt"], "asPublished": m8["snapshotDateAsPublished"]},
                    "VX": {"path": str(collector.DATASET.relative_to(ROOT)), "sha256": sha256(snapshot).hexdigest()},
                    "PS": {"pokedex": SHOWDOWN + "pokedex.json", "moves": SHOWDOWN + "moves.json", "championsMoveOverrides": MOD,
                           "pokedexSha256": sha256(dex_bytes).hexdigest(), "movesSha256": sha256(moves_bytes).hexdigest(),
                           "championsMoveOverridesSha256": sha256(mod_bytes).hexdigest()},
                },
                "scope": "로컬 분석용. 앱 코드와 대전 통계 스냅샷은 별도 출처이며 확인 상태는 필드별로 적용.",
                "limitations": ["승률·실전 선출률·종 단위 채용률·기술별 습득 경로는 미확인. M8 통계는 외부 공개 선별 표본.",
                                "도감에 있는 모든 기술·특성·도구 효과가 시뮬에서 검증되었다는 뜻은 아님."]}
    assert all(row["nationalDex"] == species[pid]["nationalDex"] for pid, row in official.items())
    assert all(set(row["learnsetIdsFromApp"]) <= moves.keys() for row in species.values())
    assert set(m8["rankedPokemon"]) <= official.keys() and official.keys() <= species.keys()
    assert all(row.get("movePct", {}).keys() <= moves.keys() for row in m8["rankedPokemon"].values())
    assert all(set(team["speciesIds"]) <= official.keys() for team in m8["publicLadderTeams"])
    assert moves["protect"]["championsMaxPp"] == moves["wish"]["championsMaxPp"] == 8
    for key, table in {**tables, "m8-public-evidence": m8, "manifest": manifest}.items():
        (output / f"{key}.json").write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print("Move implementation counts:", Counter(row["appEligibility"] for row in moves.values()))
    print("Mega records with a Showdown base-stat match:", sum(bool(m["baseStatsAfterShowdown"]) for m in megas))


if __name__ == "__main__":
    main()
