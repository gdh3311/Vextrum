"""선출 계획 공동 최적화 (v4).

같은 6마리라도 누구를 선봉에 세우고 누구를 남기느냐로 성적이 크게 바뀐다. 기존 흐름은 고정된 선출 휴리스틱으로
싸운 뒤 진 판을 '멤버 문제'로 보고 팀을 고쳤다. 여기서는 팀을 고치기 전에, 상대 전략마다 선출(선봉 2·후발 2)을
직접 바꿔 보고 같은 판에서 확실히 나아질 때만 계획으로 채택한다.

상대 전략은 팀 미리보기(6마리 종)로만 추정한다(battle_lab.preview_family). 실제 상대 세트는 쓰지 않는다.
"""
from itertools import combinations

from . import battle_lab, parallel

# 미리보기로 추정한 상대 전략 → 그 전략의 상대를 만드는 플레이북
# (미리보기 추정과 실제 플레이북의 대응을 측정해 정함: 비 89%, 쾌청 82%, 사이코필드 87%, 순풍 60%, 트릭룸 44%)
FAMILY_STYLES = {"rain": {"rain"}, "sun": {"sun"}, "psychic": {"psychic"}, "tailwind": {"tailwind", "balance", "setup"},
                 "trickroom": {"trickroom", "setup", "balance"}, "balance": {"balance", "setup", "trickroom"}}
FAMILY_LABELS = {"rain": "비", "sun": "쾌청", "trickroom": "트릭룸", "tailwind": "순풍", "psychic": "사이코필드",
                 "balance": "균형·랭크업", "sand": "모래바람", "snow": "눈"}
RUNS = {"quick": 12, "standard": 20, "deep": 36}
MAX_KEYS = 6  # 비용 상한: 자주 나오는 미리보기 열쇠 6개까지


def _opponents(e, fmt, styles, limit=12):
    pools = battle_lab._draft_pools(e, fmt)
    seen, out = set(), []
    for style in styles:
        if style not in pools:
            continue
        pool, _, _ = pools[style]
        for c in sorted(pool, key=lambda c: -c.popularity):
            if c.id not in seen:
                seen.add(c.id)
                out.append(e.default_resolved(c.id, fmt))
            if len(out) >= limit:
                return out
    return out


def static_picks(e, fmt, team, styles, width, count=4, top=3):
    """90가지 선출을 그 전략의 대표 상대들에 대한 상성으로 점수 매겨 상위 몇 개를 고른다 (검증 전 후보)."""
    own = battle_lab._resolve(e, fmt, team)
    foes = _opponents(e, fmt, styles)
    if not foes:
        return []
    matrix = [[e.matchup(m, f, fmt)["score"] for f in foes] for m in own]
    picks = []
    for group in combinations(range(len(own)), min(count, len(own))):
        coverage = []
        for j in range(len(foes)):
            values = sorted((matrix[i][j] for i in group), reverse=True)
            coverage.append(.76 * values[0] + .24 * values[min(1, len(values) - 1)])
        base = .79 * sum(coverage) / len(coverage) + .21 * min(coverage)
        for leads in combinations(group, min(width, len(group))):
            pressure = sum(max(matrix[i][j] for i in leads) for j in range(len(foes))) / len(foes)
            order = (*leads, *(i for i in group if i not in leads))
            picks.append((.72 * base + .28 * pressure, tuple(own[i]["id"] for i in order)))
    picks.sort(key=lambda row: -row[0])
    out = []
    for _, pick in picks:
        key = (frozenset(pick[:width]), frozenset(pick[width:]))
        if all((frozenset(p[:width]), frozenset(p[width:])) != key for p in out):
            out.append(pick)
        if len(out) == top:
            break
    return out


def preview_keys(e, fmt, runs, seed, styles=None):
    """이 시드·전략 묶음에서 실제로 나올 상대들의 미리보기 열쇠 → 그 열쇠를 만든 플레이북들 (빈도순)."""
    from random import Random

    out = {}
    for match_seed in battle_lab._match_seeds(e, fmt, runs, seed, styles):
        style, roster = battle_lab._draft(e, fmt, match_seed, Random(match_seed))
        key = battle_lab.preview_key(e, fmt, [c.id for c in roster])
        styles_for, count = out.get(key, (set(), 0))
        out[key] = (styles_for | {style}, count + 1)
    return dict(sorted(out.items(), key=lambda kv: -kv[1][1]))


def key_label(key):
    if key.startswith("mix:"):
        return " / ".join(FAMILY_LABELS.get(k, k) for k in key[4:].split("|")) + " 혼합"
    return FAMILY_LABELS.get(key, key)


def _key_styles(key):
    families = key[4:].split("|") if key.startswith("mix:") else [key]
    return set().union(*(FAMILY_STYLES.get(f, {f}) for f in families))


