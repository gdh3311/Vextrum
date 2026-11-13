"""팀 단위 세트 최적화.

사용률 1위 세트를 그대로 쓰지 않고, 팀 안에서의 역할을 기준으로 도구·특성·기술·능력 포인트를 다시 고른다.

1. 후보 만들기: 실제 채용 도구 + 역할 규칙(공격수: 생명의구슬·달인의띠·타입 강화 도구·구애스카프, 연약한 선봉: 기합의띠,
   내구형: 자뭉열매·먹다남은음식·울퉁불퉁멧·메타 위협 타입 반감 열매), 합법 특성, 메타 상대 커버리지로 고른 기술 조합,
   최속·내구·트릭룸 능력 포인트 분배.
2. 계산으로 거르기: 메타 상위권 상대 상성 점수에 '팀이 이미 잘 받는 상대'보다 '팀이 못 받는 상대'를 더 무겁게 둔다.
3. 시뮬레이션으로 확인: 기본 팀과 바꾼 팀을 같은 상대·같은 난수로 싸우게 해 실제로 승률이 오른 변경만 받아들인다.
"""
from dataclasses import dataclass

from . import mechanics as mx, parallel
from .engine import RESIST_BERRIES, TYPE_ITEMS, Engine, weight
from .simulation import PROTECT, SUPPORT

# 챔피언스에 있고 배틀 엔진이 효과를 계산하는 도구만 후보로 쓴다.
SIMULATED_ITEMS = {
    "Air Balloon", "Black Belt", "Black Glasses", "Charcoal", "Choice Scarf", "Dragon Fang", "Expert Belt",
    "Fairy Feather", "Focus Sash", "Hard Stone", "Leftovers", "Life Orb", "Light Clay", "Lum Berry", "Magnet",
    "Metal Coat", "Miracle Seed", "Mystic Water", "Never-Melt Ice", "Poison Barb", "Rocky Helmet", "Scope Lens",
    "Sharp Beak", "Silk Scarf", "Silver Powder", "Sitrus Berry", "Soft Sand", "Spell Tag", "Twisted Spoon",
    "Wide Lens", "White Herb", "Mental Herb", "Chesto Berry", "Bright Powder", "Muscle Band", "Wise Glasses",
    "Normal Gem", "Focus Band", "Grassy Seed", "Electric Seed", "Psychic Seed", *RESIST_BERRIES,
}
TYPE_BOOST = {t: item for item, t in TYPE_ITEMS.items()}
RESIST_BERRY = {t: item for item, t in RESIST_BERRIES.items()}
UTILITY = SUPPORT | mx.NEW_SUPPORT | PROTECT
# 엔진이 아직 단점(고정·혼란·충전)을 계산하지 않는 기술은 새로 넣지 않는다.
UNMODELED = {"Outrage", "Thrash", "Petal Dance", "Raging Fury", "Solar Beam", "Solar Blade", "Sky Attack",
             "Meteor Beam", "Focus Punch", "Dream Eater", "Belch", "Steel Beam", "Mind Blown"}
NATURE_FOR = {  # (올릴 능력치, 내릴 능력치) → 성격
    ("spe", "spa"): "Jolly", ("spe", "atk"): "Timid", ("atk", "spa"): "Adamant", ("spa", "atk"): "Modest",
    ("atk", "spe"): "Brave", ("spa", "spe"): "Quiet", ("def", "spa"): "Impish", ("spd", "spa"): "Careful",
    ("def", "atk"): "Bold", ("spd", "atk"): "Calm",
}
LABELS = {"item": "도구", "ability": "특성", "moves": "기술", "points": "능력 포인트"}
DEPTHS = {"quick": (40, 160), "standard": (60, 240), "deep": (100, 400)}  # (1차 판 수, 2·3차 판 수)


@dataclass
class Variant:
    kind: str
    set: dict
    note: str
    score: float = 0.


def _name(e, kind, value):
    if kind == "item":
        return e.d["items"].get(value, {}).get("ko") or value or "없음"
    if kind == "ability":
        return e.d["abilities"].get(value, {}).get("ko") or value
    if kind == "move":
        return e.M.get(value, {}).get("ko") or value
    return value


def _attacks(e, moves):
    return [m for m in moves if e.M.get(m, {}).get("power") and m not in UTILITY]


