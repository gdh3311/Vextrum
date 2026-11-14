"""팀 전략 가이드: 내 파티를 어떻게 굴리고, 메타의 무엇을 어떻게 상대할지 규칙 기반으로 정리한다.

모든 문장은 세트(기술/특성/도구)와 간이 데미지 계산에서 나온 사실만으로 만든다.
"""
from __future__ import annotations

import re
from itertools import combinations
from random import Random

from . import auto_team, battle_lab, regulation, simulation
from .enemy import mini
from .engine import ROLE_MOVES, Engine, weight
from .typechart import type_multiplier

WEATHER = {
    "Drizzle": ("비", "Water", {"Swift Swim"}, "비가 유지되는 동안 물 기술이 1.5배 강해집니다."),
    "Drought": ("쾌청", "Fire", {"Chlorophyll", "Solar Power"}, "쾌청이 유지되는 동안 불꽃 기술이 1.5배 강해집니다."),
    "Sand Stream": ("모래바람", "Rock", {"Sand Rush", "Sand Force"}, "모래 피해를 받는 상대는 턴 종료 피해로 기합의띠·멀티스케일의 풀 HP 조건을 잃을 수 있습니다. 바위 타입은 특방이 1.5배가 됩니다."),
    "Snow Warning": ("눈", "Ice", {"Slush Rush", "Ice Body"}, "눈이 유지되는 동안 얼음 타입의 방어가 1.5배가 됩니다."),
}
WEATHER_MOVES = {"Drizzle": "Rain Dance", "Drought": "Sunny Day", "Sand Stream": "Sandstorm", "Snow Warning": "Snowscape"}
WEATHER_ROCKS = {"Drizzle": "Damp Rock", "Drought": "Heat Rock", "Sand Stream": "Smooth Rock", "Snow Warning": "Icy Rock"}
WEATHER_ATTACKS = {
    "Drizzle": {"Electro Shot", "Hurricane", "Thunder"},
    "Drought": {"Solar Beam", "Solar Blade"},
    "Snow Warning": {"Blizzard", "Aurora Veil"},
}
TERRAIN = {
    "Grassy Surge": ("그래스필드", {"Grassy Glide"}, "그래스필드에서 풀 기술이 강해지고 매 턴 회복합니다. 상대의 지진 피해도 줄어듭니다."),
    "Psychic Surge": ("사이코필드", {"Expanding Force"}, "사이코필드에서 와이드포스가 전체기가 됩니다. 상대 선공기를 막아 주지만 내 선공기도 막힙니다."),
    "Electric Surge": ("일렉트릭필드", {"Rising Voltage"}, "일렉트릭필드에서 전기 기술이 강해지고 잠듦을 막습니다."),
    "Misty Surge": ("미스트필드", set(), "미스트필드로 상태이상을 막고 드래곤 기술 피해를 줄입니다."),
}
SPEED_MOVES = {"Tailwind", "Trick Room", "Icy Wind", "Electroweb", "Thunder Wave", "Scary Face", "Bulldoze", "Glare"}
INTIM_PROOF = {"Defiant", "Competitive", "Clear Body", "White Smoke", "Hyper Cutter", "Inner Focus", "Own Tempo",
               "Oblivious", "Scrappy", "Full Metal Body", "Guard Dog", "Mirror Armor", "Contrary"}
PRIORITY_BLOCK = {"Psychic Surge", "Queenly Majesty", "Dazzling", "Armor Tail"}


def n(r: dict) -> str:
    return r["ko"] or r["name"]


def names(rs) -> str:
    return ", ".join(n(r) for r in rs)


def attackers(e: Engine, team, fmt):
    return [r for r in team if set(e.roles(r, fmt)) & {"physical", "special", "mixed"}]


def has_support(mon, move):
    return move in mon["moves"] and mon["item"] not in simulation.CHOICE | {"Assault Vest"}


