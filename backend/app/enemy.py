"""Phase 4: 상대 팀 분석 / 예상 선봉 / 선출·선봉 추천.

원본 데이터에 선봉 통계가 없으므로, 예상 선봉은 동료 채용 순서·역할 시너지·내 팀에 대한 압박으로 추정한다.
상대는 포켓몬마다 가장 흔한 세트를 들고 있다고 가정한다.
"""
from __future__ import annotations

from itertools import combinations

from .engine import ROLE_MOVES, Engine, weight

WEATHER = [
    ("Drizzle", "rain", "비 파티", {"Swift Swim"}, "Water",
     "비 아래 물 기술과 쓱쓱 가속을 조심. 날씨를 덮어쓰거나 전기/풀로 압박"),
    ("Drought", "sun", "쾌청 파티", {"Chlorophyll", "Solar Power"}, "Fire",
     "쾌청 아래 불꽃 기술과 엽록소 가속을 조심. 바위 기술과 날씨 덮어쓰기가 유효"),
    ("Sand Stream", "sand", "모래바람 파티", {"Sand Rush", "Sand Force"}, "Rock",
     "모래헤치기 가속을 조심. 물/풀/격투로 압박"),
    ("Snow Warning", "snow", "설경 파티", {"Slush Rush", "Ice Body"}, "Ice",
     "오로라베일과 눈보라를 조심. 불꽃/강철/격투로 압박"),
]
OTHER_TERRAINS = [("Grassy Surge", "그래스필드"), ("Electric Surge", "일렉트릭필드"), ("Misty Surge", "미스트필드")]
CORE_KEYS = ("rain", "sun", "sand", "snow", "psyspam", "trickroom")


def mini(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "ko": r["ko"], "sprite": r["sprite"], "types": r["types"]}


def pool(e: Engine, r: dict, fmt: str) -> tuple[set, set]:
    """상대가 들고 있을 법한 기술/특성 (채용률 20% 이상 포함)."""
    u = e.P[r["id"]]["usage"].get(fmt) or {}
    moves = set(r["moves"]) | {m["name"] for m in u.get("moves", []) if m["pct"] >= 20}
    abil = {r["ability"]}
    if not r["mega"]:
        abil |= {a["name"] for a in u.get("abilities", []) if a["pct"] >= 20}
    return moves, abil