class Tuner:
    def __init__(self, e: Engine, fmt: str, top: int = 24):
        self.e, self.fmt = e, fmt
        self.meta = [f for f in e.meta(fmt, top)]
        self.w = [weight(e.rank(f["id"], fmt) or 250) for f in self.meta]
        total = sum(self.w)
        self.w = [x / total for x in self.w]
        self.bulk_line = e.percentiles(fmt)["bulky"]

    # ---------- 계산 점수
    def matchups(self, s):
        r = self.e.resolve(s, self.fmt)
        return [self.e.matchup(r, foe, self.fmt)["score"] for foe in self.meta]

    def gaps(self, team, skip):
        """다른 팀원들이 각 메타 상대를 얼마나 잘 받는지 → 못 받을수록 1에 가깝다."""
        others = [self.matchups(s) for i, s in enumerate(team) if i != skip]
        return [1 - max((row[j] for row in others), default=0) / 100 for j in range(len(self.meta))]

    def value(self, s, gaps):
        return sum(w * m * (1 + 1.6 * g) for w, m, g in zip(self.w, self.matchups(s), gaps))

    # ---------- 후보
    def _threat_type(self, r):
        """메타 상대가 이 포켓몬에게 효과가 굉장한 기술로 가장 많이 노리는 타입."""
        weights = {}
        for foe, w in zip(self.meta, self.w):
            hit = self.e.best_hit(foe, r, self.fmt)
            if hit and hit["eff"] >= 2:
                weights[hit["type"]] = weights.get(hit["type"], 0) + w * hit["pct"]
        return max(weights, key=weights.get) if weights else None

    def items(self, s, used):
        e, r = self.e, self.e.resolve(s, self.fmt)
        # 메가스톤과, 엔진이 아직 계산하지 않는 도구(탈출버튼 등)는 바꾸지 않는다.
        if r["mega"] or s.get("item") and s["item"] not in SIMULATED_ITEMS:
            return []
        usage = [row["name"] for row in e.P[s["id"]]["usage"].get(self.fmt, {}).get("items", [])[:6]
                 if row["pct"] >= 3]
        attacks = _attacks(e, r["moves"])
        bulky = r["stats"]["hp"] * (r["stats"]["def"] + r["stats"]["spd"]) >= self.bulk_line
        rules = []
        if len(attacks) >= 2:
            rules += ["Life Orb", "Expert Belt"]
            stab = max((m for m in attacks if e.M[m]["type"] in r["types"]),
                       key=lambda m: e.M[m]["power"], default=None)
            if stab and stab in r["moves"]:
                rules.append(TYPE_BOOST.get(e.M[stab]["type"]))
            if len(attacks) >= 3 and not set(r["moves"]) & PROTECT:
                rules.append("Choice Scarf")
        if not bulky:
            rules.append("Focus Sash")
        else:
            rules += ["Sitrus Berry", "Rocky Helmet" if r["stats"]["def"] >= r["stats"]["spd"] else "Leftovers"]
        if self.fmt == "Singles":
            rules.append("Leftovers")
        if threat := self._threat_type(r):
            rules.append(RESIST_BERRY.get(threat))
        out = []
        for item in dict.fromkeys([*usage, *rules]):
            if (item and item != s.get("item") and item not in used and item in e.d["items"]
                    and item in SIMULATED_ITEMS and not e.find_mega(e.P[s["id"]], stone=item)):
                out.append(Variant("item", {**s, "item": item}, f"{_name(e, 'item', s.get('item'))} → {_name(e, 'item', item)}"))
        return out

    def abilities(self, s):
        e = self.e
        if e.resolve(s, self.fmt)["mega"]:
            return []
        return [Variant("ability", {**s, "ability": a},
                        f"{_name(e, 'ability', s.get('ability'))} → {_name(e, 'ability', a)}")
                for a in e.P[s["id"]]["abilities"] if a != s.get("ability") and a in e.d["abilities"]]

    def moves(self, s, gaps):
        """보조기는 그대로 두고, 공격기 칸을 '팀이 못 받는 상대'까지 고려한 커버리지로 다시 고른다."""
        e = self.e
        p = e.P[s["id"]]
        usage = {row["name"]: row["pct"] for row in p["usage"].get(self.fmt, {}).get("moves", [])}
        keep = [m for m in s["moves"] if m in UTILITY or not e.M.get(m, {}).get("power")]
        slots = 4 - len(keep)
        if slots <= 0:
            return []
        pool = {m for m, pct in usage.items() if pct >= 3 and e.M.get(m, {}).get("power")}
        for m in p.get("learnset", []):
            mv = e.M.get(m)
            if (mv and not mv.get("unknown") and not mv.get("selfdestruct") and not mv.get("recharge")
                    and mv["power"] >= 70 and (mv["accuracy"] or 100) >= 85 and mv["category"] != "Status"):
                pool.add(m)
        pool -= set(keep) | UNMODELED
        probe = e.resolve({**s, "moves": list(pool)[:4] or s["moves"]}, self.fmt)
        cover = {}
        for m in pool:
            hits = [e.damage(probe, m, foe, self.fmt) for foe in self.meta]
            if hits and hits[0] is not None:
                cover[m] = [min(1, h["pct"] / 80) * (h["acc"] or 100) / 100 for h in hits]
        weights = [w * (1 + 1.6 * g) for w, g in zip(self.w, gaps)]
        chosen, cur = [], [0.] * len(self.meta)
        while len(chosen) < slots and cover:
            best = max((m for m in cover if m not in chosen), default=None,
                       key=lambda m: sum(w * max(c, x) for w, c, x in zip(weights, cur, cover[m]))
                       + .002 * usage.get(m, 0))
            if best is None:
                break
            chosen.append(best)
            cur = [max(c, x) for c, x in zip(cur, cover[best])]
        moves = keep + chosen
        if sorted(moves) == sorted(s["moves"]) or len(moves) < len(s["moves"]):
            return []
        added = [m for m in moves if m not in s["moves"]]
        removed = [m for m in s["moves"] if m not in moves]
        note = (", ".join(_name(e, "move", m) for m in removed) + " → "
                + ", ".join(_name(e, "move", m) for m in added))
        return [Variant("moves", {**s, "moves": moves}, note)]

    def spreads(self, s):
        e = self.e
        r = e.resolve(s, self.fmt)
        attacks = _attacks(e, r["moves"])
        physical = sum(e.M[m]["category"] == "Physical" for m in attacks) >= len(attacks) / 2
        main, off = ("atk", "spa") if physical else ("spa", "atk")
        out = []
        if attacks:
            fast = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 0)
            fast.update({main: 32, "spe": 32, "hp": 2})
            out.append(Variant("points", {**s, "points": fast, "nature": NATURE_FOR[("spe", off)]},
                               "공격·스피드 최대 (최속)"))
            if r["speed"] <= 90:
                room = dict.fromkeys(fast, 0)
                room.update({main: 32, "hp": 32, "def": 2})
                out.append(Variant("points", {**s, "points": room, "nature": NATURE_FOR[(main, "spe")]},
                                   "HP·공격 최대, 스피드 최저 (트릭룸)"))
        bulky = dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 0)
        bulky.update({"hp": 32, "def": 17, "spd": 17})
        if attacks:
            bulky.update({"def": 1, "spd": 1, main: 32})
            nature = NATURE_FOR[(main, off)]
        else:
            nature = NATURE_FOR[("def" if r["stats"]["def"] < r["stats"]["spd"] else "spd", "atk")]
        out.append(Variant("points", {**s, "points": bulky, "nature": nature},
                           "HP·화력 최대" if attacks else "HP·방어·특방 분산 (내구)"))
        return [v for v in out if v.set["points"] != s.get("points") or v.set["nature"] != s.get("nature")]

    # ---------- 탐색
    def candidates(self, team, locked=frozenset(), per_member=8):
        trials = []
        for i, s in enumerate(team):
            if s["id"] in locked:
                continue
            gaps = self.gaps(team, i)
            base = self.value(s, gaps)
            used = {m.get("item") for j, m in enumerate(team) if j != i and m.get("item")}
            options = [*self.items(s, used), *self.abilities(s), *self.moves(s, gaps), *self.spreads(s)]
            for v in options:
                v.score = self.value(v.set, gaps) - base
            # 계산 점수는 순서를 정하는 데만 쓰고, 종류별로 고르게 남긴다.
            options.sort(key=lambda v: -v.score)
            picked, per_kind = [], {}
            for v in options:
                if per_kind.get(v.kind, 0) < 3 and len(picked) < per_member:
                    picked.append(v)
                    per_kind[v.kind] = per_kind.get(v.kind, 0) + 1
            trials += [(i, v) for v in picked]
        return trials

    def _rates(self, teams, runs, seed):
        reports = parallel.compare_teams(self.e, self.fmt, teams, runs, seed, "ultra")
        return [(r["win"] + .5 * r["draw"]) / r["runs"] for r in reports]

    def _outcomes(self, teams, runs, seed):
        reports = parallel.compare_teams(self.e, self.fmt, teams, runs, seed, "ultra")
        return [r["outcomes"] for r in reports]

    def tune(self, team: list[dict], depth: str = "standard", seed: int = 2711, locked: set[str] = frozenset(),
             progress=None):
        screen, confirm = DEPTHS.get(depth, DEPTHS["standard"])
        report = progress or (lambda *args: None)
        team = [dict(s) for s in team]
        trials = self.candidates(team, locked)
        name = lambda i: self.e.P[team[i]["id"]]["ko"] or self.e.P[team[i]["id"]]["name"]
        report(0, [f"{name(i)} · {v.note}" for i, v in trials[::max(1, len(trials) // 8)]], 0)
        info = {"tried": len(trials), "screenRuns": screen, "confirmRuns": confirm}
        if not trials:
            return team, [], info
        swap = lambda i, v, base=team: [v.set if j == i else s for j, s in enumerate(base)]
        # 1차: 모든 변경 후보를 짧게
        rates = self._rates([team] + [swap(i, v) for i, v in trials], screen, seed)
        ranked = sorted(zip(trials, rates[1:]), key=lambda row: -row[1])
        shortlist = [t for t, r in ranked if r > rates[0]][:8]
        info["screened"] = len(shortlist)
        report(1, [f"{name(i)} · {v.note}" for i, v in shortlist], (len(trials) + 1) * screen)
        if not shortlist:
            return team, [], info
        # 2차: 새 상대군에서 다시 (1차의 운을 걸러낸다)
        from .battle_lab import clearly_better

        outs2 = self._outcomes([team] + [swap(i, v) for i, v in shortlist], confirm, seed + 101)
        rates2 = [sum(o) / len(o) for o in outs2]
        report(2, [f"{name(i)} · {v.note}" for i, v in shortlist[:4]], (len(shortlist) + 1) * confirm)
        best = {}
        for (i, v), value, out in zip(shortlist, rates2[1:], outs2[1:]):
            # 같은 판 차이의 한쪽 신뢰 하한이 0보다 클 때만 (표본 수를 반영, 고정 1%p 기준 대신)
            if clearly_better(outs2[0], out) and (i not in best or value > best[i][1]):
                best[i] = (v, value)
        if not best:
            return team, [], {**info, "base": rates2[0]}
        combined = [best[i][0].set if i in best else s for i, s in enumerate(team)]
        single = max(best.items(), key=lambda row: row[1][1])
        alone = swap(single[0], single[1][0])
        # 3차: 좋았던 변경을 합친 팀과 가장 좋았던 하나만 바꾼 팀을 또 다른 상대군에서 확인
        base_out, combined_out, alone_out = self._outcomes([team, combined, alone], confirm, seed + 202)
        base_rate, combined_rate, alone_rate = (sum(o) / len(o) for o in (base_out, combined_out, alone_out))
        report(3, [], 3 * confirm)
        if alone_rate > combined_rate and len(best) > 1:
            best, combined, combined_rate, combined_out = {single[0]: single[1]}, alone, alone_rate, alone_out
        info.update(base=round(base_rate, 3), tuned=round(combined_rate, 3))
        if not clearly_better(base_out, combined_out):  # 새 상대군에서도 확실히 나아야 채택
            return team, [], info
        changes = [{"id": team[i]["id"], "name": self.e.P[team[i]["id"]]["ko"] or self.e.P[team[i]["id"]]["name"],
                    "kind": LABELS[v.kind], "change": v.note, "gain": round(100 * (value - rates2[0]), 1)}
                   for i, (v, value) in sorted(best.items())]
        return combined, changes, info