# ------------------------------------------------------------------ 팀의 축과 운영법
def axes(e: Engine, team: list[dict], fmt: str, *, leads=(), effects=None, foes=()) -> list[dict]:
    out = []
    roles = {r["id"]: set(e.roles(r, fmt)) for r in team}

    lead_ids = {m["id"] for m in leads}

    def add(label, members, play, *, key=None, setters=()):
        seen, uniq = set(), []
        for r in members:
            if r["id"] not in seen:
                seen.add(r["id"])
                uniq.append(mini(r))
        out.append({"label": label, "members": uniq, "play": play, "key": key,
                    "opening": any(r["id"] in lead_ids for r in setters),
                    "activations": effects.get(key, 0) if effects is not None and key else None})

    for ability, (label, wtype, abusers, play) in WEATHER.items():
        starters = [r for r in team if r["ability"] == ability or has_support(r, WEATHER_MOVES[ability])
                    or ability == "Snow Warning" and has_support(r, "Chilly Reception")]
        if not starters:
            continue
        attacks = WEATHER_ATTACKS.get(ability, set()) | {"Weather Ball"}
        users = [x for x in team if (
            x["ability"] in abusers or attacks.intersection(x["moves"])
            or (wtype in {"Ice", "Rock"} and wtype in x["types"])
            or (wtype in {"Water", "Fire"} and any(e.M[m]["type"] == wtype and e.M[m]["power"] for m in x["moves"])))]
        duration = ", ".join(f"{n(r)} {8 if r['item'] == WEATHER_ROCKS[ability] else 5}턴" for r in starters)
        timing = "후발 시동이므로 첫 턴부터 적용하려면 교체가 필요합니다. " if leads and not any(
            r["id"] in lead_ids for r in starters) else ""
        add(f"{label} 축", starters + users,
            timing + f"시동 턴 포함 {duration}. " + play + (f" 현재 선출 수혜 포켓몬 · {names(users)}." if users else ""),
            key=simulation.WEATHER[ability], setters=starters)

    for r in team:
        if r["ability"] in TERRAIN:
            label, moves, play = TERRAIN[r["ability"]]
            users = [x for x in team if set(x["moves"]) & moves]
            add(label, [r] + users, play + (f" {names(users)}의 필드 기술과 함께 선출하세요." if users else ""))

    weather_axes = [a["label"] for a in out if a["key"] in {"rain", "sun", "sand", "snow"}]
    if len(weather_axes) > 1:
        add("날씨 덮어쓰기", [], f"{'와 '.join(weather_axes)}은 한 번에 하나만 유지됩니다. 필요한 날씨 시동을 나중에 내보내세요.")
    tr = [r for r in team if has_support(r, "Trick Room")]
    if tr:
        slow = [r for r in attackers(e, team, fmt) if r not in tr and (
            sum(r["speed"] < f["speed"] for f in foes) > len(foes) / 2 if foes else r["speed"] <= 95)]
        support = [r for r in leads if r not in tr and ("Fake Out" in r["moves"] or
                   any(has_support(r, move) for move in simulation.REDIRECT))]
        timing = "시동 포켓몬이 후발이라 필드에 내보낸 뒤 기술을 써야 합니다. " if leads and not any(
            r["id"] in lead_ids for r in tr) else ""
        add("트릭룸", tr + slow + support,
            timing + f"{names(tr)}의 트릭룸은 시동 턴 포함 5턴이며, 보통 이후 4턴을 활용합니다. 같은 우선도 안에서 느린 쪽이 먼저 움직입니다."
            + (f" 저속 공격수 · {names(slow)}." if slow else " 이 선출은 저속 화력보다 상대 트릭룸을 되돌리는 데 쓸 수 있습니다.")
            + (f" 시동 보조 후보 · {names(support)}." if support else ""), key="trickroom", setters=tr)
    tw = [r for r in team if has_support(r, "Tailwind")]
    if tw:
        timing = "시동 포켓몬이 후발입니다. " if leads and not any(r["id"] in lead_ids for r in tw) else ""
        add("순풍", tw, timing + f"{names(tw)}의 순풍은 시동 턴 포함 4턴입니다. 같은 턴에 아직 움직이지 않은 아군부터 스피드 2배가 적용됩니다.",
            key="tailwind", setters=tw)
    fo = [r for r in team if "Fake Out" in r["moves"]]
    if fo and fmt == "Doubles":
        add("속이다 지원", fo, f"{names(fo)}의 속이다는 첫 행동 턴에 사용할 수 있습니다. 고스트의 노말 무효, 정신력의 풀죽음 방지, 방어·선공기 차단을 확인하세요.")
    inti = [r for r in team if r["ability"] == "Intimidate"]
    if inti:
        add("위협", inti, f"{names(inti)}의 위협은 등장 시 발동합니다. 상대의 공격 하락 무효나 오기·승기를 확인하세요."
            + (" 교체로 여러 번 발동시키는 사이클 운영이 가능합니다." if len(inti) >= 2 or any("pivot" in roles[r["id"]] for r in inti) else ""))
    red = [r for r in team if any(has_support(r, m) for m in ROLE_MOVES["redirect"])]
    setup = [r for r in team if r not in red and any(has_support(r, m) for m in ROLE_MOVES["setup"])]
    if red and setup and fmt == "Doubles":
        add("유도 + 랭크업", red + setup, f"{names(red)}이(가) 공격을 끌어오는 동안 {names(setup)}이(가) 랭크업한 뒤 전개합니다.")
    elif setup:
        add("랭크업 에이스", setup, f"{names(setup)}이(가) 랭크업할 턴을 만들어 주는 것이 핵심입니다. 상대의 도발·앙코르·흑안개를 먼저 확인하세요.")
    fast = [r for r in attackers(e, team, fmt) if "fast" in roles[r["id"]]]
    if len(fast) >= 4:
        add("고속 공세", fast, "같은 우선도에서 속도 우위를 노릴 수 있습니다. 상대의 선공기, 순풍, 트릭룸에 따라 행동 순서가 바뀝니다.")
    if not out:
        add("상성 중심", [], "현재 선출에서 공격을 받아낼 포켓몬과 상대를 압박할 포켓몬을 함께 봅니다.")
    return out


