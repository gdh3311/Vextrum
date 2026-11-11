"""Doubles team preview and opening plans for the player's selected sets."""
from itertools import combinations

from .enemy import mini, pool
from .engine import ROLE_MOVES, SPREAD_TARGETS, Engine, weight

FORMAT = "Doubles"
WEATHERS = {"Drought": "sun", "Drizzle": "rain", "Sand Stream": "sand", "Snow Warning": "snow"}
WEATHER_SPEED = {"Swift Swim": "rain", "Chlorophyll": "sun", "Sand Rush": "sand", "Slush Rush": "snow"}
WEATHER_NAMES = {"sun": "쾌청", "rain": "비", "sand": "모래바람", "snow": "설경"}
TERRAINS = {"Psychic Surge": "psychic", "Grassy Surge": "grassy", "Electric Surge": "electric", "Misty Surge": "misty"}
TERRAIN_NAMES = {"psychic": "사이코필드", "grassy": "그래스필드", "electric": "일렉트릭필드", "misty": "미스트필드"}
GUARD = {"Protect", "Detect", "Spiky Shield", "King's Shield", "Baneful Bunker", "Silk Trap", "Burning Bulwark"}
BLOCK_PRIORITY = {"Armor Tail", "Dazzling", "Queenly Majesty"}
BLOCK_FLINCH = {"Inner Focus", "Shield Dust"}


def name(mon):
    return mon["ko"] or mon["name"]


def _grounded(mon):
    return "Flying" not in mon["types"] and mon["ability"] != "Levitate" and mon["item"] != "Air Balloon"


