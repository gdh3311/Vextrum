"""Team Workspace 백엔드: 빠른 분석 · 교체 추천 · 매치업 · 실험실 · 실전 피드백.

원칙 (docs/VEXTRUM_WORKBENCH_ARCHITECTURE.md)
- 빠른 분석(Fast)은 정적 계산만 한다. 승률이라는 말을 쓰지 않는다 (basis: "static").
- 승률은 오직 모의전(Deep) 작업에서 나오며, 같은 상대·같은 난수의 짝지은 비교와 신뢰구간으로만 결론을 낸다.
  신뢰구간이 0을 넘지 않으면 '결론 보류'.
- 모든 결과에 teamRevision 을 붙인다. 클라이언트는 현재 revision 과 다른 결과를 '이전 버전 결과'로만 보여 준다.
- 사용자가 잠근 포켓몬·필드는 어떤 추천 적용으로도 바뀌지 않는다 (apply_locks).
- 모의전이 지원하지 않는 기술·특성·도구가 있으면 그 실험을 '정밀하지 않음'으로 표시한다.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections.abc import Mapping
from collections import Counter
from random import Random

from . import auto_team, battle_lab, parallel, regulation, strategy
from .engine import Engine, weight
from .typechart import TYPES

LOCKABLE = ("pokemon", "moves", "item", "ability", "nature", "points", "mega")
SPEED_CONTROL = {"Tailwind": "tailwind", "Trick Room": "trickroom", "Icy Wind": "speed_drop",
                 "Electroweb": "speed_drop", "Thunder Wave": "paralysis", "Scary Face": "speed_drop",
                 "Bulldoze": "speed_drop", "Rock Tomb": "speed_drop"}
ALLY_HITTING = {"Earthquake", "Surf", "Discharge", "Bulldoze", "Lava Plume", "Sludge Wave", "Explosion",
                "Self-Destruct", "Boomburst", "Parabolic Charge", "Mind Blown", "Petal Blizzard", "Magnitude"}
WEATHER_SET = {"Drizzle": "rain", "Drought": "sun", "Sand Stream": "sand", "Snow Warning": "snow",
               "Mega Sol": "sun", "Rain Dance": "rain", "Sunny Day": "sun", "Sandstorm": "sand", "Snowscape": "snow"}
VERDICT_LABELS = {"better": "개선", "worse": "악화", "hold": "결론 보류"}


# ---------------------------------------------------------------- 공용
def sig(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def _full(e: Engine, fmt: str, s: dict) -> dict:
    return {**e.default_set(s["id"], fmt), **s}


def _name(r: dict) -> str:
    return r.get("ko") or r.get("name") or r.get("id")


def _meta(e: Engine, fmt: str):
    meta, pool = auto_team._pool(e, fmt)
    weights = [weight(e.rank(f["id"], fmt) or 250) for f in meta]
    return meta, pool, weights


def unsupported(e: Engine, s: dict) -> list[str]:
    """모의전이 아직 효과를 계산하지 않는 이 세트의 요소 (기술·특성·도구)."""
    from .simulation import UNIMPLEMENTED_ABILITIES, UNIMPLEMENTED_ITEMS, move_supported

    out = [m for m in s.get("moves") or [] if not move_supported(e, m)]
    if s.get("ability") in UNIMPLEMENTED_ABILITIES:
        out.append(s["ability"])
    if s.get("item") in UNIMPLEMENTED_ITEMS:
        out.append(s["item"])
    return out


def legality(e: Engine, fmt: str, sets: list[dict]) -> list[dict]:
    """세트·팀 규칙 위반. severity high 는 모의전·추천 적용을 막는다."""
    issues = []
    species, items = Counter(), Counter()
    for i, raw in enumerate(sets):
        pid = raw.get("id")
        if pid not in e.P:
            issues.append({"slot": i, "severity": "high", "kind": "species", "text": f"알 수 없는 포켓몬: {pid}"})
            continue
        p = e.P[pid]
        s = _full(e, fmt, raw)
        learn = set(p.get("learnset") or [])
        for mv in s.get("moves") or []:
            if mv not in e.M:
                issues.append({"slot": i, "severity": "high", "kind": "move", "text": f"알 수 없는 기술: {mv}"})
            elif learn and mv not in learn:
                issues.append({"slot": i, "severity": "high", "kind": "move",
                               "text": f"{_name(p)}은(는) {e.M[mv].get('ko') or mv}을(를) 배우지 못합니다"})
        if len(s.get("moves") or []) != len(set(s.get("moves") or [])):
            issues.append({"slot": i, "severity": "high", "kind": "move", "text": "같은 기술이 두 번 들어 있습니다"})
        mega = e.find_mega(p, name=s["mega"]) if s.get("mega") else None
        if s.get("mega") and not mega:
            issues.append({"slot": i, "severity": "high", "kind": "mega", "text": f"없는 메가 폼: {s['mega']}"})
        if mega and s.get("item") and not e.find_mega(p, stone=s["item"]):
            issues.append({"slot": i, "severity": "high", "kind": "mega",
                           "text": f"{mega['name']}은(는) 맞는 메가스톤이 필요합니다"})
        if s.get("ability") and s["ability"] not in (p.get("abilities") or []):
            issues.append({"slot": i, "severity": "high", "kind": "ability",
                           "text": f"{_name(p)}은(는) 특성 {s['ability']}을(를) 가질 수 없습니다"})
        if s.get("item") and s["item"] not in e.d.get("items", {}):
            issues.append({"slot": i, "severity": "high", "kind": "item", "text": f"알 수 없는 도구: {s['item']}"})
        if s.get("nature") and s["nature"] not in e.d.get("natures", {}):
            issues.append({"slot": i, "severity": "high", "kind": "nature", "text": f"알 수 없는 성격: {s['nature']}"})
        pts = s.get("points") or {}
        if any(int(v) > 32 or int(v) < 0 for v in pts.values()) or sum(int(v) for v in pts.values()) > 66:
            issues.append({"slot": i, "severity": "high", "kind": "points",
                           "text": "능력 포인트는 능력치마다 0~32, 합계 66 이하입니다"})
        missing = unsupported(e, s)
        if missing:
            issues.append({"slot": i, "severity": "info", "kind": "simulation",
                           "text": "모의전이 효과를 계산하지 않는 요소: " + ", ".join(missing)})
        species[auto_team.species(e, pid)] += 1
        if s.get("item"):
            items[s["item"]] += 1
    for k, n in species.items():
        if n > 1:
            issues.append({"slot": None, "severity": "high", "kind": "species", "text": "같은 종이 두 번 들어 있습니다"})
    for k, n in items.items():
        if n > 1:
            issues.append({"slot": None, "severity": "high", "kind": "item", "text": f"같은 도구가 두 번 들어 있습니다: {k}"})
    return issues


def blocking(issues) -> bool:
    return any(i["severity"] == "high" for i in issues)


# ---------------------------------------------------------------- 정적 팀 프로필 (빠른 분석·교체 후보 공용)
def profile(cands, weights):
    """Candidate 목록의 정적 지표. 승률이 아니다."""
    n_types = len(TYPES)
    weak = [sum(c.weak[t] for c in cands) for t in range(n_types)]
    resist = [sum(c.resist[t] for c in cands) for t in range(n_types)]
    coverage = sum(w * max(c.matchups[j] for c in cands) for j, w in enumerate(weights)) / (sum(weights) or 1)
    backup = sum(w * sorted((c.matchups[j] for c in cands), reverse=True)[min(1, len(cands) - 1)]
                 for j, w in enumerate(weights)) / (sum(weights) or 1)
    features = Counter(f for c in cands for f in c.features)
    stacked = [TYPES[t] for t in range(n_types) if weak[t] >= 3 or (weak[t] >= 2 and resist[t] == 0)]
    phys, spec = features["physical"], features["special"]
    return {"weak": weak, "resist": resist, "coverage": coverage, "backup": backup, "features": features,
            "stacked": stacked, "balance": abs(phys - spec)}


def static_score(p) -> float:
    """정적 점수 (교체 후보 '찾기'용). 진단에서 실제 승률과의 상관이 낮았으므로 결론에 쓰지 않는다."""
    # 상성 점수는 0~100 척도 (Candidate.matchups). 1점 ≈ 메타 가중 평균 대응력 1점.
    return (p["coverage"] + .4 * p["backup"] - 6 * len(p["stacked"]) - 2 * p["balance"]
            + 3 * min(1, p["features"]["tailwind"] + p["features"]["trickroom"]))


# ---------------------------------------------------------------- 전략 무결성 (정적 + 모의전)
def integrity(e: Engine, fmt: str, sets: list[dict], resolved: list[dict]) -> list[dict]:
    """태그된 전략이 실제로 성립할 조건을 갖췄는지. 문제가 있어도 탈락시키지 않고 근거와 함께 알린다."""
    meta, _, _ = _meta(e, fmt)
    cands = [auto_team._candidate(e, fmt, meta, _full(e, fmt, s)) for s in sets]
    analysis = strategy.analyze(e, fmt, cands)
    by_name = {_name(r): r for r in resolved}
    out = []
    for tag in analysis["tags"]:
        setters = [by_name[n] for n in tag["setters"] if n in by_name]
        payoffs = [by_name[n] for n in tag["payoffs"] if n in by_name]
        if tag["key"] == "tailwind" and payoffs:
            fast = [r for r in payoffs if r["item"] == "Choice Scarf" or r["speed"] >= 160]
            if len(fast) == len(payoffs):
                out.append({"key": "tailwind_payoff_fast", "severity": "mid",
                            "text": "순풍 수혜자가 이미 충분히 빠릅니다: " + ", ".join(_name(r) for r in fast),
                            "detail": "순풍 없이도 먼저 움직이므로 순풍의 실제 이득이 작을 수 있습니다."})
        if tag["key"] == "trickroom":
            fast_setters = [r for r in setters if r["speed"] >= 120]
            slow = [r for r in payoffs if r["speed"] <= 75]
            if fast_setters:
                out.append({"key": "trickroom_setter_fast", "severity": "mid",
                            "text": "트릭룸 시동이 빠릅니다: " + ", ".join(_name(r) for r in fast_setters),
                            "detail": "트릭룸 아래에서는 이 포켓몬이 가장 늦게 움직입니다."})
            if len(slow) < 2:
                out.append({"key": "trickroom_few_payoffs", "severity": "mid",
                            "text": f"트릭룸 아래에서 먼저 움직일 느린 공격수가 {len(slow)}마리입니다",
                            "detail": "시동과 수혜 2마리가 같은 4선출에 들어가야 전략이 성립합니다."})
    weathers = {}
    for r in resolved:
        for key in [r["ability"], *r["moves"]]:
            if key in WEATHER_SET:
                weathers.setdefault(WEATHER_SET[key], []).append(_name(r))
    if len(weathers) >= 2:
        out.append({"key": "weather_conflict", "severity": "mid",
                    "text": "서로 덮어쓰는 날씨가 함께 있습니다: " +
                            ", ".join(f"{k}({', '.join(v)})" for k, v in weathers.items()),
                    "detail": "두 날씨를 같은 판에 쓰지 않는 선출 계획이 있는지 확인하세요."})
    for r in resolved:
        hits = [m for m in r["moves"] if m in ALLY_HITTING]
        if hits:
            victims = [_name(o) for o in resolved if o is not r and not _immune_to(e, o, hits[0])]
            if victims:
                out.append({"key": "ally_spread", "severity": "low",
                            "text": f"{_name(r)}의 {e.M[hits[0]].get('ko') or hits[0]}은(는) 아군도 맞힙니다",
                            "detail": "맞는 아군: " + ", ".join(victims)})
    megas = [_name(r) for r, s in zip(resolved, sets) if _full(e, fmt, s).get("mega")]
    if len(megas) >= 2:
        out.append({"key": "multi_mega", "severity": "low", "text": "메가 후보가 여러 마리입니다: " + ", ".join(megas),
                    "detail": "배틀당 메가진화는 1번입니다. 상대에 따라 누구를 메가로 쓸지 선출 계획이 필요합니다."})
    roles = Counter(f for c in cands for f in c.features if f in auto_team.FEATURE_NAMES)
    for f, n in roles.items():
        if n >= 4 and f not in {"attacker", "physical", "special"}:
            out.append({"key": "role_overlap", "severity": "low",
                        "text": f"같은 역할이 {n}마리: {auto_team.FEATURE_NAMES[f]}", "detail": "선출에서 겹칠 수 있습니다."})
    return {"tags": analysis["tags"], "primary": analysis.get("primary"), "secondary": analysis.get("secondary"),
            "issues": out}


def _immune_to(e, r, move):
    kind = e.M[move]["type"]
    if kind == "Ground":
        return "Flying" in r["types"] or r["ability"] == "Levitate" or r["item"] == "Air Balloon"
    if kind == "Water":
        return r["ability"] in {"Water Absorb", "Storm Drain", "Dry Skin"}
    if kind == "Electric":
        return "Ground" in r["types"] or r["ability"] in {"Volt Absorb", "Lightning Rod", "Motor Drive"}
    return r["ability"] == "Telepathy"


# ---------------------------------------------------------------- Fast Analysis
_fast_cache: dict = {}


def fast(e: Engine, fmt: str, sets: list[dict], revision: int = 0) -> dict:
    """편집 즉시 반영하는 정적 분석. 섹션마다 해시를 붙여 클라이언트가 바뀐 부분만 강조할 수 있게 한다."""
    start = time.perf_counter()
    sets = [s for s in sets if s.get("id")][:6]
    key = (fmt, sig(sets))
    if key in _fast_cache:
        body = _fast_cache[key]
    else:
        issues = legality(e, fmt, sets)
        valid = [s for s in sets if s["id"] in e.P]
        resolved = [e.resolve(_full(e, fmt, s), fmt) for s in valid]
        base = e.analyze_team([_full(e, fmt, s) for s in valid], fmt, 20) if valid else {"members": []}
        speeds = sorted(({"id": r["id"], "name": _name(r), "speed": round(r["speed"]),
                          "tailwind": round(r["speed"] * 2)} for r in resolved), key=lambda x: -x["speed"])
        control = [{"id": r["id"], "name": _name(r), "move": m, "kind": SPEED_CONTROL[m],
                    "label": e.M[m].get("ko") or m} for r in resolved for m in r["moves"] if m in SPEED_CONTROL]
        priority = [{"id": r["id"], "name": _name(r), "move": m, "label": e.M[m].get("ko") or m}
                    for r in resolved for m in r["moves"] if e.M[m].get("priority", 0) > 0 and e.M[m]["power"]]
        megas = [{"id": r["id"], "name": _name(r), "mega": r["mega"]} for r in resolved if r["mega"]]
        integ = integrity(e, fmt, valid, resolved) if valid else {"tags": [], "issues": []}
        guide = None
        try:
            from .guide import team_guide

            g = team_guide(e, [_full(e, fmt, s) for s in valid], fmt) or {}
            guide = {"lead": g.get("lead"), "axes": g.get("axes", [])[:4]}
        except Exception:  # noqa: BLE001 - 가이드는 보조 정보
            guide = None
        sections = {
            "legality": issues,
            "types": {"rows": base.get("typeRows", []), "warnings": [w for w in base.get("warnings", [])
                                                                    if w.get("kind") == "type"]},
            "balance": base.get("damageSplit"),
            "roles": base.get("roleCoverage", []),
            "speed": {"order": speeds, "control": control, "priority": priority},
            "mega": megas,
            "meta": {"score": base.get("metaScore"), "matchups": base.get("matchups", [])[:20]},
            "strategy": integ,
            "lead": guide,
        }
        body = {"sections": sections,
                "hashes": {k: sig(v) for k, v in sections.items()},
                "members": [{"slot": i, "id": s["id"], "hash": sig(_full(e, fmt, s)) if s["id"] in e.P else None,
                             "unsupported": unsupported(e, _full(e, fmt, s)) if s["id"] in e.P else []}
                            for i, s in enumerate(sets)],
                "blocking": blocking(issues)}
        if len(_fast_cache) > 256:
            _fast_cache.clear()
        _fast_cache[key] = body
    return {**body, "basis": "static", "teamRevision": revision, "format": fmt,
            "elapsedMs": round(1000 * (time.perf_counter() - start), 1)}


# ---------------------------------------------------------------- 잠금
def apply_locks(old: dict | None, new: dict, locks: dict | None) -> dict:
    """추천 세트를 적용할 때 잠긴 필드는 원래 값으로 되돌린다. 포켓몬 자체가 잠겨 있으면 교체를 거부한다."""
    locks = locks or {}
    if old is not None and locks.get("pokemon") and new.get("id") != old.get("id"):
        raise ValueError("잠긴 포켓몬은 교체할 수 없습니다")
    if old is None or new.get("id") != old.get("id"):
        return dict(new)
    out = dict(new)
    for field in LOCKABLE[1:]:
        if locks.get(field) and field in old:
            out[field] = old[field]
    return out


# ---------------------------------------------------------------- Replacement Finder (정적 후보)
MODES = {"best": "최고 성능", "weakness": "약점 보완", "keep": "전략 유지", "pivot": "전략 전환",
         "joker": "조커 발굴", "owned": "보유 포켓몬"}


def replacements(e: Engine, fmt: str, sets: list[dict], slot: int, mode: str = "best",
                 locks: list[dict] | None = None, owned: list[str] | None = None, target_type: str | None = None,
                 limit: int = 6, revision: int = 0) -> dict:
    """한 자리 교체 후보. 정적 지표로 후보를 '찾고' 설명한다. 승률 결론은 validate_replacements 로."""
    start = time.perf_counter()
    if not 0 <= slot < len(sets):
        raise ValueError("교체할 자리를 골라 주세요")
    locks = locks or [{} for _ in sets]
    if (locks[slot] if slot < len(locks) else {}).get("pokemon"):
        raise ValueError("잠긴 포켓몬의 자리는 교체 추천을 하지 않습니다")
    meta, pool, weights = _meta(e, fmt)
    full = [_full(e, fmt, s) for s in sets]
    cands = [auto_team._candidate(e, fmt, meta, s) for s in full]
    others = cands[:slot] + cands[slot + 1:]
    old = cands[slot]
    base = profile(cands, weights)
    base_score = static_score(base)
    base_family = strategy.family(strategy.analyze(e, fmt, cands))
    old_roles = {f for f in old.features if f in auto_team.FEATURE_NAMES}
    taken = {c.species for c in others}
    items = {c.set.get("item") for c in others if c.set.get("item")}
    owned_set = {auto_team.species(e, p) for p in owned or []}
    rows = []
    seen = set()
    for alt in pool:
        if alt.species in taken or alt.species == old.species or (alt.set.get("item") in items):
            continue
        if mode == "joker" and auto_team._rank_of(e, fmt, alt.id) <= auto_team.JOKER_RANK:
            continue
        if mode == "owned" and alt.species not in owned_set:
            continue
        if unsupported(e, alt.set):
            continue
        team = others[:slot] + [alt] + others[slot:]
        p = profile(team, weights)
        score = static_score(p)
        fam = strategy.family(strategy.analyze(e, fmt, team)) if mode in ("keep", "pivot") else None
        if mode == "keep" and fam != base_family:
            continue
        if mode == "pivot" and fam == base_family:
            continue
        if mode == "weakness":
            score += 8 * (len(base["stacked"]) - len(p["stacked"]))
            if target_type in TYPES:
                t = TYPES.index(target_type)
                score += 10 * ((base["weak"][t] - p["weak"][t]) + (p["resist"][t] - base["resist"][t]))
        key = (alt.species, alt.set.get("item"))
        if key in seen:
            continue
        seen.add(key)
        rows.append((score - base_score, alt, p, fam))
    rows.sort(key=lambda r: -r[0])
    best_per_species, out = set(), []
    for delta, alt, p, fam in rows:
        if alt.species in best_per_species:
            continue
        best_per_species.add(alt.species)
        out.append(_explain(e, fmt, old, alt, base, p, delta, base_family, fam, meta, weights, cands, slot))
        if len(out) == limit:
            break
    return {"slot": slot, "mode": mode, "modeLabel": MODES.get(mode, mode), "basis": "static",
            "teamRevision": revision, "candidates": out, "out": _brief(old.resolved),
            "note": "정적 지표로 고른 후보입니다. 실제 성능은 '모의전 검증'에서 같은 상대·같은 난수로 비교합니다.",
            "elapsedMs": round(1000 * (time.perf_counter() - start), 1)}


def _brief(r):
    return {"id": r["id"], "name": r.get("name"), "ko": r.get("ko"), "sprite": r.get("sprite"), "types": r.get("types")}


def _explain(e, fmt, old, alt, base, p, delta, base_family, fam, meta, weights, cands, slot):
    fixed = [TYPES[t] for t in range(len(TYPES)) if (base["weak"][t] - base["resist"][t]) >= 1
             and (p["weak"][t] - p["resist"][t]) < (base["weak"][t] - base["resist"][t])]
    new = [TYPES[t] for t in range(len(TYPES)) if (p["weak"][t] - p["resist"][t]) >= 2
           and (p["weak"][t] - p["resist"][t]) > (base["weak"][t] - base["resist"][t])]
    lost = sorted(f for f in old.features if f in auto_team.FEATURE_NAMES and f not in alt.features
                  and not any(f in c.features for i, c in enumerate(cands) if i != slot))
    gained = sorted(f for f in alt.features if f in auto_team.FEATURE_NAMES
                    and not any(f in c.features for c in cands))
    threats = []
    for j, f in enumerate(meta[:20]):
        before = max(c.matchups[j] for c in cands)
        after = max([*(c.matchups[j] for i, c in enumerate(cands) if i != slot), alt.matchups[j]])
        if abs(after - before) >= 8:
            threats.append({"id": f["id"], "name": _name(f), "sprite": f.get("sprite"),
                            "before": round(before), "after": round(after)})
    threats.sort(key=lambda t: -abs(t["after"] - t["before"]))
    r = alt.resolved
    reasons = []
    if fixed:
        reasons.append("약점 보완: " + ", ".join(fixed))
    if gained:
        reasons.append("새 역할: " + ", ".join(auto_team.FEATURE_NAMES[f] for f in gained))
    better = [t for t in threats if t["after"] > t["before"]][:3]
    if better:
        reasons.append("대응 개선: " + ", ".join(t["name"] for t in better))
    risks = []
    if lost:
        risks.append("잃는 역할: " + ", ".join(auto_team.FEATURE_NAMES[f] for f in lost))
    if new:
        risks.append("새 약점: " + ", ".join(new))
    worse = [t for t in threats if t["after"] < t["before"]][:3]
    if worse:
        risks.append("대응 악화: " + ", ".join(t["name"] for t in worse))
    return {"pokemon": _brief(r), "set": alt.set, "staticDelta": round(delta, 2),
            "rank": auto_team._rank_of(e, fmt, alt.id) if auto_team._rank_of(e, fmt, alt.id) < 999 else None,
            "roles": {"lost": [auto_team.FEATURE_NAMES[f] for f in lost],
                      "gained": [auto_team.FEATURE_NAMES[f] for f in gained]},
            "weaknesses": {"fixed": fixed, "new": new},
            "threats": threats[:6], "strategy": {"before": base_family, "after": fam},
            "speedControl": {"before": int(base["features"]["tailwind"] + base["features"]["trickroom"]),
                             "after": int(p["features"]["tailwind"] + p["features"]["trickroom"])},
            "reasons": reasons, "risks": risks,
            "sources": ["팀 상성: 앱 정적 계산 (타입·기술·스피드)", "상대 메타: 랭커 순위 상위 20종 대표 세트",
                        "세트: 랭커 채용률 기반 생성 세트"]}


# ---------------------------------------------------------------- 작업(Deep) — revision 관리·취소
class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.items: dict[str, dict] = {}

    def start(self, kind: str, revision: int, scope: str, fn, *args):
        """scope 가 같은 이전 작업은 취소한다 (팀을 다시 고치면 구버전 작업 결과가 반영되지 않게)."""
        job = uuid.uuid4().hex[:12]
        entry = {"id": job, "kind": kind, "teamRevision": revision, "scope": scope, "state": "running",
                 "progress": {"done": 0, "total": 1, "note": ""}, "result": None, "error": None,
                 "cancel": threading.Event(), "created": time.time()}
        with self.lock:
            for other in self.items.values():
                if other["scope"] == scope and other["state"] == "running":
                    other["cancel"].set()
                    other["state"] = "cancelled"
            for key in [k for k, v in self.items.items() if time.time() - v["created"] > 3600]:
                self.items.pop(key, None)
            self.items[job] = entry

        def run():
            try:
                result = fn(entry, *args)
                if not entry["cancel"].is_set():
                    entry.update(state="done", result=result)
            except Cancelled:
                entry["state"] = "cancelled"
            except ValueError as error:
                entry.update(state="error", error=str(error))
            except Exception:  # noqa: BLE001 - 앱에 실패를 알린다
                import traceback

                traceback.print_exc()
                entry.update(state="error", error="실험 중 오류가 났습니다. 다시 시도해 주세요.")

        threading.Thread(target=run, daemon=True, name=f"wb-{kind}-{job}").start()
        return job

    def view(self, job: str):
        entry = self.items.get(job)
        if entry is None:
            return None
        return {k: v for k, v in entry.items() if k != "cancel"}

    def cancel(self, job: str):
        entry = self.items.get(job)
        if entry and entry["state"] == "running":
            entry["cancel"].set()
            entry["state"] = "cancelled"
        return entry is not None


class Cancelled(Exception):
    pass


JOBS = Jobs()


def _check(entry):
    if entry["cancel"].is_set():
        raise Cancelled()


def _step(entry, done, total, note):
    _check(entry)
    entry["progress"] = {"done": done, "total": total, "note": note}


def paired_verdict(before, after):
    st = battle_lab.paired(before, after)
    verdict = "better" if st["low"] > 0 else "worse" if st["high"] < 0 else "hold"
    return {"diff": round(st["diff"], 3), "low": round(st["low"], 3), "high": round(st["high"], 3), "n": st["n"],
            "verdict": verdict, "label": VERDICT_LABELS[verdict]}


def _rate(r):
    return round((r["win"] + .5 * r["draw"]) / max(1, r["runs"]), 3)


def report_summary(r) -> dict:
    """모의전 결과 요약 (실험 결과 화면 공용)."""
    return {"rate": _rate(r), "ci": battle_lab.wilson(r["win"] + .5 * r["draw"], r["runs"]), "games": r["runs"],
            "byArchetype": [{"style": s["style"], "label": s["label"], "win": s["win"], "runs": s["runs"]}
                            for s in r["strategies"]],
            "lossTags": r.get("lossTags", [])[:5], "lossCauses": r.get("lossCauses", [])[:4],
            "members": [{"id": m["id"], "ko": m.get("ko"), "name": m.get("name"), "pickRate": m["pickRate"],
                         "koPerGame": m["koPerGame"], "winRate": m["winRate"]} for m in r.get("memberStats", [])],
            "picks": [{"against": s["label"], **p} for s in r["strategies"] for p in s.get("picks", [])[:1]],
            "executed": dict(r.get("activations") or {}),
            "cpuStyles": {k: {"runs": v["runs"], "rate": round(v["score"] / max(1, v["runs"]), 3)}
                          for k, v in (r.get("cpuStyles") or {}).items()}}


STYLES = ["balanced", "aggressive", "defensive", "setup", "pivot"]
SCREEN_SEED, HOLDOUT_SEED = 41_000_013, 42_000_029  # 탐색(후보 거르기)과 최종 검증은 다른 상대군


def validate_replacements(entry, e, fmt, sets, slot, candidates, games=40, holdout=80, difficulty="master"):
    """교체 후보 검증: (1) 선별 상대군에서 원본+후보 전부를 같은 판으로 (2) 상위 2개를 다른 상대군에서 다시.
    선출은 양쪽 모두 같은 선출 판단(상대 미리보기 기반)으로 각자 다시 정한다 → 팀 구성 변화와 선출 변화가 함께 반영된다.
    선출이 얼마나 바뀌었는지는 따로 기록한다."""
    if blocking(legality(e, fmt, sets)):
        raise ValueError("규칙 위반이 있는 팀은 검증하지 않습니다")
    teams = [sets] + [sets[:slot] + [c] + sets[slot + 1:] for c in candidates]
    for t in teams[1:]:
        if blocking(legality(e, fmt, t)):
            raise ValueError("규칙 위반이 있는 후보가 있습니다")
    _step(entry, 0, 2, "선별 상대군")
    screen = parallel.compare_teams(e, fmt, teams, games, SCREEN_SEED, difficulty, cpu_styles=STYLES)
    rows = []
    for c, r in zip(candidates, screen[1:]):
        rows.append({"pokemon": c["id"], "set": c, "screen": {**paired_verdict(screen[0]["outcomes"], r["outcomes"]),
                                                               "rate": _rate(r)},
                     "pickShift": _pick_shift(screen[0], r)})
    order = sorted(range(len(rows)), key=lambda i: -rows[i]["screen"]["diff"])[:2]
    _step(entry, 1, 2, "독립 검증 상대군")
    finals = parallel.compare_teams(e, fmt, [teams[0]] + [teams[i + 1] for i in order], holdout, HOLDOUT_SEED,
                                    difficulty, cpu_styles=STYLES)
    for i, r in zip(order, finals[1:]):
        rows[i]["holdout"] = {**paired_verdict(finals[0]["outcomes"], r["outcomes"]), "rate": _rate(r),
                              "summary": report_summary(r)}
    _step(entry, 2, 2, "완료")
    precise = not any(unsupported(e, _full(e, fmt, s)) for t in teams for s in t)
    return {"slot": slot, "difficulty": difficulty, "styles": STYLES, "screenGames": games, "holdoutGames": holdout,
            "original": {"screen": _rate(screen[0]), "holdout": _rate(finals[0]),
                         "summary": report_summary(finals[0])},
            "candidates": rows, "precise": precise, "versions": regulation.versions(e.d),
            "teamRevision": entry["teamRevision"],
            "method": "같은 상대·같은 난수 짝지은 비교. 선별 상대군과 독립 검증 상대군은 다르다. "
                      "95% 신뢰구간이 0을 넘지 않으면 결론 보류."}


def _pick_shift(a, b):
    """두 팀 성적표의 최다 선출 비교: 같은 상대 유형에서 선봉이 바뀐 비율."""
    def top(r):
        return {s["style"]: frozenset(s["picks"][0]["leads"]) for s in r["strategies"] if s.get("picks")}

    ta, tb = top(a), top(b)
    common = [k for k in ta if k in tb]
    return round(sum(ta[k] != tb[k] for k in common) / len(common), 2) if common else None


# ---------------------------------------------------------------- Matchup Intelligence
def foe_hypotheses(e: Engine, fmt: str, pid: str, limit: int = 3) -> list[dict]:
    """공개되지 않은 상대 세트의 가설: 채용률 상위 도구·특성 조합. 확률은 채용률의 곱(정규화)."""
    u = e.P[pid]["usage"].get(fmt, {})
    base = e.default_set(pid, fmt)
    items = [r for r in u.get("items", [])[:4] if r["pct"] >= 5] or [{"name": base.get("item"), "pct": 100}]
    abilities = [r for r in u.get("abilities", [])[:2] if r["pct"] >= 10] or [{"name": base.get("ability"), "pct": 100}]
    rows = []
    for it in items:
        for ab in abilities:
            s = {**base, "item": it["name"], "ability": ab["name"]}
            mega = e.find_mega(e.P[pid], stone=it["name"]) if it["name"] else None
            s["mega"] = mega["name"] if mega else None
            rows.append((it["pct"] * ab["pct"], s))
    rows.sort(key=lambda r: -r[0])
    rows = rows[:limit]
    total = sum(w for w, _ in rows) or 1
    return [{"prob": round(w / total, 3), "set": s} for w, s in rows]


def vs_pokemon(e: Engine, fmt: str, sets: list[dict], foe_id: str, revision: int = 0) -> dict:
    """상대 포켓몬 하나를 현재 팀으로 어떻게 상대할지 (가설 세트별 데미지·스피드). 정적 계산."""
    from . import lab

    if foe_id not in e.P:
        raise ValueError("알 수 없는 상대 포켓몬")
    team = [e.resolve(_full(e, fmt, s), fmt) for s in sets if s.get("id") in e.P]
    hyps = foe_hypotheses(e, fmt, foe_id)
    rows = []
    for r in team:
        per = []
        for h in hyps:
            b = e.resolve(h["set"], fmt)
            d = lab.duel(e, r, b, fmt)
            per.append((h["prob"], d, b))
        best_out = [(p, (d["mine"] or [{}])[0]) for p, d, _ in per]
        best_in = [(p, (d["theirs"] or [{}])[0]) for p, d, _ in per]
        exp_out = sum(p * (m.get("max", 0) + m.get("min", 0)) / 2 for p, m in best_out)
        exp_in = sum(p * (m.get("max", 0) + m.get("min", 0)) / 2 for p, m in best_in)
        worst_in = max((m.get("max", 0) for _, m in best_in), default=0)
        ko_all = all(m.get("min", 0) >= 100 for _, m in best_out)
        faster = [p for p, d, b in per if r["speed"] > b["speed"]]
        rows.append({"id": r["id"], "name": _name(r), "sprite": r.get("sprite"),
                     "dealt": round(exp_out, 1), "taken": round(exp_in, 1), "worstTaken": round(worst_in, 1),
                     "bestMove": (best_out[0][1] or {}).get("ko") or (best_out[0][1] or {}).get("move"),
                     "ohko": ko_all, "outspeedProb": round(sum(faster), 2),
                     "notes": per[0][1].get("notes", [])[:3]})
    safest = sorted(rows, key=lambda x: (x["taken"] - .5 * x["dealt"]))[:3]
    ko = [x for x in rows if x["ohko"]]
    switch = [x for x in rows if x["worstTaken"] <= 35]
    foe = e.resolve(hyps[0]["set"], fmt)
    threats = []
    for mv in foe["moves"]:
        hits = [(x["name"], e.damage(foe, mv, e.resolve(_full(e, fmt, s), fmt), fmt)) for x, s in
                zip(rows, [s for s in sets if s.get("id") in e.P])]
        hits = [(n, h) for n, h in hits if h]
        if hits:
            n, h = max(hits, key=lambda nh: nh[1]["pct"])
            threats.append({"move": mv, "label": e.M[mv].get("ko") or mv, "target": n, "pct": round(h["pct"], 1)})
    threats.sort(key=lambda t: -t["pct"])
    advice = []
    if not ko and not any(x["dealt"] >= 60 for x in rows):
        advice.append("이 상대를 크게 때릴 수단이 없습니다. 상대 약점 타입의 공격 기술이나 대응 멤버를 고려하세요: " +
                      ", ".join(_weak_types(foe)))
    if not switch:
        advice.append("상대 최선 공격을 35% 이하로 받는 교체 후보가 없습니다.")
    return {"foe": _brief(foe), "hypotheses": [{"prob": h["prob"], "item": h["set"].get("item"),
                                                 "ability": h["set"].get("ability"), "mega": h["set"].get("mega")}
                                                for h in hyps],
            "rows": rows, "safest": [x["id"] for x in safest], "ko": [x["id"] for x in ko],
            "switchIns": [x["id"] for x in switch], "threats": threats[:4], "advice": advice,
            "basis": "static", "teamRevision": revision,
            "note": "상대 세트는 확정되지 않았습니다. 채용률 상위 도구·특성 가설의 확률 가중 평균입니다."}


def _weak_types(r):
    from .typechart import type_multiplier

    return [t for t in TYPES if type_multiplier(t, r["types"], r["ability"]) >= 2][:4]


def vs_team(e: Engine, fmt: str, sets: list[dict], enemy: list[str], revision: int = 0) -> dict:
    """상대 6마리: 기존 선출 분석 + 상대 전략 확률 가설."""
    from .enemy import analyze_enemy

    enemy = sorted(enemy[:6])
    out = analyze_enemy(e, enemy, [_full(e, fmt, s) for s in sets], fmt)
    out["hypotheses"] = battle_lab.preview_strategy(e, fmt, [p for p in enemy if p in e.P])
    out["teamRevision"] = revision
    out["basis"] = "static"
    return out


def prediction_snapshot(e, fmt, sets, enemy, *, include_simulation=False):
    """Freeze the pre-battle recommendation separately from the player's later choices."""
    from .enemy import analyze_enemy

    if (len(enemy) != 6 or len(sets) != 6 or any(p not in e.P for p in enemy)
            or len({auto_team.species(e, p) for p in enemy}) != 6 or blocking(legality(e, fmt, sets))):
        raise ValueError("서로 다른 상대 6마리와 규칙에 맞는 내 팀 6마리가 필요합니다.")
    enemy = sorted(enemy)
    report = analyze_enemy(e, enemy, [_full(e, fmt, s) for s in sets], fmt)
    rec = report["recommendation"]

    def ids(rows):
        return [m["id"] for m in rows]

    lead, back = ids(rec["lead"]), ids(rec["back"])
    forecast = None
    unavailable = None
    if include_simulation:
        try:
            result = validate_vs_team({"cancel": threading.Event(), "teamRevision": 0}, e, fmt, sets,
                                      enemy, [lead + back], games=18)
        except ValueError as error:
            unavailable = str(error)
        else:
            row = result["rows"][0]
            unavailable = row.get("unavailable")
            if not unavailable:
                forecast = {k: row[k] for k in ("games", "rate", "ci", "openingExamples", "used")}
                forecast["opponentHypotheses"] = result["opponentHypotheses"]
                forecast["opponentPlans"] = result["opponentPlans"]
    return {"at": time.time(), "basis": "static", "versions": regulation.versions(e.d),
            "season": regulation.provenance(e.d)["officialSeason"], "enemy": sorted(enemy),
            "teamSignature": feedback_team_signature(sets), "format": fmt,
            "lead": lead, "back": back, "simulation": forecast, "simulationUnavailable": unavailable,
            "enemyLeadCandidates": [ids(row["members"]) for row in report["leads"][:3]]}