# ------------------------------------------------------------------ 이론상 공격 범위
def win_conditions(e: Engine, team, fmt, meta, ws) -> list[dict]:
    rows = []
    for a in attackers(e, team, fmt):
        beats, cov = [], 0.0
        for b, w in zip(meta, ws):
            h = e.best_hit(a, b, fmt)
            if not h:
                continue
            c = min(1, h["pct"] / 75) * h["acc"] / 100
            cov += w * c
            if h["pct"] >= 70:
                beats.append({**mini(b), "move": h["move"], "pct": h["pct"], "w": w})
        rows.append({"mon": mini(a), "coverage": round(100 * cov / sum(ws)),
                     "beats": e.with_move_ko(sorted(beats, key=lambda x: -x["w"])[:5])})
    rows.sort(key=lambda r: -r["coverage"])
    return rows[:3]


# ------------------------------------------------------------------ 시너지 / 주의 조합
def synergies(e: Engine, team, fmt) -> list[dict]:
    out = []
    roles = {r["id"]: set(e.roles(r, fmt)) for r in team}

    def add(kind, a, b, text):
        out.append({"kind": kind, "members": [mini(a), mini(b)], "text": text})

    if fmt != "Doubles":
        for a in team:
            if "pivot" in roles[a["id"]]:
                for b in team:
                    if b is not a and "setup" in roles[b["id"]]:
                        add("good", a, b, f"{n(a)}의 교체 기술로 {n(b)}을(를) 안전하게 내보내 랭크업 기회를 만듭니다.")
        return out[:6]

    for a, b in combinations(team, 2):
        for x, y in ((a, b), (b, a)):
            xm = {m for m in x["moves"] if e.M[m]["power"] or has_support(x, m)}
            ym = {m for m in y["moves"] if e.M[m]["power"] or has_support(y, m)}
            for mv in x["moves"]:  # 아군까지 때리는 전체기
                m = e.M[mv]
                if m["target"] == "allAdjacent" and m["power"]:
                    mult = type_multiplier(m["type"], y["types"], y["ability"])
                    mk = m["ko"] or mv
                    if mult == 0:
                        add("good", x, y, f"{n(x)}의 {mk}을(를) {n(y)}이(가) 무효로 받아, 아군 피해 없이 전체기를 쓸 수 있습니다.")
                    elif mult >= 2:
                        guard = " 아군이 방어할 때 쓰거나 다른 기술을 고르세요." if ym & simulation.PROTECT else " 다른 기술을 고르거나 함께 내보내는 턴을 피하세요."
                        add("warn", x, y, f"{n(x)}의 {mk}은 함께 나온 {n(y)}도 맞힙니다. 타입 상성 {mult:g}배." + guard)
            if "Fake Out" in xm and ym & (ROLE_MOVES["setup"] | {"Trick Room", "Tailwind"}):
                what = next(iter(ym & (ROLE_MOVES["setup"] | {"Trick Room", "Tailwind"})))
                add("good", x, y, f"{n(x)}의 속이다가 통하는 상대라면 {n(y)}의 {e.M[what]['ko'] or what} 전개를 보조할 수 있습니다.")
            if xm & ROLE_MOVES["redirect"] and ym & ROLE_MOVES["setup"]:
                add("good", x, y, f"{n(x)}이(가) 공격을 끌어오는 동안 {n(y)}이(가) 랭크업합니다.")
            if x["ability"] in WEATHER:
                label, wtype, abusers, _ = WEATHER[x["ability"]]
                if y["ability"] in abusers:
                    add("good", x, y, f"{n(x)}의 {label} 아래에서 {n(y)}의 특성이 발동합니다.")
                elif any(e.M[m]["type"] == wtype and e.M[m]["power"] for m in y["moves"]) and wtype in ("Water", "Fire"):
                    add("good", x, y, f"{n(x)}의 {label} 아래에서 {n(y)}의 {'물' if wtype == 'Water' else '불꽃'} 기술이 1.5배가 됩니다.")
            if x["ability"] in TERRAIN and ym & TERRAIN[x["ability"]][1]:
                mv = next(iter(ym & TERRAIN[x["ability"]][1]))
                add("good", x, y, f"{n(x)}의 {TERRAIN[x['ability']][0]}에서 {n(y)}의 {e.M[mv]['ko'] or mv}이(가) 강화됩니다.")
            if "Helping Hand" in xm and any(e.M[m]["target"] in ("allAdjacent", "allAdjacentFoes") and e.M[m]["power"] for m in y["moves"]):
                add("good", x, y, f"{n(x)}의 도우미로 {n(y)}의 전체기 화력을 1.5배로 올립니다.")
            if "Tailwind" in xm and 85 <= y["speed"] < e.percentiles(fmt)["fast"] and \
                    roles[y["id"]] & {"physical", "special", "mixed"}:
                add("good", x, y, f"{n(x)}의 순풍으로 {n(y)}의 스피드가 {round(y['speed'])}에서 {round(2*y['speed'])}로 오릅니다.")
    seen, uniq = set(), []
    for s in sorted(out, key=lambda s: s["kind"] != "warn"):
        key = (s["members"][0]["id"], s["members"][1]["id"], s["text"][:12])
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    return uniq[:9]