class DoublesPreview:
    def __init__(self, e: Engine, mine, foes, strategies, leads, confirmed, team_sets):
        self.e = e
        self.mine = {m["id"]: m for m in mine}
        self.foes = {m["id"]: m for m in foes}
        self.strategies = strategies
        self.enemy_moves = {f["id"]: pool(e, f, FORMAT)[0] for f in foes}
        self.matchups = {(m["id"], f["id"]): e.matchup(m, f, FORMAT)["score"]
                         for m in self.mine.values() for f in foes}
        self.base_abilities = {s["id"]: s.get("ability") for s in team_sets}
        self.opening_scores = {}
        self.scenarios = [self._scenario(l) for l in leads[:3]]
        if len(set(confirmed)) == 2 and set(confirmed) <= self.foes.keys():
            previous = next((s for s in self.scenarios if set(s["ids"]) == set(confirmed)), None)
            actual = self._scenario({"ids": list(confirmed), "members": [mini(self.foes[i]) for i in confirmed],
                                     "level": "HIGH", "prob": 1.0, "why": ["배틀에서 확인한 선봉"]})
            self.scenarios = [{**actual, "confirmed": True},
                              *(s for s in self.scenarios if s is not previous)]

    def _scenario(self, lead):
        ids = lead["ids"]
        remaining = [f for f in self.foes if f not in ids]
        backs = list(combinations(remaining, min(2, len(remaining))))

        def score(back):
            group = tuple(ids) + back
            # 상대가 이 네 마리로 내 팀의 여러 포켓몬을 얼마나 넓게 위협하는지 본다.
            coverage = sum(max(100 - self.matchups[m, f] for f in group) for m in self.mine) / max(len(self.mine), 1)
            synergy = 0.0
            for f in back:
                mates = self.e.P[f]["usage"].get(FORMAT, {}).get("teammates", [])
                synergy += sum((10 - mates.index(g)) * .24 for g in group if g in mates[:10])
                synergy += 7 * weight(self.e.rank(f, FORMAT) or 200)
            for s in self.strategies:
                setters = {m["id"] for m in s.get("setters", [])}
                members = {m["id"] for m in s["members"]}
                if setters.intersection(group) and (members - setters).intersection(group):
                    synergy += 3
            megas = sum(bool(self.foes[f]["mega"]) for f in group)
            return coverage + synergy - 4 * max(0, megas - 1)

        back = max(backs, key=score)
        return {**lead, "back": [mini(self.foes[f]) for f in back]}

    def _pair_score(self, lead, foes):
        key = tuple(lead), tuple(foes)
        if key in self.opening_scores:
            return self.opening_scores[key]
        scores = [self.matchups[m, f] for m in lead for f in foes]
        best = sum(max(self.matchups[m, f] for m in lead) for f in foes) / len(foes)
        floor = min(max(self.matchups[m, f] for f in foes) for m in lead)
        own = self._opening_forms([self.mine[m] for m in lead], self.base_abilities)
        enemy = self._opening_forms([self.foes[f] for f in foes], {})
        weather, terrain = self._field(own + enemy)
        speed = max(self._speed(m, weather) for m in own) > max(self._speed(f, weather) for f in enemy)
        help_moves = set.union(*(set(m["moves"]) for m in own))
        control = any(self._fake_out(m, f, enemy, terrain) for m in own for f in enemy)

        def pressure(side, other, estimated):
            damage = 0.0
            for i, mon in enumerate(side):
                moves = self.enemy_moves[mon["id"]] if estimated else None
                hit = max(self._best(mon, other, side[1 - i], weather, terrain, moves),
                          key=lambda h: h[0], default=None)
                if hit:
                    damage += min(hit[0], 135)
            return damage / len(side)

        damage_edge = pressure(own, enemy, False) - pressure(enemy, own, True)
        result = (.55 * sum(scores) / len(scores) + .30 * best + .15 * floor
                  + .12 * damage_edge + 2 * speed + 2 * control
                  + 2 * bool(help_moves & {"Tailwind", "Trick Room", "Wide Guard"}))
        self.opening_scores[key] = result
        return result

    def _opening_forms(self, side, base_abilities):
        result, mega_used = [], False
        for mon in side:
            if mon["mega"] and mega_used:
                ability = base_abilities.get(mon["id"]) or self.e.default_set(mon["id"], FORMAT)["ability"]
                mon = self.e.resolve({**mon, "mega": None, "ability": ability}, FORMAT)
            mega_used |= bool(mon["mega"])
            result.append(mon)
        return result

    def _bring_score(self, chosen, scenario):
        foes = scenario["ids"] + [m["id"] for m in scenario["back"]]
        scores = [sorted((self.matchups[m, f] for m in chosen), reverse=True) for f in foes]
        return sum(.72 * row[0] + .28 * row[1] for row in scores) / len(scores)

    def recommend(self, locked):
        if len(self.mine) < 2 or not self.scenarios:
            return None
        fixed = (len(locked) == min(4, len(self.mine)) and len(set(locked)) == len(locked)
                 and set(locked) <= self.mine.keys())
        primary = self.scenarios[0]
        focus = [primary] if primary.get("confirmed") else self.scenarios
        total = sum(s["prob"] for s in focus) or 1
        options = []
        for lead in combinations(self.mine, 2):
            rest = [m for m in self.mine if m not in lead]
            lead_scores = [self._pair_score(lead, s["ids"]) for s in focus]
            for back in combinations(rest, min(2, len(rest))):
                chosen = lead + back
                by_scenario = [.64 * sc + .36 * self._bring_score(chosen, s) for sc, s in zip(lead_scores, focus)]
                average = sum(sc * s["prob"] for sc, s in zip(by_scenario, focus)) / total
                floor = min(by_scenario)
                megas = sum(bool(self.mine[i]["mega"]) for i in chosen)
                penalty = 4 * max(0, megas - 1) + 4 * all(self.mine[i]["mega"] for i in lead)
                options.append({"lead": lead, "back": back, "score": .72 * average + .28 * floor - penalty,
                                "floor": floor - penalty, "opening": by_scenario[0] - penalty})
        options.sort(key=lambda o: (-o["score"], -o["floor"], o["lead"], o["back"]))
        selected = next((o for o in options if set(o["lead"]) == set(locked[:2])
                         and set(o["back"]) == set(locked[2:])), None) if fixed else None
        best = selected or options[0]
        others = [o for o in options if o["lead"] != best["lead"]]
        alternative = max(others, key=lambda o: o["opening"], default=None)
        alternatives = [alternative] if alternative else []
        for option in others:
            if len(alternatives) >= 3:
                break
            if all(option["lead"] != alt["lead"] for alt in alternatives):
                alternatives.append(option)

        def group(ids):
            return [self.mine[i] for i in ids]

        lead, back = group(best["lead"]), group(best["back"])
        plans = [self._plan(lead, back, s) for s in self.scenarios[:3]]
        return {
            "lead": [self.e.describe(m, FORMAT) for m in lead],
            "back": [self.e.describe(m, FORMAT) for m in back],
            "score": round(best["score"], 1), "floor": round(best["floor"], 1),
            "locked": selected is not None,
            "plans": plans,
            "alternatives": [
                {"lead": [mini(m) for m in group(o["lead"])], "back": [mini(m) for m in group(o["back"])],
                 "score": round(o["score"], 1), "floor": round(o["floor"], 1),
                 "label": "첫 후보 맞춤" if i == 0 and not primary.get("confirmed") else "대안"}
                for i, o in enumerate(alternatives)
            ],
        }

    @staticmethod
    def _field(leads):
        # 빠른 포켓몬의 등장 특성이 먼저 발동하므로 느린 쪽의 날씨·필드가 남는다.
        ordered = sorted(leads, key=lambda m: m["speed"])
        weather = next((WEATHERS[m["ability"]] for m in ordered if m["ability"] in WEATHERS), "")
        terrain = next((TERRAINS[m["ability"]] for m in ordered if m["ability"] in TERRAINS), "")
        return weather, terrain

    @staticmethod
    def _speed(mon, weather):
        return int(mon["speed"] * (2 if WEATHER_SPEED.get(mon["ability"]) == weather else 1))

    @staticmethod
    def _priority_blocked(target, target_side, terrain):
        return (terrain == "psychic" and _grounded(target)
                or any(f["ability"] in BLOCK_PRIORITY for f in target_side))

    def _fake_out(self, mon, target, foes, terrain):
        return ("Fake Out" in mon["moves"] and not self._priority_blocked(target, foes, terrain)
                and ("Ghost" not in target["types"] or mon["ability"] == "Scrappy")
                and target["ability"] not in BLOCK_FLINCH and target["item"] != "Covert Cloak")

    def _hit(self, mon, move, target, weather, terrain):
        meta = self.e.M.get(move)
        if meta is None:
            return None
        spread = meta["target"] in SPREAD_TARGETS or (
            move == "Expanding Force" and terrain == "psychic" and _grounded(mon))
        hit = self.e.damage(mon, move, target, FORMAT, spread=spread, weather=weather,
                            psychic_terrain=terrain == "psychic" and _grounded(mon), recharge_discount=False)
        if hit is None or not hit["pct"]:
            return None
        if move in {"Solar Beam", "Solar Blade", "Electro Shot"} and not (
            mon["item"] == "Power Herb" or weather == ("rain" if move == "Electro Shot" else "sun")
        ):
            return None
        if terrain == "grassy" and _grounded(target) and move in {"Earthquake", "Bulldoze", "Magnitude"}:
            hit["pct"] = round(hit["pct"] / 2, 1)
        if weather == "rain" and move in {"Hurricane", "Thunder"}:
            hit["acc"] = 100
        return hit

    def _best(self, mon, targets, ally, weather, terrain, moves=None):
        moves = mon["moves"] if moves is None else sorted(moves)
        hits = []
        for move in moves:
            if move in {"Fake Out", "Sucker Punch", "Upper Hand"}:
                continue
            others = []
            for target in targets:
                hit = self._hit(mon, move, target, weather, terrain)
                if hit and not (hit["priority"] > 0 and self._priority_blocked(target, targets, terrain)):
                    others.append((hit, target))
            if not others:
                continue
            kind = self.e.M[move]["target"]
            spread = kind in SPREAD_TARGETS or (move == "Expanding Force" and terrain == "psychic" and _grounded(mon))
            friendly = self._hit(mon, move, ally, weather, terrain) if ally and kind == "allAdjacent" else None
            if friendly and friendly["pct"] >= 25:
                continue
            for hit, target in others:
                extra = sum(min(100, h["pct"]) for h, t in others if t != target) if spread else 0
                value = (min(100, hit["pct"]) + .65 * extra) * hit["acc"] / 100
                if friendly:
                    value -= friendly["pct"]
                hits.append((value, hit, target, spread, friendly))
        return hits

    def _move(self, mon, move, target=None, **extra):
        return {"mon": mini(mon), "move": move, "moveKo": self.e.M.get(move, {}).get("ko") or move,
                "target": mini(target) if target else None, **extra}

    def _plan(self, lead, back, scenario):
        double_mega = all(m["mega"] for m in lead)
        lead = self._opening_forms(lead, self.base_abilities)
        foes = self._opening_forms([self.foes[i] for i in scenario["ids"]], {})
        weather, terrain = self._field(lead + foes)
        present = {f["id"] for f in foes}
        active = [s for s in self.strategies
                  if present.intersection(m["id"] for m in s.get("setters", s["members"]))]
        setters = {f["id"] for f in foes if self.enemy_moves[f["id"]] & {"Tailwind", "Trick Room"}}
        stop = [f for f in foes if f["id"] in setters]
        focus = max(stop or foes, key=lambda f: sum(100 - self.matchups[m["id"], f["id"]] for m in lead))
        enemy_back = [self.foes[m["id"]] for m in scenario["back"]]
        threat_order = sorted(foes + enemy_back, key=lambda f: -sum(
            100 - self.matchups[m["id"], f["id"]] for m in lead + back))
        risk_map, risks = {}, []
        for mon in lead:
            incoming = []
            for f in foes:
                for candidate in self._best(f, lead, None, weather, terrain, self.enemy_moves[f["id"]]):
                    _, move, target, spread, _ = candidate
                    if target is mon:
                        incoming.append((move, f, spread))
            worst = max(incoming, key=lambda x: x[0]["pct"], default=None)
            risk_map[mon["id"]] = worst
            if worst and worst[0]["pct"] >= 55:
                move, foe, _ = worst
                risks.append({"from": mini(foe), "move": move["move"], "to": mini(mon), "pct": move["pct"]})

        switch, actions, denied = None, [], None
        attacks = []
        for mon in lead:
            ally = next(m for m in lead if m is not mon)
            risk = risk_map[mon["id"]]
            speed = self._speed(mon, weather)
            possible = self._best(mon, foes, ally, weather, terrain)
            threat = bool(risk and risk[0]["pct"] >= 90
                          and (self._speed(risk[1], weather) >= speed or risk[0]["priority"] > 0))
            redirect = next((f for f in foes if f is not focus and self.enemy_moves[f["id"]] & ROLE_MOVES["redirect"]), None)
            best = max(possible, key=lambda h: h[0] + (11 if h[2] is focus else 0), default=None)
            safe_ko = best and best[1]["pct"] >= 110 and speed > self._speed(best[2], weather)
            koed = safe_ko and risk and best[2] is risk[1]
            moves = set(mon["moves"])

            if denied is None and stop and self._fake_out(mon, focus, foes, terrain) and not redirect and not safe_ko:
                action = self._move(mon, "Fake Out", focus, kind="support", reason="속이다로 시동을 한 턴 늦추기")
                denied = focus
            elif (denied is None and "Taunt" in moves and stop and not redirect and not threat
                  and not (mon["ability"] == "Prankster" and (
                      "Dark" in focus["types"] or self._priority_blocked(focus, foes, terrain)))
                  and focus["ability"] not in {"Aroma Veil", "Oblivious", "Good as Gold", "Magic Bounce"}
                  and focus["item"] != "Mental Herb"
                  and ("Trick Room" in self.enemy_moves[focus["id"]] or speed > self._speed(focus, weather))):
                action = self._move(mon, "Taunt", focus, kind="support", reason="도발로 시동 기술 제한")
                denied = focus
            elif ("Wide Guard" in moves and risk and risk[2] and risk[0]["pct"] >= 60
                  and not safe_ko and not any(a["move"] == "Wide Guard" for a in actions)):
                action = self._move(mon, "Wide Guard", kind="support", reason="상대 전체기에서 아군 둘을 보호")
            elif (threat and not koed and (not denied or risk[1] is not denied) and (guards := sorted(moves & GUARD))):
                action = self._move(mon, guards[0], kind="support", reason=f"{name(risk[1])}의 큰 피해를 피하면서 상대 행동 확인")
            elif (not threat and "Tailwind" in moves and not any(a["move"] == "Tailwind" for a in actions)
                  and not any("Trick Room" in self.enemy_moves[f["id"]] for f in foes)
                  and max(self._speed(m, weather) for m in lead) < max(self._speed(f, weather) for f in foes)
                  and not safe_ko):
                action = self._move(mon, "Tailwind", kind="support", reason="순풍으로 아군 선공권 확보")
            elif best:
                action = self._attack(mon, best, weather)
                attacks.append((mon, possible, action))
            else:
                action = None
            if action:
                actions.append(action)
            if threat and not koed and (not denied or risk[1] is not denied) and not switch and (
                action is None or action["kind"] == "attack"
            ):
                alternatives = []
                for m in back:
                    taken = []
                    for f in foes:
                        hits = self._best(f, [m], None, weather, terrain, self.enemy_moves[f["id"]])
                        taken.append(max((h[1]["pct"] for h in hits), default=0))
                    alternatives.append((max(taken), sum(taken), m))
                if alternatives:
                    taken, combined, candidate = min(alternatives, key=lambda row: (row[0], row[1]))
                    if taken < min(58, risk[0]["pct"] * .65) and combined < 95:
                        switch = {"out": mini(mon), "in": mini(candidate), "reason": "상대 양쪽의 공격을 고려해 후발로 받아내기",
                                  "move": risk[0]["move"], "takenPct": taken}
                        actions = [a for a in actions if a["mon"]["id"] != mon["id"]]
                        attacks = [a for a in attacks if a[0] is not mon]

        if len(attacks) == 2 and all(a["pct"] < 95 for _, _, a in attacks):
            pair = [max((h for h in possible if h[2] is focus), key=lambda h: h[0], default=None)
                    for _, possible, _ in attacks]
            if all(pair) and sum(h[1]["pct"] for h in pair) >= 112 and all(h[1]["acc"] >= 85 for h in pair):
                actions = [self._attack(mon, h, weather) for (mon, _, _), h in zip(attacks, pair)]

        end = threat_order[0]
        closer = max(lead + back, key=lambda m: self.matchups[m["id"], end["id"]] + 5 * (m in back))
        checks = max(self._best(closer, [end], None, "", ""), key=lambda h: h[0], default=None)
        finish = (f"{name(closer)}의 {self.e.M[checks[1]['move']].get('ko') or checks[1]['move']}를 "
                  f"{name(end)} 대응용으로 남겨 두세요." if checks else
                  f"{name(end)}의 공격을 받아낼 포켓몬의 체력을 남겨 두세요.")
        redirectors = [f for f in foes if self.enemy_moves[f["id"]] & ROLE_MOVES["redirect"]]
        cautions = []
        if redirectors:
            cautions.append(f"{name(redirectors[0])}의 유도에 단일기가 끌릴 수 있습니다.")
        fake_out = [f for f in foes if "Fake Out" in self.enemy_moves[f["id"]]
                    and any(self._fake_out({**f, "moves": ["Fake Out"]}, m, lead, terrain) for m in lead)]
        if fake_out:
            cautions.append(f"{name(fake_out[0])}의 속이다 가능성을 열어 두고 첫 턴 방어를 고려하세요.")
        if terrain == "psychic":
            cautions.append("사이코필드가 깔리면 접지한 상대에게 선공기가 막힙니다.")
        if any("Trick Room" in self.enemy_moves[f["id"]] for f in foes):
            cautions.append("트릭룸이 깔리면 느린 쪽부터 행동합니다. 방어와 교체로 지속 턴을 흘리세요.")
        elif any("Tailwind" in self.enemy_moves[f["id"]] for f in foes):
            cautions.append("상대 순풍이 깔리면 아래 행동 순서가 바뀔 수 있습니다.")
        if double_mega:
            cautions.append(f"선봉 둘 모두 메가 후보입니다. 첫 턴 계산에는 {name(lead[0])}의 메가진화를 적용했습니다.")
        if (actions and any(a["kind"] == "attack" and a["pct"] >= 80 for a in actions)
                and any(self.enemy_moves[f["id"]] & GUARD for f in foes)):
            cautions.append("큰 피해를 줄 수 있는 턴이라도 상대 방어를 확인한 뒤 집중 공격을 결정하세요.")
        self.e.with_move_ko(risks)
        if switch:
            self.e.with_move_ko([switch])
        pace = sorted([{"mon": mini(m), "side": side, "speed": self._speed(m, weather)}
                       for side, mons in (("mine", lead), ("foe", foes)) for m in mons], key=lambda row: -row["speed"])
        return {
            "enemyLead": scenario["members"], "enemyBack": scenario["back"], "confirmed": bool(scenario.get("confirmed")),
            "level": scenario["level"], "prob": scenario["prob"], "score": round(self._pair_score(
                [m["id"] for m in lead], scenario["ids"]), 1),
            "focus": mini(focus), "goal": "상대 시동 지연" if focus["id"] in setters else "압박이 큰 상대부터 견제",
            "strategies": [s["label"] for s in active[:3]],
            "field": [value for value in (WEATHER_NAMES.get(weather), TERRAIN_NAMES.get(terrain)) if value],
            "pace": pace, "actions": actions, "switch": switch, "risks": sorted(risks, key=lambda r: -r["pct"]),
            "cautions": cautions, "finish": finish,
        }

    def _attack(self, mon, candidate, weather):
        _, hit, target, spread, friendly = candidate
        return self._move(mon, hit["move"], target, kind="attack", pct=hit["pct"], accuracy=hit["acc"],
                          faster=self._speed(mon, weather) > self._speed(target, weather), spread=spread,
                          allyPct=friendly["pct"] if friendly else None)
