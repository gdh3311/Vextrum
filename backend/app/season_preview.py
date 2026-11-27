"""다음 시즌 미리보기: 발표된 레귤레이션·밸런스 조정·새 포켓몬이 지금 메타와 내 팀에 미칠 영향.

시즌이 시작되기 전에 대비할 수 있게, 공식 공지로 만든 '다음 시즌 규칙' 엔진과 지금 엔진을 비교한다.
- 밸런스: 바뀐 기술을 실제로 많이 쓰는 메타 상위 포켓몬 (채용률 기준), 새로 배우는 기술, 특성 변경
- 새 포켓몬: 지금 메타 상위권과의 1:1 상성 점수 (엔진의 matchup, 50 이 호각) — 잘 잡는 상대와 위협
- 내 팀: 위 변화가 내 팀 포켓몬에 닿는 곳, 새 포켓몬과 내 팀의 상성
수치는 앱의 계산식·통계에서 나온 추정이며 실제 랭크전 결과가 아니다.
"""
from __future__ import annotations

from .engine import Engine
from .mechanics import FLINCH

FIELD_LABELS = {"accuracy": "명중률", "power": "위력", "priority": "우선도", "flinch": "풀죽음 확률"}
FLAG_TEXT = {
    "flashFirePersists": ("Flash Fire", "타오르는불꽃 효과가 메가진화 뒤에도 유지"),
    "stalwartBypassesSubstitute": ("Stalwart", "굳건한신념이 대타출동을 무시"),
}


def _name(p):
    return p.get("ko") or p["name"]


def _mon(e, pid):
    p = e.P[pid]
    return {"id": pid, "name": p["name"], "ko": p.get("ko"), "sprite": p["sprite"],
            "rank": (e.rank(pid, "Doubles") or None), "provisional": bool(p.get("provisional"))}


def _move_ko(e, move):
    return (e.M.get(move) or {}).get("ko") or move


def balance_impact(now: Engine, nxt: Engine, fmt: str, top: int = 80):
    """바뀐 기술·새 기술·특성 변경이 메타 상위 포켓몬에 닿는 곳."""
    moves = {}
    for name, fields in nxt.rules.get("moveChanges", {}).items():
        current = now.M.get(name, {})
        before = {k: current.get(k, FLINCH.get(name, 0)) if k == "flinch" else current.get(k) for k in fields}
        if k_changes := {k: (before[k], v) for k, v in fields.items() if before[k] != v}:
            moves[name] = k_changes
    ranked = now.ranked(fmt)[:top]
    move_rows = []
    for name, fields in moves.items():
        users = []
        for p in ranked:
            pct = next((m["pct"] for m in p["usage"][fmt]["moves"] if m["name"] == name), 0)
            if pct >= 10:
                users.append({**_mon(now, p["id"]), "rank": p["usage"][fmt]["rank"], "pct": pct})
        move_rows.append({
            "move": name, "ko": _move_ko(now, name),
            "changes": [{"field": k, "label": FIELD_LABELS.get(k, k), "before": a, "after": b} for k, (a, b) in fields.items()],
            "users": users[:12],
        })
    move_rows.sort(key=lambda r: -sum(u["pct"] / (u["rank"] ** .5) for u in r["users"]))

    learn_rows = []
    for pid, learned in nxt.rules.get("learnChanges", {}).items():
        if pid not in now.P:
            continue
        new = [m for m in learned if m not in now.P[pid].get("learnset", [])]
        if new:
            learn_rows.append({**_mon(now, pid), "rank": now.rank(pid, fmt),
                               "moves": [{"move": m, "ko": _move_ko(now, m)} for m in new]})
    learn_rows.sort(key=lambda r: r["rank"] or 999)

    ability_rows = []
    for flag, (ability, text) in FLAG_TEXT.items():
        if nxt.rules.get("flags", {}).get(flag) and not now.rules.get("flags", {}).get(flag):
            holders = [{**_mon(now, p["id"]), "rank": p["usage"][fmt]["rank"]} for p in ranked
                       if ability in p["abilities"] or any(ability in m["abilities"] for m in p["megas"])]
            ability_rows.append({"ability": ability, "text": text, "holders": holders[:12]})
    return {"moves": move_rows, "learn": learn_rows, "abilities": ability_rows}