def validate_vs_team(entry, e, fmt, sets, enemy, picks, games=30, difficulty="master"):
    """Compare fixed selections against identical sampled sets, enemy lines and seeds."""
    from . import simulation

    width = 2 if fmt == "Doubles" else 1
    count = battle_lab.limit(fmt)
    if (not count <= len(enemy) <= 6 or len(set(enemy)) != len(enemy) or any(p not in e.P for p in enemy)
            or len({auto_team.species(e, p) for p in enemy}) != len(enemy)
            or blocking(legality(e, fmt, sets))):
        raise ValueError("규칙에 맞는 내 팀과 상대 포켓몬을 확인해 주세요.")
    player = battle_lab._resolve(e, fmt, sets)
    index = {m["id"]: i for i, m in enumerate(player)}
    if not picks or any(len(p) != count or len(set(p)) != count or not set(p) <= index.keys() for p in picks):
        raise ValueError("선봉과 후발에 서로 다른 포켓몬을 골라 주세요.")
    full = {s["id"]: _full(e, fmt, s) for s in sets}
    problems = {pid: simulation.unsupported(e, fmt, full[pid]) for pid in set().union(*picks)}
    enemy = sorted(enemy)
    variants = [[h for h in foe_hypotheses(e, fmt, pid, limit=8)
                 if not simulation.unsupported(e, fmt, h["set"])] for pid in enemy]
    missing = [_name(e.P[p]) for p, options in zip(enemy, variants) if not options]
    if missing:
        raise ValueError("모의전에 사용할 수 있는 상대 대표 세트가 없습니다 · " + ", ".join(missing))
    preview = [e.default_resolved(p["id"], fmt) for p in player]
    strategy = battle_lab.preview_strategy(e, fmt, enemy)["scenario"]
    scenarios = []
    for g in range(games):
        rng = Random(51_000_007 + g)
        roster, items = {}, set()
        for i in rng.sample(range(len(variants)), len(variants)):
            options = variants[i]
            available = [h for h in options if h["set"]["item"] not in items]
            if available:
                choice = rng.choices(available, weights=[h["prob"] for h in available])[0]["set"]
            else:
                choice = {**options[0]["set"], "item": None, "mega": None}
            choice = _sample_matchup_moves(e, fmt, choice, rng)
            roster[i] = choice
            if choice["item"]:
                items.add(choice["item"])
        foes = battle_lab._resolve(e, fmt, [roster[i] for i in range(len(enemy))])
        style = rng.choices(list(strategy), weights=list(strategy.values()))[0] if g % 2 else "balance"
        core = ()
        if style in battle_lab.FIELD_ROLES:
            starter, payoff = battle_lab.PLAYBOOKS[style][1]
            features = [auto_team._candidate(e, fmt, (), roster[i]).features for i in range(len(enemy))]
            pairs = [(i, j) for i, first in enumerate(features) for j, second in enumerate(features)
                     if i != j and starter in first and payoff in second]
            if pairs:
                core = rng.choice(pairs)
        theirs, _ = battle_lab._choose(e, fmt, foes, preview, rng, style=style, core=core)
        scenarios.append(([roster[i] for i in theirs], rng.randrange(2 ** 31), style if core else None))

    out = []
    results = []
    for k, pick in enumerate(picks[:3]):
        _step(entry, k, len(picks[:3]), "선출 " + " · ".join(pick))
        line = {"pick": pick, "lead": pick[:width], "back": pick[width:]}
        unsupported = {issue["name"] for pid in pick for issue in problems[pid]}
        if unsupported:
            labels = ", ".join(e.M.get(m, {}).get("ko") or m for m in sorted(unsupported))
            out.append({**line, "unavailable": f"모의전에 아직 반영되지 않은 요소 · {labels}"})
            results.append([])
            continue
        score = Counter()
        tactics = Counter()
        openings = Counter()
        outcomes = []
        for g, (foe, seed, style) in enumerate(scenarios):
            _check(entry)
            b = simulation.Battle(e, fmt, [full[p] for p in pick], foe, seed, log=False, difficulty=difficulty,
                                  foe_strategy=style,
                                  cpu_style=battle_lab.PRACTICE_STYLES[g % len(battle_lab.PRACTICE_STYLES)])
            while not b.winner:
                b.advance()
            score[b.winner] += 1
            outcomes.append({"win": 1., "draw": .5, "loss": 0.}[b.winner])
            score.update(f"exec:{x}" for x in b.activated[0])
            tactics.update(b.strategy_used[0])
            openings.update([tuple(b.opening_choices)])
        n = len(outcomes)
        results.append(outcomes)
        out.append({**line, "games": n, "rate": round(sum(outcomes) / n, 3),
                    "ci": battle_lab.wilson(sum(outcomes), n),
                    "executed": {k[5:]: v for k, v in score.items() if k.startswith("exec:")},
                    "used": dict(tactics),
                    "openingExamples": [{"games": n, "actions": [{"actor": a, "move": m, "target": t,
                                                                  "moveKo": e.M.get(m, {}).get("ko") or m}
                                                                  for a, m, t in line]}
                                        for line, n in openings.most_common(2) if line]})
    for row, outcomes in zip(out[1:], results[1:]):
        if results[0] and outcomes:
            row["vsFirst"] = paired_verdict(results[0], outcomes)
    return {"rows": out, "difficulty": difficulty, "teamRevision": entry["teamRevision"],
            "enemy": enemy, "opponentHypotheses": len({sig(foe) for foe, _, _ in scenarios}),
            "opponentPlans": dict(Counter(style for _, _, style in scenarios if style)),
            "note": "채용 자료를 바탕으로 기술·도구·특성을 가정했습니다. 모든 선출에 같은 상대·난수를 썼습니다."}


