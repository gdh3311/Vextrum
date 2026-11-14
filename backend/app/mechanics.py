"""포켓몬 챔피언스 배틀 규칙 (가상 배틀 시뮬레이터용).

근거 (2026-11 조사):
- Game8 상태 이상 가이드 https://game8.co/games/Pokemon-Champions/archives/594084
- Championspedia (v1.2.0 게임 내 설명) https://thechampionspedia.com/status-conditions
- Smogon Champions Battle Mechanics Research https://www.smogon.com/forums/threads/champions-battle-mechanics-research.3780372/
- 커뮤니티 검증 문서 https://github.com/alfredocox/Pokemon-Champions-Sim-Planner/blob/main/CHAMPIONS_MECHANICS_VERIFICATION.md

챔피언스에서 본가(SV)와 달라진 점:
- 마비: 스피드 ×0.5, 행동 불가 12.5% (SV 25%)
- 잠듦: 1턴째 반드시 잠, 2턴째 1/3 확률로 깸, 3턴째 반드시 깸
- 얼음: 행동 시도마다 25% 확률로 풀림, 3턴째 반드시 풀림. 불꽃 기술에 맞으면 풀림
- 맹독: 1/16, 2/16, … 교체하면 1/16로 초기화
- 급소: 1/24, ×1.5 / 데미지 난수 85~100%
- 기술 변경: 위력·명중·추가 효과 확률 일부 (CHAMPIONS_MOVES)
그 밖의 수치는 본가와 같다고 본다.
"""
from __future__ import annotations

import json

RULES_CONTRACT = "champions-local-2026.11-r1"

# ---------------------------------------------------------------- 기술 데이터 보정 (SV → 챔피언스)
CHAMPIONS_MOVES = {
    "Apple Acid": {"power": 90}, "Beak Blast": {"power": 120}, "Bone Rush": {"power": 30},
    "Fire Lash": {"power": 90}, "First Impression": {"power": 100}, "Grav Apple": {"power": 90},
    "Infernal Parade": {"power": 65}, "Mountain Gale": {"power": 120}, "Night Daze": {"power": 90},
    "Psyshield Bash": {"power": 90}, "Spirit Shackle": {"power": 90}, "Trop Kick": {"power": 85},
    "Crabhammer": {"accuracy": 95}, "Syrup Bomb": {"accuracy": 90},
    "Growth": {"type": "Grass"}, "Snap Trap": {"type": "Steel"},
}
# 무게에 따라 위력이 바뀌는 기술과 고정 데미지 기술: 기술 목록에서 빠지지 않도록 기준 위력을 준다
VARIABLE_POWER = {"Low Kick": 60, "Grass Knot": 60, "Heavy Slam": 60, "Heat Crash": 60}
HALF_HP = {"Super Fang", "Ruination", "Nature's Madness"}


def patch_moves(moves: dict) -> None:
    for name, change in CHAMPIONS_MOVES.items():
        if name in moves:
            moves[name].update(change)
    for name, power in VARIABLE_POWER.items():
        if name in moves and not moves[name].get("power"):
            moves[name].update(power=power, variable=True)
    for name in HALF_HP:
        if name in moves and not moves[name].get("power"):
            moves[name].update(power=1, fixed="half")
    for name, kind in FIXED_DAMAGE.items():
        if name in moves and not moves[name].get("power"):
            moves[name].update(power=1, fixed=kind)


# ---------------------------------------------------------------- 상태 이상
STATUS_LABELS = {"brn": "화상", "par": "마비", "slp": "잠듦", "psn": "독", "tox": "맹독", "frz": "얼음"}
STATUS_MOVES = {
    "Will-O-Wisp": "brn", "Thunder Wave": "par", "Glare": "par", "Stun Spore": "par", "Nuzzle": "par",
    "Spore": "slp", "Sleep Powder": "slp", "Hypnosis": "slp", "Lovely Kiss": "slp", "Sing": "slp",
    "Toxic": "tox", "Poison Powder": "psn",
}
POWDER = {"Spore", "Sleep Powder", "Stun Spore", "Poison Powder", "Rage Powder"}
STATUS_IMMUNE_TYPES = {"brn": {"Fire"}, "par": {"Electric"}, "psn": {"Poison", "Steel"}, "tox": {"Poison", "Steel"},
                       "frz": {"Ice"}, "slp": set()}
