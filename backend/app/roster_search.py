"""Use losses from simulated battles to explore different six-Pokémon rosters."""
from dataclasses import dataclass, field
from itertools import combinations

from . import auto_team


# Rounds, active branches, variants per branch, screen games, confirmation games.
BUDGETS = {"quick": (1, 2, 4, 14, 21), "standard": (2, 3, 5, 21, 35),
           "deep": (3, 4, 6, 28, 49)}


def signature(roster):
    return frozenset(c.species for c in roster)


@dataclass
class Branch:
    group: tuple
    roster: tuple
    report: dict
    history: list = field(default_factory=list)


def _proposals(e, fmt, branch, pool, fixed, valid, weights, extra, limit, seen):
    group, team, report = branch.group, branch.roster, branch.report
    strategies = report["strategies"]
    weakness = next((row for row in strategies if row["loss"]), strategies[0])
    threats = [e.default_resolved(f["id"], fmt) for f in weakness.get("lossFoes", ())]
    base_score = auto_team._score(team, group, weights, extra)
    base_roles = {}
    for style in group:
        for feature, minimum in auto_team.STYLES[style].requirements:
            keep = min(minimum, sum(feature in c.features for c in team))
            base_roles[feature] = max(base_roles.get(feature, 0), keep)
    base_types = {t for c in team for t in c.resolved["types"]}
    core_types = auto_team.TYPE_CORES.get(extra.core, (set(), ""))[0]
    picked = {m["id"]: m["picked"] / report["runs"] for m in report.get("memberStats", ())}
    threat_scores = {}
    old_species = signature(team)

    def matchup(c):
        key = id(c)
        if key not in threat_scores:
            threat_scores[key] = [e.matchup(c.resolved, foe, fmt)["score"] for foe in threats]
        return threat_scores[key]

    original_answers = [sorted((matchup(c)[i] for c in team), reverse=True)[:2]
                        for i in range(len(threats))]

    def keeps_plan(roster):
        types = {t for c in roster for t in c.resolved["types"]}
        return (valid(roster)
                and all(sum(feature in c.features for c in roster) >= count for feature, count in base_roles.items())
                and len(core_types & types) >= len(core_types & base_types))

    def score(roster, slots):
        value = .26 * (auto_team._score(roster, group, weights, extra) - base_score)
        # Reward an answer to the Pokémon that actually did damage in losses, and
        # a second usable answer in doubles. The battle result still decides.
        for i, (old_best, old_backup) in enumerate(original_answers):
            best, backup = sorted((matchup(c)[i] for c in roster), reverse=True)[:2]
            value += (.70 * (best - old_best) + .30 * (backup - old_backup)) / len(threats)
        return value + sum(2 * (1 - picked.get(team[i].id, 0)) for i in slots)

    def replace(swaps):
        return tuple(swaps.get(i, c) for i, c in enumerate(team))

    def untested(roster):
        return (group, signature(roster)) not in seen

    singles, by_slot = [], {}
    for i, old in enumerate(team):
        if old.id in fixed:
            continue
        others = team[:i] + team[i + 1:]
        rows = []
        for candidate in pool:
            if candidate.species in old_species or not auto_team._eligible(candidate, others):
                continue
            trial = replace({i: candidate})
            if untested(trial):
                rows.append((score(trial, (i,)), trial, candidate))
        rows.sort(key=lambda row: -row[0])
        distinct = {}
        for value, trial, candidate in rows:
            if keeps_plan(trial) and candidate.species not in distinct:
                distinct[candidate.species] = (value, trial)
            if len(distinct) == 2:
                break
        singles.extend(distinct.values())
        choices = {}
        for _, _, candidate in rows:
            choices.setdefault(candidate.species, candidate)
            if len(choices) == 3:
                break
        by_slot[i] = tuple(choices.values())

    pairs = []
    for i, j in combinations(by_slot, 2):
        for first in by_slot[i]:
            for second in by_slot[j]:
                if not auto_team._eligible(first, (second,)):
                    continue
                trial = replace({i: first, j: second})
                if untested(trial) and keeps_plan(trial):
                    pairs.append((score(trial, (i, j)), trial))
    # Reserve room for one paired swap, even if all high scores are single swaps.
    ranked = sorted(singles, key=lambda row: -row[0])
    if pairs:
        ranked.insert(min(len(ranked), limit - 1), max(pairs, key=lambda row: row[0]))
    proposals = []
    for _, roster in ranked:
        if untested(roster):
            seen.add((group, signature(roster)))
            proposals.append(roster)
        if len(proposals) == limit:
            break
    return weakness, proposals


