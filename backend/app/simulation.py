"""Local, approximate singles/doubles practice and repeatable CPU simulations."""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from random import Random
from threading import Lock
from time import monotonic
from typing import Literal
from uuid import uuid4

from .engine import Engine, SPREAD_TARGETS

MAX_TURNS = 40
Difficulty = Literal["poke", "great", "ultra", "master", "champion"]
FIRST_TURN = {"Fake Out", "First Impression"}
PROTECT = {"Protect", "Detect", "King's Shield", "Spiky Shield", "Baneful Bunker", "Silk Trap", "Burning Bulwark"}
HEAL = {"Recover", "Roost", "Slack Off", "Soft-Boiled", "Milk Drink", "Synthesis", "Moonlight", "Morning Sun", "Shore Up"}
BOOSTS = {
    "Swords Dance": {"atk": 2}, "Nasty Plot": {"spa": 2}, "Dragon Dance": {"atk": 1, "spe": 1},
    "Calm Mind": {"spa": 1, "spd": 1}, "Bulk Up": {"atk": 1, "def": 1},
    "Quiver Dance": {"spa": 1, "spd": 1, "spe": 1}, "Iron Defense": {"def": 2},
    "Agility": {"spe": 2}, "Shell Smash": {"atk": 2, "spa": 2, "spe": 2, "def": -1, "spd": -1},
}
CHOICE = {"Choice Band", "Choice Specs", "Choice Scarf"}
SUPPORT = PROTECT | HEAL | BOOSTS.keys() | {"Tailwind", "Trick Room"}
WEATHER = {"Drought": "sun", "Drizzle": "rain", "Sand Stream": "sand", "Snow Warning": "snow"}
WEATHER_MOVES = {"Sunny Day": "sun", "Rain Dance": "rain", "Sandstorm": "sand", "Snowscape": "snow"}
WEATHER_LABELS = {"sun": "쾌청", "rain": "비", "sand": "모래바람", "snow": "눈"}
WEATHER_SPEED = {"Chlorophyll": "sun", "Swift Swim": "rain", "Sand Rush": "sand", "Slush Rush": "snow"}
WEATHER_CHARGE = {"Solar Beam": "sun", "Solar Blade": "sun", "Electro Shot": "rain"}
SUPPORT |= WEATHER_MOVES.keys()


def _stage(level: int) -> float:
    return (2 + max(0, level)) / (2 - min(0, level))


@dataclass
class Fighter:
    mon: dict
    hp: int
    stages: dict[str, int] = field(default_factory=dict)
    entered: int = 1
    choice: str | None = None
    recharge: bool = False
    protected: bool = False
    protect_chain: int = 0
    flinched: bool = False
    item_used: bool = False
    dealt: int = 0
    taken: int = 0
    kos: int = 0
    victims: Counter = field(default_factory=Counter)
    charging: tuple[str, int | None] | None = None

    @property
    def max_hp(self) -> int:
        return self.mon["stats"]["hp"]

    @property
    def name(self) -> str:
        return self.mon["ko"] or self.mon["name"]

    def effective(self) -> dict:
        item = None if self.item_used else self.mon["item"]
        stats = {stat: max(1, int(n * _stage(self.stages.get(stat, 0)))) for stat, n in self.mon["stats"].items()}
        return {**self.mon, "item": item, "stats": stats}

    def withdraw(self):
        self.stages.clear()
        self.choice = None
        self.charging = None
        self.recharge = self.protected = self.flinched = False
        self.protect_chain = 0