STATUS_IMMUNE_ABILITIES = {
    "brn": {"Water Veil", "Water Bubble", "Thermal Exchange"}, "par": {"Limber"},
    "slp": {"Insomnia", "Vital Spirit", "Sweet Veil"}, "psn": {"Immunity", "Pastel Veil"},
    "tox": {"Immunity", "Pastel Veil"}, "frz": {"Magma Armor"},
}
ALL_STATUS_IMMUNE = {"Purifying Salt", "Comatose", "Good as Gold"}
# 공격 기술의 추가 효과: 상태 이상 (확률 %)
SECONDARY_STATUS = {
    "Scald": ("brn", 30), "Scorching Sands": ("brn", 30), "Lava Plume": ("brn", 30), "Sacred Fire": ("brn", 50),
    "Heat Wave": ("brn", 10), "Flamethrower": ("brn", 10), "Fire Blast": ("brn", 10), "Flare Blitz": ("brn", 10),
    "Fire Punch": ("brn", 10), "Blaze Kick": ("brn", 10), "Matcha Gotcha": ("brn", 20), "Pyro Ball": ("brn", 10),
    "Thunderbolt": ("par", 10), "Thunder": ("par", 30), "Discharge": ("par", 30), "Body Slam": ("par", 30),
    "Thunder Punch": ("par", 10), "Volt Tackle": ("par", 10), "Nuzzle": ("par", 100), "Force Palm": ("par", 30),
    "Zap Cannon": ("par", 100), "Bounce": ("par", 30), "Dragon Breath": ("par", 30),
    "Ice Beam": ("frz", 10), "Blizzard": ("frz", 10), "Ice Punch": ("frz", 10),
    "Sludge Bomb": ("psn", 30), "Poison Jab": ("psn", 30), "Gunk Shot": ("psn", 30), "Sludge Wave": ("psn", 10),
    "Cross Poison": ("psn", 10), "Mortal Spin": ("psn", 100), "Malignant Chain": ("tox", 50),
    "Dire Claw": ("dire", 30),  # 챔피언스: 50% → 30%, 독·마비·잠듦 중 하나
}
FLINCH = {
    "Rock Slide": 30, "Air Slash": 30, "Iron Head": 20, "Bite": 30, "Dark Pulse": 20, "Zen Headbutt": 20,
    "Waterfall": 20, "Icicle Crash": 30, "Headbutt": 30, "Extrasensory": 10, "Twister": 20, "Astonish": 30,
    "Stomp": 30, "Double Iron Bash": 30, "Fire Fang": 10, "Ice Fang": 10, "Thunder Fang": 10,
    "Heart Stamp": 30, "Steamroller": 30, "Upper Hand": 100, "Fake Out": 100,
}
# 맞은 상대의 능력 변화 (확률 %)
TARGET_STAGES = {
    "Moonblast": ({"spa": -1}, 10), "Spirit Break": ({"spa": -1}, 100), "Breaking Swipe": ({"atk": -1}, 100),
    "Lunge": ({"atk": -1}, 100), "Trop Kick": ({"atk": -1}, 100), "Mystical Fire": ({"spa": -1}, 100),
    "Struggle Bug": ({"spa": -1}, 100), "Fire Lash": ({"def": -1}, 100), "Crunch": ({"def": -1}, 20),
    "Shadow Ball": ({"spd": -1}, 20), "Psychic": ({"spd": -1}, 10), "Earth Power": ({"spd": -1}, 10),
    "Bug Buzz": ({"spd": -1}, 10), "Energy Ball": ({"spd": -1}, 10), "Flash Cannon": ({"spd": -1}, 10),
    "Focus Blast": ({"spd": -1}, 10), "Liquidation": ({"def": -1}, 20), "Play Rough": ({"atk": -1}, 10),
    "Mud Shot": ({"spe": -1}, 100), "Thunderous Kick": ({"def": -1}, 100), "Apple Acid": ({"spd": -1}, 100),
    "Grav Apple": ({"def": -1}, 100), "Skitter Smack": ({"spa": -1}, 100), "Acid Spray": ({"spd": -2}, 100),
    "Lumina Crash": ({"spd": -2}, 100), "Bitter Malice": ({"atk": -1}, 100), "Chilling Water": ({"atk": -1}, 100),
    "Pounce": ({"spe": -1}, 100), "Mud-Slap": ({"spe": -1}, 100), "Triple Arrows": ({"def": -1}, 50),
}
# 쓴 포켓몬 자신의 능력 변화 (확률 %)
SELF_STAGES = {
    "Close Combat": ({"def": -1, "spd": -1}, 100), "Draco Meteor": ({"spa": -2}, 100), "Overheat": ({"spa": -2}, 100),
    "Leaf Storm": ({"spa": -2}, 100), "Fleur Cannon": ({"spa": -2}, 100), "Psycho Boost": ({"spa": -2}, 100),
    "Make It Rain": ({"spa": -1}, 100), "Superpower": ({"atk": -1, "def": -1}, 100),
    "Armor Cannon": ({"def": -1, "spd": -1}, 100), "Headlong Rush": ({"def": -1, "spd": -1}, 100),
    "Hammer Arm": ({"spe": -1}, 100), "Ice Hammer": ({"spe": -1}, 100),
    "V-create": ({"def": -1, "spd": -1, "spe": -1}, 100), "Clanging Scales": ({"def": -1}, 100),
    "Dragon Ascent": ({"def": -1, "spd": -1}, 100), "Hyperspace Fury": ({"def": -1}, 100),
    "Spin Out": ({"spe": -2}, 100), "Flame Charge": ({"spe": 1}, 100), "Trailblaze": ({"spe": 1}, 100),
    "Rapid Spin": ({"spe": 1}, 100), "Power-Up Punch": ({"atk": 1}, 100), "Aqua Step": ({"spe": 1}, 100),
    "Esper Wing": ({"spe": 1}, 100), "Torch Song": ({"spa": 1}, 100), "Meteor Mash": ({"atk": 1}, 20),
    "Charge Beam": ({"spa": 1}, 70), "Scale Shot": ({"def": -1, "spe": 1}, 100),
}
RECOIL = {
    "Flare Blitz": 1 / 3, "Brave Bird": 1 / 3, "Wave Crash": 1 / 3, "Double-Edge": 1 / 3, "Wood Hammer": 1 / 3,
    "Volt Tackle": 1 / 3, "Head Smash": 1 / 2, "Light of Ruin": 1 / 2, "Take Down": 1 / 4, "Wild Charge": 1 / 4,
    "Head Charge": 1 / 4, "Submission": 1 / 4,
}
HIGH_CRIT = {
    "Leaf Blade", "Night Slash", "Stone Edge", "Cross Chop", "Shadow Claw", "Psycho Cut", "Slash", "Drill Run",
    "Crabhammer", "Aqua Cutter", "Blaze Kick", "Air Cutter", "Razor Leaf", "Karate Chop", "Spacial Rend",
    "Snipe Shot", "Cross Poison", "Poison Tail", "Esper Wing", "Triple Arrows", "Ivy Cudgel", "Attack Order",
    "Kowtow Cleave",
}
ALWAYS_CRIT = {"Wicked Blow", "Surging Strikes", "Flower Trick", "Frost Breath", "Storm Throw", "Zippy Zap"}
CRIT_CHANCE = [1 / 24, 1 / 8, 1 / 2, 1.]

