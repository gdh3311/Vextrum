"""포켓몬 연구실: 한 마리의 세트를 기준으로
  - 상대별 1:1 우열 (기술별 데미지 범위, 확정수, 스피드)
  - 추천 파트너 (왜 맞는지, 누구를 대신 잡아 주는지)
  - 운용법 (선봉/후발, 노릴 상대, 피할 상대, 스피드, 도구·기술 설명)
을 계산한다. 데미지는 난수 85~100% 범위로 보여 준다 (급소·랭크 변화 미반영).
"""
from __future__ import annotations

import math

from .enemy import mini
from .engine import ROLE_LABELS, ROLE_MOVES, Engine, weight
from .guide import TERRAIN, WEATHER, n, polish
from .typechart import TYPES, type_multiplier

ITEM_NOTES = {
    "Focus Sash": "체력이 가득일 때 어떤 공격이든 한 번 버팁니다. 날씨·설치기·속이다로 미리 깎이면 무효가 되니 주의하세요.",
    "Life Orb": "화력이 1.3배가 되는 대신 공격할 때마다 체력이 10% 줄어듭니다.",
    "Choice Scarf": "스피드가 1.5배가 되지만 처음 고른 기술만 쓸 수 있습니다. 선공으로 마무리한 뒤 교체로 기술을 바꾸세요.",
    "Choice Band": "물리 화력이 1.5배가 되지만 처음 고른 기술만 쓸 수 있습니다.",
    "Choice Specs": "특수 화력이 1.5배가 되지만 처음 고른 기술만 쓸 수 있습니다.",
    "Assault Vest": "특방이 1.5배가 되는 대신 변화기를 쓸 수 없습니다 (방어도 불가).",
    "Sitrus Berry": "체력이 절반 이하가 되면 25% 회복합니다.",
    "Leftovers": "매 턴 체력을 1/16씩 회복합니다. 방어와 함께 쓰면 누적됩니다.",
    "Rocky Helmet": "접촉 공격을 받으면 상대 체력을 1/6 깎습니다.",
    "Clear Amulet": "위협 등 능력 하락을 받지 않습니다.",
    "Covert Cloak": "속이다의 풀죽음 같은 추가 효과를 받지 않습니다.",
    "Safety Goggles": "버섯포자·분노가루와 날씨 피해를 무시합니다.",
    "Mental Herb": "도발·앙코르에 한 번 걸려도 바로 풀립니다.",
    "White Herb": "내려간 능력을 한 번 되돌립니다.",
    "Eviolite": "방어와 특방이 1.5배가 됩니다.",
    "Weakness Policy": "약점을 찔리면 공격·특공이 2랭크 오릅니다.",
}
MOVE_NOTES = {
    "Protect": "집중 공격과 속이다를 흘리고, 순풍·트릭룸 턴을 소모시킵니다. 연속으로 쓰면 실패율이 올라갑니다.",
    "Detect": "방어와 같습니다.",
    "Fake Out": "등장 직후 턴에만 쓸 수 있는 선공기. 상대 한 마리를 풀죽게 해 그 턴에 아무것도 못 하게 합니다.",
    "Tailwind": "4턴 동안 아군 스피드 2배. 첫 턴에 깔고 남은 턴에 화력을 몰아 쓰세요.",
    "Trick Room": "5턴 동안 느린 쪽이 먼저 움직입니다. 우선도가 낮아 그 턴 마지막에 발동합니다.",
    "Follow Me": "그 턴 상대의 단일 대상 기술을 전부 자신에게 끌어옵니다.",
    "Rage Powder": "상대의 단일 대상 기술을 자신에게 끌어옵니다 (풀 타입·방진고글에는 무효).",
    "Helping Hand": "옆 포켓몬의 그 턴 기술 위력을 1.5배로 올립니다.",
    "Wide Guard": "그 턴 상대의 전체기를 아군 둘 다 막습니다.",
    "Taunt": "3턴간 상대가 변화기를 못 쓰게 합니다. 트릭룸·순풍·랭크업 시동을 막습니다.",
    "Encore": "상대가 방금 쓴 기술만 3턴간 쓰게 합니다. 방어·변화기를 쓴 직후가 기회입니다.",
    "Will-O-Wisp": "화상으로 상대 물리 화력을 절반으로 줄입니다.",
    "Thunder Wave": "마비로 상대 스피드를 절반으로 줄입니다.",
    "Spore": "확정으로 잠재웁니다 (풀 타입·방진고글·일렉트릭/미스트필드에는 무효).",
    "Icy Wind": "상대 두 마리의 스피드를 1랭크 내리는 전체기입니다.",
    "Electroweb": "상대 두 마리의 스피드를 1랭크 내리는 전체기입니다.",
    "Snarl": "상대 두 마리의 특공을 1랭크 내리는 전체기입니다.",
    "Parting Shot": "상대의 공격·특공을 내리고 교체합니다.",
    "U-turn": "공격한 뒤 교체합니다. 위협·속이다를 다시 쓰는 데 좋습니다.",
    "Volt Switch": "공격한 뒤 교체합니다 (땅 타입에는 무효라 교체도 실패).",
    "Flip Turn": "공격한 뒤 교체합니다.",
    "Swords Dance": "공격 2랭크 상승. 방어·유도·속이다로 만든 턴에 쓰세요.",
    "Nasty Plot": "특공 2랭크 상승. 방어·유도·속이다로 만든 턴에 쓰세요.",
    "Dragon Dance": "공격·스피드 1랭크 상승.",
    "Calm Mind": "특공·특방 1랭크 상승.",
    "Substitute": "체력 1/4로 분신을 만들어 변화기와 한 번의 공격을 막습니다.",
    "Stealth Rock": "상대가 교체해 나올 때마다 바위 상성 피해를 줍니다.",
    "Knock Off": "상대의 도구를 떨어뜨립니다 (도구가 있으면 위력 1.5배).",
    "Sucker Punch": "상대가 공격 기술을 고른 턴에만 성공하는 선공기입니다.",
    "Extreme Speed": "우선도 +2의 선공기입니다.",
}
LEAD_ROLES = {"fakeout", "tailwind", "trickroom", "weather", "terrain", "intimidate", "redirect", "hazard"}


