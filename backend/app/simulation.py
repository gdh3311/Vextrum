"""Local, approximate singles/doubles practice and repeatable CPU simulations."""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import replace, dataclass, field
from random import Random
from threading import Lock
from time import monotonic
from typing import Literal
from uuid import uuid4

from . import mechanics as mx
from .engine import ATE, Engine, MOLD, SPREAD_TARGETS
from .typechart import type_multiplier

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
REDIRECT = {"Follow Me", "Rage Powder"}
PRIORITY_BLOCK = {"Armor Tail", "Dazzling", "Queenly Majesty"}
SPEED_DROP = {"Icy Wind", "Electroweb", "Rock Tomb", "Bulldoze", "Low Sweep"}
PIVOT = {"U-turn", "Volt Switch", "Flip Turn", "Parting Shot", "Chilly Reception"}
REACTIVE = {"Sucker Punch", "Thunderclap", "Upper Hand"}
UNTRACEABLE = {"Trace", "Imposter", "Illusion", "Zen Mode", "Stance Change", "Disguise", "Multitype",
               "Power Construct", "Schooling", "Comatose", "Shields Down", "As One (Glastrier)",
               "As One (Spectrier)", "Commander", "Protosynthesis", "Quark Drive"}
NO_WEATHER = {"Cloud Nine", "Air Lock"}
DRAIN = {"Drain Punch", "Giga Drain", "Horn Leech", "Leech Life", "Draining Kiss", "Dream Eater", "Mega Drain",
         "Absorb", "Oblivion Wing", "Parabolic Charge", "Bitter Blade"}
TARGETED_SUPPORT = {"Taunt", "Parting Shot"} | set(mx.STATUS_MOVES) | set(mx.TARGET_DEBUFFS) | {
    "Encore", "Leech Seed", "Pain Split", "Yawn", "Strength Sap"}
TERRAIN = {"Psychic Surge": "psychic", "Grassy Surge": "grassy", "Electric Surge": "electric", "Misty Surge": "misty"}
TERRAIN_MOVES = {f"{kind.title()} Terrain": kind for kind in TERRAIN.values()}
SEEDS = {"Grassy Seed": ("grassy", "def"), "Electric Seed": ("electric", "def"),
         "Psychic Seed": ("psychic", "spd"), "Misty Seed": ("misty", "spd")}
TERRAIN_LABELS = {"psychic": "사이코필드", "grassy": "그래스필드", "electric": "일렉트릭필드", "misty": "미스트필드"}
ABSORB_HEAL = {"Water Absorb": "Water", "Dry Skin": "Water", "Volt Absorb": "Electric", "Earth Eater": "Ground"}
ABSORB_BOOST = {"Storm Drain": ("Water", "spa", 1), "Lightning Rod": ("Electric", "spa", 1),
                "Motor Drive": ("Electric", "spe", 1), "Sap Sipper": ("Grass", "atk", 1),
                "Well-Baked Body": ("Fire", "def", 2)}
SUPPORT = PROTECT | HEAL | BOOSTS.keys() | REDIRECT | TARGETED_SUPPORT | TERRAIN_MOVES.keys() | {
    "Tailwind", "Trick Room", "Wide Guard", "Quick Guard", "Helping Hand", "Chilly Reception",
}
WEATHER = {"Drought": "sun", "Drizzle": "rain", "Sand Stream": "sand", "Snow Warning": "snow"}
WEATHER_MOVES = {"Sunny Day": "sun", "Rain Dance": "rain", "Sandstorm": "sand", "Snowscape": "snow"}
WEATHER_LABELS = {"sun": "쾌청", "rain": "비", "sand": "모래바람", "snow": "눈"}
WEATHER_SPEED = {"Chlorophyll": "sun", "Swift Swim": "rain", "Sand Rush": "sand", "Slush Rush": "snow"}
WEATHER_CHARGE = {"Solar Beam": "sun", "Solar Blade": "sun", "Electro Shot": "rain"}
LOW_HP_BOOST = {"Blaze": "Fire", "Torrent": "Water", "Overgrow": "Grass", "Swarm": "Bug"}
SUPPORT |= WEATHER_MOVES.keys()
SUPPORT |= mx.NEW_SUPPORT

# Known gaps from the simulator audit. Coverage for other effects remains approximate.
UNIMPLEMENTED_ITEMS = {"Eject Button", "Quick Claw", "Iron Ball", "Leppa Berry", "Red Card", "Big Root",
                       "Shell Bell", "Metronome"}
UNIMPLEMENTED_ABILITIES = {"Cursed Body", "Flower Veil", "Illusion", "Moody",
                           "Frisk", "Pickpocket", "Damp", "Telepathy", "Snow Cloak", "Magician", "Bulletproof"}
RULE_UNVERIFIED_ABILITIES = {"Emergency Exit", "Wimp Out"}
UNIMPLEMENTED_MOVES = {"Curse"}  # Ghost Curse currently applies the cost without its residual effect.


def move_supported(e, move):
    move = e.move_names.get(move, move)
    data = e.M.get(move)
    return bool(data and not data.get("unknown") and move not in UNIMPLEMENTED_MOVES
                and (move in SUPPORT or data["power"] and not data.get("selfdestruct")))


def unsupported(e, fmt, entry):
    s = {**e.default_set(entry["id"], fmt), **entry}
    moves = s["moves"] if s["moves"] is not None else e.default_set(s["id"], fmt)["moves"]
    problems = [{"kind": "move", "name": move, "id": e.move_ids.get(move, move)}
                for move in moves if not move_supported(e, move)]
    form = e.find_mega(e.P[s["id"]], name=s["mega"]) if s["mega"] else None
    for ability in dict.fromkeys((s["ability"] or e.default_set(s["id"], fmt)["ability"],
                                  form["abilities"][0] if form else None)):
        if ability in UNIMPLEMENTED_ABILITIES:
            problems.append({"kind": "ability", "name": ability})
    if s["item"] in UNIMPLEMENTED_ITEMS:
        problems.append({"kind": "item", "name": s["item"]})
    return [{"pokemon": s["id"], "status": "UNSIMULATABLE", **p} for p in problems]


def rules_report(e, fmt, sets):
    issues = [issue for s in sets for issue in unsupported(e, fmt, s)]
    for s in sets:
        base = e.default_set(s["id"], fmt)
        ability = s.get("ability") or base["ability"]
        if ability in RULE_UNVERIFIED_ABILITIES:
            issues.append({"pokemon": s["id"], "kind": "ability", "name": ability, "status": "RULE_UNVERIFIED"})
    return {"status": "UNSIMULATABLE" if any(r["status"] == "UNSIMULATABLE" for r in issues) else "RULE_UNVERIFIED",
            "issues": issues, "rulesVersion": mx.RULES_CONTRACT}
TARGETED_SUPPORT -= {"Nuzzle"}
STAT_LABELS = {"atk": "공격", "def": "방어", "spa": "특공", "spd": "특방", "spe": "스피드"}
THAW_MOVES = {"Flare Blitz", "Scald", "Sacred Fire", "Scorching Sands", "Flame Wheel", "Pyro Ball", "Fusion Flare",
              "Steam Eruption", "Matcha Gotcha"}


def _stage(level: int) -> float:
    return (2 + max(0, level)) / (2 - min(0, level))


CPU_STYLES = {
    # ko: 쓰러뜨리기 가산, focus: 같은 목표 집중, counter: 승리 조건 요원 우선 공격 가산, setup: 전개(순풍·트릭룸·벽·랭크업) 배율,
    # protect: 방어 허용, danger: 몸을 사리는 위험선(낮을수록 잘 피함), pivot: 교체·퇴장기 선호선, heal: 회복 시작 체력
    "balanced": {"ko": .3, "focus": False, "counter": 0., "setup": 1., "protect": False, "danger": .85, "pivot": 0., "heal": 1 / 3},
    "aggressive": {"ko": .55, "focus": True, "counter": 0., "setup": .6, "protect": False, "danger": 1.3, "pivot": 0., "heal": .2},
    "defensive": {"ko": .25, "focus": False, "counter": 0., "setup": .9, "protect": True, "danger": .6, "pivot": .1, "heal": .5,
                  "caution": .3},
    "setup": {"ko": .3, "focus": False, "counter": 0., "setup": 1.6, "protect": True, "danger": .85, "pivot": 0., "heal": 1 / 3},
    "pivot": {"ko": .3, "focus": False, "counter": 0., "setup": .9, "protect": False, "danger": .7, "pivot": .3, "heal": 1 / 3},
    "counter": {"ko": .35, "focus": True, "counter": .35, "setup": 1., "protect": False, "danger": .85, "pivot": 0., "heal": 1 / 3},
}
STYLE_LABELS = {"balanced": "균형형", "aggressive": "공격형", "defensive": "수비형", "setup": "전개형",
                "pivot": "피벗형", "counter": "카운터형"}


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
    known_moves: set[str] = field(default_factory=set)
    taunt: int = 0
    helped: bool = False
    unburden: bool = False
    ability_revealed: bool = False
    flash_fire: bool = False
    status: str = ""  # brn par slp psn tox frz
    status_turns: int = 0
    toxic: int = 0
    sub: int = 0
    seeded: bool = False
    encore: int = 0
    encore_move: str | None = None
    last_move: str | None = None
    failed_move_turn: int = 0
    yawn: int = 0
    destiny: bool = False
    disguise: bool = True
    mega_shown: bool = False
    mega_form: dict | None = None  # 메가진화하면 바뀔 모습 (메가스톤을 든 메가 후보만)

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
        self.taunt = 0
        self.helped = False
        self.unburden = False
        self.flash_fire = False
        self.recharge = self.protected = self.flinched = False
        self.protect_chain = 0
        if self.status == "tox":
            self.toxic = 1  # 챔피언스: 교체하면 맹독 카운트가 1/16로 돌아간다
        self.sub = self.encore = self.yawn = 0
        self.seeded = self.destiny = False
        self.encore_move = self.last_move = None
        self.failed_move_turn = 0