def _sample_matchup_moves(e, fmt, entry, rng):
    """Include common alternate moves while keeping the set usable with its item."""
    from . import simulation

    moves = entry["moves"]
    item = entry["item"]
    p = e.P[entry["id"]]
    restricted = simulation.CHOICE | {"Assault Vest"}
    if not moves or item in restricted and any(e.M[m]["category"] == "Status" for m in moves):
        legal = [m for m in moves if e.M[m]["category"] != "Status"]
        if not legal:
            legal = [m for m in p["learnset"] if e.M[m]["power"] and simulation.move_supported(e, m)][:4]
        moves = legal
    usage = {r["name"]: r["pct"] for r in p["usage"].get(fmt, {}).get("moves", [])}
    alternate = [m for m, rate in usage.items() if rate >= 15 and m not in moves
                 and simulation.move_supported(e, m)
                 and (e.M[m]["category"] != "Status" or item not in restricted)][:4]
    attacks = sum(bool(e.M[m]["power"]) for m in moves)
    replaceable = [i for i, m in enumerate(moves) if usage.get(m, 0) < 80 and (not e.M[m]["power"] or attacks > 1)]
    if alternate and replaceable and rng.random() < .45:
        i = min(replaceable, key=lambda i: usage.get(moves[i], 0))
        move = rng.choices(alternate, weights=[usage[m] for m in alternate])[0]
        moves = [*moves[:i], move, *moves[i + 1:]]
    return {**entry, "moves": moves}