def rng(pct: float) -> tuple[float, float]:
    return round(pct * 0.85 / 0.925, 1), round(pct / 0.925, 1)


def ko_text(lo: float, hi: float) -> str:
    if hi <= 0:
        return "효과 없음"
    fast, slow = math.ceil(100 / hi), math.ceil(100 / max(lo, 0.1))
    if fast > 6:
        return "6타 이상"
    return f"확정 {fast}타" if fast == slow else f"난수 {fast}타"


def hit_row(e: Engine, h: dict, pct_used: float | None = None) -> dict:
    lo, hi = rng(h["pct"])
    m = e.M[h["move"]]
    return {"move": h["move"], "ko": m["ko"], "type": h["type"], "category": m["category"], "power": m["power"],
            "min": lo, "max": hi, "koText": ko_text(lo, hi), "eff": h["eff"], "acc": h["acc"],
            "priority": h["priority"], "spread": m["target"] in ("allAdjacent", "allAdjacentFoes"),
            **({"usage": pct_used} if pct_used is not None else {})}


def turns(h: dict | None) -> tuple[int, int]:
    """(운이 좋을 때, 확실할 때) 쓰러뜨리는 데 필요한 타수."""
    if not h or h["max"] <= 0:
        return 99, 99
    return math.ceil(100 / h["max"]), math.ceil(100 / max(h["min"], 0.1))