class Battle:
    def __init__(self, engine: Engine, fmt: str, mine: list[dict], foe: list[dict], seed: int, *,
                 log: bool = True, context: dict | None = None, foe_strategy: str | None = None,
                 difficulty: Difficulty = "ultra", manual: bool = False, cpu_style: str = "balanced"):
        self.engine, self.fmt, self.seed = engine, fmt, seed
        self.rng = Random(seed)
        self.width = 2 if fmt == "Doubles" else 1
        self.teams = [self._fighters(mine), self._fighters(foe)]
        self.mega_left = [True, True]  # 레귤레이션 MC: 배틀당 메가진화 1회
        self.active = [[i if i < len(team) else None for i in range(self.width)] for team in self.teams]
        self.turn = 1
        self.winner: str | None = None
        self.tailwind = [0, 0]
        self.trick_room = 0
        self.weather = ""
        self.weather_turns = 0
        self.terrain = ""
        self.terrain_turns = 0
        self.redirect = [None, None]
        self.wide_guard = [False, False]
        self.quick_guard = [False, False]
        self.screens = [{}, {}]  # reflect / light / veil -> 남은 턴
        self.hazards = [{}, {}]  # rocks / spikes / tspikes / web
        self.wish = [{}, {}]  # slot -> (남은 턴, 회복량)
        self.activated = [set(), set()]
        # 패배 원인 태깅용 사건 기록 (편별): 선제기·광역기 KO, 행동 전 KO, 명중 낮은 기술 빗나감, 첫 기절
        self.trace = [dict(priority_ko=0, spread_ko=0, spread_taken=0, taken=0, ko_before_move=0, low_acc_miss=0,
                           setup_moves=0) for _ in range(2)]
        self.first_faint = None
        self.opening = []  # 내 편(0)의 첫 턴 행동
        self.opening_actions = []
        self.executed_attacks = Counter()  # (공격자, 기술, 대상) → 실제 시도·명중·KO
        self.log: list[dict] = []
        self.keep_log = log
        self.context = context or {}
        self.foe_strategy = foe_strategy
        # 상대 CPU 플레이 스타일 (랭크=판단 깊이와 별개): balanced·aggressive·defensive·setup·pivot·counter
        self.cpu_style = cpu_style if cpu_style in CPU_STYLES else "balanced"
        self.difficulty = difficulty
        self.manual = manual
        self.replacement_turn: int | None = None
        self._pivot_slot: int | None = None
        self._replacement_phase = 0
        self._pending = []
        self.seen = [{i for i in row if i is not None} for row in self.active]
        self.updated = monotonic()
        leads = [(side, f) for side in range(2) for _, f in self._present(side)]
        if manual:
            for side, fighter in leads:
                self._event(f"{'상대' if side else '내 팀'}의 {fighter.name} 등장", "entry", ref=self._ref(fighter))
        for side, fighter in sorted(leads, key=lambda lead: lead[1].mon["speed"], reverse=True):
            self._on_entry(side, fighter)

    def _fighters(self, sets: list[dict]) -> list[Fighter]:
        """메가 후보는 기본 폼으로 시작한다 (기본 폼 특성이 등장 시 발동). 진화는 _mega_turn 에서."""
        fighters = []
        for s in sets:
            s = {**self.engine.default_set(s["id"], self.fmt), **s}
            mega = self.engine.resolve(s, self.fmt) if s.get("mega") else None
            if mega is not None and not mega["mega"]:
                mega = None
            mon = self.engine.resolve({**s, "mega": None}, self.fmt) if mega else self.engine.resolve(s, self.fmt)
            fighters.append(Fighter(mon, mon["stats"]["hp"], mega_form=mega))
        return fighters

    @staticmethod
    def _mega_gain(f: Fighter) -> int:
        return sum(f.mega_form["stats"].values()) - sum(f.mon["stats"].values())

    def _mega_turn(self, player_slot=None):
        """Apply a manual choice or the automatic policy once per side."""
        for side in range(2):
            if not self.mega_left[side]:
                continue
            ready = [f for slot, f in self._present(side) if f.mega_form and f.hp
                     and (side != 0 or not self.manual or slot == player_slot)]
            if not ready:
                continue
            fighter = max(ready, key=self._mega_gain)
            ratio = fighter.hp / fighter.max_hp
            fighter.mon = fighter.mega_form
            fighter.hp = max(1, round(ratio * fighter.max_hp))
            fighter.mega_form = None
            fighter.mega_shown = True
            self.mega_left[side] = False
            self._seen_cache = {}
            self._event(f"{fighter.name}(으)로 메가진화했다!", "mega", ref=self._ref(fighter))
            self._entry_ability(side, fighter)

    def _event(self, message: str, kind: str = "detail", **fields):
        if self.keep_log:
            # 화면이 한 줄씩 재생할 수 있도록 이 시점의 HP와 필드 배치를 함께 남긴다.
            self.log.append({"turn": self.turn, "text": message, "kind": kind, **fields,
                             "hp": [[f.hp for f in team] for team in self.teams],
                             "active": [row.copy() for row in self.active]})

    def _ref(self, fighter) -> list[int] | None:
        """[편, 팀 안 번호] — 화면 애니메이션용"""
        for side, team in enumerate(self.teams):
            for i, f in enumerate(team):
                if f is fighter:
                    return [side, i]
        return None

    def _bench(self, side: int) -> list[int]:
        return [i for i, f in enumerate(self.teams[side]) if f.hp > 0 and i not in self.active[side]]

    def _present(self, side: int) -> list[tuple[int, Fighter]]:
        return [(slot, self.teams[side][i]) for slot, i in enumerate(self.active[side])
                if i is not None and self.teams[side][i].hp > 0]

    def _speed(self, side: int, f: Fighter) -> float:
        wind = 2 if self.tailwind[side] else 1
        weather = 2 if WEATHER_SPEED.get(f.mon["ability"]) == self._wx else 1
        unburden = 2 if f.unburden else 1
        para = .5 if f.status == "par" and f.mon["ability"] != "Quick Feet" else 1.5 if (
            f.status and f.mon["ability"] == "Quick Feet") else 1
        return f.mon["speed"] * _stage(f.stages.get("spe", 0)) * wind * weather * unburden * para

    @staticmethod
    def _grounded(f: Fighter) -> bool:
        return ("Flying" not in f.mon["types"] and f.mon["ability"] != "Levitate"
                and (f.mon["item"] != "Air Balloon" or f.item_used))

    def _unnerved(self, fighter) -> bool:
        """긴장감: 상대 필드에 있으면 열매를 먹지 못한다."""
        side = self._side(fighter)
        return any(f.mon["ability"] in {"Unnerve", "As One (Glastrier)", "As One (Spectrier)"}
                   for _, f in self._present(1 - side))

    @property
    def _wx(self) -> str:
        """효과로서의 날씨: 필드에 구름보호·에어록이 있으면 없는 것으로 본다."""
        if self.weather and any(f.mon["ability"] in NO_WEATHER for side in range(2) for _, f in self._present(side)):
            return ""
        return self.weather

    def _ability(self, fighter):
        fighter.ability_revealed = True
        ability = fighter.mon["ability"]
        label = self.engine.d["abilities"].get(ability, {}).get("ko") or ability
        self._event(f"{fighter.name}의 특성 · {label}", "field")

    def _on_entry(self, side: int, fighter: Fighter):
        self._entry_ability(side, fighter)

    def _entry_ability(self, side: int, fighter: Fighter):
        """등장(또는 메가진화) 때 발동하는 특성."""
        ability = fighter.mon["ability"]
        if ability == "Trace":
            traceable = [f for _, f in self._present(1 - side) if f.mon["ability"] not in UNTRACEABLE]
            if traceable:
                copied = self.rng.choice(traceable).mon["ability"]
                fighter.mon = {**fighter.mon, "ability": copied}
                self._ability(fighter)
                ability = copied
        if ability == "Intimidate":
            self._ability(fighter)
            for _, target in self._present(1 - side):
                if target.mon["ability"] == "Guard Dog":
                    self._change_stages(target, {"atk": 1})
                    self._ability(target)
                elif target.mon["ability"] not in {"Inner Focus", "Own Tempo", "Oblivious", "Scrappy"}:
                    self._lower(target, {"atk": -1}, fighter)
        if ability == "Hospitality":
            for _, ally in self._present(side):
                if ally is not fighter and self._heal(ally, ally.max_hp // 4):
                    self._ability(fighter)
        if ability in WEATHER:
            self._ability(fighter)
            self._set_weather(side, WEATHER[ability], fighter)
        if ability in TERRAIN:
            self._ability(fighter)
            self._set_terrain(side, TERRAIN[ability], fighter)
        elif self.terrain:
            self._seed(fighter)

    def _change_stages(self, fighter, changes, *, ignore_ability=False):
        ability = None if ignore_ability else fighter.mon["ability"]
        changed = {}
        for stat, delta in changes.items():
            old = fighter.stages.get(stat, 0)
            delta = -delta if ability == "Contrary" else delta * 2 if ability == "Simple" else delta
            new = max(-6, min(6, old + delta))
            if new != old:
                fighter.stages[stat] = new
                changed[stat] = new - old
        if (fighter.mon["item"] == "White Herb" and not fighter.item_used
                and any(v < 0 for v in fighter.stages.values())):
            self._consume(fighter)
            for stat, v in list(fighter.stages.items()):
                if v < 0:
                    fighter.stages[stat] = 0
            self._event(f"{fighter.name}은(는) 하양허브로 능력 변화를 원래대로 되돌렸다!", "field")
        return changed

    def _lower(self, fighter, changes, source, *, reflect=True):
        ability = None if source.mon["ability"] in MOLD else fighter.mon["ability"]
        if fighter.mon["item"] == "Clear Amulet" or ability in {"Clear Body", "White Smoke", "Full Metal Body"}:
            return False
        if ability == "Mirror Armor" and reflect:
            self._ability(fighter)
            return self._lower(source, changes, fighter, reflect=False)
        changes = {stat: delta for stat, delta in changes.items() if not (stat == "atk" and ability == "Hyper Cutter")}
        changed = self._change_stages(fighter, changes, ignore_ability=ability is None)
        if changed and ability in {"Contrary", "Simple"}:
            self._ability(fighter)
        if ability in {"Defiant", "Competitive"} and any(delta < 0 for delta in changed.values()) and (
            any(fighter is f for f in self.teams[0]) != any(source is f for f in self.teams[0])
        ):
            boost = "atk" if ability == "Defiant" else "spa"
            self._change_stages(fighter, {boost: 2})
            self._ability(fighter)
        self._stage_event(fighter, changed)
        return bool(changed)

    def _stage_event(self, fighter, changed):
        if changed:
            detail = " · ".join(f"{STAT_LABELS.get(stat, stat)} {('↑' if delta > 0 else '↓') * min(3, abs(delta))}"
                                for stat, delta in changed.items())
            self._event(f"{fighter.name} · {detail}", "stat", ref=self._ref(fighter), stages=changed)

    def _side(self, fighter) -> int:
        return 0 if any(f is fighter for f in self.teams[0]) else 1

    def _hurt(self, fighter, amount, message, *, kind="residual"):
        """기술 외의 데미지 (날씨, 상태 이상, 반동, 설치 기술). HP 바가 움직이도록 이벤트를 남긴다."""
        if not fighter.hp or amount <= 0:
            return 0
        amount = min(fighter.hp, max(1, int(amount)))
        fighter.hp -= amount
        fighter.taken += amount
        self._event(f"{fighter.name}{message}" + (" · 기절" if not fighter.hp else ""), kind, ref=self._ref(fighter),
                    amount=amount, pct=round(100 * amount / fighter.max_hp), fainted=not fighter.hp)
        return amount

    def _can_status(self, target, status, source=None, move=None) -> bool:
        if not target.hp or target.status:
            return False
        mold = source is not None and source.mon["ability"] in MOLD
        ability = None if mold else target.mon["ability"]
        corrosion = source is not None and source.mon["ability"] == "Corrosion" and status in {"psn", "tox"}
        if not corrosion and set(target.mon["types"]) & mx.STATUS_IMMUNE_TYPES.get(status, set()):
            return False
        if ability in mx.ALL_STATUS_IMMUNE or ability in mx.STATUS_IMMUNE_ABILITIES.get(status, set()):
            return False
        if ability == "Leaf Guard" and self._wx == "sun":
            return False
        if self._grounded(target) and (self.terrain == "misty" or self.terrain == "electric" and status == "slp"):
            return False
        if status == "frz" and self._wx == "sun":
            return False
        if move is not None:
            if move in mx.POWDER and ("Grass" in target.mon["types"] or ability == "Overcoat"
                                      or target.mon["item"] == "Safety Goggles"):
                return False
            if move == "Thunder Wave" and type_multiplier("Electric", target.mon["types"], ability) == 0:
                return False
            if target.sub and move not in mx.SOUND and source is not target:
                return False
        return True

    def _inflict(self, target, status, source=None, move=None) -> bool:
        if not self._can_status(target, status, source, move):
            return False
        target.status, target.status_turns = status, 0
        target.toxic = 1 if status == "tox" else 0
        target.yawn = 0
        self._event(f"{target.name}은(는) {mx.STATUS_LABELS[status]} 상태가 되었다!", "status",
                    ref=self._ref(target), status=status)
        if not self._unnerved(target) and (target.mon["item"] == "Lum Berry" and not target.item_used or (
                status == "slp" and target.mon["item"] == "Chesto Berry" and not target.item_used)):
            self._consume(target)
            self._cure(target, "리샘열매로 " if target.mon["item"] == "Lum Berry" else "잠깨는열매로 ")
        elif source is not None and target.mon["ability"] == "Synchronize" and status in {"brn", "par", "psn", "tox"}:
            self._ability(target)
            self._inflict(source, status)
        return True

    def _cure(self, fighter, prefix=""):
        if fighter.status:
            label = mx.STATUS_LABELS[fighter.status]
            fighter.status, fighter.status_turns, fighter.toxic = "", 0, 0
            self._event(f"{fighter.name}의 {prefix}{label} 상태가 나았다!", "status", ref=self._ref(fighter), status="")

    def _can_act(self, actor, move) -> bool:
        """상태 이상 때문에 행동하지 못하는지 확인한다 (챔피언스 규칙)."""
        if actor.status == "slp":
            actor.status_turns += 2 if actor.mon["ability"] == "Early Bird" else 1
            if actor.status_turns >= 3 or actor.status_turns == 2 and self.rng.random() < 1 / 3:
                self._cure(actor)
                return True
            self._event(f"{actor.name}은(는) 쿨쿨 잠들어 있다.", "status", ref=self._ref(actor), status="slp")
            return False
        if actor.status == "frz":
            actor.status_turns += 1
            if move in THAW_MOVES or actor.status_turns >= 3 or self.rng.random() < .25:
                self._cure(actor)
                return True
            self._event(f"{actor.name}은(는) 얼어붙어서 움직일 수 없다!", "status", ref=self._ref(actor), status="frz")
            return False
        if actor.status == "par" and self.rng.random() < .125:
            self._event(f"{actor.name}은(는) 몸이 저려서 움직일 수 없다!", "status", ref=self._ref(actor), status="par")
            return False
        return True

    def _screen(self, actor, target, move) -> float:
        side = self._side(target)
        screens = self.screens[side]
        if not screens or actor.mon["ability"] == "Infiltrator" or side == self._side(actor):
            return 1.
        physical = self.engine.M.get(move, {}).get("category") == "Physical"
        if screens.get("veil") or screens.get("reflect" if physical else "light"):
            return 2732 / 4096 if self.width == 2 else .5
        return 1.

    def _heal(self, fighter, amount):
        if fighter.hp:
            before = fighter.hp
            fighter.hp = min(fighter.max_hp, before + max(1, amount))
            return fighter.hp - before
        return 0

    def _mental_herb(self, fighter):
        if fighter.mon["item"] == "Mental Herb" and not fighter.item_used:
            self._consume(fighter)
            fighter.taunt = fighter.encore = 0
            fighter.encore_move = None
            self._event(f"{fighter.name}은(는) 멘탈허브로 정신을 되찾았다!", "field")

    def _consume(self, fighter):
        fighter.item_used = True
        if fighter.mon["ability"] == "Unburden":
            fighter.unburden = True
            self._ability(fighter)

    def _set_terrain(self, side, terrain, actor):
        self.terrain = terrain
        self.terrain_turns = 8 if actor.mon["item"] == "Terrain Extender" else 5
        self.activated[side].add(terrain)
        self._event(f"필드 · {TERRAIN_LABELS[terrain]}", "field", terrain=terrain)
        for s in range(2):
            for _, f in self._present(s):
                self._seed(f)

    def _seed(self, fighter):
        stat = SEEDS.get(fighter.mon["item"])
        if stat and not fighter.item_used and self.terrain == stat[0]:
            self._consume(fighter)
            if changed := self._change_stages(fighter, {stat[1]: 1}):
                self._stage_event(fighter, changed)

    def _set_weather(self, side: int, weather: str, actor: Fighter):
        rocks = {"sun": "Heat Rock", "rain": "Damp Rock", "sand": "Smooth Rock", "snow": "Icy Rock"}
        self.weather = weather
        self.weather_turns = 8 if actor.mon["item"] == rocks[weather] else 5
        self.activated[side].add(weather)
        self._event(f"날씨 · {WEATHER_LABELS[weather]}", "field", weather=weather)

    def _move_name(self, move: str) -> str:
        return self.engine.M.get(move, {}).get("ko") or move

    def _moves(self, f: Fighter) -> list[str]:
        if f.recharge:
            return []
        moves = [m for m in f.mon["moves"] if
                 (m in SUPPORT or self.engine.M[m]["power"] and not self.engine.M[m].get("selfdestruct"))
                 and (not f.taunt or m not in SUPPORT)
                 and (not f.choice or m == f.choice)
                 and (not f.encore or m == f.encore_move)
                 and (m not in FIRST_TURN or f.entered == self.turn)]
        return moves or ["Struggle"]

    def _move_type(self, actor, move):
        kind = self.engine.M.get(move, {}).get("type")
        if move == "Weather Ball" and self._wx:
            return {"sun": "Fire", "rain": "Water", "sand": "Rock", "snow": "Ice"}[self._wx]
        return ATE.get(actor.mon["ability"], kind) if kind == "Normal" else kind

    def _spread(self, actor, move):
        return self.engine.M.get(move, {}).get("target") in SPREAD_TARGETS or (
            move == "Expanding Force" and self.terrain == "psychic" and self._grounded(actor)
        )

    def _targets(self, side: int, slot: int, move: str, target: int | None) -> list[Fighter]:
        opponents = self._present(1 - side)
        actor = dict(self._present(side))[slot]
        category = self.engine.M.get(move, {}).get("target")
        if self._spread(actor, move):
            allies = [f for ally, f in self._present(side) if ally != slot] if category == "allAdjacent" else []
            return [f for _, f in opponents] + allies
        redirect = self.redirect[1 - side]
        if redirect is not None and move != "Snipe Shot":
            redirect_slot, redirect_move = redirect
            ignores_powder = ("Grass" in actor.mon["types"] or actor.mon["ability"] == "Overcoat"
                              or actor.mon["item"] == "Safety Goggles")
            if redirect_move != "Rage Powder" or not ignores_powder:
                redirected = next((f for i, f in opponents if i == redirect_slot), None)
                if redirected:
                    return [redirected]
        draw = {"Electric": "Lightning Rod", "Water": "Storm Drain"}.get(self._move_type(actor, move))
        if draw and category == "normal" and actor.mon["ability"] not in MOLD:
            original = next((f for i, f in opponents if i == target), opponents[0][1]) if opponents else None
            if original is not None and original.mon["ability"] == draw:
                return [original]
            conductors = [(self._speed(s, f), f) for s in (side, 1 - side) for _, f in self._present(s)
                          if f is not actor and f.mon["ability"] == draw]
            if conductors:
                return [max(conductors, key=lambda row: row[0])[1]]
        return [next((f for i, f in opponents if i == target), opponents[0][1])] if opponents else []

    def _damage(self, actor: Fighter, target: Fighter, move: str, spread: bool) -> tuple[float, float]:
        if move == "Struggle":
            return max(1, 0.22 * actor.mon["stats"]["atk"] / target.mon["stats"]["def"] * target.max_hp), 100
        meta = self.engine.M.get(move, {})
        if meta.get("fixed"):
            kind = self._move_type(actor, move)
            if type_multiplier(kind or "Normal", target.mon["types"],
                               None if actor.mon["ability"] in MOLD else target.mon["ability"]) == 0:
                return 0, meta.get("accuracy", 100)
            fixed = meta["fixed"]
            amount = (max(1, target.hp // 2) if fixed == "half" else 50 if fixed == "level"
                      else max(0, target.hp - actor.hp) if fixed == "endeavor" else actor.hp)
            return amount, meta.get("accuracy", 100)
        attacker, defender = actor.effective(), target.effective()
        mold = actor.mon["ability"] in MOLD
        if move in mx.SOUND and target.mon["ability"] == "Soundproof" and not mold:
            return 0, 100  # 방음: 소리 기술 무효
        if target.mon["ability"] == "Unaware" and not mold:
            attacker["stats"] = dict(actor.mon["stats"])
        if actor.mon["ability"] == "Unaware":
            defender["stats"] = dict(target.mon["stats"])
        defender["stats"]["hp"] = target.max_hp
        if self._wx == "sand" and "Rock" in target.mon["types"]:
            defender["stats"]["spd"] = round(defender["stats"]["spd"] * 1.5)
        if self._wx == "snow" and "Ice" in target.mon["types"]:
            defender["stats"]["def"] = round(defender["stats"]["def"] * 1.5)
        hit = self.engine.damage(attacker, move, defender, self.fmt, spread=spread,
                                 full_hp=target.hp == target.max_hp, recharge_discount=False,
                                 weather="sun" if actor.mon["ability"] == "Mega Sol" else self._wx,
                                 psychic_terrain=self.terrain == "psychic" and self._grounded(actor),
                                 estimate_intimidate=False,
                                 power_multiplier=2 if move == "Stomping Tantrum" and self.turn > 1
                                 and actor.failed_move_turn == self.turn - 1 else 1)
        if not hit:
            return 0, 100
        accuracy = hit["acc"]
        if move in ("Thunder", "Hurricane"):
            accuracy = 100 if self._wx == "rain" else 50 if self._wx == "sun" else accuracy
        if move == "Blizzard" and self._wx == "snow":
            accuracy = 100
        accuracy = self._accuracy(actor, target, accuracy)
        power = 1.5 if actor.helped else 1.
        physical = meta.get("category") == "Physical"
        if move in ("Eruption", "Water Spout", "Dragon Energy"):
            power *= max(1, int(150 * actor.hp / actor.max_hp)) / 150  # 남은 HP 비례
        if move == "Last Respects":
            fainted = sum(1 for f in self.teams[self._side(actor)] if not f.hp)
            power *= 1 + min(100, fainted)  # 50 + 50 × 쓰러진 아군
        if actor.mon["ability"] == "Solar Power" and self._wx == "sun" and not physical:
            power *= 1.5
        item = None if actor.item_used else actor.mon["item"]
        if item == "Muscle Band" and physical or item == "Wise Glasses" and not physical:
            power *= 1.1
        if item == "Normal Gem" and hit["type"] == "Normal" and meta.get("power"):
            power *= 1.3
        if actor.status:
            if move == "Facade":
                power *= 2
            if actor.mon["ability"] == "Guts" and physical:
                power *= 1.5
            elif actor.status == "brn" and physical and move != "Facade":
                power *= .5  # 화상: 물리 데미지 절반 (급소여도 그대로)
        if meta.get("variable"):
            power *= mx.weight_power(move, mx.weight(self.engine, actor.mon["id"]),
                                     mx.weight(self.engine, target.mon["id"])) / 60
        if actor.mon["ability"] == "Sheer Force" and (move in mx.SECONDARY_STATUS or move in mx.TARGET_STAGES
                                                      or move in mx.FLINCH or move in SPEED_DROP):
            power *= 1.3
        power *= self._screen(actor, target, move)
        kind, ability = hit["type"], actor.mon["ability"]
        target_ability = None if mold else target.mon["ability"]
        if move == "Knock Off" and self._removable(target):
            power *= 1.5
        if ability in {"Protean", "Libero"} and kind not in actor.mon["types"]:
            power *= 1.5
        if ability == "Skill Link" and meta.get("hits") and 2.9 < meta["hits"] < 3.5:
            power *= 5 / meta["hits"]
        if ability == "Mega Launcher" and "pulse" in meta.get("flags", ()):
            power *= 1.5
        if ability == "Parental Bond" and not meta.get("hits") and not self._spread(actor, move):
            power *= 1.25
        if kind == "Fairy" and any(f.mon["ability"] == "Fairy Aura" for s in range(2) for _, f in self._present(s)):
            power *= 4 / 3
        if ability == "Liquid Voice" and move in mx.SOUND:
            power *= 1.2
        if target_ability == "Thick Fat" and kind in {"Fire", "Ice"}:
            power *= .5
        if target_ability == "Disguise" and target.disguise:
            power = 0
        if (actor.hp * 3 <= actor.max_hp and LOW_HP_BOOST.get(actor.mon["ability"]) == hit["type"]
            or actor.flash_fire and hit["type"] == "Fire"):
            power *= 1.5
        if actor.mon["ability"] == "Supreme Overlord":
            side = 0 if any(f is actor for f in self.teams[0]) else 1
            power *= 1 + .1 * sum(self.teams[side][i].hp == 0 for i in self.seen[side])
        if self.width == 2 and actor.mon["ability"] not in MOLD:
            for side in range(2):
                if any(f is target for f in self.teams[side]):
                    if any(f is not target and f.mon["ability"] == "Friend Guard" for _, f in self._present(side)):
                        power *= .75
                    break
        if self._grounded(actor) and (self.terrain, hit["type"]) in {("grassy", "Grass"), ("electric", "Electric")}:
            power *= 1.3
        if self._grounded(target) and (
            self.terrain == "misty" and hit["type"] == "Dragon"
            or self.terrain == "grassy" and move in {"Earthquake", "Bulldoze", "Magnitude"}
        ):
            power *= .5
        if target.mon["item"] == "Air Balloon" and not target.item_used and hit["type"] == "Ground":
            return 0, accuracy
        if not power and target_ability == "Disguise":
            return target.max_hp / 8 + .01, accuracy
        return hit["pct"] * target.max_hp / 100 * power, accuracy

    def _options(self, side: int, slot: int, f: Fighter) -> list[dict]:
        if f.charging:
            move, target = f.charging
            return [{"slot": slot, "kind": "move", "move": move, "target": target,
                     "label": f"{self._move_name(move)} 발사", "type": self.engine.M[move]["type"],
                     "priority": self._priority(f, move)}]
        options = []
        bench = self._bench(side)
        for move in self._moves(f):
            meta = self.engine.M.get(move, {})
            spread = self._spread(f, move)
            targets = [None] if (move in SUPPORT and move not in TARGETED_SUPPORT) or spread else [
                i for i, _ in self._present(1 - side)
            ]
            foes = dict(self._present(1 - side))
            options.extend({"slot": slot, "kind": "move", "move": move, "target": target,
                            "label": self._move_name(move), "type": meta.get("type"),
                            "category": meta.get("category"), "power": meta.get("power"),
                            "eff": type_multiplier(meta.get("type") or "Normal", foes[target].mon["types"],
                                                   foes[target].mon["ability"])
                            if target is not None and target in foes and meta.get("category") != "Status" else None,
                            "priority": self._priority(f, move), "pivot": move in PIVOT and bool(bench),
                            "scope": ("all" if meta.get("target") == "allAdjacent" else "foes")
                            if spread else None} for target in targets)
        if f.recharge:
            options.append({"slot": slot, "kind": "wait", "label": "재충전"})
        options.extend({"slot": slot, "kind": "switch", "target": i, "label": f"{self.teams[side][i].name} 교체"}
                       for i in bench)
        return options

    def _auto(self, side: int) -> list[dict]:
        if side == 1 and self.difficulty in {"master", "champion"}:
            from .battle_ai import choose_actions

            return choose_actions(self)
        return self._greedy(side)

    def _seen(self, side: int, f: "Fighter") -> "Fighter":
        """side 쪽 CPU 가 보는 상대 포켓몬: 그 종의 흔한 세트 + 배틀에서 공개된 정보(특성·메가·쓴 기술·HP 비율).
        상대의 실제 도구·성격·능력 포인트는 모른다 (명세: 비공개 정보를 CPU 에 주지 않는다)."""
        if any(f is x for x in self.teams[side]):
            return f
        cache = self.__dict__.setdefault("_seen_cache", {})
        key = (self.turn, side)
        if cache.get("key") != key:
            cache.clear()
            cache["key"] = key
        proxy = cache.get(id(f))
        if proxy is None:
            pid = f.mon["id"]
            guess = self.engine.default_set(pid, self.fmt)
            if f.ability_revealed:
                guess["ability"] = f.mon["ability"]
            if f.mon.get("mega") != guess.get("mega"):
                guess["mega"] = f.mon.get("mega")
                if guess.get("item") and self.engine.find_mega(self.engine.P[pid], stone=guess["item"]):
                    guess["item"] = None
            moves = list(dict.fromkeys(sorted(f.known_moves - {"Struggle"}) + guess["moves"]))
            mon = self.engine.resolve({**guess, "moves": moves}, self.fmt)
            ratio = f.hp / f.max_hp if f.max_hp else 0
            proxy = replace(f, mon=mon, hp=max(1, round(ratio * mon["stats"]["hp"])) if f.hp else 0,
                            choice=f.choice if f.choice in f.known_moves else None)
            cache[id(f)] = proxy
        return proxy

    def _greedy(self, side: int) -> list[dict]:
        chosen, reserves = [], set()
        difficulty = self.difficulty if side == 1 else "ultra"
        style = CPU_STYLES[self.cpu_style if side == 1 else "balanced"]
        advanced = difficulty in {"master", "champion"} or style["focus"]
        enablers = self._enablers(1 - side) if style["counter"] else set()
        expected = {}
        for slot, actor in self._present(side):
            options = self._options(side, slot, actor)
            attacks = [a for a in options if a["kind"] == "move" and a["move"] not in SUPPORT]
            ally_ids = {id(f) for _, f in self._present(side)}

            def estimates(a):
                targets = self._targets(side, slot, a["move"], a["target"])
                return [
                    (seen, *self._damage(actor, seen, a["move"], len(targets) > 1))
                    for target in targets
                    if id(target) in ally_ids or not self._priority_blocked(side, target, actor, a["move"])
                    for seen in (self._seen(side, target),)
                ]

            hits = [(a, estimates(a)) for a in attacks]

            def value(a, hits):
                score = 0
                for target, raw, acc in hits:
                    ally = id(target) in ally_ids
                    remaining = max(0, target.hp - expected.get(id(target), 0)) if advanced and not ally else target.hp
                    if not remaining:
                        continue
                    score += (-1 if ally else 1) * (
                        min(raw, remaining) / target.max_hp + (style["ko"] if raw >= remaining else 0)
                        + (style["counter"] if not ally and id(target) in enablers else 0)
                    ) * acc / 100
                    if not ally and raw > 0 and difficulty in {"ultra", "master", "champion"}:
                        move = a["move"]
                        if move == "Fake Out" and self.width == 2 and (
                            target.mon["ability"] not in {"Inner Focus", "Shield Dust"}
                            and target.mon["item"] != "Covert Cloak"
                        ):
                            score += .20
                        elif self._priority(actor, move) > 0 and raw >= remaining:
                            score += .13
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
            enemies = [self._speed(1 - side, self._seen(side, f)) for _, f in self._present(1 - side)]
            strategy = self.foe_strategy if side == 1 else None
            # 순풍·트릭룸: 실제로 뒤집히는 스피드 관계 수로 가치를 매긴다.
            control = max(((style["setup"] * self._speed_control_value(side, actor, a["move"], strategy), a)
                           for a in options
                           if a.get("move") in {"Tailwind", "Trick Room"}
                           and not any(c.get("move") in {"Tailwind", "Trick Room"} for c in chosen)),
                          key=lambda row: row[0], default=(0., None))
            preferred = control[1]["move"] if control[1] is not None else None
            setup = None
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
            tactical = difficulty in {"ultra", "master", "champion"}
            defensive = self._defense(side, actor, options, switches, best_score,
                                      allow_protect=difficulty == "champion" or style["protect"],
                                      danger_line=style["danger"], caution=style.get("caution", 0.)) if tactical else None
            parting = next((a for a in options if a.get("move") == "Parting Shot"), None)
            utility = max(((style["setup"] * (self._support_value(side, slot, actor, a) or 0.), a) for a in options
                           if a.get("move") in mx.NEW_SUPPORT and not any(c.get("move") == a["move"] for c in chosen)),
                          key=lambda row: row[0], default=(0., None))
            if difficulty in {"poke", "great"}:
                utility = (utility[0] * .7, utility[1])
            if control[1] is not None and control[0] >= max(.22, best_score * .9) and (
                not defensive or control[0] >= .6 and actor.hp > actor.max_hp * .4
            ):
                action = control[1]
            elif defensive:
                action = defensive
            elif utility[1] is not None and utility[0] > max(.12, best_score * 1.05):
                action = utility[1]
            elif tactical and parting and switches and best_score < .30 + style["pivot"]:
                action = parting
            elif tactical and style["pivot"] and switches and best is not None and best_score < style["pivot"] \
                    and actor.entered != self.turn:
                action = min(switches, key=lambda a: self._threat_to(side, self.teams[side][a["target"]]))
            elif heals and 0 < actor.hp <= actor.max_hp * style["heal"] and best_score < 0.35:
                action = heals[0]
            elif setup and actor.hp >= actor.max_hp / 2 and self.turn <= 4 and best_score < (
                .95 if preferred and setup.get("move") == preferred else .55
            ):
                action = setup
            elif boost and actor.hp >= actor.max_hp * .8 and self.turn <= 3 and best_score < (
                .65 if strategy == "setup" else .42
            ) * style["setup"]:
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

    def _enablers(self, side):
        """side 팀의 승리 조건을 여는 포켓몬 (순풍·트릭룸·날씨·필드·날따름) — 카운터형 CPU가 먼저 노린다."""
        out = set()
        keys = {"Tailwind", "Trick Room", "Follow Me", "Rage Powder"} | set(WEATHER_MOVES)
        for f in self.teams[side]:
            seen = self._seen(1 - side, f)  # 공개 정보(흔한 세트)로만 판단
            if set(seen.mon["moves"]) & keys or seen.mon["ability"] in WEATHER or seen.mon["ability"] in TERRAIN:
                out.add(id(seen))
        return out

    def _threat_to(self, side, target):
        enemies = [self._seen(side, f) for _, f in self._present(1 - side)]
        worst = 0.
        for enemy in enemies:
            for m in enemy.mon["moves"]:
                if m in self.engine.M:
                    raw, acc = self._damage(enemy, target, m, False)
                    worst = max(worst, raw * acc / 100 / max(1, target.hp))
        return worst

    def _defense(self, side, actor, options, switches, attack_score, *, allow_protect, danger_line=.85, caution=0.):
        # caution: 수비형 CPU는 자기 공격이 꽤 좋아도 위험하면 방어·교체를 고른다.
        if attack_score >= .75 + caution or not switches and not allow_protect:
            return None
        enemies = [self._seen(side, f) for _, f in self._present(1 - side)]
        forecasts = [(f, f.mon["moves"]) for f in enemies]

        def pressure(target):
            incoming = []
            for enemy, moves in forecasts:
                hits = (self._damage(enemy, target, m, False) for m in moves if m in self.engine.M)
                incoming.append(max((raw * acc / 100 for raw, acc in hits), default=0))
            return sum(incoming) / max(1, target.hp)

        danger = pressure(actor)
        if danger < danger_line:
            return None
        if switches and (actor.entered != self.turn or danger >= 1.25):
            best = min(switches, key=lambda a: pressure(self.teams[side][a["target"]]))
            incoming = self.teams[side][best["target"]]
            if pressure(incoming) < min(.62, danger * .5) and attack_score < .55 + caution:
                return best
        if allow_protect and len(self._present(side)) == 2 and not actor.protect_chain and attack_score < .52 + caution:
            return next((a for a in options if a.get("move") in PROTECT), None)
        return None

    def _support(self, side: int, slot: int, actor: Fighter, move: str, target_slot: int | None):
        if move in PROTECT:
            actor.protected = self.rng.random() < 1 / 3 ** actor.protect_chain
            actor.protect_chain += 1
            if not actor.protected:
                self._event("방어에 실패했습니다.")
                return False
        elif move in HEAL:
            return bool(self._heal(actor, actor.max_hp // 2))
        elif move in BOOSTS:
            changed = self._change_stages(actor, BOOSTS[move])
            if changed.get("atk", 0) > 0 or changed.get("spa", 0) > 0:
                self.activated[side].add("setup")
            return bool(changed)
        elif move == "Tailwind":
            if self.tailwind[side]:
                return False
            self.tailwind[side] = 4
            self.activated[side].add("tailwind")
            self._event(f"{'상대' if side else '내 팀'}의 뒤에서 순풍이 불기 시작했다!")
        elif move == "Trick Room":
            self.trick_room = 0 if self.trick_room else 5
            if self.trick_room:
                self.activated[side].add("trickroom")
            self._event("행동 순서가 뒤집혔다!" if self.trick_room else "트릭룸이 풀렸다!")
        elif move in WEATHER_MOVES:
            if self.weather == WEATHER_MOVES[move]:
                return False
            self._set_weather(side, WEATHER_MOVES[move], actor)
        elif move in TERRAIN_MOVES:
            if self.terrain == TERRAIN_MOVES[move]:
                return False
            self._set_terrain(side, TERRAIN_MOVES[move], actor)
        elif move == "Chilly Reception":
            self._set_weather(side, "snow", actor)
            return True
        elif move in REDIRECT:
            self.redirect[side] = slot, move
        elif move == "Wide Guard":
            self.wide_guard[side] = True
        elif move == "Quick Guard":
            self.quick_guard[side] = True
        elif move == "Helping Hand":
            for _, partner in self._present(side):
                if partner is not actor:
                    partner.helped = True
        elif move in mx.EXTRA_BOOSTS:
            cost = mx.HP_COST.get(move)
            if cost and actor.hp <= actor.max_hp * cost:
                self._event(f"{self._move_name(move)} 실패")
                return False
            if move == "Curse" and "Ghost" in actor.mon["types"]:
                targets = self._targets(side, slot, move, target_slot)
                self._hurt(actor, actor.max_hp // 2, "은(는) 자신의 체력을 깎아 저주를 걸었다")
                return False
            if cost:
                self._hurt(actor, actor.max_hp * cost, "은(는) 체력을 깎았다")
            changed = self._change_stages(actor, mx.EXTRA_BOOSTS[move])
            self._stage_event(actor, changed)
            if move == "Tidy Up":
                self.hazards = [{}, {}]
            if changed.get("atk", 0) > 0 or changed.get("spa", 0) > 0:
                self.activated[side].add("setup")
        elif move in mx.SCREENS:
            kind = mx.SCREENS[move]
            if self.screens[side].get(kind) or kind == "veil" and self.weather != "snow":
                self._event(f"{self._move_name(move)} 실패")
                return False
            self.screens[side][kind] = 8 if actor.mon["item"] == "Light Clay" else 5
            self.activated[side].add("screens")
            self._event(f"{'상대' if side else '내 팀'}에 {self._move_name(move)}이(가) 펼쳐졌다!", "field")
        elif move in mx.HAZARDS:
            hazards = self.hazards[1 - side]
            key, cap = {"Stealth Rock": ("rocks", 1), "Spikes": ("spikes", 3), "Toxic Spikes": ("tspikes", 2),
                        "Sticky Web": ("web", 1)}[move]
            if hazards.get(key, 0) >= cap:
                self._event(f"{self._move_name(move)} 실패")
                return False
            hazards[key] = hazards.get(key, 0) + 1
            self._event(f"{'내 팀' if side else '상대'} 주변에 {self._move_name(move)}이(가) 설치되었다!", "field")
        elif move == "Substitute":
            cost = actor.max_hp // 4
            if actor.sub or actor.hp <= cost:
                self._event(f"{self._move_name(move)} 실패")
                return False
            self._hurt(actor, cost, "은(는) 대타를 만들었다")
            actor.sub = cost
        elif move == "Wish":
            if slot in self.wish[side]:
                self._event(f"{self._move_name(move)} 실패")
                return False
            self.wish[side][slot] = (2, actor.max_hp // 2)
        elif move in {"Life Dew", "Lunar Blessing", "Jungle Healing"}:
            for _, ally in self._present(side):
                self._heal(ally, ally.max_hp // 4)
                if move != "Life Dew":
                    self._cure(ally)
        elif move == "Rest":
            if actor.hp == actor.max_hp or not self._can_status(actor, "slp") and actor.status != "slp":
                self._event(f"{self._move_name(move)} 실패")
                return False
            actor.status = ""
            actor.hp = actor.max_hp
            self._inflict(actor, "slp")
            actor.status_turns = 0
        elif move == "Coaching":
            for _, ally in self._present(side):
                if ally is not actor:
                    self._stage_event(ally, self._change_stages(ally, {"atk": 1, "def": 1}))
        elif move == "Haze":
            for s in range(2):
                for _, f in self._present(s):
                    f.stages.clear()
            self._event("모든 포켓몬의 능력 변화가 원래대로 돌아왔다!", "field")
        elif move == "Defog":
            self.hazards = [{}, {}]
            self.screens[1 - side] = {}
            self._event("함정과 벽이 걷혔다!", "field")
        elif move == "Heal Pulse":
            partner = next((f for _, f in self._present(side) if f is not actor), None)
            if not partner or not self._heal(partner, partner.max_hp // 2):
                self._event(f"{self._move_name(move)} 실패")
                return False
        elif move == "Destiny Bond":
            actor.destiny = True
            self._event(f"{actor.name}은(는) 상대를 길동무로 삼으려 하고 있다.")
        elif move in {"Healing Wish", "Memento"}:
            if move == "Memento":
                foes = self._targets(side, slot, move, target_slot)
                if foes:
                    self._lower(foes[0], {"atk": -2, "spa": -2}, actor)
            else:
                self.wish[side][slot] = (0, 10 ** 6)
            self._hurt(actor, actor.hp, "은(는) 쓰러졌다", kind="damage")
        elif move in TARGETED_SUPPORT:
            targets = self._targets(side, slot, move, target_slot)
            if targets:
                target = targets[0]
                ability = None if actor.mon["ability"] in MOLD else target.mon["ability"]
                blocked = ability == "Good as Gold" or (move == "Parting Shot" and ability == "Soundproof")
                if blocked:
                    self._ability(target)
                elif target.protected:
                    return None
                elif not self._priority_blocked(side, target, actor, move):
                    if move == "Parting Shot":
                        if self._lower(target, {"atk": -1, "spa": -1}, actor) or ability == "Mirror Armor":
                            return True
                    elif move != "Taunt":
                        if self._targeted(side, actor, target, move):
                            return True
                    elif ability != "Oblivious" and not target.taunt:
                        target.taunt = 3
                        self._event(f"{target.name}은(는) 보조기를 쓸 수 없게 됐다.")
                        self._mental_herb(target)
                        return True
            self._event(f"{self._move_name(move)} 실패")
            return False
        return True

    @staticmethod
    def _accuracy(actor, target, accuracy):
        if "No Guard" in (actor.mon["ability"], target.mon["ability"]):
            return 100
        if actor.mon["ability"] == "Compound Eyes":
            accuracy *= 1.3
        if actor.mon["item"] == "Wide Lens":
            accuracy *= 1.1
        if target.mon["item"] == "Bright Powder" and not target.item_used:
            accuracy *= .9
        return min(100, accuracy)

    def _targeted(self, side, actor, target, move) -> bool:
        """상대를 노리는 보조 기술. 성공하면 True."""
        meta = self.engine.M.get(move, {})
        accuracy = meta.get("accuracy", 100) or 100
        if move == "Toxic" and "Poison" in actor.mon["types"]:
            accuracy = 100
        accuracy = self._accuracy(actor, target, accuracy)
        if target.mon["ability"] == "Magic Bounce" and actor.mon["ability"] not in MOLD:
            self._ability(target)
            return False
        if move not in {"Pain Split", "Heal Pulse"} and self._side(target) != side and self.rng.random() * 100 >= accuracy:
            self._event(f"{target.name}에게 빗나갔습니다.", "miss", ref=self._ref(target))
            return True
        if move in mx.STATUS_MOVES:
            return self._inflict(target, mx.STATUS_MOVES[move], actor, move)
        if move in mx.TARGET_DEBUFFS:
            if target.sub and move not in mx.SOUND:
                return False
            if move == "Toxic Thread":
                self._inflict(target, "psn", actor, move)
            return self._lower(target, mx.TARGET_DEBUFFS[move], actor) or move == "Toxic Thread"
        if move == "Yawn":
            if target.yawn or not self._can_status(target, "slp", actor, move):
                return False
            target.yawn = 2
            self._event(f"{target.name}은(는) 졸음이 쏟아지기 시작했다.", "status", ref=self._ref(target))
            return True
        if move == "Encore":
            last = target.last_move
            if target.encore or not last or last in {"Encore", "Struggle", "Transform"} or last not in target.mon["moves"]:
                return False
            target.encore, target.encore_move = 3, last
            self._event(f"{target.name}은(는) 앙코르를 받았다!", "status", ref=self._ref(target))
            self._mental_herb(target)
            return True
        if move == "Leech Seed":
            if target.seeded or "Grass" in target.mon["types"] or target.sub:
                return False
            target.seeded = True
            self._event(f"{target.name}에게 씨앗을 심었다!", "status", ref=self._ref(target))
            return True
        if move == "Pain Split":
            if target.sub:
                return False
            share = (actor.hp + target.hp) // 2
            actor.hp, target.hp = min(actor.max_hp, share), min(target.max_hp, share)
            self._event("서로의 체력을 나눠 가졌다!", "field")
            return True
        if move == "Strength Sap":
            if target.stages.get("atk", 0) <= -6:
                return False
            self._heal(actor, target.effective()["stats"]["atk"])
            self._lower(target, {"atk": -1}, actor)
            return True
        return False

    def _speed_control_value(self, side, actor, move, strategy=None) -> float:
        """순풍·트릭룸의 가치: 앞으로 몇 턴 동안 선공이 뒤집히는 (내 포켓몬, 상대) 쌍의 수.
        필드에 있는 포켓몬은 1, 대기 포켓몬은 0.4로 센다. 공격 점수(상대 체력 비율)와 같은 척도."""
        if move == "Tailwind" and (self.tailwind[side] or self.trick_room):
            return 0.
        undo_room = move == "Trick Room" and self.trick_room
        on_field = {id(f) for _, f in self._present(side)} | {id(f) for _, f in self._present(1 - side)}
        allies = [f for f in self.teams[side] if f.hp > 0]
        foes = [f for f in self.teams[1 - side] if f.hp > 0]
        if not foes:
            return 0.
        net = 0.
        for a in allies:
            sa = self._speed(side, a)
            attacks = any(self.engine.M.get(m, {}).get("power") for m in a.mon["moves"])
            if not attacks:
                continue
            for f in foes:
                sf = self._speed(1 - side, self._seen(side, f))
                w = (1 if id(a) in on_field else .4) * (1 if id(f) in on_field else .4)
                if move == "Tailwind":
                    net += w * (sa < sf < 2 * sa)
                else:
                    order = (sa < sf) - (sa > sf)
                    net += w * (-order if undo_room else order)
        if net <= 0:
            return 0.
        value = .2 * net
        if move == "Tailwind" and self._priority(actor, move) > 0:
            value += .08  # 짓궂은마음: 이번 턴부터 바로 효과
        if strategy in {"tailwind", "trickroom"} and move.lower().replace(" ", "") == strategy:
            value += .25
        # 남은 아군이 적을수록 가치가 줄어든다.
        return min(1.4, value) * min(1., len(allies) / 3)

    def _support_value(self, side, slot, actor, action) -> float | None:
        """새로 다루는 보조 기술의 대략적인 가치 (공격 점수와 같은 척도). 해당 없으면 None."""
        move = action.get("move")
        if move not in mx.NEW_SUPPORT:
            return None
        foes = dict(self._present(1 - side))
        target = foes.get(action.get("target")) or next(iter(foes.values()), None)
        hp = actor.hp / actor.max_hp
        bench = len(self._bench(1 - side))
        if move in mx.STATUS_MOVES:
            status = mx.STATUS_MOVES[move]
            if not target or not self._can_status(target, status, actor, move) or target.mon["ability"] == "Magic Bounce":
                return 0.
            physical = sum(self.engine.M.get(m, {}).get("category") == "Physical" for m in self._seen(side, target).mon["moves"]) >= 2
            faster = self._speed(1 - side, target) > self._speed(side, actor) and not self.trick_room
            value = {"slp": .8, "par": .3 + .25 * faster, "brn": .6 if physical else .12,
                     "tox": .3 + .15 * (self.width == 1), "psn": .18}[status]
            return value * (target.hp / target.max_hp) * (self.engine.M.get(move, {}).get("accuracy", 100) or 100) / 100
        if move in mx.EXTRA_BOOSTS:
            gains = mx.EXTRA_BOOSTS[move]
            fresh = sum(v for k, v in gains.items() if v > 0 and actor.stages.get(k, 0) < 2)
            cost = mx.HP_COST.get(move, 0)
            return 0. if hp <= cost + .25 else .12 * fresh * hp * (1.3 if self.turn <= 3 else .8)
        if move in mx.TARGET_DEBUFFS:
            if not target or target.sub:
                return 0.
            physical = sum(self.engine.M.get(m, {}).get("category") == "Physical" for m in self._seen(side, target).mon["moves"]) >= 2
            stats = mx.TARGET_DEBUFFS[move]
            relevant = sum(-v for k, v in stats.items() if (k == "atk") == physical or k in {"spe", "def", "spd"})
            return .12 * relevant
        if move in mx.SCREENS:
            kind = mx.SCREENS[move]
            if self.screens[side].get(kind) or kind == "veil" and self.weather != "snow":
                return 0.
            return .55 if kind == "veil" else .4
        if move in mx.HAZARDS:
            key = {"Stealth Rock": "rocks", "Spikes": "spikes", "Toxic Spikes": "tspikes", "Sticky Web": "web"}[move]
            if self.hazards[1 - side].get(key) and key in {"rocks", "web"} or self.hazards[1 - side].get(key, 0) >= 2:
                return 0.
            return {"rocks": .12, "spikes": .08, "tspikes": .07, "web": .09}[key] * bench
        if move == "Substitute":
            return .3 if hp > .55 and not actor.sub else 0.
        if move in {"Wish", "Life Dew", "Lunar Blessing", "Jungle Healing", "Rest"}:
            return .7 * (1 - hp) if hp < .6 else 0.
        if move == "Strength Sap":
            return .75 * (1 - hp) if target and hp < .7 else 0.
        if move == "Pain Split":
            return .8 * max(0., target.hp / target.max_hp - hp) if target else 0.
        if move == "Yawn":
            return .4 if target and not target.yawn and self._can_status(target, "slp", actor, move) else 0.
        if move == "Encore":
            if not target or target.encore or not target.last_move:
                return 0.
            return .55 if target.last_move in SUPPORT else .1
        if move == "Leech Seed":
            return .3 if target and not target.seeded and "Grass" not in target.mon["types"] else 0.
        if move == "Destiny Bond":
            return .45 if hp < .35 else 0.
        if move == "Defog":
            return .1 * len(self.hazards[side]) + .2 * bool(self.screens[1 - side])
        if move == "Haze":
            return .1 * sum(max(0, v) for _, f in self._present(1 - side) for v in f.stages.values())
        if move in {"Healing Wish", "Memento"}:
            return .4 if hp < .25 and self._bench(side) else 0.
        if move == "Coaching":
            return .25 if len(self._present(side)) == 2 else 0.
        return .1

    def _priority(self, actor, move):
        priority = -6 if move == "Chilly Reception" else self.engine.M.get(move, {}).get("priority", 0)
        ability = actor.mon["ability"]
        if (ability == "Prankster" and move in SUPPORT
            or ability == "Gale Wings" and actor.hp == actor.max_hp and self._move_type(actor, move) == "Flying"
            or move == "Grassy Glide" and self.terrain == "grassy" and self._grounded(actor)):
            priority += 1
        if ability == "Triage" and (move in HEAL or move in DRAIN):
            priority += 3
        return priority

    def _priority_blocked(self, side, target, actor, move, priority=None):
        if move in SUPPORT and actor.mon["ability"] == "Prankster" and "Dark" in target.mon["types"]:
            return True
        if (self._priority(actor, move) if priority is None else priority) <= 0:
            return False
        return ((self.terrain == "psychic" and self._grounded(target))
                or (self.quick_guard[1 - side] and move != "Feint")
                or (actor.mon["ability"] not in MOLD
                    and any(f.mon["ability"] in PRIORITY_BLOCK for _, f in self._present(1 - side))))

    def _absorb(self, actor, target, move):
        if actor.mon["ability"] in MOLD:
            return False
        ability, kind = target.mon["ability"], self._move_type(actor, move)
        if not kind or type_multiplier(kind, target.mon["types"]) == 0:
            return False
        if ability in ABSORB_HEAL and ABSORB_HEAL[ability] == kind:
            self._ability(target)
            self._heal(target, target.max_hp // 4)
            return True
        boost = ABSORB_BOOST.get(ability)
        if boost and boost[0] == kind:
            self._ability(target)
            self._change_stages(target, {boost[1]: boost[2]})
            return True
        if ability == "Flash Fire" and kind == "Fire":
            self._ability(target)
            target.flash_fire = True
            return True
        return False

    @staticmethod
    def _removable(fighter) -> bool:
        item = fighter.mon["item"]
        return bool(item) and not fighter.item_used and not (
            (fighter.mon.get("mega") or fighter.mega_form) and item.endswith(("ite", "ite X", "ite Y", "ite Z")))

    def _on_hit(self, actor, target, move, contact):
        """맞은 쪽 특성 (챔피언스 메가 특성 포함)."""
        ability = target.mon["ability"]
        physical = self.engine.M.get(move, {}).get("category") == "Physical"
        if ability == "Stamina":
            self._stage_event(target, self._change_stages(target, {"def": 1}))
        elif ability == "Justified" and self._move_type(actor, move) == "Dark" and target.hp:
            self._ability(target)
            self._stage_event(target, self._change_stages(target, {"atk": 1}))
        elif ability == "Weak Armor" and physical:
            self._stage_event(target, self._change_stages(target, {"def": -1, "spe": 2}))
        elif ability == "Toxic Debris" and physical:
            hazards = self.hazards[self._side(actor)]
            if hazards.get("tspikes", 0) < 2:
                hazards["tspikes"] = hazards.get("tspikes", 0) + 1
                self._ability(target)
        elif ability == "Seed Sower" and self.terrain != "grassy":
            self._ability(target)
            self._set_terrain(self._side(target), "grassy", target)
        elif ability == "Spicy Spray" and actor.hp:
            if self._inflict(actor, "brn", target):
                self._ability(target)
        if contact and target.hp and actor.mon["ability"] == "Poison Touch" and self.rng.random() < .3:
            self._inflict(target, "psn", actor)
        if contact and actor.hp:
            if ability == "Flame Body" and self.rng.random() < .3:
                self._inflict(actor, "brn", target)
            elif ability in {"Static"} and self.rng.random() < .3:
                self._inflict(actor, "par", target)
            elif ability == "Poison Point" and self.rng.random() < .3:
                self._inflict(actor, "psn", target)
            elif ability in {"Gooey", "Tangling Hair"}:
                self._lower(actor, {"spe": -1}, target)

    def _secondary(self, actor, target, move):
        luck = 2 if actor.mon["ability"] == "Serene Grace" else 1
        status, chance = mx.SECONDARY_STATUS.get(move, (None, 0))
        if status and self.rng.random() * 100 < chance * luck:
            if status == "dire":
                status = self.rng.choice(("psn", "par", "slp"))
            self._inflict(target, status, actor)
        changes, chance = mx.TARGET_STAGES.get(move, ({}, 0))
        if move in SPEED_DROP:
            changes, chance = {"spe": -1}, 100
        elif move == "Snarl":
            changes, chance = {"spa": -1}, 100
        if changes and self.rng.random() * 100 < chance * luck:
            self._lower(target, changes, actor)

    def _attack(self, side, slot, actor, move, target_slot, priority, remaining):
        if actor.charging:
            actor.charging = None
        elif move in WEATHER_CHARGE:
            if move == "Electro Shot":
                actor.stages["spa"] = min(6, actor.stages.get("spa", 0) + 1)
            if self._wx != WEATHER_CHARGE[move]:
                if actor.mon["item"] == "Power Herb" and not actor.item_used:
                    self._consume(actor)
                else:
                    actor.charging = move, target_slot
                    self._event(f"{actor.name}의 {self._move_name(move)} 준비")
                    return False
        targets = self._targets(side, slot, move, target_slot)
        wide = self._spread(actor, move)
        contact = "contact" in self.engine.M.get(move, {}).get("flags", ())
        did_hit = False
        neutral_result = False
        dealt = 0
        for target in targets:
            opponent = any(target is foe for foe in self.teams[1 - side])
            observation = (actor.mon["id"], move, target.mon["id"]) if opponent and side == 0 else None
            if observation:
                self.executed_attacks[(*observation, "attempts")] += 1
            if move in REACTIVE and not any(
                queued_actor is target and action["kind"] == "move" and action["move"] not in SUPPORT
                and (move != "Upper Hand" or queued_priority > 0)
                for queued_priority, _, _, queued_actor, action in remaining
            ):
                self._event(f"{self._move_name(move)} 실패")
                continue
            pierce = target.protected and contact and actor.mon["ability"] in {"Unseen Fist", "Piercing Drill"}
            if target.protected and move != "Feint" and not pierce:
                neutral_result = True
                self._event(f"{target.name}의 방어에 막혔습니다.", "blocked", ref=self._ref(target))
                continue
            if wide and self.wide_guard[1 - side if opponent else side]:
                neutral_result = True
                self._event(f"{target.name}에게 향한 공격이 와이드가드에 막혔다.")
                continue
            if opponent and self._priority_blocked(side, target, actor, move, priority):
                if (actor.mon["ability"] not in MOLD and not self.quick_guard[1 - side]
                    and not (self.terrain == "psychic" and self._grounded(target))):
                    blocker = next((f for _, f in self._present(1 - side) if f.mon["ability"] in PRIORITY_BLOCK), None)
                    if blocker:
                        self._ability(blocker)
                self._event(f"{target.name}에게 선제기가 막혔다.")
                continue
            raw, acc = self._damage(actor, target, move, len(targets) > 1)
            if self.rng.random() * 100 >= acc:
                self._event(f"{target.name}에게 빗나갔습니다.", "miss", ref=self._ref(target))
                if acc < 90 and opponent:
                    self.trace[side]["low_acc_miss"] += 1
                continue
            if self._absorb(actor, target, move):
                neutral_result = True
                continue
            if raw <= 0:
                self._event(f"{target.name}에게 효과가 없습니다.", "immune", ref=self._ref(target))
                continue
            did_hit = True
            if observation:
                self.executed_attacks[(*observation, "hits")] += 1
            if move == "Feint":
                target.protected = False
                self.wide_guard[1 - side if opponent else side] = False
                self.quick_guard[1 - side if opponent else side] = False
            if pierce:
                self._ability(actor)
                raw *= .25
            fixed = self.engine.M.get(move, {}).get("fixed")
            crit = False
            if not fixed:
                stage = (move in mx.HIGH_CRIT) + (actor.mon["ability"] == "Super Luck") + (
                    actor.mon["item"] in {"Scope Lens", "Razor Claw"})
                no_crit = target.mon["ability"] in {"Battle Armor", "Shell Armor"} and actor.mon["ability"] not in MOLD
                crit = not no_crit and (move in mx.ALWAYS_CRIT or self.rng.random() < mx.CRIT_CHANCE[min(3, stage)])
                if crit:
                    raw = raw * 1.5 / self._screen(actor, target, move) * (
                        1.5 if actor.mon["ability"] == "Sniper" else 1)
                raw = raw * self.rng.uniform(.85, 1) / .925
            if target.sub and move not in mx.SOUND and actor.mon["ability"] != "Infiltrator" and target is not actor:
                hit = min(target.sub, max(1, round(raw)))
                target.sub -= hit
                did_hit = True
                self._event(f"{target.name}의 대타가 공격을 대신 받았다!" + (
                    " 대타는 사라졌다!" if not target.sub else ""), "blocked", ref=self._ref(target))
                continue
            if target.mon["ability"] == "Disguise" and target.disguise and actor.mon["ability"] not in MOLD:
                target.disguise = False
                self._ability(target)
                self._hurt(target, target.max_hp / 8, "의 탈이 벗겨졌다!", kind="damage")
                did_hit = True
                continue
            amount = min(target.hp, max(1, round(raw)))
            sturdy = target.mon["ability"] == "Sturdy" and actor.mon["ability"] not in MOLD
            if target.hp == target.max_hp and amount == target.hp and (
                sturdy or target.mon["item"] == "Focus Sash" and not target.item_used
            ):
                if sturdy:
                    self._ability(target)
                else:
                    self._consume(target)
                amount -= 1
            elif amount == target.hp and target.mon["item"] == "Focus Band" and self.rng.random() < .1:
                self._event(f"{target.name}은(는) 기합의머리띠로 버텼다!", "field")
                amount -= 1
            if (actor.mon["item"] == "Normal Gem" and not actor.item_used and opponent
                    and self._move_type(actor, move) == "Normal" and self.engine.M.get(move, {}).get("power")):
                self._consume(actor)
            target.hp -= amount
            if observation and not target.hp:
                self.executed_attacks[(*observation, "kos")] += 1
            target.taken += amount
            dealt += amount
            if opponent:
                actor.dealt += amount
                victim = 1 - side
                self.trace[victim]["taken"] += amount
                if wide:
                    self.trace[victim]["spread_taken"] += amount
                if not target.hp:
                    actor.kos += 1
                    if actor.hp and actor.mon["ability"] == "Moxie":
                        self._ability(actor)
                        self._stage_event(actor, self._change_stages(actor, {"atk": 1}))
                    actor.victims[target.mon["id"]] += 1
                    if self.first_faint is None:
                        self.first_faint = victim
                    if priority > 0:
                        self.trace[victim]["priority_ko"] += 1
                    if wide:
                        self.trace[victim]["spread_ko"] += 1
                    if any(queued is target and action["kind"] == "move" for _, _, _, queued, action in remaining):
                        self.trace[victim]["ko_before_move"] += 1
            ability = None if actor.mon["ability"] in MOLD else target.mon["ability"]
            secondary = ability != "Shield Dust" and target.mon["item"] != "Covert Cloak"
            chance = mx.FLINCH.get(move, 0) * (2 if actor.mon["ability"] == "Serene Grace" else 1)
            if not chance and actor.mon["item"] in {"King's Rock", "Razor Fang"}:
                chance = 10
            target.flinched |= (secondary and ability != "Inner Focus" and actor.mon["ability"] != "Sheer Force"
                                and chance > 0 and self.rng.random() * 100 < chance)
            meta = self.engine.M.get(move, {})
            eff = type_multiplier(meta.get("type") or "Normal", target.mon["types"],
                                  None if actor.mon["ability"] in MOLD else target.mon["ability"])
            self._event(f"{target.name} HP −{amount}" + (" · 기절" if not target.hp else ""),
                        "damage", target=target.name, amount=amount, fainted=not target.hp,
                        ref=self._ref(target), eff=eff, pct=round(100 * amount / target.max_hp), crit=crit,
                        type=self._move_type(actor, move))
            if crit:
                self._event("급소에 맞았다!", "crit", ref=self._ref(target))
            if not target.hp and target.destiny and opponent:
                self._event(f"{target.name}은(는) 상대를 길동무로 삼았다!", "field")
                self._hurt(actor, actor.hp, "은(는) 길동무가 되었다", kind="damage")
            if target.status == "frz" and target.hp and (self._move_type(actor, move) == "Fire" or move in THAW_MOVES):
                self._cure(target)
            if target.hp and secondary and actor.mon["ability"] != "Sheer Force":
                self._secondary(actor, target, move)
            if target.hp and opponent:
                self._on_hit(actor, target, move, contact)
                if move == "Knock Off" and self._removable(target) and target.mon["ability"] != "Sticky Hold":
                    target.item_used = True
                    self._event(f"{target.name}의 도구를 탁 떨어뜨렸다!", "field")
            if opponent and move in {"Ceaseless Edge", "Stone Axe"}:
                key, cap = ("spikes", 3) if move == "Ceaseless Edge" else ("rocks", 1)
                hazards = self.hazards[1 - side]
                if hazards.get(key, 0) < cap:
                    hazards[key] = hazards.get(key, 0) + 1
                    self._event(f"{'내 팀' if side else '상대'} 주변에 {'압정' if key == 'spikes' else '뾰족한 바위'}이(가) 흩어졌다!",
                                "field")
            if not target.item_used:
                if (target.hp and target.hp <= target.max_hp // 2 and target.mon["item"] == "Sitrus Berry"
                        and not self._unnerved(target)):
                    self._consume(target)
                    self._heal(target, target.max_hp // 4)
                elif target.mon["item"] == "Air Balloon":
                    self._consume(target)
            if contact:
                if target.mon["ability"] in {"Rough Skin", "Iron Barbs"}:
                    self._ability(target)
                    actor.hp = max(0, actor.hp - max(1, actor.max_hp // 8))
                if target.mon["item"] == "Rocky Helmet":
                    actor.hp = max(0, actor.hp - max(1, actor.max_hp // 6))
        if did_hit and move in DRAIN:
            self._heal(actor, int(dealt * (.75 if move in {"Draining Kiss", "Oblivion Wing"} else .5)))
        if did_hit and actor.hp:
            changes, chance = mx.SELF_STAGES.get(move, ({}, 0))
            if changes and self.rng.random() * 100 < chance * (2 if actor.mon["ability"] == "Serene Grace" else 1):
                self._stage_event(actor, self._change_stages(actor, changes))
            if move in {"Rapid Spin", "Mortal Spin"} and self.hazards[side]:
                self.hazards[side] = {}
                self._event(f"{actor.name}은(는) 설치된 함정을 걷어냈다!", "field")
        if did_hit and dealt and move in mx.RECOIL and actor.mon["ability"] not in {"Rock Head", "Magic Guard"}:
            self._hurt(actor, dealt * mx.RECOIL[move], "은(는) 반동으로 데미지를 입었다")
        if did_hit and move == "Final Gambit":
            self._hurt(actor, actor.hp, "은(는) 목숨을 걸었다")
        if did_hit and (move == "Struggle" or actor.mon["item"] == "Life Orb" and actor.mon["ability"] not in {
            "Magic Guard", "Sheer Force"} or actor.mon["item"] == "Life Orb" and actor.mon["ability"] == "Sheer Force"
            and move not in mx.SECONDARY_STATUS and move not in mx.TARGET_STAGES and move not in mx.FLINCH
        ) and actor.mon["ability"] != "Magic Guard":
            divisor = 4 if move == "Struggle" else 10
            self._hurt(actor, max(1, actor.max_hp // divisor), "은(는) 생명이 조금 깎였다")
        actor.recharge = did_hit and bool(self.engine.M.get(move, {}).get("recharge"))
        if not (did_hit or neutral_result):
            actor.failed_move_turn = self.turn
        return did_hit

    def advance(self, my_actions: list[dict] | None = None, mega_slot=None):
        if self._pivot_slot is not None or self.replacement_slots():
            raise ValueError("교체할 대기 포켓몬을 먼저 골라 주세요.")
        if self.manual and my_actions is None:
            raise ValueError("필드에 있는 포켓몬마다 명령을 골라 주세요.")
        if my_actions is None:
            self._mega_turn()
            mine = self._auto(0)
        else:
            mine = my_actions
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
        if my_actions is not None:
            if mega_slot is not None and (not self.manual or not self.mega_left[0]
                    or mega_slot not in active or not active[mega_slot].mega_form
                    or by_slot[mega_slot]["kind"] != "move"):
                raise ValueError("이번 턴에 기술을 쓸 메가진화 후보를 골라 주세요.")
            self._mega_turn(mega_slot)
        if self._resolve_actions(mine, self._auto(1), interactive=self.manual):
            self._end_turn()

    def _resolve_actions(self, mine, theirs, *, interactive=False):
        actions = []
        for side, side_actions in enumerate((mine, theirs)):
            present = dict(self._present(side))
            for a in side_actions:
                actor = present[a["slot"]]
                priority = 7 if a["kind"] == "switch" else self._priority(actor, a.get("move"))
                actions.append((priority, self.rng.random(), side, actor, a))
        return self._run_actions(actions, interactive=interactive)

    def _run_actions(self, actions, *, interactive):
        def order(entry):
            priority, tie, side, actor, action = entry
            direction = -1 if self.trick_room and action["kind"] != "switch" else 1
            return priority, direction * self._speed(side, actor), tie

        while actions:
            priority, _, side, actor, action = actions.pop(max(range(len(actions)), key=lambda i: order(actions[i])))
            slot, kind = action["slot"], action["kind"]
            current = self.active[side][slot]
            if current is None or self.teams[side][current] is not actor:
                continue
            if not actor.hp or actor.flinched:
                if actor.hp and actor.flinched:
                    if kind == "move":
                        actor.failed_move_turn = self.turn
                    self._event(f"{actor.name}은(는) 풀죽어서 움직이지 못했다!")
                continue
            move, target = action.get("move"), action.get("target")
            if move not in PROTECT:
                actor.protect_chain = 0
            if kind == "switch":
                if side == 0 and self.turn == 1:
                    self.opening.append("교체")
                    self.opening_actions.append((actor.mon["id"], "switch", self.teams[side][target].mon["id"]))
                self._switch(side, slot, target, acts_next_turn=True)
            elif kind == "wait":
                actor.recharge = False
                self._event(f"{actor.name} 재충전")
            else:
                if actor.encore and actor.encore_move and move != actor.encore_move and not actor.charging:
                    move = actor.encore_move
                    target = None if move in SUPPORT and move not in TARGETED_SUPPORT else next(
                        (i for i, _ in self._present(1 - side)), None)
                    priority = self._priority(actor, move)
                if actor.taunt and move in SUPPORT:
                    actor.failed_move_turn = self.turn
                    self._event(f"{actor.name}의 {self._move_name(move)}은(는) 도발에 막혔다.")
                    continue
                if not self._can_act(actor, move):
                    actor.charging = None
                    actor.failed_move_turn = self.turn
                    continue
                if move != "Destiny Bond":
                    actor.destiny = False
                actor.last_move = move
                actor.known_moves.add(move)
                if side == 0 and self.turn == 1:
                    self.opening.append(move)
                    targets = dict(self._present(1))
                    aimed = targets.get(target)
                    self.opening_actions.append((actor.mon["id"], move, aimed.mon["id"] if aimed else ""))
                self._event(f"{'상대 ' if side else ''}{actor.name}의 {self._move_name(move)}!",
                            "move", side=side, ref=self._ref(actor), move=move,
                            moveId=self.engine.move_ids.get(move, "struggle"),
                            type=self.engine.M.get(move, {}).get("type"))
                if actor.mon["item"] in CHOICE and move != "Struggle":
                    actor.choice = move
                if move in SUPPORT:
                    success = self._support(side, slot, actor, move, target)
                    if success is False:
                        actor.failed_move_turn = self.turn
                else:
                    success = self._attack(side, slot, actor, move, target, priority, actions)
                if success and move in PIVOT and actor.hp and self._bench(side) and any(f.hp for f in self.teams[1 - side]):
                    if side == 0 and interactive:
                        self._pivot_slot = slot
                        self._replacement_phase += 1
                        self._pending = actions
                        self.updated = monotonic()
                        return False
                    self._switch(side, slot, self._best_reserve(side), acts_next_turn=True)
        return True

    def _best_reserve(self, side):
        opponents = [f for _, f in self._present(1 - side)]

        def value(index):
            candidate = self.teams[side][index]
            incoming, outgoing = [], []
            for foe in opponents:
                meta = self.engine.default_set(foe.mon["id"], self.fmt)["moves"]
                moves = list(dict.fromkeys([*sorted(foe.known_moves - {"Struggle"}), *meta]))[:4]
                incoming.append(max((self._coverage(move, candidate) for move in moves), default=1))
                outgoing.append(max((self._coverage(move, foe) for move in candidate.mon["moves"]), default=0))
            return (.23 * candidate.hp / candidate.max_hp + .22 * sum(outgoing)
                    - .36 * sum(incoming) + .17 * (candidate.mon["ability"] == "Intimidate"))

        return max(self._bench(side), key=value)

    def _coverage(self, move, target):
        meta = self.engine.M.get(move, {})
        if not meta.get("power"):
            return 0
        return min(1, meta["power"] / 90) * type_multiplier(meta["type"], target.mon["types"], target.mon["ability"])

    def _end_turn(self):
        for side in range(2):
            self.redirect[side] = None
            self.wide_guard[side] = False
            self.quick_guard[side] = False
            for slot, actor in self._present(side):
                guard = actor.mon["ability"] == "Magic Guard"
                if (self._wx == "sand" and not set(actor.mon["types"]) & {"Rock", "Ground", "Steel"} and not guard
                    and actor.mon["ability"] not in {"Sand Veil", "Sand Rush", "Sand Force", "Overcoat"}
                    and actor.mon["item"] != "Safety Goggles"):
                    self._hurt(actor, actor.max_hp // 16, "은(는) 모래바람에 데미지를 입었다")
                if actor.hp and actor.mon["ability"] == "Solar Power" and self._wx == "sun" and not guard:
                    self._hurt(actor, actor.max_hp // 8, "은(는) 선파워로 체력이 깎였다")
                wish = self.wish[side].get(slot)
                if wish:
                    turns, amount = wish
                    if turns <= 1:
                        del self.wish[side][slot]
                        if self._heal(actor, amount):
                            self._event(f"{actor.name}의 소원이 이루어졌다!", "heal", ref=self._ref(actor))
                    else:
                        self.wish[side][slot] = (turns - 1, amount)
                if self.terrain == "grassy" and self._grounded(actor):
                    self._heal(actor, actor.max_hp // 16)
                if actor.mon["item"] == "Leftovers" and actor.hp < actor.max_hp:
                    self._heal(actor, actor.max_hp // 16)
                    self._event(f"{actor.name}은(는) 먹다남은음식으로 체력을 회복했다.", "heal", ref=self._ref(actor))
                if actor.seeded and actor.hp and not guard:
                    drained = self._hurt(actor, actor.max_hp // 8, "의 체력을 씨앗이 빼앗는다")
                    receiver = next((f for _, f in self._present(1 - side)), None)
                    if receiver:
                        self._heal(receiver, drained)
                if actor.status in {"psn", "tox"} and actor.mon["ability"] == "Poison Heal":
                    self._heal(actor, actor.max_hp // 8)
                elif actor.status in {"psn", "tox"} and not guard:
                    if actor.status == "tox":
                        self._hurt(actor, actor.max_hp * actor.toxic // 16, "은(는) 맹독 데미지를 입었다")
                        actor.toxic = min(15, actor.toxic + 1)
                    else:
                        self._hurt(actor, actor.max_hp // 8, "은(는) 독 데미지를 입었다")
                elif actor.status == "brn" and not guard:
                    self._hurt(actor, actor.max_hp // 16, "은(는) 화상 데미지를 입었다")
                if actor.yawn:
                    actor.yawn -= 1
                    if not actor.yawn and actor.hp:
                        self._inflict(actor, "slp")
                if actor.encore:
                    actor.encore -= 1
                    if not actor.encore:
                        actor.encore_move = None
                        self._event(f"{actor.name}의 앙코르 상태가 풀렸다.", "status", ref=self._ref(actor))
                if actor.mon["ability"] == "Speed Boost" and actor.hp and actor.entered < self.turn + 1 and (
                    actor.stages.get("spe", 0) < 6):
                    self._ability(actor)
                    self._stage_event(actor, self._change_stages(actor, {"spe": 1}))
                actor.protected = actor.flinched = actor.helped = False
                actor.taunt = max(0, actor.taunt - 1)
            self.tailwind[side] = max(0, self.tailwind[side] - 1)
            for kind in list(self.screens[side]):
                self.screens[side][kind] -= 1
                if not self.screens[side][kind]:
                    del self.screens[side][kind]
        self.trick_room = max(0, self.trick_room - 1)
        self.terrain_turns = max(0, self.terrain_turns - 1)
        if not self.terrain_turns and self.terrain:
            self._event(f"{TERRAIN_LABELS[self.terrain]}이(가) 사라졌다.", "field", terrain="")
            self.terrain = ""
        self.weather_turns = max(0, self.weather_turns - 1)
        if not self.weather_turns and self.weather:
            self._event(f"{WEATHER_LABELS[self.weather]}이(가) 그쳤다.", "field", weather="")
            self.weather = ""
        for side in range(2):
            for slot, index in enumerate(self.active[side]):
                if index is not None and not self.teams[side][index].hp:
                    self.active[side][slot] = None
        self._check_winner()
        if not self.winner and self.turn >= MAX_TURNS:
            self.winner = "draw"
        if not self.winner and not self.replacement_slots():
            self._fill_vacancies(0, after_turn=True)
            self._fill_vacancies(1, after_turn=True)
            self._check_winner()  # 설치 기술로 마지막 포켓몬이 쓰러질 수 있다
        self.turn += 1
        self.updated = monotonic()

    def _check_winner(self):
        living = [any(f.hp for f in team) for team in self.teams]
        if not all(living):
            self.winner = ("win" if living[0] else "loss") if any(living) else "draw"

    def replacement_slots(self):
        if self.winner or not self.manual:
            return []
        return [i for i, active in enumerate(self.active[0]) if active is None] if self._bench(0) else []

    def replace(self, turn, choices, phase=None):
        if self._pivot_slot is not None:
            if turn != self.turn or phase != self._replacement_phase:
                return
            slot = self._pivot_slot
            if choices.keys() != {slot} or choices[slot] not in self._bench(0):
                raise ValueError("교체할 대기 포켓몬을 골라 주세요.")
            self._pivot_slot = None
            actions, self._pending = self._pending, []
            self._switch(0, slot, choices[slot], acts_next_turn=True)
            if self._run_actions(actions, interactive=True):
                self._end_turn()
            return
        if phase is not None:
            return
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
        self._check_winner()
        if not self.replacement_slots():
            self.replacement_turn = turn
        self.updated = monotonic()

    def _fill_vacancies(self, side, *, after_turn):
        while None in self.active[side] and self._bench(side):
            slot = self.active[side].index(None)
            self._switch(side, slot, self._best_reserve(side), acts_next_turn=after_turn)

    @staticmethod
    def _key(action: dict) -> tuple:
        return tuple(action.get(k) for k in ("kind", "move", "target"))

    def _switch(self, side: int, slot: int, incoming: int, *, acts_next_turn: bool = False):
        outgoing = self.active[side][slot]
        if outgoing is not None:
            fighter = self.teams[side][outgoing]
            if fighter.mon["ability"] == "Regenerator" and self._heal(fighter, fighter.max_hp // 3):
                self._ability(fighter)
            fighter.withdraw()
            self._event(f"{'상대 ' if side else ''}{fighter.name} 교체 아웃", "withdraw", ref=self._ref(fighter))
        self.active[side][slot] = incoming
        if self.redirect[side] is not None and self.redirect[side][0] == slot:
            self.redirect[side] = None
        self.seen[side].add(incoming)
        fighter = self.teams[side][incoming]
        fighter.entered = self.turn + 1 if acts_next_turn else self.turn
        self._event(f"{'상대 ' if side else ''}{fighter.name} 등장", "entry", ref=self._ref(fighter))
        wish = self.wish[side].get(slot)
        if wish and wish[0] == 0:
            del self.wish[side][slot]
            fighter.hp = fighter.max_hp
            fighter.status = ""
            self._event(f"{fighter.name}의 체력이 회복되었다!", "heal", ref=self._ref(fighter))
        self._entry_hazards(side, fighter)
        if not fighter.hp:
            self.active[side][slot] = None
            return
        self._on_entry(side, fighter)

    def _entry_hazards(self, side, fighter):
        hazards = self.hazards[side]
        if not hazards or fighter.mon["item"] == "Heavy-Duty Boots":
            return
        guard = fighter.mon["ability"] == "Magic Guard"
        if hazards.get("rocks") and not guard:
            share = type_multiplier("Rock", fighter.mon["types"]) / 8
            self._hurt(fighter, fighter.max_hp * share, "에게 뾰족한 바위가 박혔다")
        if not self._grounded(fighter):
            return
        if hazards.get("spikes") and not guard and fighter.hp:
            share = {1: 1 / 8, 2: 1 / 6}.get(hazards["spikes"], 1 / 4)
            self._hurt(fighter, fighter.max_hp * share, "은(는) 압정뿌리기에 데미지를 입었다")
        if hazards.get("tspikes") and fighter.hp:
            if "Poison" in fighter.mon["types"]:
                del hazards["tspikes"]
                self._event(f"{fighter.name}이(가) 독압정을 흡수했다!", "field")
            else:
                self._inflict(fighter, "tox" if hazards["tspikes"] >= 2 else "psn")
        if hazards.get("web") and fighter.hp:
            self._event(f"{fighter.name}은(는) 끈적끈적네트에 걸렸다!")
            self._lower(fighter, {"spe": -1}, fighter)

    def view(self, battle_id: str) -> dict:
        def member(f):
            return {**{k: f.mon[k] for k in ("id", "name", "ko", "sprite", "types")},
                    "hp": f.hp, "maxHp": f.max_hp, "dealt": f.dealt, "taken": f.taken, "kos": f.kos,
                    "status": f.status, "stages": {k: v for k, v in f.stages.items() if v},
                    "mega": bool(f.mon.get("mega")), "sub": bool(f.sub)}

        field = [
            (WEATHER_LABELS.get(self.weather), self.weather_turns), (TERRAIN_LABELS.get(self.terrain), self.terrain_turns),
            ("트릭룸", self.trick_room), ("내 순풍", self.tailwind[0]), ("상대 순풍", self.tailwind[1]),
        ]
        names = {"reflect": "리플렉터", "light": "빛의장막", "veil": "오로라베일"}
        for side, label in ((0, "내 "), (1, "상대 ")):
            field.extend((label + names[k], t) for k, t in self.screens[side].items())
        slots = self.replacement_slots()
        replacement = {"slots": slots, "bench": self._bench(0)} if slots else None
        if self._pivot_slot is not None:
            replacement = {"kind": "pivot", "phase": self._replacement_phase,
                           "slots": [self._pivot_slot], "bench": self._bench(0)}
        return {"id": battle_id, "turn": self.turn, "seed": self.seed, "winner": self.winner,
                "difficulty": self.difficulty,
                "megaOptions": [slot for slot, f in self._present(0) if f.mega_form and not f.recharge]
                if self.manual and self.mega_left[0] and not self.winner and not replacement else [],
                "replacement": replacement,
                "field": [f"{name} {turns}턴" for name, turns in field if turns],
                "teams": [[member(f) if side == 0 or not self.manual or self.winner or i in self.seen[side] else None
                           for i, f in enumerate(team)] for side, team in enumerate(self.teams)],
                "active": [side.copy() for side in self.active],
                "weather": self.weather, "terrain": self.terrain, "trickRoom": bool(self.trick_room),
                "hazards": [{k: v for k, v in h.items() if v} for h in self.hazards],
                "options": [] if self.winner or replacement else [
                    {"slot": slot, "options": self._options(0, slot, f)} for slot, f in self._present(0)
                ], "log": self.log.copy() if self.winner else self.log[-100:], "logCount": len(self.log),
                **self.context}


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

    def advance(self, key: str, turn: int, actions: list[dict] | None, mega_slot=None) -> dict:
        with self.lock:
            battle = self._session(key)
            if turn > battle.turn:
                raise ValueError("invalid turn")
            if not battle.winner and turn == battle.turn and battle._pivot_slot is None:
                battle.advance(actions, mega_slot)
            self.battles.move_to_end(key)
            return battle.view(key)

    def replace(self, key: str, turn: int, choices: dict[int, int], phase=None) -> dict:
        with self.lock:
            battle = self._session(key)
            battle.replace(turn, choices, phase)
            self.battles.move_to_end(key)
            return battle.view(key)

    def _session(self, key):
        battle = self.battles.get(key)
        if not battle or monotonic() - battle.updated > 3600:
            self.battles.pop(key, None)
            raise KeyError(key)
        return battle