# ---------------------------------------------------------------- Simulation Lab
def experiment(entry, e, fmt, a, b, games=60, difficulty="master", styles=None, archetypes=None,
               lead_a=None, lead_b=None):
    """두 구성(팀·세트·선봉)을 같은 상대·같은 난수로 비교."""
    for t in (a, b):
        if blocking(legality(e, fmt, t)):
            raise ValueError("규칙 위반이 있는 팀은 실험하지 않습니다")
    pol = []
    for team, lead in ((a, lead_a), (b, lead_b)):
        pol.append({"*": tuple(lead)} if lead else None)
    _step(entry, 0, 1, "모의전")
    ra, rb = parallel.compare_teams(e, fmt, [a, b], games, 43_000_019, difficulty,
                                    styles=set(archetypes) if archetypes else None, policies=pol,
                                    cpu_styles=styles or STYLES)
    _step(entry, 1, 1, "완료")
    precise = not any(unsupported(e, _full(e, fmt, s)) for t in (a, b) for s in t)
    return {"a": report_summary(ra), "b": report_summary(rb), "diff": paired_verdict(ra["outcomes"], rb["outcomes"]),
            "games": games, "difficulty": difficulty, "styles": styles or STYLES,
            "archetypes": sorted(archetypes) if archetypes else None, "precise": precise,
            "versions": regulation.versions(e.d), "teamRevision": entry["teamRevision"]}


