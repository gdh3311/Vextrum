"""Ranked CPU planning from visible battle state and commonly used sets."""
from collections import Counter
from copy import copy
from dataclasses import replace
from itertools import product
from random import Random

from .simulation import HEAL, PIVOT, PROTECT, REACTIVE, REDIRECT, SPEED_DROP, SUPPORT, WEATHER_SPEED


def _copy_battle(battle):
    forecast = copy(battle)
    forecast.teams = [
        [replace(f, stages=f.stages.copy(), known_moves=f.known_moves.copy(), victims=Counter()) for f in team]
        for team in battle.teams
    ]
    forecast.active = [slots.copy() for slots in battle.active]
    forecast.seen = [seen.copy() for seen in battle.seen]
    forecast.activated = [effects.copy() for effects in battle.activated]
    forecast.tailwind = battle.tailwind.copy()
    forecast.redirect = battle.redirect.copy()
    forecast.wide_guard = battle.wide_guard.copy()
    forecast.quick_guard = battle.quick_guard.copy()
    forecast.screens = [dict(x) for x in battle.screens]
    forecast.hazards = [dict(x) for x in battle.hazards]
    forecast.wish = [dict(x) for x in battle.wish]
    forecast.log = []
    forecast.keep_log = False
    return forecast


def _observation(battle):
    forecast = _copy_battle(battle)
    forecast._hidden_count = sum(1 for i, f in enumerate(battle.teams[0]) if i not in battle.seen[0] and f.hp)
    for i, fighter in enumerate(forecast.teams[0]):
        if i not in battle.seen[0]:
            fighter.hp = 0
            continue
        pid = fighter.mon["id"]
        default = battle.engine.default_set(pid, battle.fmt)
        observed = sorted(fighter.known_moves - {"Struggle"})
        moves = list(dict.fromkeys(observed + default["moves"]))
        # Entry announcements and the current form are visible. Item and investment are estimates.
        if fighter.ability_revealed:
            default["ability"] = fighter.mon["ability"]
        if fighter.mon["mega"] != default["mega"]:
            default["mega"] = fighter.mon["mega"]
            if default["item"] and battle.engine.find_mega(battle.engine.P[pid], stone=default["item"]):
                default["item"] = None
        ratio = fighter.hp / fighter.max_hp
        fighter.mon = battle.engine.resolve({**default, "moves": moves}, battle.fmt)
        fighter.hp = max(1, round(ratio * fighter.max_hp)) if ratio else 0
        fighter.choice = None
        fighter.item_used = False
    return forecast


def _attack_value(battle, side, slot, actor, action):
    move = action["move"]
    targets = battle._targets(side, slot, move, action.get("target"))
    allies = {id(f) for _, f in battle._present(side)}
    value = 0.
    for target in targets:
        ally = id(target) in allies
        if not ally and battle._priority_blocked(side, target, actor, move):
            continue
        damage, accuracy = battle._damage(actor, target, move, len(targets) > 1)
        score = min(target.hp, damage) / target.max_hp + .35 * (damage >= target.hp)
        if damage and not ally:
            if move == "Fake Out" and target.mon["ability"] not in {"Inner Focus", "Shield Dust"}:
                score += .32
            elif move in SPEED_DROP:
                score += .07
            elif move in PIVOT and battle._bench(side):
                score += .12
        if move in REACTIVE:
            score *= .7
        value += (-score if ally else score) * accuracy / 100
    return value


def _incoming(battle, side, target):
    pressure = 0.
    for _, attacker in battle._present(1 - side):
        hits = [battle._damage(attacker, target, move, False) for move in battle._moves(attacker)
                if move not in SUPPORT and not battle._priority_blocked(1 - side, target, attacker, move)]
        pressure += max((damage * accuracy / 100 for damage, accuracy in hits), default=0)
    return pressure / max(1, target.hp)


