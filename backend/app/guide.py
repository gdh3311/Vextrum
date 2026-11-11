"""팀 전략 가이드: 내 파티를 어떻게 굴리고, 메타의 무엇을 어떻게 상대할지 규칙 기반으로 정리한다.

모든 문장은 세트(기술/특성/도구)와 간이 데미지 계산에서 나온 사실만으로 만든다.
"""
from __future__ import annotations

import re
from itertools import combinations

from .enemy import mini
from .engine import ROLE_MOVES, Engine, weight
from .typechart import type_multiplier

WEATHER = {
    "Drizzle": ("비", "Water", {"Swift Swim"}, "비를 깔고 물 기술 화력(1.5배)으로 밀어붙입니다. 날씨는 5턴이니 시동 포켓몬을 후발로 남겨 다시 깔 수 있게 하세요."),
    "Drought": ("쾌청", "Fire", {"Chlorophyll", "Solar Power"}, "쾌청 아래 불꽃 기술(1.5배)과 솔라빔을 씁니다. 물 기술 피해가 반감되는 것도 활용하세요."),
    "Sand Stream": ("모래바람", "Rock", {"Sand Rush", "Sand Force"}, "모래바람으로 기합의띠·멀티스케일을 깨고, 바위 타입의 특방 상승을 활용합니다."),
    "Snow Warning": ("설경", "Ice", {"Slush Rush", "Ice Body"}, "설경으로 얼음 타입의 방어를 올리고 눈보라·오로라베일을 씁니다."),
}
WEATHER_MOVES = {"Drizzle": "Rain Dance", "Drought": "Sunny Day", "Sand Stream": "Sandstorm", "Snow Warning": "Snowscape"}
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


# ------------------------------------------------------------------ 팀의 축과 운영법
def axes(e: Engine, team: list[dict], fmt: str) -> list[dict]:
    out = []
    roles = {r["id"]: set(e.roles(r, fmt)) for r in team}

    def add(label, members, play):
        seen, uniq = set(), []
        for r in members:
            if r["id"] not in seen:
                seen.add(r["id"])
                uniq.append(mini(r))
        out.append({"label": label, "members": uniq, "play": play})

    for ability, (label, wtype, abusers, play) in WEATHER.items():
        starters = [r for r in team if r["ability"] == ability or WEATHER_MOVES[ability] in r["moves"]]
        if not starters:
            continue
        attacks = WEATHER_ATTACKS.get(ability, set()) | {"Weather Ball"}
        users = [x for x in team if x not in starters and (
            x["ability"] in abusers or attacks.intersection(x["moves"])
            or any(e.M[m]["type"] == wtype and e.M[m]["power"] for m in x["moves"]))]
        add(f"{label} 축", starters + users,
            play + (f" 수혜자: {names(users)}." if users else " 날씨 시동 포켓몬 자체의 화력과 상대 날씨 견제에 활용하세요."))

    for r in team:
        if r["ability"] in TERRAIN:
            label, moves, play = TERRAIN[r["ability"]]
            users = [x for x in team if set(x["moves"]) & moves]
            add(label, [r] + users, play + (f" {names(users)}의 필드 기술과 함께 선출하세요." if users else ""))

    tr = [r for r in team if "Trick Room" in r["moves"]]
    if tr:
        slow = [r for r in attackers(e, team, fmt) if r["speed"] <= 95 and r not in tr]
        add("트릭룸", tr + slow,
            f"{names(tr)}(으)로 트릭룸을 깔고 5턴 동안 느린 어태커로 먼저 때립니다."
            + (f" 트릭룸 아래 에이스: {names(slow)}." if slow else " 느린 어태커가 없어 상대 스피드 견제용으로만 쓰입니다.")
            + " 시동 턴에는 방어·속이다·유도로 시동 포켓몬을 지키세요.")
    tw = [r for r in team if "Tailwind" in r["moves"]]
    if tw:
        add("순풍", tw, f"{names(tw)}(으)로 순풍을 깔면 4턴 동안 아군 스피드가 2배가 됩니다. 첫 턴에 깔고, 남은 3턴에 화력을 몰아 쓰세요.")
    fo = [r for r in team if "Fake Out" in r["moves"]]
    if fo and fmt == "Doubles":
        add("속이다 지원", fo, f"{names(fo)}의 속이다로 등장 턴에 상대 한 마리를 멈춥니다. 그 사이 옆 포켓몬이 랭크업·시동·집중 공격을 합니다.")
    inti = [r for r in team if r["ability"] == "Intimidate"]
    if inti:
        add("위협", inti, f"{names(inti)}이(가) 나올 때마다 상대 공격이 1랭크 내려갑니다."
            + (" 교체로 여러 번 발동시키는 사이클 운영이 가능합니다." if len(inti) >= 2 or any("pivot" in roles[r["id"]] for r in inti) else ""))
    red = [r for r in team if set(r["moves"]) & ROLE_MOVES["redirect"]]
    setup = [r for r in team if set(r["moves"]) & ROLE_MOVES["setup"] and r not in red]
    if red and setup and fmt == "Doubles":
        add("유도 + 랭크업", red + setup, f"{names(red)}이(가) 공격을 끌어오는 동안 {names(setup)}이(가) 랭크업한 뒤 전개합니다.")
    elif setup:
        add("랭크업 에이스", setup, f"{names(setup)}이(가) 랭크업할 턴을 만들어 주는 것이 핵심입니다. 상대의 도발·앙코르·흑안개를 먼저 확인하세요.")
    fast = [r for r in attackers(e, team, fmt) if "fast" in roles[r["id"]]]
    if len(fast) >= 4:
        add("고속 공세", fast, "빠른 어태커로 먼저 때려 수적 우위를 만드는 팀입니다. 상대의 순풍·트릭룸을 허용하면 급격히 불리해지니 시동 포켓몬을 최우선으로 노리세요.")
    if not out:
        add("밸런스형", [], "뚜렷한 축 없이 개별 상성으로 싸우는 팀입니다. 상대 6마리를 보고 유리한 4마리(싱글 3마리)를 고르는 선출이 가장 중요합니다.")
    return out