# ------------------------------------------------------------------ 메타 전략별 대비
def prep(e: Engine, team, fmt, leads=()) -> list[dict]:
    rows = []
    lead_ids = {m["id"] for m in leads}

    def actions(moves=(), abilities=(), damage_types=(), resist=None):
        out = []
        for mon in team:
            supported = [m for m in mon["moves"] if m in moves or (
                e.M[m]["power"] and e.M[m]["type"] in damage_types)]
            if mon["item"] in simulation.CHOICE | {"Assault Vest"}:
                supported = [m for m in supported if e.M[m]["power"]]
            for move in supported:
                name = e.M[move].get("ko") or move
                timing = " (후발)" if leads and mon["id"] not in lead_ids else ""
                out.append((mon, f"{n(mon)}{timing} · {name}"))
            if mon["ability"] in abilities:
                ability = e.d["abilities"].get(mon["ability"], {}).get("ko") or mon["ability"]
                out.append((mon, f"{n(mon)} · {ability}"))
            elif resist and type_multiplier(resist, mon["types"], mon["ability"]) < 1:
                out.append((mon, f"{n(mon)} · {'무효' if not type_multiplier(resist, mon['types'], mon['ability']) else '반감'}"))
        return out

    def add(label, options, note):
        answers = list({m["id"]: mini(m) for m, _ in options}.values())
        advice = " / ".join(dict.fromkeys(s for _, s in options))
        rows.append({"label": label, "level": "ok" if answers else "weak", "answers": answers,
                     "advice": (advice + ". " + note) if advice else "현재 선출에서 확인된 대응 수단이 없습니다."})

    if fmt == "Doubles":
        room_moves = {move for m in team if m["item"] not in simulation.CHOICE | {"Assault Vest"} for move in m["moves"]}
        note = "트릭룸은 시동 턴 포함 5턴입니다."
        if "Trick Room" in room_moves:
            note += " 이미 켜진 상태에서 트릭룸을 쓰면 해제합니다."
        if room_moves & {"Taunt", "Fake Out", "Encore"}:
            note += " 대상의 방어와 기술별 차단 수단을 확인하세요."
        add("트릭룸", actions({"Taunt", "Trick Room", "Encore", "Fake Out"}), note)
        add("순풍", actions(SPEED_MOVES | {m for m in e.M if e.M[m]["priority"] > 0 and e.M[m]["power"]}),
            "순풍은 시동 턴 포함 4턴입니다. 선공기는 우선도와 기술별 성공 조건을 확인하세요.")
    add("비 파티", actions({"Sunny Day", "Sandstorm", "Snowscape", "Chilly Reception"},
                           {"Drought", "Sand Stream", "Snow Warning"}, {"Electric", "Grass"}, resist="Water"),
        "상대의 날씨 재전개와 물 타입 외 공격수도 확인하세요.")
    add("쾌청 파티", actions({"Rain Dance", "Sandstorm", "Snowscape", "Chilly Reception"},
                             {"Drizzle", "Sand Stream", "Snow Warning"}, {"Rock", "Water"}, resist="Fire"),
        "쾌청이 유지되는 동안 물 기술 화력은 절반입니다.")
    add("사이코스팸", actions({"Grassy Terrain", "Electric Terrain", "Misty Terrain", "Wide Guard"},
                            set(TERRAIN) - {"Psychic Surge"}, resist="Psychic"),
            "사이코필드는 접지한 포켓몬을 향한 상대의 선공기를 막습니다.")
    special = [(m, f"{n(m)} · 특수 화력") for m in team if set(e.roles(m, fmt)) & {"special", "mixed"}]
    add("위협", special + actions(abilities=INTIM_PROOF), "위협은 물리 공격 랭크에 영향을 줍니다.")
    if fmt == "Doubles":
        add("속이다", actions(simulation.PROTECT | {"Quick Guard"}, PRIORITY_BLOCK | {"Inner Focus"},
                             resist=None)
            + [(m, f"{n(m)} · 고스트 타입의 노말 무효") for m in team if "Ghost" in m["types"]],
            "고스트는 노말 기술에 무효이며, 정신력은 속이다의 피해를 받고 풀죽음을 막습니다.")
    add("선공기 공세", actions(simulation.PROTECT | {"Quick Guard", "Psychic Terrain"}, PRIORITY_BLOCK),
        "상대의 우선도, 대상과 필드 상태를 확인하세요.")
    return rows


