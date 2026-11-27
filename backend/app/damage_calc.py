"""데미지 계산기 (앱의 '데미지 계산' 화면).

배틀 엔진의 Engine.damage(평균 난수 0.925 기준 근사)를 그대로 쓰고, 난수 16단계(0.85~1.00)로 최소~최대와
몇 번에 쓰러뜨리는지(확정/난수 n타 확률)를 낸다. 랭크·급소·도우미·벽은 여기서 수치에 반영한다.
엔진과 같은 근사라 실제 게임과 1~2% 차이가 날 수 있다.
"""
from __future__ import annotations

import math

from .engine import Engine
from .mechanics import FLINCH

ROLLS = [(85 + i) / 100 for i in range(16)]


def _stage(v: float, s: int) -> float:
    s = max(-6, min(6, s))
    return v * (2 + s) / 2 if s >= 0 else v * 2 / (2 - s)


def _ko(rolls_hp: list[int], hp: int, max_hits: int = 6):
    """(n, 확률): n번 맞혀 쓰러뜨릴 확률이 처음으로 0보다 커지는 n 과 그 확률 (난수 16단계 균등)."""
    n, chance, _ = _ko_detail(rolls_hp, hp, max_hits)
    return n, chance


def _ko_detail(rolls_hp: list[int], hp: int, max_hits: int = 8):
    """(처음 쓰러뜨릴 수 있는 횟수, 그 확률, 확정으로 쓰러뜨리는 횟수)"""
    if not rolls_hp or max(rolls_hp) <= 0:
        return None, 0., None
    first, chance_first = None, 0.
    dist = {0: 1.}
    for n in range(1, max_hits + 1):
        nxt = {}
        for total, p in dist.items():
            for r in rolls_hp:
                key = min(total + r, hp)  # HP 이상은 한데 모아 상태 수를 줄인다
                nxt[key] = nxt.get(key, 0.) + p / len(rolls_hp)
        dist = nxt
        chance = dist.get(hp, 0.)
        if chance > 0 and first is None:
            first, chance_first = n, chance
        if chance >= .9995:
            return first, chance_first, n
    return first, chance_first, None


def calc(e: Engine, fmt: str, attacker: dict, defender: dict, *, weather: str = "auto", spread: bool | None = None,
         crit: bool = False, helping_hand: bool = False, screen: bool = False, atk_stage: int = 0, def_stage: int = 0,
         psychic_terrain: bool = False, hp_pct: int = 100) -> dict:
    a, b = e.resolve(attacker, fmt), e.resolve(defender, fmt)
    hp = b["stats"]["hp"]
    current = max(1, math.ceil(hp * max(1, min(100, hp_pct)) / 100))
    rows = []
    for move in a["moves"]:
        m = e.M.get(move)
        accuracy = m.get("accuracy") if m else None
        if not m or m["category"] == "Status" or not m["power"]:
            rows.append({"move": move, "ko": m.get("ko") if m else None, "status": True,
                         "type": m["type"] if m else None, "category": m["category"] if m else None,
                         "accuracy": accuracy})
            continue
        phys = m["category"] == "Physical"
        atk_key = "def" if move == "Body Press" else ("atk" if phys else "spa")
        def_key = "def" if phys or move in ("Psyshock", "Psystrike", "Secret Sword") else "spd"
        sa, sb = atk_stage, def_stage
        if crit:  # 급소: 내 능력 하락과 상대 능력 상승을 무시
            sa, sb = max(0, sa), min(0, sb)
        aa = {**a, "stats": {**a["stats"], atk_key: _stage(a["stats"][atk_key], sa)}}
        bb = {**b, "stats": {**b["stats"], def_key: _stage(b["stats"][def_key], sb)}}
        h = e.damage(aa, move, bb, fmt, spread=spread, full_hp=hp_pct >= 100, recharge_discount=False,
                     weather=None if weather == "auto" else ("" if weather == "none" else weather),
                     psychic_terrain=psychic_terrain, estimate_intimidate=False,
                     power_multiplier=1.5 if helping_hand else 1)
        if h is None:
            rows.append({"move": move, "ko": m.get("ko"), "status": True, "type": m["type"], "category": m["category"]})
            continue
        mult = (1.5 if crit else 1) * (1 if crit or not screen else (2732 / 4096 if fmt == "Doubles" else .5))
        top = h["pct"] / 100 / .925 * hp * mult  # 난수 1.00 일 때 HP 데미지
        rolls_hp = [math.floor(top * r) for r in ROLLS]
        n, chance, sure = _ko_detail(rolls_hp, current)
        rows.append({
            "move": move, "ko": m.get("ko"), "type": h["type"], "category": m["category"], "power": m["power"],
            "accuracy": accuracy, "flinch": m.get("flinch", FLINCH.get(move, 0)),
            "eff": h["eff"], "minHp": rolls_hp[0], "maxHp": rolls_hp[-1],
            "minPct": round(100 * rolls_hp[0] / hp, 1), "maxPct": round(100 * rolls_hp[-1] / hp, 1),
            "hits": n, "chance": round(chance, 3), "sureHits": sure, "spread": spread if spread is not None else None,
        })
    summary = lambda r: {k: r[k] for k in ("id", "name", "ko", "sprite", "types", "ability", "item", "nature",
                                           "stats", "mega")}
    return {"attacker": summary(a), "defender": summary(b), "defenderHp": hp, "currentHp": current, "moves": rows}