def strategies(e: Engine, enemy: list[dict], fmt: str) -> list[dict]:
    info = [(r, *pool(e, r, fmt), set(e.roles(r, fmt))) for r in enemy]
    out = []

    def add(key, label, members, tip, strong):
        seen, uniq = set(), []
        for r in members:
            if r["id"] not in seen:
                seen.add(r["id"])
                uniq.append(mini(r))
        out.append({"key": key, "label": label, "confidence": "HIGH" if strong else "MEDIUM",
                    "members": uniq, "tip": tip})

    def having(pred):
        return [r for r, mv, ab, ro in info if pred(r, mv, ab, ro)]

    def attacker(ro):
        return bool(ro & {"physical", "special", "mixed"})

    for ability, key, label, abusers, wtype, tip in WEATHER:
        setters = having(lambda r, mv, ab, ro: ability in ab)
        if not setters:
            continue
        ab_users = having(lambda r, mv, ab, ro: bool(ab & abusers))
        typed = having(lambda r, mv, ab, ro: wtype in r["types"] and r not in setters)
        full = bool(ab_users or typed)  # 날씨를 살리는 동료가 없으면 '요소'로만 표시
        add(key, label if full else label.replace(" 파티", " 요소"), setters + ab_users + typed, tip,
            bool(ab_users) or len(typed) >= 2)

    surge = having(lambda r, mv, ab, ro: "Psychic Surge" in ab)
    if surge:
        ef = having(lambda r, mv, ab, ro: "Expanding Force" in mv)
        psy = having(lambda r, mv, ab, ro: "Psychic" in r["types"] and r not in surge and "special" in ro)
        if ef or psy:
            add("psyspam", "사이코스팸", surge + ef + psy,
                "사이코필드 + 와이드포스. 필드를 덮어쓰거나 악 타입으로 압박 (내 선공기는 필드에 막힘)", bool(ef))
    for ability, label in OTHER_TERRAINS:
        s = having(lambda r, mv, ab, ro: ability in ab)
        if s:
            add("terrain", label, s, "필드 보정 기술과 필드 의존 특성을 확인", False)

    tr = having(lambda r, mv, ab, ro: "Trick Room" in mv)
    if tr:
        slow = having(lambda r, mv, ab, ro: r["speed"] <= 95 and r not in tr and attacker(ro))
        if slow or len(tr) >= 2:
            add("trickroom", "트릭룸", tr + slow,
                "트릭룸 시동을 도발/속이다/집중 공격으로 막거나, 방어로 턴을 흘리기", len(slow) >= 2)
    tw = having(lambda r, mv, ab, ro: "Tailwind" in mv)
    if tw:
        add("tailwind", "순풍", tw, "순풍 턴에는 방어/교체로 버티고, 시동 포켓몬을 먼저 처리", len(tw) >= 2)
    prio = having(lambda r, mv, ab, ro: "priority" in ro)
    if len(prio) >= 3:
        add("priority", "선공기 공세", prio, "체력이 깎인 포켓몬은 선공기에 마무리당함. 내구를 남기는 교체가 중요", True)
    fo = having(lambda r, mv, ab, ro: "Fake Out" in mv)
    if len(fo) >= 2 and fmt == "Doubles":
        add("fakeout", "속이다 압박", fo, "첫 턴 속이다를 전제로 방어/고스트 타입으로 대응", False)
    inti = having(lambda r, mv, ab, ro: "Intimidate" in ab)
    if len(inti) >= 2:
        add("intimidate", "위협 사이클", inti, "물리 어태커가 약해짐. 특수 화력이나 오기/승기로 대응", True)
    red = having(lambda r, mv, ab, ro: bool(mv & ROLE_MOVES["redirect"]))
    setup = having(lambda r, mv, ab, ro: bool(mv & ROLE_MOVES["setup"]))
    if red and [s for s in setup if s not in red] and fmt == "Doubles":
        add("redirect", "유도 + 랭크업", red + setup, "유도 포켓몬을 먼저 쓰러뜨리거나 전체기로 함께 타격", False)
    fast = having(lambda r, mv, ab, ro: "fast" in ro and attacker(ro))
    if len(fast) >= 4:
        add("hyper", "고속 공세", fast, "스피드 컨트롤(순풍/트릭룸/얼다바람)과 내구형으로 받아내기", False)
    if not out:
        add("balance", "밸런스형", [], "뚜렷한 축이 없습니다. 개별 상성 위주로 선출하세요", False)
    return out