def threats(e: Engine, team, fmt, meta, *, leads=(), attacks=()) -> list[dict]:
    rows = []
    for b in meta:
        per = [(a, e.matchup(a, b, fmt)) for a in team]
        score = e.team_score([m["score"] for _, m in per])
        hits = sorted(((a, m["hit"]) for a, m in per if m["hit"] and m["hit"]["pct"] > 0),
                      key=lambda pair: -pair[1]["pct"] * pair[1]["acc"])
        steps, damage = [], []
        if hits:
            a, hit = hits[0]
            move = hit["move"]
            meta_move = e.M[move]
            mk = meta_move["ko"] or move
            damage.append({"mon": mini(a), "move": move, "moveKo": mk,
                           "pct": hit["pct"], "accuracy": hit["acc"]})
            timing = " · 후발" if leads and a not in leads else ""
            steps.append(f"{n(a)}{timing}의 {mk} · 예상 피해 {hit['pct']:.0f}% · 기본 명중 {hit['acc']:g}%.")
            if move in simulation.REACTIVE:
                condition = "아직 행동하지 않은 상대가 선공 공격기를 골라야 합니다." if move == "Upper Hand" else "아직 행동하지 않은 상대가 공격기를 골라야 합니다."
                steps.append(f"{mk} 성공 조건 · {condition} 방어·변화기·교체에는 실패할 수 있습니다.")
            elif move in simulation.FIRST_TURN:
                steps.append(f"{mk}는 첫 행동 턴에만 쓸 수 있습니다. 방어·선공기 차단과 상대 특성을 확인하세요.")
            elif move in simulation.WEATHER_CHARGE:
                steps.append("해당 날씨나 파워풀허브가 없으면 준비 턴이 필요합니다.")
            if fmt == "Doubles" and meta_move.get("target") == "allAdjacent":
                partners = [p for p in team if p is not a and (ally := e.damage(a, move, p, fmt)) and ally["pct"] > 0]
                if partners:
                    steps.append(f"{mk}는 같은 턴에 나온 아군도 공격합니다 · {names(partners)}.")
            seen = next((r for r in attacks if (r["actor"], r["move"], r["target"]) == (a["id"], move, b["id"])), None)
            if seen:
                damage[0]["observed"] = {k: seen[k] for k in ("attempts", "hits", "kos")}
        danger = sorted(((a, m["taken"]) for a, m in per if m["taken"] and m["taken"]["pct"] >= 80),
                        key=lambda x: -x[1]["pct"])
        if danger:
            a, hit = danger[0]
            mk = e.M[hit["move"]]["ko"] or hit["move"]
            steps.append(f"{n(a)}이(가) {n(b)}의 {mk}에 받는 예상 피해 · {hit['pct']:.0f}%.")
        rows.append({"mon": mini(b), "rank": e.rank(b["id"], fmt), "score": round(score, 1), "label": e.label(score),
                     "steps": steps, "damage": damage, "answer": mini(hits[0][0]) if hits else None})
    rows.sort(key=lambda r: r["score"])
    return [r for r in rows if r["score"] < 62][:6] or rows[:3]