def verdict(mine: dict | None, theirs: dict | None, a_speed: float, b_speed: float) -> dict:
    """1:1로 서로 최선의 기술만 눌렀을 때 누가 먼저 쓰러뜨리는가."""
    my_prio = bool(mine and mine["priority"] > 0)
    th_prio = bool(theirs and theirs["priority"] > 0)
    tie = a_speed == b_speed and my_prio == th_prio
    first = (my_prio and not th_prio) or (my_prio == th_prio and a_speed > b_speed)
    my_fast, my_sure = turns(mine)
    th_fast, th_sure = turns(theirs)

    def i_win(my_t, th_t, i_go_first):
        return my_t <= th_t if i_go_first else my_t < th_t

    if tie:
        sure_win, lucky_win = i_win(my_sure, th_fast, False), i_win(my_fast, th_sure, True)
    else:
        sure_win, lucky_win = i_win(my_sure, th_fast, first), i_win(my_fast, th_sure, first)
    if my_fast >= 99 and th_fast >= 99:
        label, text = "EVEN", "서로 유효타가 없습니다."
    elif sure_win:
        label, text = "WIN", "1:1이면 내가 먼저 쓰러뜨립니다."
    elif not lucky_win:
        label, text = "LOSE", "1:1이면 상대가 먼저 쓰러뜨립니다."
    elif tie:
        label, text = "EVEN", "스피드가 같아 먼저 움직이는 쪽이 이깁니다."
    else:
        label, text = "EVEN", "난수와 선택에 따라 갈립니다."
    return {"label": label, "text": text, "speed": "tie" if a_speed == b_speed else "fast" if a_speed > b_speed else "slow",
            "first": first, "myTurns": my_sure if my_sure < 99 else None, "theirTurns": th_sure if th_sure < 99 else None}


def enemy_pool(e: Engine, b: dict, fmt: str) -> list[tuple[str, float | None]]:
    """상대가 쓸 수 있는 기술: 세트의 4개 + 채용률 8% 이상."""
    u = e.P[b["id"]]["usage"].get(fmt) or {}
    pool = {m["name"]: m["pct"] for m in u.get("moves", []) if m["pct"] >= 8}
    for mv in b["moves"]:
        pool.setdefault(mv, None)
    return list(pool.items())


def duel(e: Engine, a: dict, b: dict, fmt: str) -> dict:
    mine = [hit_row(e, h) for h in (e.damage(a, mv, b, fmt) for mv in a["moves"]) if h]
    theirs = []
    for mv, pct in enemy_pool(e, b, fmt):
        h = e.damage(b, mv, a, fmt)
        if h:
            theirs.append(hit_row(e, h, pct))
    mine.sort(key=lambda r: -r["max"])
    theirs.sort(key=lambda r: -r["max"])
    usable = [r for r in mine if r["move"] != "Fake Out"] or mine
    their_main = [r for r in theirs if r["move"] in b["moves"] and r["move"] != "Fake Out"] or theirs
    best, worst = (usable[0] if usable else None), (their_main[0] if their_main else None)
    v = verdict(best, worst, a["speed"], b["speed"])
    notes = []
    if best:
        notes.append(f"내 최선: {best['ko'] or best['move']} {best['min']:.0f}~{best['max']:.0f}% ({best['koText']}).")
    else:
        notes.append("이 세트에는 상대를 때릴 공격 기술이 없습니다.")
    if worst:
        notes.append(f"상대 최선: {worst['ko'] or worst['move']} {worst['min']:.0f}~{worst['max']:.0f}% ({worst['koText']}).")
    if a["speed"] == b["speed"]:
        notes.append(f"스피드가 같습니다 ({a['speed']:.0f}). 누가 먼저 움직일지는 무작위입니다.")
    elif a["speed"] > b["speed"]:
        notes.append(f"내가 더 빠릅니다 ({a['speed']:.0f} > {b['speed']:.0f})." +
                     (" 다만 상대 순풍 아래에서는 역전됩니다." if b["speed"] * 2 > a["speed"] else ""))
    else:
        notes.append(f"상대가 더 빠릅니다 ({b['speed']:.0f} > {a['speed']:.0f})." +
                     (" 내 순풍 아래에서는 내가 먼저 움직입니다." if a["speed"] * 2 > b["speed"] else ""))
    hidden = [r for r in theirs if r["move"] not in b["moves"] and worst and r["max"] > worst["max"] * 1.2]
    if hidden:
        r = hidden[0]
        notes.append(f"주의: 상대가 {r['ko'] or r['move']}(채용률 {r['usage']:.0f}%)을(를) 들고 있으면 "
                     f"{r['min']:.0f}~{r['max']:.0f}% ({r['koText']})입니다.")
    if b["item"] == "Focus Sash" and best and best["max"] >= 100:
        notes.append("상대가 기합의띠라 한 번에 쓰러뜨릴 수 없습니다. 속이다·날씨·연속기로 먼저 깎으세요.")
    fu = e.P[b["id"]]["usage"].get(fmt) or {}
    return {"me": e.describe(a, fmt), "foe": e.describe(b, fmt), "mine": mine, "theirs": theirs,
            "foeItems": [{"name": i["name"], "ko": (e.d["items"].get(i["name"]) or {}).get("ko"), "pct": i["pct"]}
                         for i in fu.get("items", [])[:6]],
            "status": [{"move": mv, "ko": e.M[mv]["ko"], "type": e.M[mv]["type"]} for mv in a["moves"]
                       if e.M[mv]["category"] == "Status"],
            "verdict": v, "notes": polish(notes)}