def likely_leads(e: Engine, enemy: list[dict], fmt: str, team: list[dict], strats: list[dict]) -> list[dict]:
    roles = {r["id"]: set(e.roles(r, fmt)) for r in enemy}
    core = [set(m["id"] for m in s["members"]) for s in strats if s["key"] in CORE_KEYS]

    def pressure(r):  # 내 팀을 얼마나 압박하는가
        if not team:
            return 0.0
        return (sum(100 - e.matchup(m, r, fmt)["score"] for m in team) / len(team) - 50) * 0.35

    def solo(r):
        ro = roles[r["id"]]
        s = 24 * weight(e.rank(r["id"], fmt) or 200)
        if fmt == "Singles":
            s += 8 * ("hazard" in ro) + 6 * ("pivot" in ro) + 5 * ("fast" in ro) + 8 * (r["item"] == "Focus Sash")
        else:
            s += 6 * ("intimidate" in ro) + 5 * ("fakeout" in ro) + 6 * bool(ro & {"tailwind", "trickroom"})
            s += 6 * bool(ro & {"weather", "terrain"})
        return s + pressure(r)

    cands = []
    if fmt == "Singles":
        for r in enemy:
            why = []
            if roles[r["id"]] & {"hazard"}:
                why.append("설치기 선봉")
            if r["item"] == "Focus Sash":
                why.append("기합의띠")
            cands.append(([r], 20 + solo(r), why))
    else:
        for a, b in combinations(enemy, 2):
            s, why = 20 + solo(a) + solo(b), []
            ta = e.P[a["id"]]["usage"].get(fmt, {}).get("teammates", [])
            tb = e.P[b["id"]]["usage"].get(fmt, {}).get("teammates", [])
            syn = (10 - ta.index(b["id"]) if b["id"] in ta else 0) + (10 - tb.index(a["id"]) if a["id"] in tb else 0)
            if syn:
                s += syn * 1.2
                why.append("자주 함께 쓰이는 조합")
            for x, y in ((roles[a["id"]], roles[b["id"]]), (roles[b["id"]], roles[a["id"]])):
                if "fakeout" in x and y & {"setup", "trickroom", "tailwind"}:
                    s += 12
                    why.append("속이다로 시동 보조")
                if "redirect" in x and y & {"setup", "trickroom"}:
                    s += 12
                    why.append("유도로 시동 보조")
            if any(a["id"] in c and b["id"] in c for c in core):
                s += 16
                why.append("전략의 핵심 조합")
            if a["mega"] and b["mega"]:
                s -= 18
            cands.append(([a, b], s, why))
    cands.sort(key=lambda c: -c[1])
    top = cands[:6]
    tot = sum(max(c[1], 1) ** 3 for c in top) or 1
    best = max(top[0][1], 1)
    return [{"members": [mini(r) for r in ms], "ids": [r["id"] for r in ms],
             "prob": round(max(s, 1) ** 3 / tot, 3),
             "level": "HIGH" if s >= best * 0.92 else "MEDIUM" if s >= best * 0.8 else "LOW",
             "why": list(dict.fromkeys(why))} for ms, s, why in top[:4]]