def newcomer_report(nxt: Engine, fmt: str, meta_top: int = 30):
    """새로 참가하는 포켓몬(지금 데이터에 채용 기록이 없는 것)의 지금 메타 상대 상성."""
    meta = [p for p in nxt.ranked(fmt)[:meta_top]]
    foes = [nxt.default_resolved(p["id"], fmt) for p in meta]
    out = []
    for pid, p in nxt.P.items():
        if not p.get("provisional") or not nxt.eligible(pid):
            continue
        forms = [(None, nxt.resolve(nxt.default_set(pid, fmt), fmt))]
        for m in nxt.mega_forms(p):
            if m.get("stone"):
                forms.append((m["name"], nxt.resolve({**nxt.default_set(pid, fmt), "item": m["stone"], "mega": m["name"]}, fmt)))
        for mega, mon in forms:
            scores = [(nxt.matchup(mon, foe, fmt)["score"], foe) for foe in foes]
            if not scores:
                continue
            avg = sum(s for s, _ in scores) / len(scores)
            good = sorted(scores, key=lambda r: -r[0])[:5]
            bad = sorted(scores, key=lambda r: r[0])[:5]
            row = lambda r: {**_mon(nxt, r[1]["id"]), "score": r[0]}
            out.append({**_mon(nxt, pid), "mega": mega,
                        "types": mon["types"], "stats": mon["stats"], "speed": round(mon["speed"]),
                        "ability": mon["ability"], "moves": mon["moves"],
                        "average": round(avg, 1), "beats": [row(r) for r in good], "threats": [row(r) for r in bad]})
    out.sort(key=lambda r: -r["average"])
    return out


def team_impact(now: Engine, nxt: Engine, fmt: str, sets: list[dict], balance: dict, newcomers: list[dict]):
    """내 팀에 닿는 변화: 바뀐 기술을 쓰는 멤버, 새 기술을 배우는 멤버, 새 포켓몬과의 상성."""
    team = [s for s in sets if s.get("id") in nxt.P]
    if not team:
        return None
    changed = {r["move"]: r for r in balance["moves"]}
    learn = {r["id"]: r for r in balance["learn"]}
    members = []
    for s in team:
        full = {**nxt.default_set(s["id"], fmt), **s}
        notes = []
        for move in full.get("moves") or []:
            if move in changed:
                notes.append(f"{changed[move]['ko']}: " + ", ".join(
                    f"{c['label']} {c['before']}→{c['after']}" for c in changed[move]["changes"]))
        if s["id"] in learn:
            notes.append("새로 배움: " + ", ".join(m["ko"] for m in learn[s["id"]]["moves"]))
        if not nxt.eligible(s["id"]):
            notes.append("다음 시즌 규정으로 참가할 수 없음")
        members.append({**_mon(nxt, s["id"]), "notes": notes})
    mine = [nxt.resolve({**nxt.default_set(s["id"], fmt), **s}, fmt) for s in team]
    versus = []
    for row in newcomers:
        if row["mega"]:
            continue
        foe = nxt.resolve(nxt.default_set(row["id"], fmt), fmt)
        scores = [{**_mon(nxt, m["id"]), "score": nxt.matchup(m, foe, fmt)["score"]} for m in mine]
        best = max(scores, key=lambda r: r["score"])
        versus.append({**_mon(nxt, row["id"]), "answers": [r for r in scores if r["score"] >= 55],
                       "best": best, "covered": best["score"] >= 55})
    return {"members": members, "newcomers": versus}


def report(now: Engine, nxt: Engine, fmt: str, changes: list[dict], sets: list[dict] | None = None):
    balance = balance_impact(now, nxt, fmt)
    newcomers = newcomer_report(nxt, fmt)
    return {
        "format": fmt,
        "changes": changes,
        "balance": balance,
        "newcomers": newcomers,
        "team": team_impact(now, nxt, fmt, sets or [], balance, newcomers),
        "note": "앱의 계산식과 지금까지의 통계로 낸 추정입니다. 새 포켓몬은 공개 도감 기준 임시 세트로 계산합니다.",
    }