def _alternatives(battle, side, base):
    choices = []
    for first in base:
        slot = first["slot"]
        actor = dict(battle._present(side))[slot]
        options = battle._options(side, slot, actor)
        attacks, tactics, switches, pivots = [], [], [], []
        danger = _incoming(battle, side, actor)
        for action in options:
            move = action.get("move")
            if action["kind"] == "switch":
                incoming = battle.teams[side][action["target"]]
                relief = min(1.5, danger) - min(1.5, _incoming(battle, side, incoming))
                entry = .12 * (incoming.mon["ability"] in {"Intimidate", "Grassy Surge", "Psychic Surge"})
                switches.append((.16 + .45 * relief + entry, action))
            elif move is None:
                continue
            elif move not in SUPPORT:
                row = (_attack_value(battle, side, slot, actor, action), action)
                attacks.append(row)
                if move in PIVOT and battle._bench(side) and row[0] > 0:
                    pivots.append(row)
            elif move in PIVOT:
                if battle._bench(side) or move == "Parting Shot":
                    pivots.append((.38, action))
            elif move in PROTECT:
                tactics.append((.12 + .4 * min(1.3, danger) / (3 ** actor.protect_chain), action))
            elif move in REDIRECT or move == "Helping Hand":
                if len(base) == 2:
                    tactics.append((.42, action))
            elif move in {"Wide Guard", "Quick Guard"}:
                foes = battle._present(1 - side)
                useful = (any(a.get("scope") for i, f in foes for a in battle._options(1 - side, i, f))
                          if move == "Wide Guard" else
                          any(battle._priority(f, m) > 0 and m not in SUPPORT for _, f in foes for m in battle._moves(f)))
                if useful:
                    tactics.append((.5, action))
            elif move in HEAL:
                tactics.append((.65 * (1 - actor.hp / actor.max_hp), action))
            elif (value := battle._support_value(side, slot, actor, action)) is not None:
                if value > .05:
                    tactics.append((value, action))
            else:
                tactics.append((.28, action))
        ranked = sorted(attacks, key=lambda row: row[0], reverse=True)
        # Keep a credible move into each target so focusing and splitting are both possible.
        best_by_target = {}
        for score, action in ranked:
            best_by_target.setdefault(action.get("target"), (score, action))
        tempo = next((row for row in ranked if (
            row[1]["move"] in SPEED_DROP or battle._priority(actor, row[1]["move"]) > 0
        ) and row[0] > 0), None)
        tactical = sorted(tactics, key=lambda row: row[0], reverse=True)[:2]
        switch = sorted(switches, key=lambda row: row[0], reverse=True)[:2]
        pivot = sorted(pivots, key=lambda row: row[0], reverse=True)[:1]
        selected = list(best_by_target.values()) + tactical + switch
        selected.extend(row for row in pivot if row not in selected)
        if tempo and tempo not in selected:
            selected.append(tempo)
        if not any(battle._key(a) == battle._key(first) for _, a in selected):
            selected.insert(0, (.4, first))
        choices.append(selected)
    return choices


def _plan_key(battle, actions):
    return tuple(battle._key(a) for a in actions)


def _plans(battle, side, budget):
    base = battle._greedy(side)
    alternatives = _alternatives(battle, side, base)
    scored = []
    for combination in product(*alternatives):
        scores, actions = zip(*combination) if combination else ((), ())
        switches = {a["target"] for a in actions if a["kind"] == "switch"}
        if len(switches) != sum(a["kind"] == "switch" for a in actions):
            continue
        moves = [a.get("move") for a in actions]
        if len(moves) == 2 and moves[0] == moves[1] and moves[0] in {
            "Tailwind", "Trick Room", "Wide Guard", "Quick Guard", "Helping Hand", *REDIRECT
        }:
            continue
        scored.append((sum(scores), actions))
    scored.sort(key=lambda row: row[0], reverse=True)
    plans = [base]
    keys = {_plan_key(battle, actions) for actions in plans}
    predicates = (
        lambda a: a.get("move") in PROTECT or a.get("move") in REDIRECT | {"Wide Guard", "Quick Guard"},
        lambda a: a["kind"] == "switch",
        lambda a: a.get("move") in PIVOT,
    )
    for predicate in predicates:
        if len(plans) >= budget:
            break
        line = next((actions for _, actions in scored if _plan_key(battle, actions) not in keys
                     and any(predicate(action) for action in actions)), None)
        if line:
            plans.append(list(line))
            keys.add(_plan_key(battle, line))
    for _, actions in scored:
        if len(plans) >= budget:
            break
        key = _plan_key(battle, actions)
        if key not in keys:
            plans.append(list(actions))
            keys.add(key)
    return plans


def _position(battle, side):
    material = sum(f.hp / f.max_hp + .65 * bool(f.hp) for f in battle.teams[side])
    field = .045 * battle.tailwind[side] + .05 * sum(battle.screens[side].values())
    field -= .04 * len(battle._bench(side)) * len(battle.hazards[side])
    direction = -1 if battle.trick_room else 1
    opponents = [f for _, f in battle._present(1 - side)]
    rivals = [battle._speed(1 - side, f) for f in opponents]
    for _, actor in battle._present(side):
        if rivals:
            field += .075 * sum(direction * (battle._speed(side, actor) - r) > 0 for r in rivals) / len(rivals)
        field += .075 * sum(actor.stages.get(stat, 0) for stat in ("atk", "spa"))
        field -= .05 * bool(actor.taunt)
        field -= {"slp": .3, "frz": .25, "par": .12, "brn": .14, "tox": .12, "psn": .07}.get(actor.status, 0)
        field += .06 * bool(actor.sub) - .05 * actor.seeded - .15 * bool(actor.encore)
        field += .06 * (WEATHER_SPEED.get(actor.mon["ability"]) == battle.weather)
        if opponents:
            reach = [max((battle._coverage(m, target) for m in actor.mon["moves"]), default=0) for target in opponents]
            field += .12 * min(3, max(reach))
    return material + field


import os