def recommend(e: Engine, team: list[dict], enemy: list[dict], fmt: str, leads: list[dict]) -> dict | None:
    n_lead, n_bring = (2, 4) if fmt == "Doubles" else (1, 3)
    if len(team) < n_lead:
        return None
    n_bring = min(n_bring, len(team))
    by_id = {r["id"]: r for r in enemy}
    mu = {(a["id"], f["id"]): e.matchup(a, f, fmt) for a in team for f in enemy}
    roles = {a["id"]: set(e.roles(a, fmt)) for a in team}
    foe_roles = {f["id"]: set(e.roles(f, fmt)) for f in enemy}

    def duel(lead, eids):
        s = sum(mu[(a["id"], f)]["score"] for a in lead for f in eids) / (len(lead) * len(eids))
        ro = set().union(*(roles[a["id"]] for a in lead))
        return s + 3 * ("fakeout" in ro) + 3 * ("speedcontrol" in ro) + 2 * ("intimidate" in ro)

    psum = sum(l["prob"] for l in leads) or 1

    def lead_score(lead):
        return sum(l["prob"] * duel(lead, l["ids"]) for l in leads) / psum

    def coverage(group):
        tot = 0.0
        for f in enemy:
            s = sorted((mu[(a["id"], f["id"])]["score"] for a in group), reverse=True)
            tot += s[0] if len(s) == 1 else 0.65 * s[0] + 0.35 * s[1]
        return tot / len(enemy)

    options = []
    for lead in combinations(team, n_lead):
        ls = lead_score(lead)
        rest = [a for a in team if a not in lead]
        best = None
        for back in combinations(rest, n_bring - n_lead):
            megas = sum(1 for a in lead + back if a["mega"])
            sc = 0.6 * ls + 0.4 * coverage(lead + back) - 4 * max(0, megas - 1)
            if sum(1 for a in lead if a["mega"]) > 1:
                sc -= 6
            if best is None or sc > best[0]:
                best = (sc, back)
        options.append((best[0], lead, best[1]))
    options.sort(key=lambda o: -o[0])
    score, lead, back = options[0]

    plans = []
    for l in leads[:3]:
        foes = [by_id[i] for i in l["ids"]]
        actions, risks, switch = [], [], None
        for a in lead:
            hits = [(mu[(a["id"], f["id"])]["hit"], f) for f in foes if mu[(a["id"], f["id"])]["hit"]]
            if hits:
                h, f = max(hits, key=lambda x: min(x[0]["pct"], 100) * x[0]["acc"])
                actions.append({"mon": mini(a), "move": h["move"], "target": mini(f), "pct": h["pct"],
                                "faster": mu[(a["id"], f["id"])]["faster"]})
            taken = [(mu[(a["id"], f["id"])]["taken"], f) for f in foes if mu[(a["id"], f["id"])]["taken"]]
            if not taken:
                continue
            worst, foe = max(taken, key=lambda x: x[0]["pct"])
            if worst["pct"] >= 60:
                risks.append({"from": mini(foe), "move": worst["move"], "to": mini(a), "pct": worst["pct"]})
            if worst["pct"] >= 85 and back and not switch:
                cand = max(back, key=lambda b: mu[(b["id"], foe["id"])]["score"])
                cmu = mu[(cand["id"], foe["id"])]
                if cmu["score"] >= 52 and (not cmu["taken"] or cmu["taken"]["pct"] < worst["pct"] * 0.6):
                    reason = f"{foe['ko'] or foe['name']}의 공격을 받아내기"
                    if roles[cand["id"]] & {"terrain", "weather"} and \
                            any(foe_roles[f["id"]] & {"terrain", "weather"} for f in foes):
                        reason += " + 날씨/필드 덮어쓰기"
                    switch = {"out": mini(a), "in": mini(cand), "reason": reason, "move": worst["move"],
                              "takenPct": cmu["taken"]["pct"] if cmu["taken"] else 0}
        if switch:
            actions = [x for x in actions if x["mon"]["id"] != switch["out"]["id"]]
            e.with_move_ko([switch])
        e.with_move_ko(actions)
        e.with_move_ko(risks)
        plans.append({"enemyLead": l["members"], "level": l["level"], "prob": l["prob"],
                      "score": round(duel(lead, l["ids"]), 1), "actions": actions,
                      "risks": sorted(risks, key=lambda r: -r["pct"]), "switch": switch})

    return {"lead": [e.describe(a, fmt) for a in lead], "back": [e.describe(a, fmt) for a in back],
            "score": round(score, 1), "plans": plans,
            "alternatives": [{"lead": [mini(a) for a in ld], "back": [mini(a) for a in bk], "score": round(s, 1)}
                             for s, ld, bk in options[1:4]]}


def analyze_enemy(e: Engine, enemy_ids: list[str], team_sets: list[dict], fmt: str) -> dict:
    enemy, seen = [], set()
    for i in enemy_ids:
        if i in e.P and i not in seen:
            seen.add(i)
            enemy.append(e.default_resolved(i, fmt))
    if not enemy:
        return {"enemy": []}
    team = [e.resolve(s, fmt) for s in team_sets if s.get("id") in e.P]
    strats = strategies(e, enemy, fmt)
    leads = likely_leads(e, enemy, fmt, team, strats)
    rows = []
    for f in enemy:
        row = {**e.describe(f, fmt), "threat": None, "answer": None, "danger": []}
        if team:
            ms = [(a, e.matchup(a, f, fmt)) for a in team]
            row["threat"] = round(sum(100 - m["score"] for _, m in ms) / len(ms), 1)
            a, m = max(ms, key=lambda x: x[1]["score"])
            row["answer"] = e.with_move_ko([{**mini(a), "score": m["score"],
                                             "move": m["hit"]["move"] if m["hit"] else None,
                                             "pct": m["hit"]["pct"] if m["hit"] else 0}])[0]
            row["danger"] = e.with_move_ko(sorted(
                [{**mini(a), "move": m["taken"]["move"], "pct": m["taken"]["pct"]}
                 for a, m in ms if m["taken"] and m["taken"]["pct"] >= 70], key=lambda x: -x["pct"])[:4])
        rows.append(row)
    if team:
        rows.sort(key=lambda r: -r["threat"])
    return {"format": fmt, "enemy": rows, "strategies": strats, "leads": leads,
            "recommendation": recommend(e, team, enemy, fmt, leads) if team else None}