# ------------------------------------------------------------------ 대표 세트
def variants(e: Engine, pid: str, fmt: str) -> list[dict]:
    p = e.P[pid]
    u = p["usage"].get(fmt)
    base = e.default_set(pid, fmt)
    if not u:
        return [{"label": "기본 세트", "pct": None, "set": base}]
    out, seen = [], set()
    items_ko = e.d["items"]
    for it in u["items"][:4]:
        if it["pct"] < 6 and out:
            break
        mega = e.find_mega(p, stone=it["name"])
        s = {**base, "item": it["name"], "mega": mega["name"] if mega else None}
        if it["name"] in ("Choice Scarf", "Choice Band", "Choice Specs", "Assault Vest"):  # 변화기를 못 쓰는 도구
            atk = [m["name"] for m in u["moves"] if e.M[m["name"]]["category"] != "Status"]
            s["moves"] = atk[:4] if len(atk) >= 3 else base["moves"]
        key = (s["item"], tuple(s["moves"]))
        if key in seen:
            continue
        seen.add(key)
        label = (mega["ko"] or mega["name"]) if mega else (items_ko.get(it["name"]) or {}).get("ko") or it["name"]
        out.append({"label": f"{label}형", "pct": it["pct"], "set": s})
    return out


# ------------------------------------------------------------------ 메타 상성표
def matchup_table(e: Engine, a: dict, fmt: str, top_n: int) -> list[dict]:
    rows = []
    for b in e.meta(fmt, top_n):
        hs = [e.damage(a, mv, b, fmt) for mv in a["moves"] if mv != "Fake Out"]
        hs = [h for h in hs if h]
        best = max(hs, key=lambda h: h["pct"] * h["acc"], default=None)
        taken = e.best_hit(b, a, fmt)
        mine, theirs = (hit_row(e, best) if best else None), (hit_row(e, taken) if taken else None)
        rows.append({**mini(b), "rank": e.rank(b["id"], fmt), "mine": mine, "theirs": theirs,
                     "verdict": verdict(mine, theirs, a["speed"], b["speed"]),
                     "mySpeed": a["speed"], "foeSpeed": b["speed"]})
    return rows


