"""메타 분석 엔진: 세트 해석, 간이 데미지 계산, 상성 점수, 역할 분류, 팀 분석, 조커 탐색.

데이터에 종(種) 단위 사용률(%)이 없고 순위만 있으므로, 메타 가중치는 순위에서 유도한다
(weight = 1/sqrt(rank)). 능력치는 레벨 50 실수치 + 능력 포인트(1포인트 = +1) × 성격 보정으로 계산한다.
"""
from __future__ import annotations

import math

from .typechart import NATURES, STAT_KEYS, TYPES, type_multiplier

TYPE_ITEMS = {
    "Soft Sand": "Ground", "Charcoal": "Fire", "Mystic Water": "Water", "Miracle Seed": "Grass",
    "Magnet": "Electric", "Never-Melt Ice": "Ice", "Black Belt": "Fighting", "Poison Barb": "Poison",
    "Sharp Beak": "Flying", "Twisted Spoon": "Psychic", "Silver Powder": "Bug", "Hard Stone": "Rock",
    "Spell Tag": "Ghost", "Dragon Fang": "Dragon", "Black Glasses": "Dark", "Metal Coat": "Steel",
    "Silk Scarf": "Normal", "Fairy Feather": "Fairy",
}
RESIST_BERRIES = {
    "Occa Berry": "Fire", "Passho Berry": "Water", "Wacan Berry": "Electric", "Rindo Berry": "Grass",
    "Yache Berry": "Ice", "Chople Berry": "Fighting", "Kebia Berry": "Poison", "Shuca Berry": "Ground",
    "Coba Berry": "Flying", "Payapa Berry": "Psychic", "Tanga Berry": "Bug", "Charti Berry": "Rock",
    "Kasib Berry": "Ghost", "Haban Berry": "Dragon", "Colbur Berry": "Dark", "Babiri Berry": "Steel",
    "Roseli Berry": "Fairy", "Chilan Berry": "Normal",
}
ATE = {"Pixilate": "Fairy", "Aerilate": "Flying", "Refrigerate": "Ice", "Galvanize": "Electric"}
NO_INTIMIDATE = {"Clear Body", "White Smoke", "Hyper Cutter", "Inner Focus", "Own Tempo", "Oblivious",
                 "Scrappy", "Full Metal Body", "Guard Dog", "Defiant", "Competitive", "Contrary", "Mirror Armor"}
MOLD = {"Mold Breaker", "Teravolt", "Turboblaze"}
DEF_TARGET_MOVES = {"Psyshock", "Psystrike", "Secret Sword"}
SPREAD_TARGETS = {"allAdjacent", "allAdjacentFoes"}

