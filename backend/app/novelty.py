"""독창성 다섯 갈래와 반사실 비교 요약 (v5).

랭커 팀과 겹치는 마릿수 하나로는 부족하다. 2마리만 같아도 운영이 같으면 사실상 같은 팀이고, 4마리가 같아도
기술·역할·선출이 다르면 다른 팀이다. 그래서 다섯 가지를 따로 잰다.

  species   종 구성: 가장 닮은 랭커 팀과의 자카드 거리
  set       세트: 종마다 랭커 통계의 가장 흔한 도구·특성·기술에서 벗어난 정도
  tactical  운영: 랭커 팀들과 다른 주 전략 가족 비율 + 기본 선출과 다른 검증된 선출 계획
  synergy   시너지: 팀 안의 포켓몬 쌍 중 랭커 팀에서 함께 쓰이지 않은 쌍 비율
  viability 실전성: 챔피언 리그 승률이 그 변칙성을 받쳐 주는가 (40% → 0, 60% → 1)

overall = 앞의 네 가지 평균 × 실전성. 비주류를 많이 넣었다고 높아지지 않는다.
"""
from functools import lru_cache
from itertools import combinations

from . import auto_team, strategy
from .recommend import ranker_rosters


@lru_cache(maxsize=4)
def _ranker_profile(e, fmt):
    teams, families, pairs = [], [], set()
    for _, sets in ranker_rosters(e, fmt):
        ids = [s["id"] for s in sets]
        species = frozenset(auto_team.species(e, pid) for pid in ids)
        teams.append(species)
        pairs |= {frozenset(p) for p in combinations(sorted(species), 2)}
        try:
            roster = [auto_team._candidate(e, fmt, (), s) for s in sets]
            families.append(strategy.family(strategy.analyze(e, fmt, roster)))
        except Exception:  # noqa: BLE001 - 세트를 못 만든 랭커 팀은 전략 비교에서만 뺀다
            pass
    return tuple(teams), tuple(families), frozenset(pairs)


def _common(e, fmt, pid, kind, top):
    rows = e.P.get(pid, {}).get("usage", {}).get(fmt, {}).get(kind, [])
    return {row["name"] for row in rows[:top]}


def _set_distance(e, fmt, s):
    pid = s["id"]
    if not e.P.get(pid, {}).get("usage", {}).get(fmt):
        return 1.
    item = 0. if s.get("item") in _common(e, fmt, pid, "items", 1) else .5 if s.get("item") in _common(
        e, fmt, pid, "items", 3) else 1.
    ability = 0. if s.get("ability") in _common(e, fmt, pid, "abilities", 1) else 1.
    usual = _common(e, fmt, pid, "moves", 4)
    moves = s.get("moves") or []
    move = sum(m not in usual for m in moves) / max(1, len(moves))
    return .35 * item + .15 * ability + .5 * move


def measure(e, fmt, roster, *, family, policy_keys=0, champion_rate=None):
    teams, families, pairs = _ranker_profile(e, fmt)
    names = frozenset(c.species for c in roster)
    species = 1 - max((len(names & t) / len(names | t) for t in teams), default=0.)
    sets = sum(_set_distance(e, fmt, c.set) for c in roster) / len(roster)
    family_share = sum(f == family for f in families) / len(families) if families else 0.
    tactical = .7 * (1 - family_share) + .3 * min(1., policy_keys / 3)
    team_pairs = [frozenset(p) for p in combinations(sorted(names), 2)]
    synergy = sum(p not in pairs for p in team_pairs) / max(1, len(team_pairs))
    viability = 1. if champion_rate is None else max(0., min(1., (champion_rate - .4) / .2))
    overall = (species + sets + tactical + synergy) / 4 * viability
    return {k: round(v, 3) for k, v in (("species", species), ("set", sets), ("tactical", tactical),
                                         ("synergy", synergy), ("viability", viability), ("overall", overall))}


def counterfactual(policy_evidence, tuning, history):
    """같은 포켓몬을 두고 선출만 / 세트만 / 멤버만 바꿨을 때 각각 얼마나 나아졌는가 (검증된 변경만).
    가장 큰 쪽이 '진짜 패배 원인'에 가장 가까운 해석이다."""
    rows = []
    adopted = [p for p in policy_evidence or () if p.get("adopted")]
    if policy_evidence:
        best = max(adopted or policy_evidence, key=lambda p: p["diff"])
        rows.append({"lever": "pick", "label": "선출만 변경", "gain": round(best["diff"] if adopted else 0., 3),
                     "adopted": bool(adopted), "detail": f"{len(adopted)}개 상대 유형에서 채택"})
    if tuning and "base" in tuning:
        gain = (tuning.get("tuned", tuning["base"]) - tuning["base"]) if tuning.get("changes") else 0.
        rows.append({"lever": "set", "label": "세트만 변경", "gain": round(gain, 3), "adopted": bool(tuning.get("changes")),
                     "detail": f"{len(tuning.get('changes') or [])}곳 변경"})
    if history is not None:
        gain = 0.
        for step in history:
            before, after = step["before"], step["after"]
            gain += after["wins"] / max(1, after["runs"]) - before["wins"] / max(1, before["runs"])
        rows.append({"lever": "member", "label": "멤버 변경", "gain": round(gain, 3), "adopted": bool(history),
                     "detail": f"{len(history)}번 교체"})
    main = max((r for r in rows if r["adopted"]), key=lambda r: r["gain"], default=None)
    return {"levers": rows, "main": main["lever"] if main else None}