class Battle:
    def __init__(self, engine: Engine, fmt: str, mine: list[dict], foe: list[dict], seed: int, *,
                 log: bool = True, context: dict | None = None, foe_strategy: str | None = None,
                 difficulty: Difficulty = "ultra", manual: bool = False):
        self.engine, self.fmt, self.seed = engine, fmt, seed
        self.rng = Random(seed)
        self.width = 2 if fmt == "Doubles" else 1
        self.teams = [self._fighters(mine), self._fighters(foe)]
        self.active = [[i if i < len(team) else None for i in range(self.width)] for team in self.teams]
        self.turn = 1
        self.winner: str | None = None
        self.tailwind = [0, 0]
        self.trick_room = 0
        self.weather = ""
        self.weather_turns = 0
        self.psychic_terrain = 0
        self.activated = [set(), set()]
        self.log: list[dict] = []
        self.keep_log = log
        self.context = context or {}
        self.foe_strategy = foe_strategy
        self.difficulty = difficulty
        self.manual = manual
        self.replacement_turn: int | None = None
        self.revealed = {i for i in self.active[1] if i is not None}
        self.updated = monotonic()
        leads = [(side, f) for side in range(2) for _, f in self._present(side)]
        if manual:
            for side, fighter in leads:
                self._event(f"{'상대' if side else '내 팀'}의 {fighter.name} 등장", "entry")
        for side, fighter in sorted(leads, key=lambda lead: lead[1].mon["speed"], reverse=True):
            self._on_entry(side, fighter)

    def _fighters(self, sets: list[dict]) -> list[Fighter]:
        fighters = []
        mega_used = False
        for s in sets:
            s = {**self.engine.default_set(s["id"], self.fmt), **s}
            if mega_used:
                s = {**s, "mega": None}
            mon = self.engine.resolve(s, self.fmt)
            mega_used |= bool(mon["mega"])
            fighters.append(Fighter(mon, mon["stats"]["hp"]))
        return fighters

    def _event(self, message: str, kind: str = "detail", **fields):
        if self.keep_log:
            self.log.append({"turn": self.turn, "text": message, "kind": kind, **fields})

    def _bench(self, side: int) -> list[int]:
        return [i for i, f in enumerate(self.teams[side]) if f.hp > 0 and i not in self.active[side]]

    def _present(self, side: int) -> list[tuple[int, Fighter]]:
        return [(slot, self.teams[side][i]) for slot, i in enumerate(self.active[side])
                if i is not None and self.teams[side][i].hp > 0]

    def _speed(self, side: int, f: Fighter) -> float:
        wind = 2 if self.tailwind[side] else 1
        weather = 2 if WEATHER_SPEED.get(f.mon["ability"]) == self.weather else 1
        return f.mon["speed"] * _stage(f.stages.get("spe", 0)) * wind * weather

    @staticmethod
    def _grounded(f: Fighter) -> bool:
        return "Flying" not in f.mon["types"] and f.mon["ability"] != "Levitate" and f.mon["item"] != "Air Balloon"

    def _on_entry(self, side: int, fighter: Fighter):
        ability = fighter.mon["ability"]
        if ability in WEATHER:
            self._set_weather(side, WEATHER[ability], fighter)
        if ability == "Psychic Surge":
            self.psychic_terrain = 8 if fighter.mon["item"] == "Terrain Extender" else 5
            self.activated[side].add("psychic")
            self._event("사이코필드가 펼쳐졌습니다.", "field")

    def _set_weather(self, side: int, weather: str, actor: Fighter):
        rocks = {"sun": "Heat Rock", "rain": "Damp Rock", "sand": "Smooth Rock", "snow": "Icy Rock"}
        self.weather = weather
        self.weather_turns = 8 if actor.mon["item"] == rocks[weather] else 5
        self.activated[side].add(weather)
        self._event(f"날씨 · {WEATHER_LABELS[weather]}", "field")

    def _move_name(self, move: str) -> str:
        return self.engine.M.get(move, {}).get("ko") or move

    def _moves(self, f: Fighter) -> list[str]:
        if f.recharge:
            return []
        moves = [m for m in f.mon["moves"] if
                 (m in SUPPORT or self.engine.M[m]["power"] and not self.engine.M[m].get("selfdestruct"))
                 and (not f.choice or m == f.choice)
                 and (m not in FIRST_TURN or f.entered == self.turn)]
        return moves or ["Struggle"]

    def _targets(self, side: int, slot: int, move: str, target: int | None) -> list[Fighter]:
        opponents = self._present(1 - side)
        category = self.engine.M.get(move, {}).get("target")
        if move == "Expanding Force" and self.psychic_terrain and self._grounded(dict(self._present(side))[slot]):
            return [f for _, f in opponents]
        if category in SPREAD_TARGETS:
            allies = [f for ally, f in self._present(side) if ally != slot] if category == "allAdjacent" else []
            return [f for _, f in opponents] + allies
        return [next((f for i, f in opponents if i == target), opponents[0][1])] if opponents else []

    def _damage(self, actor: Fighter, target: Fighter, move: str, spread: bool) -> tuple[float, float]:
        if move == "Struggle":
            return max(1, 0.22 * actor.mon["stats"]["atk"] / target.mon["stats"]["def"] * target.max_hp), 100
        attacker, defender = actor.effective(), target.effective()
        defender["stats"]["hp"] = target.max_hp
        if self.weather == "sand" and "Rock" in target.mon["types"]:
            defender["stats"]["spd"] = round(defender["stats"]["spd"] * 1.5)
        if self.weather == "snow" and "Ice" in target.mon["types"]:
            defender["stats"]["def"] = round(defender["stats"]["def"] * 1.5)
        hit = self.engine.damage(attacker, move, defender, self.fmt, spread=spread,
                                 full_hp=target.hp == target.max_hp, recharge_discount=False, weather=self.weather,
                                 psychic_terrain=bool(self.psychic_terrain and self._grounded(actor)))
        if not hit:
            return 0, 100
        accuracy = hit["acc"]
        if move in ("Thunder", "Hurricane"):
            accuracy = 100 if self.weather == "rain" else 50 if self.weather == "sun" else accuracy
        if move == "Blizzard" and self.weather == "snow":
            accuracy = 100
        if self.psychic_terrain and hit["priority"] > 0 and self._grounded(target):
            return 0, 100
        return hit["pct"] * target.max_hp / 100, accuracy

    def _options(self, side: int, slot: int, f: Fighter) -> list[dict]:
        if f.charging:
            move, target = f.charging
            return [{"slot": slot, "kind": "move", "move": move, "target": target,
                     "label": f"{self._move_name(move)} 발사", "type": self.engine.M[move]["type"]}]
        options = []
        for move in self._moves(f):
            meta = self.engine.M.get(move, {})
            spread = meta.get("target") in SPREAD_TARGETS or (
                move == "Expanding Force" and self.psychic_terrain and self._grounded(f))
            targets = [None] if move in SUPPORT or spread else [i for i, _ in self._present(1 - side)]
            options.extend({"slot": slot, "kind": "move", "move": move, "target": target,
                            "label": self._move_name(move), "type": meta.get("type"),
                            "scope": ("all" if meta.get("target") == "allAdjacent" else "foes")
                            if spread else None} for target in targets)
        if f.recharge:
            options.append({"slot": slot, "kind": "wait", "label": "재충전"})
        options.extend({"slot": slot, "kind": "switch", "target": i, "label": f"{self.teams[side][i].name} 교체"}
                       for i in self._bench(side))
        return options

    def _auto(self, side: int) -> list[dict]:
        chosen, reserves = [], set()
        difficulty = self.difficulty if side == 1 else "ultra"
        advanced = difficulty in {"master", "champion"}
        expected = {}
        for slot, actor in self._present(side):
            options = self._options(side, slot, actor)
            attacks = [a for a in options if a["kind"] == "move" and a["move"] not in SUPPORT]
            ally_ids = {id(f) for _, f in self._present(side)}

            def estimates(a):
                targets = self._targets(side, slot, a["move"], a["target"])
                return [(target, *self._damage(actor, target, a["move"], len(targets) > 1)) for target in targets]

            hits = [(a, estimates(a)) for a in attacks]

            def value(a, hits):
                score = 0
                for target, raw, acc in hits:
                    ally = id(target) in ally_ids
                    remaining = max(0, target.hp - expected.get(id(target), 0)) if advanced and not ally else target.hp
                    if not remaining:
                        continue
                    score += (-1 if ally else 1) * (
                        min(raw, remaining) / target.max_hp + (.3 if raw >= remaining else 0)
                    ) * acc / 100
                charge = WEATHER_CHARGE.get(a["move"])
                if charge and charge != self.weather and not actor.charging and not (
                    actor.mon["item"] == "Power Herb" and not actor.item_used
                ):
                    score *= .55
                return score

            scores = [(value(action, predicted), action, predicted) for action, predicted in hits]
            best_score, best, best_hits = max(scores, key=lambda row: row[0], default=(0, None, []))
            if difficulty in {"poke", "great"} and best is not None:
                floor = best_score * (.42 if difficulty == "poke" else .75)
                viable = [row for row in scores if row[0] >= max(floor, 0)] or [(best_score, best, best_hits)]
                best_score, best, best_hits = self.rng.choice(viable)
                if difficulty == "poke" and best_score > 0:
                    chosen.append(best)
                    continue
            switches = [a for a in options if a["kind"] == "switch" and a["target"] not in reserves]
            heals = [a for a in options if a.get("move") in HEAL]
            allied = [self._speed(side, f) for _, f in self._present(side)]
            enemies = [self._speed(1 - side, f) for _, f in self._present(1 - side)]
            slower = sum(allied) * len(enemies) < sum(enemies) * len(allied)
            strategy = self.foe_strategy if side == 1 else None
            field_move = "Trick Room" if slower and not self.trick_room else None
            tailwind = next((a for a in options if a.get("move") == "Tailwind"), None)
            if slower and not self.trick_room and not self.tailwind[side] and tailwind:
                field_move = "Tailwind"
            preferred = None
            if enemies and not self.trick_room:
                if strategy == "tailwind" and not self.tailwind[side] and min(allied) < max(enemies):
                    preferred = "Tailwind"
                if strategy == "trickroom" and min(f.mon["speed"] for f in self.teams[side] if f.hp) < max(enemies):
                    preferred = "Trick Room"
            if preferred:
                field_move = preferred
            setup = next((a for a in options if field_move and a.get("move") == field_move
                          and not any(c.get("move") == field_move for c in chosen)), None)
            if not setup and self.turn <= 3:
                def useful_weather(move):
                    weather = WEATHER_MOVES.get(move)
                    return weather is not None and weather != self.weather and any(
                        WEATHER_SPEED.get(f.mon["ability"]) == weather
                        or any(WEATHER_CHARGE.get(m) == weather for m in f.mon["moves"])
                        or "Weather Ball" in f.mon["moves"]
                        or weather == "sand" and "Rock" in f.mon["types"]
                        or weather == "snow" and "Ice" in f.mon["types"]
                        for f in self.teams[side] if f.hp)
                setup = next((a for a in options if useful_weather(a.get("move"))
                              and not any(c.get("move") in WEATHER_MOVES for c in chosen)), None)
            boost = next((a for a in options if any(
                actor.stages.get(stat, 0) == 0 for stat in BOOSTS.get(a.get("move"), {}) if stat in {"atk", "spa"}
            )), None)
            defensive = self._defense(side, actor, options, switches, best_score) if advanced else None
            if defensive:
                action = defensive
            elif heals and 0 < actor.hp <= actor.max_hp / 3 and best_score < 0.35:
                action = heals[0]
            elif setup and actor.hp >= actor.max_hp / 2 and self.turn <= 4 and best_score < (
                .95 if preferred and setup.get("move") == preferred else .55
            ):
                action = setup
            elif boost and actor.hp >= actor.max_hp * .8 and self.turn <= 3 and best_score < (
                .65 if strategy == "setup" else .42
            ):
                action = boost
            elif switches and best is not None and best_score <= 0 and actor.entered != self.turn:
                action = switches[0]
            else:
                action = best or next((a for a in options if a["kind"] != "switch"), options[0])
            if action["kind"] == "switch":
                reserves.add(action["target"])
            if advanced and action is best:
                for target, raw, acc in best_hits:
                    if id(target) not in ally_ids:
                        expected[id(target)] = expected.get(id(target), 0) + raw * acc / 100
            chosen.append(action)
        return chosen

    def _defense(self, side, actor, options, switches, attack_score):
        if attack_score >= .75 or not switches and self.difficulty != "champion":
            return None
        enemies = [f for _, f in self._present(1 - side)]
        forecasts = [(f, self.engine.default_set(f.mon["id"], self.fmt)["moves"]) for f in enemies]

        def pressure(target):
            incoming = []
            for enemy, moves in forecasts:
                hits = (self._damage(enemy, target, m, False) for m in moves if m in self.engine.M)
                incoming.append(max((raw * acc / 100 for raw, acc in hits), default=0))
            return sum(incoming) / max(1, target.hp)

        danger = pressure(actor)
        if danger < .85:
            return None
        if switches and actor.entered != self.turn:
            best = min(switches, key=lambda a: pressure(self.teams[side][a["target"]]))
            incoming = self.teams[side][best["target"]]
            if pressure(incoming) < min(.62, danger * .5) and attack_score < .55:
                return best
        if self.difficulty == "champion" and len(self._present(side)) == 2 and not actor.protect_chain and attack_score < .52:
            return next((a for a in options if a.get("move") in PROTECT), None)
        return None

    def _support(self, side: int, actor: Fighter, move: str):
        if move in PROTECT:
            actor.protected = self.rng.random() < 1 / 3 ** actor.protect_chain
            actor.protect_chain += 1
            if not actor.protected:
                self._event("방어에 실패했습니다.")
        elif move in HEAL:
            before = actor.hp
            actor.hp = min(actor.max_hp, actor.hp + actor.max_hp // 2)
            if actor.hp > before:
                self._event(f"{actor.name}의 HP가 {actor.hp - before} 회복됐다!")
        elif move in BOOSTS:
            for stat, change in BOOSTS[move].items():
                previous = actor.stages.get(stat, 0)
                actor.stages[stat] = max(-6, min(6, previous + change))
                if stat in {"atk", "spa"} and actor.stages[stat] > previous:
                    self.activated[side].add("setup")
        elif move == "Tailwind":
            self.tailwind[side] = 4
            self.activated[side].add("tailwind")
            self._event(f"{'상대' if side else '내 팀'}의 뒤에서 순풍이 불기 시작했다!")
        elif move == "Trick Room":
            self.trick_room = 0 if self.trick_room else 5
            if self.trick_room:
                self.activated[side].add("trickroom")
            self._event("행동 순서가 뒤집혔다!" if self.trick_room else "트릭룸이 풀렸다!")
        elif move in WEATHER_MOVES:
            self._set_weather(side, WEATHER_MOVES[move], actor)

    def _attack(self, side: int, slot: int, actor: Fighter, move: str, target_slot: int | None):
        if actor.charging:
            actor.charging = None
        elif move in WEATHER_CHARGE:
            if move == "Electro Shot":
                actor.stages["spa"] = min(6, actor.stages.get("spa", 0) + 1)
            if self.weather != WEATHER_CHARGE[move]:
                if actor.mon["item"] == "Power Herb" and not actor.item_used:
                    actor.item_used = True
                else:
                    actor.charging = move, target_slot
                    self._event(f"{actor.name}의 {self._move_name(move)} 준비")
                    return
        targets = self._targets(side, slot, move, target_slot)
        did_hit = False
        for target in targets:
            if target.protected:
                self._event(f"{target.name}의 방어에 막혔습니다.")
                continue
            raw, acc = self._damage(actor, target, move, len(targets) > 1)
            if self.rng.random() * 100 >= acc:
                self._event(f"{target.name}에게 빗나갔습니다.")
                continue
            if raw <= 0:
                self._event(f"{target.name}에게 효과가 없습니다.")
                continue
            did_hit = True
            amount = min(target.hp, max(1, round(raw * self.rng.uniform(.85, 1) / .925)))
            if target.hp == target.max_hp and amount == target.hp and (
                target.mon["ability"] == "Sturdy" or target.mon["item"] == "Focus Sash" and not target.item_used
            ):
                if target.mon["item"] == "Focus Sash" and target.mon["ability"] != "Sturdy":
                    target.item_used = True
                amount -= 1
            target.hp -= amount
            target.taken += amount
            opponent = any(target is foe for foe in self.teams[1 - side])
            if opponent:
                actor.dealt += amount
                if not target.hp:
                    actor.kos += 1
                    actor.victims[target.mon["id"]] += 1
            target.flinched |= move == "Fake Out"
            self._event(f"{target.name} HP −{amount}" + (" · 기절" if not target.hp else ""),
                        "damage", target=target.name, amount=amount, fainted=not target.hp)
            if target.hp and target.hp <= target.max_hp // 2 and target.mon["item"] == "Sitrus Berry" and not target.item_used:
                target.item_used = True
                target.hp = min(target.max_hp, target.hp + max(1, target.max_hp // 4))
        if did_hit and (move == "Struggle" or actor.mon["item"] == "Life Orb"):
            divisor = 4 if move == "Struggle" else 10
            actor.hp = max(0, actor.hp - max(1, actor.max_hp // divisor))
        actor.recharge = did_hit and bool(self.engine.M.get(move, {}).get("recharge"))

    def advance(self, my_actions: list[dict] | None = None):
        if self.replacement_slots():
            raise ValueError("기절한 자리의 교체 포켓몬을 먼저 골라 주세요.")
        if self.manual and my_actions is None:
            raise ValueError("필드에 있는 포켓몬마다 명령을 골라 주세요.")
        mine = self._auto(0) if my_actions is None else my_actions
        active = dict(self._present(0))
        by_slot = {a["slot"]: a for a in mine}
        if len(mine) != len(active) or by_slot.keys() != active.keys():
            raise ValueError("active Pokémon each need one action")
        switches = [a["target"] for a in mine if a["kind"] == "switch"]
        if len(set(switches)) != len(switches):
            raise ValueError("the same reserve cannot switch in twice")
        for slot, a in by_slot.items():
            if not any(self._key(o) == self._key(a) for o in self._options(0, slot, active[slot])):
                raise ValueError("invalid battle action")
        actions = []
        for side, side_actions in enumerate((mine, self._auto(1))):
            present = dict(self._present(side))
            for a in side_actions:
                actor = present[a["slot"]]
                priority = 6 if a["kind"] == "switch" else self.engine.M.get(a.get("move"), {}).get("priority", 0)
                speed = self._speed(side, actor) * (-1 if self.trick_room and a["kind"] != "switch" else 1)
                actions.append((priority, speed, self.rng.random(), side, actor, a))
        for _, _, _, side, actor, action in sorted(actions, key=lambda a: a[:3], reverse=True):
            slot, kind = action["slot"], action["kind"]
            if not actor.hp or actor.flinched:
                if actor.hp and actor.flinched:
                    self._event(f"{actor.name}은(는) 풀죽어서 움직이지 못했다!")
                continue
            move, target = action.get("move"), action.get("target")
            if move not in PROTECT:
                actor.protect_chain = 0
            if kind == "switch":
                self._switch(side, slot, target)
            elif kind == "wait":
                actor.recharge = False
                self._event(f"{actor.name} 재충전")
            else:
                self._event(f"{'상대 ' if side else ''}{actor.name}의 {self._move_name(move)}!",
                            "move", side=side)
                if actor.mon["item"] in CHOICE and move != "Struggle":
                    actor.choice = move
                if move in SUPPORT:
                    self._support(side, actor, move)
                else:
                    self._attack(side, slot, actor, move, target)
        for side in range(2):
            for slot, actor in self._present(side):
                if self.weather == "sand" and not set(actor.mon["types"]) & {"Rock", "Ground", "Steel"}:
                    actor.hp = max(0, actor.hp - max(1, actor.max_hp // 16))
                if actor.mon["item"] == "Leftovers":
                    if actor.hp:
                        actor.hp = min(actor.max_hp, actor.hp + max(1, actor.max_hp // 16))
                actor.protected = actor.flinched = False
            self.tailwind[side] = max(0, self.tailwind[side] - 1)
        self.trick_room = max(0, self.trick_room - 1)
        self.psychic_terrain = max(0, self.psychic_terrain - 1)
        self.weather_turns = max(0, self.weather_turns - 1)
        if not self.weather_turns:
            self.weather = ""
        for side in range(2):
            for slot, index in enumerate(self.active[side]):
                if index is not None and not self.teams[side][index].hp:
                    self.active[side][slot] = None
        living = [any(f.hp for f in team) for team in self.teams]
        if not all(living):
            self.winner = ("win" if living[0] else "loss") if any(living) else "draw"
        elif self.turn >= MAX_TURNS:
            self.winner = "draw"
        if not self.winner and not self.replacement_slots():
            self._fill_vacancies(0, after_turn=True)
            self._fill_vacancies(1, after_turn=True)
        self.turn += 1
        self.updated = monotonic()

    def replacement_slots(self):
        if self.winner or not self.manual:
            return []
        return [i for i, active in enumerate(self.active[0]) if active is None] if self._bench(0) else []

    def replace(self, turn, choices):
        if turn < self.turn or turn == self.replacement_turn:
            return
        slots, bench = self.replacement_slots(), self._bench(0)
        required = min(len(slots), len(bench))
        targets = set(choices.values())
        if turn != self.turn or not required or len(choices) != required or len(targets) != required or (
            not choices.keys() <= set(slots) or not targets <= set(bench)
        ):
            raise ValueError("빈 자리에 서로 다른 대기 포켓몬을 골라 주세요.")
        for slot, target in sorted(choices.items()):
            self._switch(0, slot, target)
        self._fill_vacancies(1, after_turn=False)
        self.replacement_turn = turn
        self.updated = monotonic()

    def _fill_vacancies(self, side, *, after_turn):
        vacancies = (i for i, active in enumerate(self.active[side]) if active is None)
        for slot, target in zip(vacancies, self._bench(side)):
            self._switch(side, slot, target, replacement=after_turn)

    @staticmethod
    def _key(action: dict) -> tuple:
        return tuple(action.get(k) for k in ("kind", "move", "target"))

    def _switch(self, side: int, slot: int, incoming: int, *, replacement: bool = False):
        outgoing = self.active[side][slot]
        if outgoing is not None:
            self.teams[side][outgoing].withdraw()
        self.active[side][slot] = incoming
        if side == 1:
            self.revealed.add(incoming)
        fighter = self.teams[side][incoming]
        fighter.entered = self.turn + 1 if replacement else self.turn
        self._event(f"{'상대 ' if side else ''}{fighter.name} 등장", "entry")
        self._on_entry(side, fighter)

    def view(self, battle_id: str) -> dict:
        def member(f):
            return {**{k: f.mon[k] for k in ("id", "name", "ko", "sprite", "types")},
                    "hp": f.hp, "maxHp": f.max_hp, "dealt": f.dealt, "taken": f.taken, "kos": f.kos}

        field = [
            (WEATHER_LABELS.get(self.weather), self.weather_turns), ("사이코필드", self.psychic_terrain),
            ("트릭룸", self.trick_room), ("내 순풍", self.tailwind[0]), ("상대 순풍", self.tailwind[1]),
        ]
        slots = self.replacement_slots()
        return {"id": battle_id, "turn": self.turn, "seed": self.seed, "winner": self.winner,
                "difficulty": self.difficulty,
                "replacement": {"slots": slots, "bench": self._bench(0)} if slots else None,
                "field": [f"{name} {turns}턴" for name, turns in field if turns],
                "teams": [[member(f) if side == 0 or not self.manual or self.winner or i in self.revealed else None
                           for i, f in enumerate(team)] for side, team in enumerate(self.teams)],
                "active": [side.copy() for side in self.active],
                "options": [] if self.winner or slots else [
                    {"slot": slot, "options": self._options(0, slot, f)} for slot, f in self._present(0)
                ], "log": self.log.copy() if self.winner else self.log[-100:], **self.context}


class Sessions:
    def __init__(self):
        self.battles: OrderedDict[str, Battle] = OrderedDict()
        self.lock = Lock()

    def start(self, battle: Battle) -> dict:
        with self.lock:
            key = uuid4().hex
            self.battles[key] = battle
            while len(self.battles) > 128:
                self.battles.popitem(last=False)
            return battle.view(key)

    def advance(self, key: str, turn: int, actions: list[dict] | None) -> dict:
        with self.lock:
            battle = self._session(key)
            if turn > battle.turn:
                raise ValueError("invalid turn")
            if not battle.winner and turn == battle.turn:
                battle.advance(actions)
            self.battles.move_to_end(key)
            return battle.view(key)

    def replace(self, key: str, turn: int, choices: dict[int, int]) -> dict:
        with self.lock:
            battle = self._session(key)
            battle.replace(turn, choices)
            self.battles.move_to_end(key)
            return battle.view(key)

    def _session(self, key):
        battle = self.battles.get(key)
        if not battle or monotonic() - battle.updated > 3600:
            self.battles.pop(key, None)
            raise KeyError(key)
        return battle