_JOSA = {"이(가)": ("이", "가"), "을(를)": ("을", "를"), "은(는)": ("은", "는"), "(으)로": ("으로", "로")}
_JOSA_RE = re.compile(r"([^\s(])(\)?)(이\(가\)|을\(를\)|은\(는\)|\(으\)로)")


def _josa(m: re.Match) -> str:
    ch, paren, key = m.group(1), m.group(2) or "", m.group(3)
    if "가" <= ch <= "힣":
        jong = (ord(ch) - 0xAC00) % 28
    else:  # 영문·숫자로 끝나는 이름: 받침처럼 읽히는 글자만 받침으로 본다
        jong = 8 if ch.upper() in "LR" else 1 if ch.upper() in "MN136780" else 0
    with_b, without_b = _JOSA[key]
    if key == "(으)로":
        pick = with_b if jong not in (0, 8) else without_b
    else:
        pick = with_b if jong else without_b
    return ch + paren + pick


def polish(obj):
    """문장 속 '이(가)' 같은 표기를 앞 글자 받침에 맞는 조사로 바꾼다."""
    if isinstance(obj, str):
        return _JOSA_RE.sub(_josa, obj)
    if isinstance(obj, list):
        return [polish(x) for x in obj]
    if isinstance(obj, dict):
        return {k: polish(v) for k, v in obj.items()}
    return obj