ROLE_MOVES = {
    "fakeout": {"Fake Out"},
    "tailwind": {"Tailwind"},
    "trickroom": {"Trick Room"},
    "speedcontrol": {"Tailwind", "Trick Room", "Icy Wind", "Electroweb", "Thunder Wave", "Scary Face",
                     "Bulldoze", "Glare", "Nuzzle", "String Shot", "Sticky Web"},
    "redirect": {"Follow Me", "Rage Powder", "Spotlight"},
    "wideguard": {"Wide Guard"},
    "pivot": {"U-turn", "Volt Switch", "Flip Turn", "Parting Shot", "Baton Pass", "Teleport", "Chilly Reception"},
    "setup": {"Swords Dance", "Nasty Plot", "Dragon Dance", "Calm Mind", "Quiver Dance", "Bulk Up", "Shell Smash",
              "Belly Drum", "Iron Defense", "Coil", "Work Up", "Howl", "Tail Glow", "Shift Gear", "Curse", "Growth",
              "Agility", "Rock Polish", "Autotomize", "Cosmic Power", "Amnesia", "Victory Dance"},
    "disrupt": {"Taunt", "Encore", "Spore", "Sleep Powder", "Will-O-Wisp", "Thunder Wave", "Yawn", "Hypnosis",
                "Glare", "Stun Spore", "Disable", "Imprison", "Toxic", "Haze", "Clear Smog", "Roar", "Whirlwind"},
    "screens": {"Reflect", "Light Screen", "Aurora Veil"},
    "support": {"Helping Hand", "Heal Pulse", "Life Dew", "Pollen Puff", "Coaching", "Decorate", "Ally Switch",
                "Quick Guard", "Safeguard"},
    "hazard": {"Stealth Rock", "Spikes", "Toxic Spikes", "Sticky Web"},
    "recovery": {"Recover", "Roost", "Slack Off", "Soft-Boiled", "Synthesis", "Moonlight", "Morning Sun",
                 "Strength Sap", "Shore Up", "Wish", "Rest", "Milk Drink"},
    "antitr": {"Taunt", "Imprison", "Trick Room", "Roar", "Whirlwind"},
}
ROLE_ABILITIES = {
    "intimidate": {"Intimidate"},
    "weather": {"Drought", "Drizzle", "Sand Stream", "Snow Warning"},
    "terrain": {"Grassy Surge", "Electric Surge", "Psychic Surge", "Misty Surge"},
    "prankster": {"Prankster"},
}
ROLE_LABELS = {
    "physical": "물리 어태커", "special": "특수 어태커", "mixed": "양도 어태커", "fast": "고속", "bulky": "내구형",
    "fakeout": "속이다", "tailwind": "순풍", "trickroom": "트릭룸", "speedcontrol": "스피드 컨트롤",
    "redirect": "이목 끌기(유도)", "wideguard": "와이드가드", "pivot": "교체 기술", "setup": "랭크업",
    "disrupt": "방해/상태이상", "screens": "벽 깔기", "support": "아군 지원", "hazard": "설치기", "recovery": "회복기",
    "antitr": "트릭룸 대책", "intimidate": "위협", "weather": "날씨 변경", "terrain": "필드 변경",
    "prankster": "짓궂은마음", "priority": "선공기", "choice": "구애 아이템", "mega": "메가진화",
}
UTILITY_WEIGHTS = {
    "Doubles": {"intimidate": 30, "fakeout": 25, "speedcontrol": 30, "redirect": 30, "wideguard": 20, "priority": 20,
                "weather": 20, "terrain": 20, "disrupt": 15, "pivot": 10, "screens": 15, "support": 12,
                "prankster": 15},
    "Singles": {"intimidate": 20, "priority": 25, "pivot": 25, "hazard": 25, "disrupt": 20, "recovery": 20,
                "setup": 20, "weather": 15, "terrain": 15, "screens": 15, "speedcontrol": 10, "prankster": 15},
}
TEAM_ROLE_ROWS = {
    "Doubles": [("physical", "물리 화력"), ("special", "특수 화력"), ("speedcontrol", "스피드 컨트롤"),
                ("priority", "선공기"), ("fakeout", "속이다"), ("intimidate", "위협"), ("redirect", "유도"),
                ("field", "날씨/필드"), ("wideguard", "와이드가드"), ("antitr", "트릭룸 대책"),
                ("disrupt", "방해/상태이상")],
    "Singles": [("physical", "물리 화력"), ("special", "특수 화력"), ("priority", "선공기"), ("pivot", "교체 기술"),
                ("hazard", "설치기"), ("setup", "랭크업"), ("recovery", "회복기"), ("disrupt", "방해/상태이상"),
                ("field", "날씨/필드"), ("intimidate", "위협")],
}


def weight(rank: int) -> float:
    return 1 / math.sqrt(max(rank, 1))