# ------------------------------------------------------------------ 파트너 추천
def partners(e: Engine, a: dict, fmt: str, table: list[dict], top_n: int) -> list[dict]:
    doubles = fmt == "Doubles"
    me = e.P[a["id"]]
    mates = (me["usage"].get(fmt) or {}).get("teammates", [])
    a_roles = set(e.roles(a, fmt))
    losses = [r for r in table if r["verdict"]["label"] == "LOSE"]
    loss_w = sum(weight(r["rank"]) for r in losses) or 1
    my_weak = [t for t in TYPES if type_multiplier(t, a["types"], a["ability"]) >= 2]
    cand_ids = list(dict.fromkeys(mates[:10] + [p["id"] for p in e.ranked(fmt)[:45]]))
    out = []
    for pid in cand_ids:
        if e.P[pid]["name"].split("-")[0] == me["name"].split("-")[0]:
            continue
        p = e.default_resolved(pid, fmt)
        if p["mega"] and a["mega"]:
            continue
        roles = set(e.roles(p, fmt))
        score, why, handles = 0.0, [], []
        if pid in mates:
            k = mates.index(pid)
            score += max(0, 14 - k * 1.4)
            why.append(f"실제로 함께 쓰이는 순위 {k + 1}위")
        cover = 0.0
        for r in losses:  # 내가 지는 상대를 대신 잡아 주는가
            foe = e.default_resolved(r["id"], fmt)
            mu = e.matchup(p, foe, fmt)
            if mu["score"] >= 58 and mu["hit"]:
                cover += weight(r["rank"])
                handles.append({**mini(foe), "move": mu["hit"]["move"], "pct": mu["hit"]["pct"], "w": weight(r["rank"])})
        if handles:
            score += 26 * cover / loss_w
            top = sorted(handles, key=lambda h: -h["w"])[:3]
            why.append(f"내가 불리한 {', '.join(h['ko'] or h['name'] for h in top)}을(를) 잡아 줍니다")
        resists = [t for t in my_weak if type_multiplier(t, p["types"], p["ability"]) <= 0.5]
        if resists:
            score += 3.5 * len(resists)
            why.append("TYPES:" + ",".join(resists))
        shared = [t for t in my_weak if type_multiplier(t, p["types"], p["ability"]) >= 2]
        if shared:
            score -= 4 * len(shared)
        if doubles:
            pm, am = set(p["moves"]), set(a["moves"])
            if "Fake Out" in pm:
                score += 5
                if a_roles & {"setup", "trickroom", "tailwind"}:
                    score += 5
                    why.append("속이다로 내 시동 턴을 만들어 줍니다")
                else:
                    why.append("속이다로 첫 턴 주도권을 잡아 줍니다")
            if pm & ROLE_MOVES["redirect"]:
                score += 5 + (5 if "setup" in a_roles else 0)
                why.append("유도로 내게 오는 공격을 끌어 줍니다")
            fast_cut = e.percentiles(fmt)["fast"]
            if "Tailwind" in pm and 80 <= a["speed"] < fast_cut and a_roles & {"physical", "special", "mixed"}:
                score += 8
                why.append(f"순풍 아래에서 내가(스피드 {a['speed']:.0f}) 대부분보다 먼저 움직입니다")
            if "Trick Room" in pm and a["speed"] <= 80 and a_roles & {"physical", "special", "mixed"}:
                score += 10
                why.append("트릭룸 아래에서 느린 내가 먼저 움직입니다")
            if "Helping Hand" in pm and any(e.M[m]["target"] in ("allAdjacent", "allAdjacentFoes") and e.M[m]["power"]
                                            for m in a["moves"]):
                score += 4
                why.append("도우미로 내 전체기 화력을 올려 줍니다")
            if p["ability"] == "Intimidate" and "bulky" not in a_roles:
                score += 3
                why.append("위협으로 내가 받는 물리 피해를 줄여 줍니다")
            for x, y, mine_first in ((a, p, True), (p, a, False)):
                for mv in x["moves"]:
                    m = e.M[mv]
                    if m["target"] == "allAdjacent" and m["power"]:
                        mult = type_multiplier(m["type"], y["types"], y["ability"])
                        mk = m["ko"] or mv
                        if mult == 0:
                            score += 7
                            why.append(f"{'내' if mine_first else '파트너의'} {mk}을(를) "
                                       f"{'파트너가' if mine_first else '내가'} 무효로 받습니다")
                        elif mult >= 2:
                            score -= 8
                            why.append(f"주의: {'내' if mine_first else '파트너의'} {mk}이(가) "
                                       f"{'파트너에게' if mine_first else '내게'} {mult:g}배")
            if p["ability"] in WEATHER:
                label, wtype, abusers, _ = WEATHER[p["ability"]]
                if a["ability"] in abusers or (wtype in ("Water", "Fire") and any(
                        e.M[m]["type"] == wtype and e.M[m]["power"] for m in a["moves"])):
                    score += 9
                    why.append(f"{label}을(를) 깔아 내 화력/특성을 살려 줍니다")
            if p["ability"] in TERRAIN and am & TERRAIN[p["ability"]][1]:
                score += 10
                why.append(f"{TERRAIN[p['ability']][0]}로 내 필드 기술을 강화합니다")
        else:
            if "pivot" in roles:
                score += 4
                why.append("교체 기술로 나를 안전하게 내보내 줍니다")
            if "hazard" in roles:
                score += 3
                why.append("설치기로 내 확정수를 당겨 줍니다")
        if score <= 6 or not why:
            continue
        out.append({**mini(p), "rank": e.rank(pid, fmt), "score": round(score, 1),
                    "roles": [ROLE_LABELS[k] for k in e.roles(p, fmt)][:4],
                    "why": [w for w in why if not w.startswith("TYPES:")][:5],
                    "resists": next((w[6:].split(",") for w in why if w.startswith("TYPES:")), []),
                    "handles": e.with_move_ko(sorted(handles, key=lambda h: -h["w"])[:4]),
                    "set": e.default_set(pid, fmt)})
    out.sort(key=lambda x: -x["score"])
    return polish(out[:8])