def _candidates(e, fmt, team, report, styles, width, top):
    by_style = {b["style"]: b for b in report.get("strategies", [])}
    present = [s for s in styles if s in by_style] or list(styles)
    current = [tuple(p["leads"]) + tuple(p["back"]) for s in present for p in by_style.get(s, {}).get("picks", [])[:2]]
    out = []
    size = min(4 if fmt == "Doubles" else 3, len(team))
    for pick in current + static_picks(e, fmt, team, present, width, top=top):
        if len(pick) == size and pick not in out:
            out.append(pick)
    return out[:top + 1]


def quick(e, fmt, team, report, *, runs=10, seed=6_120_331, difficulty="ultra", keys=3, top=2):
    """탐색 중 간이 선출 최적화 (v5): 자주 나오는 미리보기 열쇠 몇 개만, 후보 2~3개를 한 번 비교한다.
    탐색 단계라 기준은 느슨하다(같은 판 비교에서 이기면 채택). 최종 후보는 optimize 로 다시 엄격하게 검증한다."""
    width = 2 if fmt == "Doubles" else 1
    plan = {}
    for key, (styles, _) in list(preview_keys(e, fmt, 4 * runs, seed).items())[:keys]:
        candidates = _candidates(e, fmt, team, report, styles, width, top)
        if not candidates:
            continue
        reports = parallel.compare_teams(e, fmt, [team] * (1 + len(candidates)), runs, seed + hash(key) % 997,
                                         difficulty, styles=styles,
                                         policies=[None] + [{key: pick} for pick in candidates])
        base, trials = reports[0], reports[1:]
        best = max(range(len(trials)), key=lambda i: sum(trials[i]["outcomes"]))
        if sum(trials[best]["outcomes"]) > sum(base["outcomes"]):
            plan[key] = candidates[best]
    return plan


def optimize(e, fmt, team, report, depth="standard", seed=8_812_007, difficulty="ultra", start=None):
    """상대 미리보기 열쇠(확신 전략 또는 두 전략 혼합)별 선출 계획을 만든다. 반환: (계획 {열쇠: pick}, 근거 목록).

    start: 탐색 중 간이 최적화로 이미 찾은 계획 (후보에 먼저 넣는다)."""
    width = 2 if fmt == "Doubles" else 1
    runs = RUNS.get(depth, RUNS["standard"])
    policy, evidence = {}, []
    keys = preview_keys(e, fmt, 6 * runs, seed)
    for key, (styles, count) in list(keys.items())[:MAX_KEYS]:
        if count < 3:  # 거의 안 나오는 열쇠는 검증할 판이 모자란다
            continue
        styles = set(styles) | (_key_styles(key) & set(battle_lab._draft_pools(e, fmt)))
        candidates = _candidates(e, fmt, team, report, styles, width, 3)
        if start and key in start and tuple(start[key]) not in candidates:
            candidates.insert(0, tuple(start[key]))
        candidates = candidates[:5]
        if not candidates:
            continue
        reports = parallel.compare_teams(e, fmt, [team] * (1 + len(candidates)), runs, seed + hash(key) % 997,
                                         difficulty, styles=styles,
                                         policies=[None] + [{key: pick} for pick in candidates])
        base, trials = reports[0], reports[1:]
        best_i = max(range(len(trials)), key=lambda i: sum(trials[i]["outcomes"]))
        screen = battle_lab.paired(base["outcomes"], trials[best_i]["outcomes"])
        adopted, stats, confirm_games = False, screen, 0
        if screen["diff"] > 0:
            # 후보 여러 개 중 최고를 같은 판으로 고르면 운이 섞인다 → 새 상대군에서 계획 없음과 다시 비교한다.
            confirm_games = 4 * runs
            check = parallel.compare_teams(e, fmt, [team, team], confirm_games, seed + 31_337 + hash(key) % 991,
                                           difficulty, styles=styles,
                                           policies=[None, {key: candidates[best_i]}])
            stats = battle_lab.paired(check[0]["outcomes"], check[1]["outcomes"])
            adopted = battle_lab.clearly_better(check[0]["outcomes"], check[1]["outcomes"])
        if adopted:
            policy[key] = candidates[best_i]
        evidence.append({
            "family": key, "label": key_label(key), "pick": list(candidates[best_i]),
            "mixed": key.startswith("mix:"), "share": round(count / (6 * runs), 3),
            "screenDiff": round(screen["diff"], 3),
            "diff": round(stats["diff"], 3), "low": round(stats["low"], 3), "high": round(stats["high"], 3),
            "games": confirm_games or runs, "tried": len(candidates), "adopted": adopted,
        })
    return policy, evidence