# ------------------------------------------------------------------ 기본 선출
def default_lead(e: Engine, team: list[dict], fmt: str, meta: list[dict], ws: list[float]) -> dict | None:
    n_lead, n_bring = (2, 4) if fmt == "Doubles" else (1, 3)
    if len(team) < n_lead:
        return None
    n_bring = min(n_bring, len(team))
    wsum = sum(ws)
    sc = {a["id"]: [e.matchup(a, b, fmt)["score"] for b in meta] for a in team}
    roles = {a["id"]: set(e.roles(a, fmt)) for a in team}

    def mean(a):
        return sum(w * s for w, s in zip(ws, sc[a["id"]])) / wsum

    def reasons(lead):
        ro, why = set().union(*(roles[a["id"]] for a in lead)), []
        if fmt == "Doubles":
            if "fakeout" in ro:
                why.append("속이다로 첫 턴 주도권")
            if ro & {"tailwind", "trickroom"}:
                why.append("첫 턴에 스피드 컨트롤 시동")
            elif "speedcontrol" in ro:
                why.append("스피드 견제 기술 보유")
            if "intimidate" in ro:
                why.append("위협으로 상대 물리 화력 견제")
            if ro & {"weather", "terrain"}:
                why.append("날씨/필드 선점")
            if "redirect" in ro:
                why.append("유도로 옆 포켓몬 보호")
        else:
            if "hazard" in ro:
                why.append("설치기로 초반 깔기")
            if "pivot" in ro:
                why.append("교체 기술로 유리한 대면 만들기")
            if "fast" in ro:
                why.append("빠른 선봉으로 선공")
        return why

    best = None
    for lead in combinations(team, n_lead):
        s = sum(mean(a) for a in lead) / n_lead + 2.5 * len(reasons(lead))
        megas = sum(1 for a in lead if a["mega"])
        if megas > 1:
            s -= 8
        if best is None or s > best[0]:
            best = (s, lead)
    lead = best[1]
    rest = [a for a in team if a not in lead]

    def coverage(group):
        tot = 0.0
        for j, w in enumerate(ws):
            s = sorted((sc[a["id"]][j] for a in group), reverse=True)
            tot += w * (s[0] if len(s) == 1 else 0.65 * s[0] + 0.35 * s[1])
        return tot / wsum - 4 * max(0, sum(1 for a in group if a["mega"]) - 1)

    back = max(combinations(rest, n_bring - n_lead), key=lambda b: coverage(lead + b)) if rest else ()
    return {"lead": [mini(a) for a in lead], "back": [mini(a) for a in back],
            "bench": [mini(a) for a in team if a not in lead and a not in back],
            "why": reasons(lead) or ["메타 상위권 상대로 평균 상성이 가장 좋은 조합"]}