def opening_claim(e, action, members, pick, report):
    actor, move = members.get(action["actor"]), action["move"]
    if not actor or actor["id"] not in pick["leads"] or not pick.get("openingRuns"):
        return None
    ids, move_ids, conditions = [actor["id"]], [], []
    if move == "switch" and action.get("into") in pick["back"]:
        ids.append(action["into"])
        text = f"{n(actor)} → {n(members[action['into']])}"
        conditions.append("교체할 후발이 필요합니다.")
    elif (move in actor["moves"] and simulation.move_supported(e, move)) or move == "Struggle":
        move_ids.append(e.move_ids.get(move, "struggle"))
        target = e.P.get(action.get("target"))
        aim = f" → {n(target)}" if target else ""
        text = f"{n(actor)} · {e.M.get(move, {}).get('ko') or move}{aim}"
        if move in simulation.REACTIVE:
            conditions.append("상대가 아직 행동하지 않았고 공격기를 골라야 합니다.")
            if move == "Upper Hand":
                conditions.append("대상의 공격기는 선공기여야 합니다.")
        if move in simulation.FIRST_TURN:
            conditions.append("등장한 뒤 처음 행동하는 턴에만 쓸 수 있습니다.")
        if move in simulation.PROTECT:
            conditions.append("연속 사용이나 방어 관통에 따라 결과가 달라집니다.")
        if e.M.get(move, {}).get("target") == "allAdjacent":
            conditions.append("같은 턴에 나온 아군도 영향을 받을 수 있습니다.")
    else:
        return None
    sample = pick.get("sample") or {}
    return {"claimId": f"opening-{sample.get('seed', 0)}-{actor['id']}", "scope": "selected4",
            "status": "SIM_OBSERVED", "requiredPokemonIds": ids, "requiredMoveIds": move_ids,
            "preconditions": conditions, "text": text,
            "proposal": {"leads": pick["leads"], "backs": pick["back"]},
            "simulation": {"games": pick["openingRuns"], "wins": pick["openingWins"],
                           "policyVersion": regulation.POLICY_VERSION, "difficulty": report.get("difficulty"),
                           "seed": sample.get("seed"), "opponentPool": sample.get("pool", "search")}}


def selection_evidence(e, fmt, team, report):
    """Turn observed selections into plans without attaching whole-roster moves."""
    members = {m["id"]: m for m in team}
    plans = []
    for block in (report or {}).get("strategies", ()):
        for pick in block.get("picks", ())[:1]:
            ids = [*pick["leads"], *pick["back"]]
            if (len(ids) != min(battle_lab.limit(fmt), len(team)) or len(set(ids)) != len(ids)
                    or not set(ids) <= members.keys()):
                continue
            if len(pick["leads"]) != min(2 if fmt == "Doubles" else 1, len(team)):
                continue
            lead = [members[i] for i in pick["leads"]]
            chosen = [members[i] for i in ids]
            actions = pick.get("openingActions", ())
            claims = [opening_claim(e, action, members, pick, report) for action in actions]
            claims = claims if all(claims) else []
            effects = pick.get("activations", {})
            plans.append({"style": block["style"], "against": block["label"], "runs": pick["runs"],
                          "win": pick["win"], "loss": pick.get("loss"), "draw": pick.get("draw"),
                          "lead": [mini(m) for m in lead],
                          "back": [mini(members[i]) for i in pick["back"]],
                          "bench": [mini(m) for m in team if m["id"] not in ids],
                          "opening": [c["text"] for c in claims], "openingClaims": claims,
                          "openingRuns": pick.get("openingRuns", 0) if claims else 0,
                          "openingWins": pick.get("openingWins", 0) if claims else 0, "activations": effects,
                          "axes": axes(e, chosen, fmt, leads=lead, effects=effects),
                          "sample": pick.get("sample"),
                          "openingAgreement": round(pick.get("openingRuns", 0) / max(1, pick["runs"]), 3) if claims else 0,
                          "difficulty": report.get("difficulty")})
    return plans