# ---------------------------------------------------------------- 보조 기술
EXTRA_BOOSTS = {
    "Cosmic Power": {"def": 1, "spd": 1}, "Coil": {"atk": 1, "def": 1}, "Work Up": {"atk": 1, "spa": 1},
    "Growth": {"atk": 1, "spa": 1}, "Howl": {"atk": 1}, "Victory Dance": {"atk": 1, "def": 1, "spe": 1},
    "Tail Glow": {"spa": 3}, "Cotton Guard": {"def": 3}, "Acid Armor": {"def": 2}, "Shelter": {"def": 2},
    "Stockpile": {"def": 1, "spd": 1}, "No Retreat": {"atk": 1, "def": 1, "spa": 1, "spd": 1, "spe": 1}, "Rock Polish": {"spe": 2}, "Shift Gear": {"atk": 1, "spe": 2}, "Amnesia": {"spd": 2},
    "Autotomize": {"spe": 2}, "Curse": {"atk": 1, "def": 1, "spe": -1}, "Clangorous Soul":
        {"atk": 1, "def": 1, "spa": 1, "spd": 1, "spe": 1}, "Belly Drum": {"atk": 6}, "Fillet Away":
        {"atk": 2, "spa": 2, "spe": 2}, "Tidy Up": {"atk": 1, "spe": 1}, "Geomancy": {"spa": 2, "spd": 2, "spe": 2},
}
HP_COST = {"Clangorous Soul": 1 / 3, "Belly Drum": 1 / 2, "Fillet Away": 1 / 2}
TARGET_DEBUFFS = {
    "Charm": {"atk": -2}, "Feather Dance": {"atk": -2}, "Screech": {"def": -2}, "Fake Tears": {"spd": -2},
    "Metal Sound": {"spd": -2}, "Scary Face": {"spe": -2}, "Tickle": {"atk": -1, "def": -1}, "Growl": {"atk": -1},
    "Noble Roar": {"atk": -1, "spa": -1}, "Eerie Impulse": {"spa": -2}, "Captivate": {"spa": -2},
    "Toxic Thread": {"spe": -2},  # 챔피언스: 스피드 -1 → -2 (독도 건다)
}
SCREENS = {"Reflect": "reflect", "Light Screen": "light", "Aurora Veil": "veil"}
HAZARDS = {"Stealth Rock", "Spikes", "Toxic Spikes", "Sticky Web"}
OTHER_SUPPORT = {"Encore", "Substitute", "Leech Seed", "Pain Split", "Wish", "Life Dew", "Strength Sap", "Yawn",
                 "Coaching", "Lunar Blessing", "Jungle Healing", "Defog", "Haze", "Healing Wish", "Memento",
                 "Destiny Bond", "Rest", "Heal Pulse"}