def _step(old, new, problem, before, after, round_number):
    def member(candidate):
        return {key: candidate.resolved[key] for key in ("id", "name", "ko", "sprite")}

    def result(report):
        target = next(r for r in report["strategies"] if r["style"] == problem["style"])
        return {"wins": report["win"], "runs": report["runs"],
                "strategyWins": target["win"], "strategyRuns": target["runs"],
                **({"rankerRate": report["rankerRate"]} if "rankerRate" in report else {})}

    return {
        "round": round_number, "strategy": problem["label"], "threats": problem.get("lossFoes", ())[:2],
        "swaps": [{"out": member(a), "in": member(b)} for a, b in zip(old, new) if a.id != b.id],
        "before": result(before), "after": result(after),
    }


def refine(e, fmt, anchors, initial, pools, fixed, valid, weights, extra, depth, measure, rank, progress,
           structural=None, policy_first=None):
    rounds, _, limit, screen_games, confirm_games = BUDGETS[depth]
    branches = [Branch(*row) for row in anchors]
    seen = {(g, signature(r)) for g, r, _ in initial}
    tested = accepted = completed = 0
    progress.update("refine", total=2 * rounds, spotlight=[c.id for c in branches[0].roster], notes=[])
    for round_number in range(1, rounds + 1):
        if policy_first:  # v5: 멤버를 바꾸기 전에 지금 6마리의 선출부터 맞춘다 (새로 바뀐 팀만 계산)
            policy_first([(b.group, b.roster, b.report) for b in branches])
        trials, batches = [], []
        for branch in branches:
            problem, variants = _proposals(e, fmt, branch, pools[branch.group], fixed, valid,
                                           weights, extra, limit, seen)
            # 구조 변경 (v4): 핵심 코어는 두고 주변 재구성, 에이스를 두고 전략 자체 변경
            for roster, kind in (structural(branch) if structural else []):
                key = (branch.group, signature(roster))
                if key not in seen and valid(roster):
                    seen.add(key)
                    variants.append(roster)
                    branch.__dict__.setdefault("kinds", {})[signature(roster)] = kind
            if variants:
                start = len(trials)
                trials += [(branch.group, r) for r in [branch.roster, *variants]]
                batches.append((branch, problem, variants, slice(start, len(trials))))
                tested += len(variants)
        if not trials:
            break
        completed += 1
        branch, problem, variants, _ = batches[0]
        progress.update(spotlight=[c.id for c in variants[0]], notes=[problem["label"]])
        seed = 912_641 + round_number * 52_391
        results = measure(trials, screen_games, seed)
        progress.update(done=2 * round_number - 1, battles=len(trials) * screen_games)
        confirmation, finalists = [], []
        for branch, problem, variants, part in batches:
            baseline, *alternatives = results[part]
            ranked = sorted(zip(variants, alternatives), key=lambda pair: rank(pair[1]), reverse=True)
            contenders = [r for r, result in ranked if rank(result) > rank(baseline)][:2]
            if contenders:
                start = len(confirmation)
                confirmation += [(branch.group, r) for r in [branch.roster, *contenders]]
                finalists.append((branch, problem, contenders, slice(start, len(confirmation))))
            branch.report = baseline
        if confirmation:
            progress.update(spotlight=[c.id for c in confirmation[1][1]], notes=[finalists[0][1]["label"]])
        results = measure(confirmation, confirm_games, seed + 23_657) if confirmation else []
        for branch, problem, contenders, part in finalists:
            baseline, *alternatives = results[part]
            roster, result = max(zip(contenders, alternatives), key=lambda pair: rank(pair[1]))
            # Ignore a change driven only by the tie-breaker. It must improve
            # either the chosen score or the overall win rate on fresh games.
            from .battle_lab import clearly_better

            # 새 상대군의 같은 판에서 확실히 나아야 바꾼다 (한쪽 90% 신뢰 하한 > 0).
            paired_data = baseline.get("outcomes") and result.get("outcomes")
            if (paired_data and not clearly_better(baseline["outcomes"], result["outcomes"])) or \
                    rank(result)[:2] <= rank(baseline)[:2]:
                branch.report = baseline
                continue
            step = _step(branch.roster, roster, problem, baseline, result, round_number)
            step["kind"] = branch.__dict__.get("kinds", {}).get(signature(roster), "member")
            branch.history.append(step)
            branch.roster, branch.report = roster, result
            accepted += 1
        progress.update(done=2 * round_number, battles=len(confirmation) * confirm_games)
    progress.update(done=2 * rounds)
    return branches, {"rounds": completed, "tested": tested, "accepted": accepted}
