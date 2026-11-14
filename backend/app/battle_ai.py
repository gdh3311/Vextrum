"""Ranked CPU planning from visible battle state and commonly used sets."""
import os
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
    forecast.strategy_used = [effects.copy() for effects in battle.strategy_used]
    forecast.tailwind = battle.tailwind.copy()
    forecast.mega_left = battle.mega_left.copy()
    forecast.redirect = battle.redirect.copy()
    forecast.wide_guard = battle.wide_guard.copy()
    forecast.quick_guard = battle.quick_guard.copy()
    forecast.screens = [dict(x) for x in battle.screens]
    forecast.hazards = [dict(x) for x in battle.hazards]
    forecast.wish = [dict(x) for x in battle.wish]
    forecast.log = []
    forecast.keep_log = False
    forecast._seen_cache = {}
    forecast.trace = [dict(t) for t in battle.trace]
    forecast.public_actions = [actions.copy() for actions in battle.public_actions]
    forecast.opening = list(battle.opening)
    forecast.opening_actions = list(battle.opening_actions)
    forecast.executed_attacks = Counter()
    return forecast


def _observation(battle, side=1):
    forecast = _copy_battle(battle)
    foe = 1 - side
    forecast._hidden_count = len(battle.teams[foe]) - len(battle.seen[foe])
    for i, fighter in enumerate(forecast.teams[foe]):
        if i not in battle.seen[foe]:
            fighter.hp = 0
            fighter.mega_form = None
            continue
        public = forecast._seen(side, fighter)
        fighter.mon = public.mon
        fighter.hp = public.hp
        fighter.mega_form = None
        fighter.choice = None
        fighter.item_used = public.item_used
    forecast._seen_cache.clear()
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
            elif move in {"Tailwind", "Trick Room"}:
                value = battle._speed_control_value(side, actor, move, getattr(battle, "foe_strategy", None)
                                                    if side == 1 else None)
                if value > .05:
                    tactics.append((value, action))
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


def _plans(battle, side, budget, *, replies=False):
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
    def split_attack(actions):
        targets = [a.get("target") for a in actions if a["kind"] == "move" and a.get("move") not in SUPPORT]
        return len(targets) == 2 and targets[0] is not None and targets[1] is not None and targets[0] != targets[1]

    def add(line):
        if line and len(plans) < budget:
            plans.append(list(line))
            keys.add(_plan_key(battle, line))

    def next_line(predicate):
        return next((actions for _, actions in scored if _plan_key(battle, actions) not in keys
                     and predicate(actions)), None)

    if replies and any(action.get("move") in SUPPORT or action["kind"] == "switch" for action in base):
        add(next_line(lambda actions: all(a["kind"] == "move" and a.get("move") not in SUPPORT for a in actions)))
    predicates = (
        lambda a: a.get("move") in PROTECT | REDIRECT | {"Wide Guard", "Quick Guard"},
        lambda a: a["kind"] == "switch",
        lambda a: a.get("move") in {"Tailwind", "Trick Room", "Encore", "Taunt", "Fake Out"},
        lambda a: a.get("move") in PIVOT,
    )
    for predicate in predicates:
        if len(plans) >= budget:
            break
        add(next_line(lambda actions: any(predicate(action) for action in actions)))
    if len(plans) < budget:
        add(next_line(split_attack))
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
    field = TW_FLAT * bool(battle.tailwind[side]) + TW_TURN * battle.tailwind[side] + .05 * sum(battle.screens[side].values())
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


# 챔피언 CPU 탐색 설정. 미러 매치 벤치마크(tools_bench_mirror.py)로 고른 값이며 환경 변수로 바꿔 실험할 수 있다.
DEPTH = int(os.environ.get("CPU_DEPTH", "2"))  # 몇 턴 앞까지 진행해 보는가
REPLIES = int(os.environ.get("CPU_REPLIES", "3"))  # 고려하는 상대 행동 조합 수
CANDIDATES = int(os.environ.get("CPU_CANDIDATES", "10"))  # 비교하는 내 행동 조합 수
SAMPLES = int(os.environ.get("CPU_SAMPLES", "2"))  # 난수(데미지·명중) 표본 수
TEMP = float(os.environ.get("CPU_TEMP", "1"))  # 상대 행동 가능성의 날카로움
RISK = float(os.environ.get("CPU_RISK", ".5"))  # 최악의 경우를 얼마나 신경 쓰는가
CONTROL = float(os.environ.get("CPU_CONTROL", ".8"))  # 순풍·트릭룸의 장기 이득 가중치
TW_FLAT = float(os.environ.get("CPU_TW_FLAT", ".12"))
TW_TURN = float(os.environ.get("CPU_TW_TURN", ".02"))