# 레벨·HP로 정해지는 고정 데미지 (챔피언스는 레벨 50)
FIXED_DAMAGE = {"Night Shade": "level", "Seismic Toss": "level", "Endeavor": "endeavor", "Final Gambit": "gambit"}
SOUND = {"Hyper Voice", "Boomburst", "Bug Buzz", "Snarl", "Overdrive", "Torch Song", "Clanging Scales",
         "Alluring Voice", "Psychic Noise", "Echoed Voice", "Disarming Voice", "Sparkling Aria", "Round"}

# 기술 목록 필터와 AI가 보조기로 다루도록 SUPPORT 에 넣을 이름들
NEW_SUPPORT = (set(STATUS_MOVES) - {"Nuzzle"}) | set(EXTRA_BOOSTS) | set(TARGET_DEBUFFS) | set(SCREENS) | HAZARDS \
    | OTHER_SUPPORT

_weights: dict | None = None


def weight(engine, pid: str) -> float:
    """포켓몬 무게(kg). Showdown 도감에서 한 번 받아 캐시한다. 모르면 60kg."""
    global _weights
    if _weights is None:
        from . import collector

        path = collector.CACHE / "pokedex.json"
        try:
            if not path.exists():
                collector.fetch("https://play.pokemonshowdown.com/data/pokedex.json", path)
            data = json.loads(path.read_text(encoding="utf-8"))
            _weights = {k: v.get("weightkg", 60.) for k, v in data.items()}
        except Exception:
            _weights = {}
    return _weights.get(pid, 60.)


def weight_power(move: str, attacker_kg: float, target_kg: float) -> int:
    if move in ("Low Kick", "Grass Knot"):
        for limit, power in ((10, 20), (25, 40), (50, 60), (100, 80), (200, 100)):
            if target_kg < limit:
                return power
        return 120
    ratio = attacker_kg / max(target_kg, .1)
    for minimum, power in ((5, 120), (4, 100), (3, 80), (2, 60)):
        if ratio >= minimum:
            return power
    return 40