def alternative_axes(e, fmt, team, meta, selected):
    """Give conflicting modes their own legal selection, including the setter."""
    width = 2 if fmt == "Doubles" else 1
    size = min(battle_lab.limit(fmt), len(team))
    selected_keys = {a["key"] for a in selected}
    core = []
    for ability, move in WEATHER_MOVES.items():
        key = simulation.WEATHER[ability]
        setters = [r for r in team if r["ability"] == ability or has_support(r, move)
                   or key == "snow" and has_support(r, "Chilly Reception")]
        if setters and (key not in selected_keys or len(selected_keys & set(simulation.WEATHER.values())) > 1):
            core.append((key, setters[0], None))
    if fmt == "Doubles":
        setter = next((m for m in team if has_support(m, "Trick Room")), None)
        slow = min((m for m in attackers(e, team, fmt) if m is not setter), key=lambda m: m["speed"], default=None)
        selected_room = next((a for a in selected if a["key"] == "trickroom"), None)
        if setter and slow and (not selected_room or not selected_room["opening"]):
            core.append(("trickroom", setter, slow))
    out = []
    for key, setter, partner in core:
        others = [r for r in team if r not in (setter, partner)]
        if key in simulation.WEATHER.values():
            others = [r for r in others if simulation.WEATHER.get(r["ability"], key) == key
                      and all(simulation.WEATHER_MOVES.get(m, key) == key for m in r["moves"])]
        group = [setter] + ([partner] if partner else [])
        if len(group) + len(others) < size:
            continue
        weights = {m["id"]: sum(e.matchup(m, foe, fmt)["score"] for foe in meta) for m in others}
        for mon in sorted(others, key=lambda m: -weights[m["id"]]):
            if len(group) == size:
                break
            if mon["mega"] and any(m["mega"] for m in group):
                continue
            group.append(mon)
        if len(group) != size:
            for mon in sorted(others, key=lambda m: -weights[m["id"]]):
                if mon not in group:
                    group.append(mon)
                if len(group) == size:
                    break
        axis = next((a for a in axes(e, group, fmt, leads=group[:width], foes=meta) if a["key"] == key), None)
        if axis:
            out.append({**axis, "lead": [mini(m) for m in group[:width]],
                        "back": [mini(m) for m in group[width:]], "evidence": "theory"})
    return out


def team_guide(e: Engine, sets: list[dict], fmt: str, top_n: int = 20, *, report=None) -> dict | None:
    sets = [s for s in sets if s.get("id") in e.P]
    team = battle_lab._resolve(e, fmt, sets)
    if not team:
        return None
    coverage = simulation.rules_report(e, fmt, sets)
    missing = {(i["pokemon"], e.move_names.get(i.get("id"), i["name"])) for i in coverage["issues"]
               if i["kind"] == "move" and i["status"] == "UNSIMULATABLE"}
    if missing:
        team = [{**m, "moves": [move for move in m["moves"] if (m["id"], move) not in missing]} for m in team]
    meta = e.meta(fmt, top_n)
    ws = [weight(e.rank(b["id"], fmt)) for b in meta]
    plans = selection_evidence(e, fmt, team, report)
    width = min(2 if fmt == "Doubles" else 1, len(team))
    lead = max(plans, key=lambda p: (p["runs"], p["win"]), default=None)
    attacks = ()
    if lead:
        order = [m["id"] for m in lead["lead"] + lead["back"]]
        selected = [next(m for m in team if m["id"] == pid) for pid in order]
        block = next(b for b in report["strategies"] if b["style"] == lead["style"])
        attacks = block["picks"][0].get("attacks", ())
        lead = {**lead, "evidence": "simulation", "why": []}
    else:
        indices, _ = battle_lab._choose(e, fmt, team, meta, Random(0))
        selected = [team[i] for i in indices]
        lead = {"lead": [mini(m) for m in selected[:width]], "back": [mini(m) for m in selected[width:]],
                "bench": [mini(m) for m in team if m not in selected], "why": [], "evidence": "selection"}
    leads = selected[:width]
    operating = axes(e, selected, fmt, leads=leads, effects=lead.get("activations"), foes=meta)
    return polish({
        "axes": operating,
        "rosterAxes": axes(e, team, fmt, foes=meta),
        "lead": lead,
        "alternatives": alternative_axes(e, fmt, team, meta, operating),
        "plans": plans,
        "testStyles": [{"id": key, "label": auto_team.STYLES[key].label}
                       for key in battle_lab._split_pools(e, fmt, "search")],
        "winConditions": win_conditions(e, selected, fmt, meta, ws),
        "synergies": synergies(e, selected, fmt),
        "prep": prep(e, selected, fmt, leads),
        "threats": threats(e, selected, fmt, meta, leads=leads, attacks=attacks),
        "rulesCoverage": coverage,
        "complete": len(team) >= (4 if fmt == "Doubles" else 3),
    })