# ---------------------------------------------------------------- Battle Feedback
def feedback_team_signature(team):
    keys = ("id", "moves", "item", "ability", "nature", "points", "mega")
    return sig([{key: s[key] for key in keys if key in s} for s in team])


def _ids(value):
    if not isinstance(value, list):
        return set()
    ids = [row.get("id") if isinstance(row, dict) else row for row in value]
    return {pid for pid in ids if isinstance(pid, str)}


def feedback(e: Engine, fmt: str, records: list[dict], sets: list[dict] | None = None) -> dict:
    """실전 기록 분석 (기기에 저장된 기록을 받아 계산만 한다). 실전 표본은 메타 확률에 섞지 않는다."""
    rows = [r for r in records if r.get("format", fmt) == fmt and r.get("outcome") in ("win", "loss", "draw")]
    n = len(rows)
    wins = sum(1 for r in rows if r["outcome"] == "win") + .5 * sum(1 for r in rows if r["outcome"] == "draw")
    losses = [r for r in rows if r["outcome"] == "loss"]
    seen_in_losses = Counter(p for r in losses for p in _ids(r.get("enemy")))
    seen_all = Counter(p for r in rows for p in _ids(r.get("enemy")))
    trouble = [{"id": p, "name": _name(e.P[p]) if p in e.P else p, "losses": k, "games": seen_all[p],
                "lossRate": round(k / seen_all[p], 2)}
               for p, k in seen_in_losses.most_common() if seen_all[p] >= 2 and k / seen_all[p] >= .6][:6]
    width = 2 if fmt == "Doubles" else 1
    paired_games, exact, deviated, lead_matches = [], [], [], 0
    calibration = []
    opening_games = opening_matches = 0
    opponent_seen = opponent_first = opponent_top = 0
    for r in rows:
        rec = r.get("prediction")
        team = r.get("team")
        if (not isinstance(rec, dict) or not isinstance(team, list) or len(team) != 6
                or not all(isinstance(s, Mapping) for s in team) or len(_ids(r.get("enemy"))) != 6
                or rec.get("basis") != "static"
                or rec.get("format") != fmt or _ids(rec.get("enemy")) != _ids(r.get("enemy"))
                or rec.get("teamSignature") != feedback_team_signature(team)):
            continue
        expected = _ids(rec.get("lead"))
        expected_back = _ids(rec.get("back"))
        actual = _ids(r.get("myLead"))
        actual_back = _ids(r.get("myBack"))
        if (len(actual) == len(expected) == width and len(actual_back) == len(expected_back) == 2
                and not actual & actual_back and (actual | actual_back) <= _ids(team)):
            lead_matches += actual == expected
            matched = actual == expected and actual_back == expected_back
            (exact if matched else deviated).append(r)
            forecast = rec.get("simulation")
            estimate = forecast.get("rate") if isinstance(forecast, dict) else None
            if (matched and isinstance(estimate, (int, float)) and 0 <= estimate <= 1
                    and rec.get("season") and r.get("season") == rec["season"]):
                calibration.append((estimate, {"win": 1., "draw": .5, "loss": 0.}[r["outcome"]]))
            opening = r.get("opening")
            examples = forecast.get("openingExamples") if isinstance(forecast, dict) else None
            if (matched and isinstance(opening, dict) and set(opening) == actual
                    and all(isinstance(m, str) and m for m in opening.values()) and isinstance(examples, list)):
                choices = [{a.get("actor"): a.get("move") for a in line["actions"]
                            if isinstance(a, dict) and isinstance(a.get("actor"), str)}
                           for line in examples if isinstance(line, dict) and isinstance(line.get("actions"), list)]
                choices = [c for c in choices if set(c) == actual]
                if choices:
                    opening_games += 1
                    opening_matches += opening in choices
        foe_lead = _ids(r.get("enemyLead"))
        raw_candidates = rec.get("enemyLeadCandidates")
        candidates = [_ids(c) for c in raw_candidates[:3] if isinstance(c, list)] if isinstance(raw_candidates, list) else []
        if len(foe_lead) == width and foe_lead <= _ids(r.get("enemy")) and candidates:
            opponent_seen += 1
            opponent_first += foe_lead == candidates[0]
            opponent_top += foe_lead in candidates
        paired_games.append(r)

    def rate(ms):
        return round(sum(1 if m["outcome"] == "win" else .5 if m["outcome"] == "draw" else 0 for m in ms) / len(ms),
                     2) if ms else None

    reasons = Counter(r["lossReason"] for r in losses if isinstance(r.get("lossReason"), str) and r["lossReason"].strip())
    observed = [r for r in losses if isinstance(r.get("turnNote"), str) and r["turnNote"].strip()]
    hypotheses = []
    for t in trouble[:3]:
        hypotheses.append({"kind": "matchup", "foe": t["id"],
                           "text": f"{t['name']} 상대 {t['games']}판 중 {t['losses']}패 — 대응 멤버·기술을 실험실에서 비교해 보세요"})
    if exact and deviated:
        hypotheses.append({"kind": "picks",
                           "text": "선출이 달랐던 판은 상대 구성과 당시 행동도 확인한 뒤 같은 조건으로 비교해 보세요."})
    return {"games": n, "rate": round(wins / n, 3) if n else None,
            "ci": battle_lab.wilson(wins, n) if n else None, "source": "real",
            "trouble": trouble, "pickCheck": {"followed": len(exact), "followedRate": rate(exact),
                                              "deviated": len(deviated), "deviatedRate": rate(deviated),
                                              "saved": len(paired_games), "leadMatches": lead_matches},
            "enemyLeadCheck": {"games": opponent_seen, "topOne": opponent_first, "topThree": opponent_top},
            "openingCheck": {"games": opening_games, "matches": opening_matches},
            "calibration": {"games": len(calibration), "simulated": round(sum(a for a, _ in calibration) / len(calibration), 3),
                            "observed": round(sum(b for _, b in calibration) / len(calibration), 3)} if calibration else None,
            "turnObservations": [{"turn": r.get("keyTurn"), "text": r["turnNote"]} for r in observed[:5]],
            "lossReasons": [{"text": k, "count": v} for k, v in reasons.most_common(6)],
            "hypotheses": hypotheses,
            "note": f"실전 기록 {n}판 기준입니다. 표본이 적으면 경향일 뿐이며 메타 데이터나 모의전 결과에 섞지 않습니다."}