# 챔피언 CPU 탐색 설정. 미러 매치 벤치마크(tools_bench_mirror.py)로 고른 값이며 환경 변수로 바꿔 실험할 수 있다.
DEPTH = int(os.environ.get("CPU_DEPTH", "2"))  # 몇 턴 앞까지 진행해 보는가
REPLIES = int(os.environ.get("CPU_REPLIES", "3"))  # 고려하는 상대 행동 조합 수
CANDIDATES = int(os.environ.get("CPU_CANDIDATES", "10"))  # 비교하는 내 행동 조합 수
SAMPLES = int(os.environ.get("CPU_SAMPLES", "2"))  # 난수(데미지·명중) 표본 수
TEMP = float(os.environ.get("CPU_TEMP", "1"))  # 상대 행동 가능성의 날카로움
RISK = float(os.environ.get("CPU_RISK", ".5"))  # 최악의 경우를 얼마나 신경 쓰는가


def _hidden(battle):
    """플레이어가 아직 보여 주지 않은 포켓몬 수 (팀 미리보기로 존재는 알지만 정체·세트는 모른다)."""
    return getattr(battle, "_hidden_count", 0)


def _rollout(battle, mine, theirs, seed):
    """mine/theirs 로 한 턴을 끝까지 진행하고(턴 종료 효과·교체 포함), 한 턴 더 표준 정책으로 진행한 뒤
    CPU(편 1) 입장의 형세를 돌려준다. 실제 플레이어처럼 다음 턴의 결과까지 본다."""
    trial = _copy_battle(battle)
    trial.rng = Random(seed)
    trial.manual = False
    trial.difficulty = "ultra"
    trial._pivot_slot = None
    trial._resolve_actions(mine, theirs)
    hidden = _hidden(battle)
    # 플레이어의 미공개 포켓몬은 체력이 가득한 미지의 전력으로 센다.
    reserve = hidden * 1.65
    trial._end_turn()
    if DEPTH > 1 and not trial.winner:
        trial.advance()
    if trial.winner == "win" or (trial.winner == "loss" and not hidden):
        return {"loss": 6., "win": -6.}[trial.winner] + _position(trial, 1) - _position(trial, 0) - reserve
    return _position(trial, 1) - _position(trial, 0) - reserve


def _softmax(values, temperature):
    top = max(values)
    weights = [2.718281828 ** ((v - top) / temperature) for v in values]
    total = sum(weights)
    return [w / total for w in weights]


def choose_actions_pro(battle):
    """실제 플레이어 수준의 판단 (챔피언 난이도).

    1. 상대(플레이어)가 고를 만한 행동 조합 여러 개를 플레이어 입장에서 평가해 가능성 가중치를 매긴다.
    2. 내 행동 후보마다 각 예상 행동과 맞붙여 2턴 앞까지 진행해 보고(같은 난수로 2회), 가중 평균과 최악의 경우를
       절반씩 본다. 미러 매치 기준 표준 정책 상대 승률: 기존 챔피언 77% → 81%.
    3. 거의 같은 점수의 후보 중에서는 무작위로 골라 수가 읽히지 않게 한다.
    """
    forecast = _observation(battle)
    forecast.manual = False
    replies = _plans(forecast, 0, REPLIES)
    candidates = _plans(forecast, 1, CANDIDATES)
    salt = battle.seed ^ (battle.turn * 196613)

    # 플레이어 입장에서 각 예상 행동이 내 기본 수에 얼마나 좋은지 → 가능성
    base = candidates[0]
    reply_value = [-_rollout(forecast, reply, base, salt + 7 * i) for i, reply in enumerate(replies)]
    weights = [.75 * w + .25 / len(replies) for w in _softmax(reply_value, TEMP)]

    def evaluate(index, actions):
        outcomes = []
        for i, reply in enumerate(replies):
            samples = [_rollout(forecast, reply, actions, salt + 31 * i + 7919 * k) for k in range(SAMPLES)]
            outcomes.append(sum(samples) / len(samples))
        expected = sum(w * o for w, o in zip(weights, outcomes))
        switches = sum(a["kind"] == "switch" for a in actions)
        return (1 - RISK) * expected + RISK * min(outcomes) - .06 * switches

    scored = [(evaluate(i, actions), actions) for i, actions in enumerate(candidates)]
    best = max(score for score, _ in scored)
    close = [actions for score, actions in scored if score >= best - .04]
    return Random(salt).choice(close)


def choose_actions(battle):
    """Compare joint CPU lines against several plausible replies for the next turn."""
    if battle.difficulty == "champion" and os.environ.get("CPU_ALGO") != "old":
        return choose_actions_pro(battle)
    forecast = _observation(battle)
    champion = battle.difficulty == "champion"
    replies = _plans(forecast, 0, 3 if champion else 2)
    candidates = _plans(forecast, 1, 9 if champion else 5)

    def evaluate(actions):
        outcomes = []
        for i, reply in enumerate(replies):
            trial = _copy_battle(forecast)
            trial.rng = Random(battle.seed ^ (battle.turn * 196613 + i * 17))
            trial._resolve_actions(reply, actions)
            outcomes.append(_position(trial, 1) - _position(trial, 0))
        mean = sum(outcomes) / len(outcomes)
        risk = .33 if champion else .15
        switches = sum(a["kind"] == "switch" for a in actions)
        return mean * (1 - risk) + min(outcomes) * risk - .10 * switches

    return max(candidates, key=evaluate)