# ------------------------------------------------------------------ 운용법
def playbook(e: Engine, a: dict, fmt: str, table: list[dict]) -> dict:
    doubles = fmt == "Doubles"
    roles = set(e.roles(a, fmt))
    name = n(a)
    wins = sorted([r for r in table if r["verdict"]["label"] == "WIN"], key=lambda r: r["rank"])
    losses = sorted([r for r in table if r["verdict"]["label"] == "LOSE"], key=lambda r: r["rank"])
    tips = []

    # 역할 한 줄
    kind = "물리 어태커" if "physical" in roles else "특수 어태커" if "special" in roles else "양도 어태커" if "mixed" in roles else "지원형"
    extra = [ROLE_LABELS[k] for k in ("fakeout", "intimidate", "tailwind", "trickroom", "redirect", "weather", "terrain",
                                      "priority", "setup", "pivot", "hazard") if k in roles]
    tips.append({"title": "역할", "text": f"{kind}" + (f" + {', '.join(extra)}" if extra else "") + "."})

    # 선봉/후발
    if roles & LEAD_ROLES:
        why = [ROLE_LABELS[k] for k in LEAD_ROLES if k in roles]
        tips.append({"title": "내보내는 시점", "text": f"선봉이 좋습니다. {', '.join(why)}은(는) 첫 턴에 쓸수록 가치가 큽니다."
                     + (" 교체로 다시 내보내면 효과를 한 번 더 쓸 수 있습니다." if roles & {"fakeout", "intimidate"} else "")})
    elif "priority" in roles or "setup" in roles:
        tips.append({"title": "내보내는 시점", "text": "후발이 좋습니다. 상대 체력이 깎인 뒤에 나와 "
                     + ("선공기로 마무리" if "priority" in roles else "랭크업 후 전개") + "하는 그림을 노리세요."})
    else:
        tips.append({"title": "내보내는 시점", "text": "선봉·후발 모두 가능합니다. 아래의 유리한 상대가 보일 때 내보내세요."})

    # 스피드
    speeds = [(r["foeSpeed"], weight(r["rank"])) for r in table]
    tot = sum(w for _, w in speeds) or 1
    out_now = sum(1 for s, _ in speeds if a["speed"] > s)
    out_tw = sum(1 for s, _ in speeds if a["speed"] * 2 > s)
    t = f"실전 스피드 {a['speed']:.0f}" + (" (구애스카프 포함)" if a["item"] == "Choice Scarf" else "")
    t += f" — 메타 상위 {len(speeds)}마리 중 {out_now}마리보다 빠릅니다."
    if doubles and out_tw > out_now:
        t += f" 순풍 아래에서는 {out_tw}마리보다 빠릅니다."
    if a["speed"] <= 80:
        t += " 느린 편이라 트릭룸 아래에서 강합니다."
    tips.append({"title": "스피드", "text": t})

    if wins:
        tips.append({"title": "노릴 상대", "text": ", ".join(
            f"{r['ko'] or r['name']}({r['mine']['ko'] or r['mine']['move']} {r['mine']['koText']})" for r in wins[:5]) + "."})
    if losses:
        tips.append({"title": "피할 상대", "text": ", ".join(
            f"{r['ko'] or r['name']}({(r['theirs']['ko'] or r['theirs']['move']) if r['theirs'] else '-'} "
            f"{r['theirs']['koText'] if r['theirs'] else ''})" for r in losses[:5])
            + ". 맞대면하면 방어를 누르거나 교체하고, 파트너로 처리하세요."})
    weak = [t for t in TYPES if type_multiplier(t, a["types"], a["ability"]) >= 4]
    if weak:
        tips.append({"title": "4배 약점", "text": "TYPES:" + ",".join(weak)})

    if a["item"] in ITEM_NOTES:
        tips.append({"title": f"도구 · {a.get('itemKo') or (e.d['items'].get(a['item']) or {}).get('ko') or a['item']}",
                     "text": ITEM_NOTES[a["item"]]})
    elif a["mega"]:
        tips.append({"title": "메가진화", "text": "한 배틀에 한 마리만 메가진화할 수 있습니다. 팀에 메가 후보가 여럿이면 상대를 보고 고르세요."})
    elif a["item"] and a["item"].endswith("Berry"):
        from .engine import RESIST_BERRIES
        if a["item"] in RESIST_BERRIES:
            tips.append({"title": "도구 · 반감 열매", "text": "약점 타입의 공격을 한 번 절반으로 줄여 줍니다. 그 한 턴에 확실히 일을 하세요."})

    moves = []
    for mv in a["moves"]:
        m = e.M[mv]
        note = MOVE_NOTES.get(mv)
        if not note:
            if m["category"] == "Status":
                note = "변화기."
            else:
                bits = [f"{'물리' if m['category'] == 'Physical' else '특수'} 위력 {m['power']}"]
                if m["type"] in a["types"]:
                    bits.append("자속(1.5배)")
                if m["target"] in ("allAdjacent", "allAdjacentFoes") and doubles:
                    bits.append("전체기 — 두 마리를 때리지만 위력 0.75배" + (", 아군도 맞습니다" if m["target"] == "allAdjacent" else ""))
                if m["priority"] > 0:
                    bits.append("선공기 — 체력이 깎인 상대를 마무리")
                if isinstance(m["accuracy"], (int, float)) and m["accuracy"] < 100:
                    bits.append(f"명중 {m['accuracy']}%")
                hits = sum(1 for r in table if r["mine"] and r["mine"]["move"] == mv)
                if hits:
                    bits.append(f"메타 상위권 {hits}마리에게 가장 아픈 기술")
                note = ", ".join(bits) + "."
        moves.append({"name": mv, "ko": m["ko"], "type": m["type"], "note": note})
    return polish({"tips": tips, "moves": moves})


def lab(e: Engine, pid: str, set_: dict | None, fmt: str, top_n: int = 20) -> dict:
    a = e.resolve({**(set_ or {}), "id": pid}, fmt) if set_ else e.resolve(e.default_set(pid, fmt), fmt)
    table = matchup_table(e, a, fmt, top_n)
    count = {k: sum(1 for r in table if r["verdict"]["label"] == k) for k in ("WIN", "EVEN", "LOSE")}
    return {
        "format": fmt, "me": e.describe(a, fmt), "variants": variants(e, pid, fmt),
        "table": table, "count": count,
        "partners": partners(e, a, fmt, table, top_n),
        "playbook": playbook(e, a, fmt, table),
    }