# 스타일별 형세 가중치 (내 형세, 상대 형세): 공격형은 상대를 깎는 쪽, 수비형은 자기 자원 보존을 더 본다.
STYLE_WEIGHTS = {"aggressive": (.9, 1.15), "defensive": (1.15, .9), "setup": (1., 1.), "pivot": (1.05, .95),
                 "counter": (.95, 1.1), "balanced": (1., 1.)}


def _hidden(battle):
    """플레이어가 아직 보여 주지 않은 포켓몬 수 (팀 미리보기로 존재는 알지만 정체·세트는 모른다)."""
    return getattr(battle, "_hidden_count", 0)


def _rollout(battle, side, actions, reply, seed, depth):
    """Resolve the proposed turn and score one side after end-of-turn effects."""
    trial = _copy_battle(battle)
    trial.rng = Random(seed)
    trial.manual = False
    trial.difficulty = "ultra"
    trial._pivot_slot = None
    joint = (reply, actions) if side == 1 else (actions, reply)
    trial._mega_turn(actions=joint)
    trial._resolve_actions(*joint)
    hidden = _hidden(battle)
    # 플레이어의 미공개 포켓몬은 체력이 가득한 미지의 전력으로 센다.
    reserve = hidden * 1.65
    trial._end_turn()
    if depth > 1 and not trial.winner:
        trial.advance()
    own, foe = STYLE_WEIGHTS[battle.cpu_style if side == 1 else "balanced"]
    value = own * _position(trial, side) - foe * _position(trial, 1 - side) - reserve
    win = "loss" if side == 1 else "win"
    loss = "win" if side == 1 else "loss"
    return value + (6 if trial.winner == win and not hidden else -6 if trial.winner == loss else 0)


def _softmax(values, temperature):
    top = max(values)
    weights = [2.718281828 ** ((v - top) / temperature) for v in values]
    total = sum(weights)
    return [w / total for w in weights]


def choose_actions_pro(battle, side=1):
    """Compare plausible opponent replies using only the observed position and action history."""
    forecast = _observation(battle, side)
    forecast.manual = False
    replies = _plans(forecast, 1 - side, max(4, REPLIES), replies=True)
    candidates = _plans(forecast, side, CANDIDATES)
    salt = battle.seed ^ (battle.turn * 196613) ^ (side * 7919)

    # 플레이어 입장에서 각 예상 행동이 내 기본 수에 얼마나 좋은지 → 가능성
    base = candidates[0]
    public = battle.public_actions[1 - side]

    def reply_bias(actions):
        keys = ["switch" if a["kind"] == "switch" else "protect" if a.get("move") in PROTECT
                else "support" if a.get("move") in SUPPORT else "attack" for a in actions]
        return .55 * sum(public[k] for k in keys) / max(4, sum(public.values()))

    reply_value = [-_rollout(forecast, side, base, reply, salt, 1) + reply_bias(reply) for reply in replies]
    weights = [.75 * w + .25 / len(replies) for w in _softmax(reply_value, TEMP)]

    def evaluate(actions):
        outcomes = []
        for i, reply in enumerate(replies):
            samples = [_rollout(forecast, side, actions, reply, salt + 31 * i + 7919 * k, DEPTH)
                       for k in range(SAMPLES)]
            outcomes.append(sum(samples) / len(samples))
        expected = sum(w * o for w, o in zip(weights, outcomes))
        switches = sum(a["kind"] == "switch" for a in actions)
        # 2턴 탐색으로는 순풍·트릭룸의 남은 턴 이득이 다 보이지 않으므로 미리 더해 준다.
        active = dict(forecast._present(side))
        tempo = sum(forecast._speed_control_value(side, active[a["slot"]], a["move"],
                                                  battle.foe_strategy if side == 1 else None)
                    for a in actions if a.get("move") in {"Tailwind", "Trick Room"}
                    and a["slot"] in active)
        return (1 - RISK) * expected + RISK * min(outcomes) - .06 * switches + CONTROL * tempo

    scored = [(evaluate(actions), actions) for actions in candidates]
    best = max(score for score, _ in scored)
    close = [actions for score, actions in scored if score >= best - .04]
    return Random(salt).choice(close)


def choose_actions(battle, side=1):
    """Compare joint CPU lines against several plausible replies for the next turn."""
    if battle.difficulty == "champion" and os.environ.get("CPU_ALGO") != "old":
        return choose_actions_pro(battle, side)
    forecast = _observation(battle, side)
    replies = _plans(forecast, 1 - side, 2, replies=True)
    candidates = _plans(forecast, side, 5)

    def evaluate(actions):
        outcomes = [_rollout(forecast, side, actions, reply, battle.seed ^ (battle.turn * 196613 + i * 17), 1)
                    for i, reply in enumerate(replies)]
        mean = sum(outcomes) / len(outcomes)
        risk = .20
        switches = sum(a["kind"] == "switch" for a in actions)
        return mean * (1 - risk) + min(outcomes) * risk - .10 * switches

    return max(candidates, key=evaluate)