# ------------------------------------------------------------------ 승리 플랜(주력)
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
            xm, ym = set(x["moves"]), set(y["moves"])
            for mv in x["moves"]:  # 아군까지 때리는 전체기
                m = e.M[mv]
                if m["target"] == "allAdjacent" and m["power"]:
                    mult = type_multiplier(m["type"], y["types"], y["ability"])
                    mk = m["ko"] or mv
                    if mult == 0:
                        add("good", x, y, f"{n(x)}의 {mk}을(를) {n(y)}이(가) 무효로 받아, 아군 피해 없이 전체기를 쓸 수 있습니다.")
                    elif mult >= 2:
                        add("warn", x, y, f"함께 내면 {n(x)}의 {mk}이(가) {n(y)}에게 {mult:g}배로 들어갑니다. 방어를 누르거나 따로 선출하세요.")
            if "Fake Out" in xm and ym & (ROLE_MOVES["setup"] | {"Trick Room", "Tailwind"}):
                what = next(iter(ym & (ROLE_MOVES["setup"] | {"Trick Room", "Tailwind"})))
                add("good", x, y, f"{n(x)}의 속이다로 한 마리를 멈추는 턴에 {n(y)}이(가) {e.M[what]['ko'] or what}을(를) 씁니다.")
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
                add("good", x, y, f"{n(x)}의 순풍 아래에서 {n(y)}(스피드 {round(y['speed'])})이(가) 대부분의 상대보다 먼저 움직입니다.")
    seen, uniq = set(), []
    for s in sorted(out, key=lambda s: s["kind"] != "warn"):
        key = (s["members"][0]["id"], s["members"][1]["id"], s["text"][:12])
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    return uniq[:9]


# ------------------------------------------------------------------ 메타 전략별 대비
def prep(e: Engine, team, fmt) -> list[dict]:
    rows = []

    def has_move(names_):
        return [r for r in team if set(r["moves"]) & set(names_)]

    def typed(t):
        return [r for r in team if t in r["types"]]

    def weak_to(t):
        return [r for r in team if type_multiplier(t, r["types"], r["ability"]) >= 2]

    def hitters(t):
        return [r for r in team if any(e.M[m]["type"] == t and e.M[m]["power"] for m in r["moves"])]

    def add(label, answers, strong, advice_ok, advice_weak, note=""):
        seen, uniq = set(), []
        for r in answers:
            if r["id"] not in seen:
                seen.add(r["id"])
                uniq.append(r)
        level = "good" if len(uniq) >= strong else "ok" if uniq else "weak"
        rows.append({"label": label, "level": level, "answers": [mini(r) for r in uniq],
                     "advice": (advice_ok if uniq else advice_weak) + note})

    if fmt == "Doubles":
        add("트릭룸", has_move(["Taunt", "Imprison", "Trick Room", "Roar", "Whirlwind", "Fake Out", "Encore"]), 2,
            "시동 턴에 도발·속이다로 막거나 시동 포켓몬에 집중 공격하세요. 깔렸다면 방어·교체로 5턴을 흘립니다.",
            "트릭룸을 막을 수단이 없습니다. 도발이나 속이다를 가진 포켓몬을 넣거나, 깔리면 방어로 턴을 흘려야 합니다.")
        own = has_move(SPEED_MOVES)
        prio = [r for r in team if "priority" in e.roles(r, fmt)]
        add("순풍", own + prio, 2,
            "내 스피드 컨트롤로 맞불을 놓거나, 순풍 4턴 동안 방어·선공기로 버팁니다.",
            "스피드 컨트롤과 선공기가 모두 없습니다. 상대 순풍 턴에 일방적으로 맞게 됩니다.")
    ww = weak_to("Water")
    add("비 파티", [r for r in team if r["ability"] in ("Drought", "Sand Stream", "Snow Warning", "Water Absorb", "Storm Drain", "Dry Skin")]
        + hitters("Electric") + hitters("Grass"), 2,
        "날씨를 덮어쓰거나 전기·풀 기술로 물 타입을 압박하세요.",
        "물 타입을 찌를 전기·풀 기술과 날씨 대책이 없습니다.",
        f" 물 약점: {names(ww)}." if ww else "")
    fw = weak_to("Fire")
    add("쾌청 파티", [r for r in team if r["ability"] in ("Drizzle", "Sand Stream", "Snow Warning", "Flash Fire")]
        + hitters("Rock") + hitters("Water"), 2,
        "날씨를 덮어쓰거나 바위·물 기술로 불꽃 타입을 압박하세요.",
        "불꽃 타입을 찌를 바위·물 기술과 날씨 대책이 없습니다.",
        f" 불꽃 약점: {names(fw)}." if fw else "")
    add("사이코스팸", typed("Dark") + [r for r in team if r["ability"] in TERRAIN and r["ability"] != "Psychic Surge"]
        + typed("Steel"), 2,
        "악 타입은 에스퍼 기술을 무효로 받습니다. 필드를 덮어쓰면 와이드포스가 약해집니다.",
        "에스퍼 기술을 받아낼 악·강철 타입과 필드 대책이 없습니다.",
        " 사이코필드에서는 내 선공기가 막히는 점도 주의하세요.")
    spec = [r for r in team if set(e.roles(r, fmt)) & {"special", "mixed"}]
    proof = [r for r in team if r["ability"] in INTIM_PROOF]
    add("위협", spec + proof, 3,
        "특수 어태커와 위협이 통하지 않는 포켓몬을 중심으로 선출하세요.",
        "화력이 전부 물리라 위협에 크게 약해집니다. 특수 어태커를 한 마리 이상 넣으세요.")
    if fmt == "Doubles":
        add("속이다", typed("Ghost") + [r for r in team if r["ability"] in ("Inner Focus", "Psychic Surge", "Armor Tail", "Queenly Majesty", "Dazzling")]
            + has_move(["Fake Out"]), 2,
            "고스트 타입·정신력은 속이다가 통하지 않습니다. 첫 턴에 방어를 섞어 속이다를 낭비시키세요.",
            "속이다를 무시할 수단이 없습니다. 첫 턴 방어로 읽기 싸움을 해야 합니다.")
    add("선공기 공세", [r for r in team if r["ability"] in PRIORITY_BLOCK] + [r for r in team if "bulky" in e.roles(r, fmt)], 2,
        "내구형으로 선공기를 받아내고, 체력이 깎인 어태커는 방어·교체로 지키세요.",
        "내구가 낮은 팀이라 체력이 깎이면 선공기에 차례로 마무리당합니다.")
    return rows