class Engine:
    def __init__(self, dataset: dict):
        self.d = dataset
        self.P: dict = dataset["pokemon"]
        self.M: dict = dataset["moves"]
        self._default: dict = {}
        self._matchups: dict = {}
        self._pct: dict = {}

    # ---------- 기본 조회 ----------
    def ranked(self, fmt: str) -> list[dict]:
        ps = [p for p in self.P.values() if fmt in p["usage"]]
        return sorted(ps, key=lambda p: p["usage"][fmt]["rank"])

    def rank(self, pid: str, fmt: str) -> int | None:
        u = self.P[pid]["usage"].get(fmt)
        return u["rank"] if u else None

    def find_mega(self, p: dict, name: str | None = None, stone: str | None = None) -> dict | None:
        for m in p["megas"]:
            if (name and m["name"] == name) or (stone and m["stone"] == stone):
                return m
        return None

    # ---------- 세트 ----------
    def default_set(self, pid: str, fmt: str) -> dict:
        """가장 많이 쓰이는 기술 4개 / 도구 / 특성 / 성격 / 노력치 분배."""
        p = self.P[pid]
        u = p["usage"].get(fmt) or next(iter(p["usage"].values()), None)
        if not u:
            return {"id": pid, "moves": [], "item": None, "ability": p["abilities"][0] if p["abilities"] else None,
                    "nature": "Hardy", "points": dict.fromkeys(STAT_KEYS, 0), "mega": None}
        item = u["items"][0]["name"] if u["items"] else None
        mega = self.find_mega(p, stone=item) if item else None
        sp = u["spreads"][0] if u["spreads"] else {}
        return {
            "id": pid, "moves": [m["name"] for m in u["moves"][:4]], "item": item,
            "ability": u["abilities"][0]["name"] if u["abilities"] else (p["abilities"][0] if p["abilities"] else None),
            "nature": u["natures"][0]["name"] if u["natures"] else "Hardy",
            "points": {k: sp.get(k, 0) for k in STAT_KEYS}, "mega": mega["name"] if mega else None,
        }

    def resolve(self, s: dict, fmt: str) -> dict:
        """세트(입력) -> 실제 전투 수치가 계산된 포켓몬."""
        p = self.P[s["id"]]
        base = self.default_set(s["id"], fmt)
        item = s.get("item", base["item"])
        mega = self.find_mega(p, name=s.get("mega")) if s.get("mega") else None
        form = mega or p
        nature = s.get("nature") or base["nature"]
        if nature not in NATURES:
            nature = "Hardy"
        up, down = NATURES[nature]
        points = {k: max(0, min(32, int((s.get("points") or base["points"]).get(k, 0)))) for k in STAT_KEYS}
        stats = {}
        for k in STAT_KEYS:
            v = form["stats"][k] + points[k]
            if k == up:
                v = math.floor(v * 1.1)
            elif k == down:
                v = math.floor(v * 0.9)
            stats[k] = v
        ability = mega["abilities"][0] if mega else (s.get("ability") or base["ability"])
        moves = [m for m in (s.get("moves") if s.get("moves") is not None else base["moves"]) if m in self.M][:4]
        speed = stats["spe"] * (1.5 if item == "Choice Scarf" else 1)
        return {
            "id": p["id"], "name": form["name"], "ko": form.get("ko"), "baseName": p["name"], "sprite": form["sprite"],
            "types": form["types"], "ability": ability, "item": item, "nature": nature, "points": points,
            "stats": stats, "moves": moves, "mega": mega["name"] if mega else None, "speed": speed,
        }

    def default_resolved(self, pid: str, fmt: str) -> dict:
        key = (fmt, pid)
        if key not in self._default:
            r = self.resolve(self.default_set(pid, fmt), fmt)
            r["_default"] = True
            self._default[key] = r
        return self._default[key]

    # ---------- 데미지 ----------
    def damage(self, a: dict, move: str, b: dict, fmt: str, *,
               spread: bool | None = None, full_hp: bool = True, recharge_discount: bool = True,
               weather: str | None = None, psychic_terrain: bool = False) -> dict | None:
        """평균 데미지를 상대 HP 대비 %로 추정한다 (급소/랭크 변화/날씨 지속 등은 무시한 근사치)."""
        m = self.M.get(move)
        if not m or m["category"] == "Status" or not m["power"] or m.get("selfdestruct"):
            return None
        mtype, power, phys = m["type"], m["power"] * m.get("hits", 1), m["category"] == "Physical"
        flags = m.get("flags", [])
        aa, ba = a["ability"], (None if a["ability"] in MOLD else b["ability"])
        if move == "Weather Ball" and weather:
            mtype = {"sun": "Fire", "rain": "Water", "sand": "Rock", "snow": "Ice"}[weather]
            power *= 2
        if weather is None:
            weather = {"Drought": "sun", "Drizzle": "rain"}.get(aa, "")
        if move == "Expanding Force" and psychic_terrain:
            power *= 1.5
        if mtype == "Normal" and aa in ATE:
            mtype, power = ATE[aa], power * 1.2
        if aa == "Technician" and m["power"] <= 60:
            power *= 1.5
        if aa == "Tough Claws" and "contact" in flags:
            power *= 1.3
        if aa == "Sharpness" and "slicing" in flags:
            power *= 1.5
        if aa == "Iron Fist" and "punch" in flags:
            power *= 1.2
        if aa == "Strong Jaw" and "bite" in flags:
            power *= 1.5
        if aa == "Punk Rock" and "sound" in flags:
            power *= 1.3

        if move == "Body Press":
            atk = a["stats"]["def"]
        elif move == "Foul Play":
            atk = b["stats"]["atk"]
        else:
            atk = a["stats"]["atk" if phys else "spa"]
        dfn = b["stats"]["def" if phys or move in DEF_TARGET_MOVES else "spd"]
        if phys and aa in ("Huge Power", "Pure Power"):
            atk *= 2
        if a["item"] == "Choice Band" and phys or a["item"] == "Choice Specs" and not phys:
            atk *= 1.5
        if phys and b["ability"] == "Intimidate" and aa not in NO_INTIMIDATE and move != "Foul Play":
            atk *= 2 / 3
        if not phys and b["item"] == "Assault Vest":
            dfn *= 1.5

        eff = type_multiplier(mtype, b["types"], ba)
        if aa == "Scrappy" and mtype in ("Normal", "Fighting") and "Ghost" in b["types"]:
            eff = type_multiplier(mtype, [t for t in b["types"] if t != "Ghost"], ba)
        if move == "Freeze-Dry" and "Water" in b["types"]:
            eff *= 4
        if eff == 0:
            return {"move": move, "pct": 0.0, "eff": 0, "type": mtype, "acc": m["accuracy"], "priority": m["priority"]}

        mod = eff
        use_spread = spread if spread is not None else fmt == "Doubles" and m["target"] in SPREAD_TARGETS
        if use_spread:
            mod *= 0.75
        if mtype in a["types"]:
            mod *= 2 if aa == "Adaptability" else 1.5
        if weather == "sun":
            mod *= 1.5 if mtype == "Fire" else 0.5 if mtype == "Water" else 1
        if weather == "rain":
            mod *= 1.5 if mtype == "Water" else 0.5 if mtype == "Fire" else 1
        if psychic_terrain and mtype == "Psychic":
            mod *= 1.3
        if a["item"] == "Life Orb":
            mod *= 1.3
        elif TYPE_ITEMS.get(a["item"]) == mtype:
            mod *= 1.2
        elif a["item"] == "Expert Belt" and eff > 1:
            mod *= 1.2
        if aa == "Tinted Lens" and eff < 1:
            mod *= 2
        if RESIST_BERRIES.get(b["item"]) == mtype and (eff > 1 or mtype == "Normal"):
            mod *= 0.5
        if full_hp and ba in ("Multiscale", "Shadow Shield"):
            mod *= 0.5
        if ba in ("Filter", "Solid Rock", "Prism Armor") and eff > 1:
            mod *= 0.75
        if ba == "Fur Coat" and phys or ba == "Ice Scales" and not phys:
            mod *= 0.5
        if ba == "Fluffy":
            mod *= (0.5 if "contact" in flags else 1) * (2 if mtype == "Fire" else 1)
        if recharge_discount and m.get("recharge"):
            mod *= 0.6  # 반동으로 한 턴 쉬는 기술은 실질 화력을 깎아서 본다

        raw = (math.floor(math.floor(22 * power * atk / max(dfn, 1)) / 50) + 2) * mod * 0.925
        return {"move": move, "pct": round(raw / b["stats"]["hp"] * 100, 1), "eff": eff, "type": mtype,
                "acc": m["accuracy"], "priority": m["priority"]}

    def best_hit(self, a: dict, b: dict, fmt: str, moves: list[str] | None = None) -> dict | None:
        best, fallback = None, None
        for mv in moves if moves is not None else a["moves"]:
            h = self.damage(a, mv, b, fmt)
            if not h:
                continue
            if mv == "Fake Out":  # 첫 턴 전용이라 주력기로 보지 않는다
                fallback = fallback or h
                continue
            if best is None or h["pct"] * h["acc"] > best["pct"] * best["acc"]:
                best = h
        return best or fallback

    def matchup(self, a: dict, b: dict, fmt: str) -> dict:
        """a 입장에서 본 1:1 상성 점수 (0~100, 50이 호각)."""
        cacheable = a.get("_default") and b.get("_default")
        key = (fmt, a["id"], b["id"])
        if cacheable and key in self._matchups:
            return self._matchups[key]
        ha, hb = self.best_hit(a, b, fmt), self.best_hit(b, a, fmt)
        pa, pb = (ha["pct"] if ha else 0), (hb["pct"] if hb else 0)
        ta, tb = min(pa, 110) / 110, min(pb, 110) / 110
        if a["speed"] > b["speed"]:
            edge = 1.0
        elif a["speed"] < b["speed"]:
            edge = 0.4 if ha and ha["priority"] > 0 and pa >= 40 else -1.0
        else:
            edge = 0.0
        if hb and hb["priority"] > 0 and pb >= 40 and edge > 0:
            edge = 0.3
        speed_w = 10 if fmt == "Doubles" else 15
        score = 50 + 38 * (ta - tb) + speed_w * edge
        if pa >= 100 and edge > 0:
            score += 8
        if pb >= 100 and edge < 0:
            score -= 8
        res = {"score": round(max(0, min(100, score)), 1), "hit": ha, "taken": hb, "faster": edge > 0}
        if cacheable:
            self._matchups[key] = res
        return res

    # ---------- 메타 기준값 ----------
    def meta(self, fmt: str, n: int) -> list[dict]:
        return [self.default_resolved(p["id"], fmt) for p in self.ranked(fmt)[:n]]

    def percentiles(self, fmt: str) -> dict:
        if fmt not in self._pct:
            meta = self.meta(fmt, 60)
            speeds = sorted(r["speed"] for r in meta)
            bulks = sorted(r["stats"]["hp"] * (r["stats"]["def"] + r["stats"]["spd"]) for r in meta)
            self._pct[fmt] = {"fast": speeds[int(len(speeds) * 0.65)], "bulky": bulks[int(len(bulks) * 0.65)]}
        return self._pct[fmt]

    # ---------- 역할 ----------
    def roles(self, r: dict, fmt: str) -> list[str]:
        out, moves = [], set(r["moves"])
        dmg = [self.M[m] for m in r["moves"] if self.M[m]["category"] != "Status" and self.M[m]["power"]]
        nphys = sum(1 for m in dmg if m["category"] == "Physical")
        nspec = len(dmg) - nphys
        if dmg:
            if nphys and nspec and min(nphys, nspec) >= 2:
                out.append("mixed")
            elif nphys >= nspec:
                out.append("physical")
            else:
                out.append("special")
        pct = self.percentiles(fmt)
        if r["speed"] >= pct["fast"]:
            out.append("fast")
        if r["stats"]["hp"] * (r["stats"]["def"] + r["stats"]["spd"]) >= pct["bulky"]:
            out.append("bulky")
        for role, names in ROLE_ABILITIES.items():
            if r["ability"] in names:
                out.append(role)
        for role, names in ROLE_MOVES.items():
            if moves & names:
                out.append(role)
        if any(m["priority"] > 0 for m in dmg if m is not self.M.get("Fake Out")):
            out.append("priority")
        if r["item"] in ("Choice Scarf", "Choice Band", "Choice Specs"):
            out.append("choice")
        if r["mega"]:
            out.append("mega")
        return out

    def describe(self, r: dict, fmt: str) -> dict:
        """API 응답용: 해석된 세트 + 역할 + 기술 메타데이터."""
        roles = self.roles(r, fmt)
        d = self.d
        return {**{k: v for k, v in r.items() if not k.startswith("_")},
                "rank": self.rank(r["id"], fmt),
                "moveInfo": [{"name": m, "ko": self.M[m]["ko"], "type": self.M[m]["type"],
                              "category": self.M[m]["category"], "power": self.M[m]["power"]} for m in r["moves"]],
                "itemKo": (d["items"].get(r["item"]) or {}).get("ko"),
                "abilityKo": (d["abilities"].get(r["ability"]) or {}).get("ko"),
                "natureKo": d["natures"].get(r["nature"]),
                "roles": [{"key": k, "label": ROLE_LABELS[k]} for k in roles]}

    # ---------- 팀 분석 ----------
    def team_score(self, scores: list[float]) -> float:
        # 가장 잘 받아치는 2마리(답)와 팀 전체 평균(얼마나 많이 위협받는가)을 함께 본다
        s = sorted(scores, reverse=True)
        if len(s) == 1:
            return s[0]
        return 0.45 * s[0] + 0.25 * s[1] + 0.30 * sum(s) / len(s)

    @staticmethod
    def label(score: float) -> str:
        return "GOOD" if score >= 62 else "EVEN" if score >= 50 else "BAD"

    def analyze_team(self, sets: list[dict], fmt: str, top_n: int = 20) -> dict:
        team = [self.resolve(s, fmt) for s in sets if s.get("id") in self.P]
        if not team:
            return {"members": []}
        members = [self.describe(r, fmt) for r in team]
        role_sets = [set(x["key"] for x in m["roles"]) for m in members]

        # 타입 상성표
        type_rows, warnings = [], []
        for t in TYPES:
            mults = [type_multiplier(t, r["types"], r["ability"]) for r in team]
            weak = sum(1 for x in mults if x >= 2)
            resist = sum(1 for x in mults if x <= 0.5)
            type_rows.append({"type": t, "mults": mults, "weak": weak, "resist": resist})
            if weak >= 3 or (weak >= 2 and resist == 0 and len(team) >= 4):
                names = [f"{r['ko'] or r['name']} {mults[i]:g}배" for i, r in enumerate(team) if mults[i] >= 2]
                warnings.append({"kind": "type", "type": t, "severity": "high" if weak - resist >= 2 else "mid",
                                 "text": f"{len(names)}마리가 {t} 타입에 약점" + ("" if resist else ", 반감 없음"),
                                 "detail": ", ".join(names)})

        # 물리/특수 비중
        phys = spec = 0.0
        for r in team:
            for mv in r["moves"]:
                m = self.M[mv]
                if m["category"] == "Physical":
                    phys += 1
                elif m["category"] == "Special":
                    spec += 1
        tot = phys + spec or 1
        split = {"physical": round(phys / tot * 100), "special": round(spec / tot * 100)}

        # 역할 커버리지 (별 0~5)
        def stars(key: str) -> tuple[int, list[str]]:
            if key == "field":
                who = [i for i, rs in enumerate(role_sets) if rs & {"weather", "terrain"}]
            elif key in ("physical", "special"):
                who = [i for i, rs in enumerate(role_sets) if key in rs or "mixed" in rs]
                n = len(who)
                return (0 if n == 0 else min(5, n + 1)), [members[i]["ko"] or members[i]["name"] for i in who]
            else:
                who = [i for i, rs in enumerate(role_sets) if key in rs]
            n = len(who)
            return (0 if n == 0 else 2 if n == 1 else 4 if n == 2 else 5), \
                   [members[i]["ko"] or members[i]["name"] for i in who]

        role_cov = []
        for key, label in TEAM_ROLE_ROWS[fmt]:
            s, who = stars(key)
            role_cov.append({"key": key, "label": label, "stars": s, "who": who})

        # 메타 상성
        meta = [m for m in self.meta(fmt, top_n)]
        matchups, bad = [], []
        for b in meta:
            per = [self.matchup(a, b, fmt) for a in team]
            score = self.team_score([x["score"] for x in per])
            order = sorted(range(len(team)), key=lambda i: -per[i]["score"])
            answers = [{"id": team[i]["id"], "name": team[i]["name"], "ko": team[i]["ko"], "sprite": team[i]["sprite"],
                        "score": per[i]["score"], "move": per[i]["hit"]["move"] if per[i]["hit"] else None,
                        "pct": per[i]["hit"]["pct"] if per[i]["hit"] else 0,
                        "eff": per[i]["hit"]["eff"] if per[i]["hit"] else 1, "faster": per[i]["faster"]}
                       for i in order[:3]]
            threatened = [{"id": team[i]["id"], "name": team[i]["name"], "ko": team[i]["ko"],
                           "sprite": team[i]["sprite"], "move": per[i]["taken"]["move"],
                           "pct": per[i]["taken"]["pct"]}
                          for i in range(len(team)) if per[i]["taken"] and per[i]["taken"]["pct"] >= 60]
            threatened.sort(key=lambda x: -x["pct"])
            self.with_move_ko(answers)
            self.with_move_ko(threatened)
            row = {"id": b["id"], "name": b["name"], "ko": b["ko"], "sprite": b["sprite"], "types": b["types"],
                   "rank": self.rank(b["id"], fmt), "score": round(score, 1), "label": self.label(score),
                   "answers": answers, "threatened": threatened[:4]}
            matchups.append(row)
            if row["label"] == "BAD":
                bad.append(row)

        # 약점 요약
        if split["physical"] >= 70 or split["special"] >= 70:
            side = "물리" if split["physical"] >= 70 else "특수"
            walls = []
            for b in meta:
                if side == "물리" and (b["ability"] == "Intimidate" or b["stats"]["def"] >= 150):
                    walls.append(b["ko"] or b["name"])
                if side == "특수" and (b["item"] == "Assault Vest" or b["stats"]["spd"] >= 150):
                    walls.append(b["ko"] or b["name"])
            warnings.append({"kind": "split", "severity": "mid",
                             "text": f"화력이 {side}에 편중 ({side} {max(split.values())}%)",
                             "detail": ("위협이 되는 메타 포켓몬: " + ", ".join(walls[:6])) if walls else
                             f"{'위협 특성이나 물리막이' if side == '물리' else '돌격조끼나 특수막이'}에 막히기 쉽습니다"})
        missing = [r["label"] for r in role_cov if r["stars"] == 0 and r["key"] in
                   (("speedcontrol", "fakeout", "priority", "intimidate") if fmt == "Doubles"
                    else ("priority", "pivot", "hazard"))]
        if missing and len(team) >= 4:
            warnings.append({"kind": "role", "severity": "low", "text": "빠진 역할: " + ", ".join(missing),
                             "detail": "아래 교체 추천에서 해당 역할을 가진 후보를 확인하세요"})
        megas = [m["ko"] or m["name"] for m in members if m["mega"]]
        if len(megas) >= 3:
            warnings.append({"kind": "mega", "severity": "low", "text": f"메가진화 후보가 {len(megas)}마리",
                             "detail": "한 배틀에서 메가진화는 1마리만 가능합니다: " + ", ".join(megas)})
        if bad:
            warnings.append({"kind": "meta", "severity": "high" if len(bad) >= 4 else "mid",
                             "text": f"메타 상위 {top_n}마리 중 {len(bad)}마리에 불리",
                             "detail": ", ".join(b["ko"] or b["name"] for b in bad)})

        return {
            "format": fmt, "members": members, "typeRows": type_rows, "damageSplit": split, "roleCoverage": role_cov,
            "warnings": sorted(warnings, key=lambda w: {"high": 0, "mid": 1, "low": 2}[w["severity"]]),
            "matchups": matchups,
            "metaScore": round(sum(m["score"] * weight(m["rank"]) for m in matchups)
                               / sum(weight(m["rank"]) for m in matchups), 1) if matchups else None,
            "suggestions": self.suggest_swaps(team, fmt, meta, type_rows) if len(team) >= 3 else [],
        }

    def suggest_swaps(self, team: list[dict], fmt: str, meta: list[dict], type_rows: list[dict]) -> list[dict]:
        """한 자리만 바꾼다면: 메타 상성 합계를 가장 많이 올려 주는 (빠질 포켓몬, 들어올 포켓몬) 조합."""
        ws = [weight(self.rank(b["id"], fmt)) for b in meta]
        wsum = sum(ws)
        base_scores = [[self.matchup(a, b, fmt)["score"] for a in team] for b in meta]
        base_team = [self.team_score(row) for row in base_scores]
        base_total = sum(w * s for w, s in zip(ws, base_team)) / wsum
        weak_types = {r["type"] for r in type_rows if r["weak"] >= 2}
        on_team = {r["baseName"].split("-")[0] for r in team}
        megas_on_team = sum(1 for r in team if r["mega"])
        out = []
        for p in self.ranked(fmt)[:140]:
            if p["name"].split("-")[0] in on_team:
                continue
            c = self.default_resolved(p["id"], fmt)
            if c["mega"] and megas_on_team >= 2:
                continue
            cs = [self.matchup(c, b, fmt)["score"] for b in meta]
            piles = sum(1 for t in weak_types if type_multiplier(t, c["types"], c["ability"]) >= 2)
            best = None
            for slot in range(len(team)):
                new_team = [self.team_score([s for i, s in enumerate(row) if i != slot] + [cs[j]])
                            for j, row in enumerate(base_scores)]
                total = sum(w * s for w, s in zip(ws, new_team)) / wsum
                if best is None or total > best[0]:
                    best = (total, slot, new_team)
            gain = best[0] - base_total - 0.8 * piles
            if gain <= 0.3:
                continue
            fixes = [meta[j] for j in range(len(meta))
                     if self.label(best[2][j]) != "BAD" and self.label(base_team[j]) == "BAD"
                     or best[2][j] - base_team[j] >= 8]
            out.append({"gain": round(gain, 1), "slot": best[1], "out": {"id": team[best[1]]["id"],
                        "name": team[best[1]]["name"], "ko": team[best[1]]["ko"], "sprite": team[best[1]]["sprite"]},
                        "in": self.describe(c, fmt), "set": self.default_set(p["id"], fmt),
                        "fixes": [{"id": b["id"], "name": b["name"], "ko": b["ko"], "sprite": b["sprite"]}
                                  for b in fixes[:5]]})
        out.sort(key=lambda x: -x["gain"])
        return out[:8]

    # ---------- 조커 ----------
    def joker_set(self, pid: str, fmt: str, meta: list[dict], ws: list[float]) -> dict:
        """실제로 쓰인 기술 풀 안에서 메타 커버리지가 최대가 되도록 기술을 고른다."""
        base = self.default_set(pid, fmt)
        u = self.P[pid]["usage"][fmt]
        pool = [m["name"] for m in u["moves"] if m["pct"] >= 3 or m["name"] in base["moves"]]
        probe = self.resolve({**base, "moves": pool[:4]}, fmt)
        cov = {}
        for mv in pool:
            hits = [self.damage(probe, mv, b, fmt) for b in meta]
            if hits[0] is None or mv == "Fake Out":
                continue
            cov[mv] = [min(1, h["pct"] / 75) * h["acc"] / 100 for h in hits]
        n_attacks = 4 if base["item"] in ("Choice Scarf", "Choice Band", "Choice Specs", "Assault Vest") else 3
        chosen, cur = [], [0.0] * len(meta)
        while len(chosen) < n_attacks and len(chosen) < len(cov):
            mv = max((m for m in cov if m not in chosen),
                     key=lambda m: sum(w * max(c, x) for w, c, x in zip(ws, cur, cov[m])))
            gain = sum(w * (max(c, x) - c) for w, c, x in zip(ws, cur, cov[mv]))
            if chosen and gain < 0.01 * sum(ws):
                break
            chosen.append(mv)
            cur = [max(c, x) for c, x in zip(cur, cov[mv])]
        for mv in pool:  # 남는 칸은 채용률 높은 순으로 (주로 방어/보조기)
            if len(chosen) >= 4:
                break
            if mv not in chosen and (mv not in cov or n_attacks == 4 or len(chosen) >= len(cov)):
                chosen.append(mv)
        for mv in pool:
            if len(chosen) >= 4:
                break
            if mv not in chosen:
                chosen.append(mv)
        return {**base, "moves": chosen}

    def jokers(self, fmt: str, min_rank: int = 50, top_n: int = 20, role: str | None = None,
               ptype: str | None = None, limit: int = 40) -> list[dict]:
        ranked = self.ranked(fmt)
        total = len(ranked)
        meta = self.meta(fmt, top_n)
        ws = [weight(self.rank(b["id"], fmt)) for b in meta]
        wsum = sum(ws)
        uw = UTILITY_WEIGHTS[fmt]
        out = []
        for p in ranked:
            rank = p["usage"][fmt]["rank"]
            if rank < min_rank or not p["usage"][fmt]["moves"]:
                continue
            s = self.joker_set(p["id"], fmt, meta, ws)
            r = self.resolve(s, fmt)
            if ptype and ptype not in r["types"]:
                continue
            roles = self.roles(r, fmt)
            if role and role not in roles:
                continue
            strong, weak, cov, good_types = [], [], 0.0, set()
            for b, w in zip(meta, ws):
                mu = self.matchup(r, b, fmt)
                h = mu["hit"]
                if h:
                    c = min(1, h["pct"] / 75) * h["acc"] / 100
                    cov += w * c
                    if c >= 0.75 or (h["eff"] >= 2 and h["pct"] >= 45):
                        good_types.add(h["type"])
                        strong.append({"id": b["id"], "name": b["name"], "ko": b["ko"], "sprite": b["sprite"],
                                       "move": h["move"], "pct": h["pct"], "eff": h["eff"], "w": w})
                if mu["score"] <= 38:
                    weak.append({"id": b["id"], "name": b["name"], "ko": b["ko"], "sprite": b["sprite"],
                                 "move": mu["taken"]["move"] if mu["taken"] else None,
                                 "pct": mu["taken"]["pct"] if mu["taken"] else 0, "w": w})
            coverage = 100 * cov / wsum
            surprise = 100 * math.log(rank) / math.log(total)
            speed = 100 * sum(w for b, w in zip(meta, ws) if r["speed"] > b["speed"]) / wsum
            utility = min(100, sum(uw.get(k, 0) for k in set(roles)))
            compression = min(100, 20 * len(good_types) + 14 * sum(1 for k in set(roles) if k in uw))
            score = coverage * .40 + surprise * .20 + compression * .20 + speed * .10 + utility * .10
            out.append({
                "pokemon": self.describe(r, fmt), "set": s, "rank": rank,
                "scores": {"coverage": round(coverage), "surprise": round(surprise), "compression": round(compression),
                           "speed": round(speed), "utility": round(utility)},
                "score": round(score, 1),
                "strong": self.with_move_ko(sorted(strong, key=lambda x: -x["w"])[:6]),
                "weak": self.with_move_ko(sorted(weak, key=lambda x: -x["w"])[:5]),
            })
        out.sort(key=lambda x: -x["score"])
        if out:  # 등급은 후보군 내 상대 평가
            top = out[0]["score"]
            for o in out:
                ratio = o["score"] / top
                o["grade"] = "S" if ratio >= 0.96 else "A" if ratio >= 0.9 else "B" if ratio >= 0.82 else "C"
        return out[:limit]

    def with_move_ko(self, rows: list[dict]) -> list[dict]:
        for r in rows:
            for key in ("move", "takenMove"):
                if key in r:
                    m = self.M.get(r[key] or "")
                    r[key + "Ko"] = m["ko"] if m else None
                    r[key + "Type"] = m["type"] if m else None
        return rows

    # ---------- 포켓몬 상세용 ----------
    def counters_and_targets(self, pid: str, fmt: str, n: int = 40) -> dict:
        me = self.default_resolved(pid, fmt)
        rows = []
        for b in self.meta(fmt, n):
            if b["id"] == pid:
                continue
            mu = self.matchup(me, b, fmt)
            rows.append({"id": b["id"], "name": b["name"], "ko": b["ko"], "sprite": b["sprite"],
                         "rank": self.rank(b["id"], fmt), "score": mu["score"],
                         "move": mu["hit"]["move"] if mu["hit"] else None, "pct": mu["hit"]["pct"] if mu["hit"] else 0,
                         "takenMove": mu["taken"]["move"] if mu["taken"] else None,
                         "takenPct": mu["taken"]["pct"] if mu["taken"] else 0})
        self.with_move_ko(rows)
        return {"counters": sorted([r for r in rows if r["score"] <= 40], key=lambda r: r["score"])[:8],
                "targets": sorted([r for r in rows if r["score"] >= 60], key=lambda r: -r["score"])[:8]}