# ------------------------------------------------------------------ 위험 상대와 대응법
def threats(e: Engine, team, fmt, meta) -> list[dict]:
    rows = []
    for b in meta:
        per = [(a, e.matchup(a, b, fmt)) for a in team]
        score = e.team_score([m["score"] for _, m in per])
        hits = sorted(((a, m) for a, m in per if m["hit"]), key=lambda x: -x[1]["score"])
        danger = sorted(((a, m) for a, m in per if m["taken"] and m["taken"]["pct"] >= 80), key=lambda x: -x[1]["taken"]["pct"])
        steps = []
        if hits:
            a, m = hits[0]
            h = m["hit"]
            mk = e.M[h["move"]]["ko"] or h["move"]
            if h["pct"] >= 100:
                steps.append(f"{n(a)}의 {mk}(으)로 한 번에 쓰러뜨립니다 ({h['pct']:.0f}%, {'선공' if m['faster'] else '후공 — 한 대 맞고 때립니다'}).")
            elif h["pct"] >= 50:
                steps.append(f"{n(a)}의 {mk}(으)로 2타에 쓰러뜨립니다 ({h['pct']:.0f}%, {'선공' if m['faster'] else '후공'}).")
            else:
                steps.append(f"가장 아픈 기술이 {n(a)}의 {mk} {h['pct']:.0f}%로, 혼자서는 잡기 어렵습니다.")
            if fmt == "Doubles" and len(hits) >= 2 and h["pct"] < 100:
                a2, m2 = max(hits[1:], key=lambda x: x[1]["hit"]["pct"])
                total = h["pct"] + m2["hit"]["pct"]
                if total >= 100:
                    mk2 = e.M[m2["hit"]["move"]]["ko"] or m2["hit"]["move"]
                    steps.append(f"{n(a)} + {n(a2)}({mk2}) 집중 공격이면 한 턴에 처리됩니다 (합계 {total:.0f}%).")
        if danger:
            a, m = danger[0]
            mk = e.M[m["taken"]["move"]]["ko"] or m["taken"]["move"]
            steps.append(f"{names(a for a, _ in danger[:3])}은(는) 맞대면을 피하세요 — {n(a)}이(가) {mk}에 {m['taken']['pct']:.0f}% 받습니다.")
        safe = [a for a, m in per if not m["taken"] or m["taken"]["pct"] < 40]
        if safe and danger:
            steps.append(f"받아내기 좋은 포켓몬: {names(safe[:2])}.")
        rows.append({"mon": mini(b), "rank": e.rank(b["id"], fmt), "score": round(score, 1), "label": e.label(score),
                     "steps": steps,
                     "answer": mini(hits[0][0]) if hits else None})
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


def team_guide(e: Engine, sets: list[dict], fmt: str, top_n: int = 20) -> dict | None:
    team = [e.resolve(s, fmt) for s in sets if s.get("id") in e.P]
    if not team:
        return None
    meta = e.meta(fmt, top_n)
    ws = [weight(e.rank(b["id"], fmt)) for b in meta]
    return polish({
        "axes": axes(e, team, fmt),
        "lead": default_lead(e, team, fmt, meta, ws),
        "winConditions": win_conditions(e, team, fmt, meta, ws),
        "synergies": synergies(e, team, fmt),
        "prep": prep(e, team, fmt),
        "threats": threats(e, team, fmt, meta),
        "complete": len(team) >= (4 if fmt == "Doubles" else 3),
    })
