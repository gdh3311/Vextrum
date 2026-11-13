"""v4 진단 실험 모음 (VEXTRUM_V4_DIAGNOSTIC_REPORT.md 의 근거).

    .venv/Scripts/python tools_diag_v4.py <실험> [인자]

실험은 각자 JSON 을 diag_out/<실험>.json 에 남긴다. 결과를 지어내지 않도록 보고서는 이 파일들의 수치만 쓴다.
연구 DB는 복사본을 쓴다 (실행 중인 앱과 잠금 충돌 방지).
"""
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

_live = Path(__file__).parent / "data" / "research.sqlite"
_copy = Path(tempfile.gettempdir()) / "vextrum_diag_research.sqlite"
if _live.is_file() and not _copy.is_file():
    shutil.copyfile(_live, _copy)
os.environ.setdefault("RESEARCH_DB", str(_copy))

from app import auto_team, battle_lab, collector, parallel, policy, strategy  # noqa: E402
from app.engine import Engine  # noqa: E402

OUT = Path(__file__).parent / "diag_out"
OUT.mkdir(exist_ok=True)
E = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
FMT = "Doubles"
TARGET = {"golisopod", "chandelure", "rillaboom", "garchomp", "dragonite", "sylveon"}


def save(name, data):
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"saved diag_out/{name}.json", flush=True)


def timed_build(**kw):
    stamps = []

    def progress(snapshot):
        stamps.append((time.perf_counter(), snapshot.get("stage"), snapshot.get("battles", 0)))

    start = time.perf_counter()
    r = auto_team.build(E, FMT, kw.pop("styles", []), [], [], progress=progress, **kw)
    total = time.perf_counter() - start
    # 진행 스냅샷 사이 시간·전투 수(누적값의 차이)를 앞 스냅샷의 단계에 붙인다.
    stages, prev = {}, (start, None, 0)
    for t, stage, battles in stamps + [(time.perf_counter(), None, None)]:
        if prev[1] is not None:
            row = stages.setdefault(prev[1], {"seconds": 0., "battles": 0})
            row["seconds"] = round(row["seconds"] + t - prev[0], 2)
            if battles is not None:
                row["battles"] += battles - prev[2]
        prev = (t, stage, battles if battles is not None else prev[2])
    return r, total, stages


def team_of(c):
    return [m["set"] for m in c["members"]]


def recover():
    """대상 팀을 같은 설정으로 다시 만든다 (빌드 결과는 서버 메모리에만 있고 저장되지 않음)."""
    found, runs = None, []
    for engine in ("v4", "v5"):
        for originality in ("unique", "balanced"):
            for tune in ("quick", "off"):
                r, total, stages = timed_build(depth="quick", tune=tune, rankers=False, originality=originality,
                                               engine=engine)
                ids = [{m["id"] for m in c["members"]} for c in r["candidates"]]
                hit = next((c for c, s in zip(r["candidates"], ids) if s == TARGET), None)
                runs.append({"engine": engine, "originality": originality, "tune": tune, "seconds": round(total, 1),
                             "stages": stages, "teams": [sorted(s) for s in ids], "hit": bool(hit)})
                print(engine, originality, tune, round(total, 1), [sorted(s) for s in ids], bool(hit), flush=True)
                if hit and not found:
                    found = {"engine": engine, "originality": originality, "tune": tune, "candidate": hit,
                             "evaluation": r["evaluation"]}
    save("recover", {"runs": runs, "found": found})




# ---------------------------------------------------------------- 공용
MASTER_STYLES = ["balanced", "aggressive", "defensive", "setup", "pivot", "counter"]
TIERS = ["poke", "great", "ultra", "master", "champion"]
TIER_KO = {"poke": "몬스터볼", "great": "슈퍼볼", "ultra": "하이퍼볼", "master": "마스터볼", "champion": "챔피언"}
MEGAS = None


def target():
    return team_of(json.loads((OUT / "recover.json").read_text(encoding="utf-8"))["found"]["candidate"])


def rate(r):
    return (r["win"] + .5 * r["draw"]) / max(1, r["runs"])


def summary(r):
    ci = battle_lab.wilson(r["win"] + .5 * r["draw"], r["runs"])
    return {"rate": round(rate(r), 3), "ci": ci, "games": r["runs"],
            "byStrategy": {s["style"]: [s["win"], s["runs"]] for s in r["strategies"]},
            "members": {m["id"]: {"pick": m["pickRate"], "lead": m["leads"], "koPerGame": m["koPerGame"],
                                  "win": m["winRate"]} for m in r.get("memberStats", [])},
            "lossTags": {t["key"]: t["share"] for t in r.get("lossTags", [])},
            "lossCauses": {c["key"]: c["shareOfLosses"] for c in r.get("lossCauses", [])}}


def mega_usage(team, r):
    """선출 순서에서 처음 나오는 메가 후보만 메가진화한다 (simulation._fighters). 선출 기록으로 누가 메가였는지 센다."""
    megas = [s["id"] for s in team if E.resolve({**E.default_set(s["id"], FMT), **s}, FMT)["mega"]]
    out = Counter()
    for block in r["strategies"]:
        for p in block["picks"]:
            order = [*p["leads"], *p["back"]]
            brought = [m for m in order if m in megas]
            key = ("both:" + brought[0]) if len(brought) == 2 else (brought[0] if brought else "none")
            out[key] += p["runs"]
    return dict(out)


def paired_row(a, b):
    st = battle_lab.paired(a["outcomes"], b["outcomes"])
    return {"base": round(rate(a), 3), "variant": round(rate(b), 3), "diff": round(st["diff"], 3),
            "low": round(st["low"], 3), "high": round(st["high"], 3), "n": st["n"]}


# ---------------------------------------------------------------- 6장: 난이도 × 스타일
def grid(games="40", champion_games="24"):
    team = target()
    cells = {}
    for tier in TIERS:
        n = int(champion_games if tier == "champion" else games)
        teams = [team] * len(MASTER_STYLES)
        # 스타일마다 같은 시드 → 같은 상대·난수, CPU 판단만 다르다
        for style in MASTER_STYLES:
            r = parallel.compare_teams(E, FMT, [team], n, 4_200_017, tier, cpu_styles=[style])[0]
            cells[f"{tier}:{style}"] = {**summary(r), "megas": mega_usage(team, r)}
            print(tier, style, cells[f"{tier}:{style}"]["rate"], cells[f"{tier}:{style}"]["ci"], flush=True)
    save("grid", cells)


def behaviour(battles="30"):
    """CPU 스타일별 실제 행동 차이 (하이퍼볼 탐욕 판단 기준, 첫 4턴): 방어·교체·변화기·광역 비율."""
    from app import simulation

    team = target()
    foes_pool = [E.default_set(p["id"], FMT) for p in E.ranked(FMT)[:12]]
    out = {}
    for style in MASTER_STYLES:
        c = Counter()
        for seed in range(int(battles)):
            foes = [foes_pool[(seed + k) % 12] for k in range(4)]
            b = simulation.Battle(E, FMT, team[:4], foes, seed, log=False, difficulty="ultra", cpu_style=style)
            for _ in range(4):
                if b.winner:
                    break
                for a in b._greedy(1):
                    move = a.get("move")
                    c["actions"] += 1
                    if a["kind"] == "switch":
                        c["switch"] += 1
                    elif move in simulation.PROTECT:
                        c["protect"] += 1
                    elif move and not E.M.get(move, {}).get("power"):
                        c["status"] += 1
                    elif move and E.M[move].get("target") in ("allAdjacentFoes", "allAdjacent"):
                        c["spread"] += 1
                    else:
                        c["attack"] += 1
                b.advance()
        out[style] = {k: round(v / c["actions"], 3) for k, v in c.items() if k != "actions"} | {"actions": c["actions"]}
        print(style, out[style], flush=True)
    save("behaviour", out)


# ---------------------------------------------------------------- 5장: 상대 유형별 선출
def picks(games="60"):
    team = target()
    out = {}
    pools = battle_lab._draft_pools(E, FMT)
    for style in pools:
        r = parallel.compare_teams(E, FMT, [team], int(games), 5_300_011, "master", styles={style},
                                   cpu_styles=["balanced", "aggressive", "defensive", "setup", "pivot"])[0]
        block = r["strategies"][0]
        top = sorted(block["picks"], key=lambda p: -p["runs"])[:3]
        out[style] = {"label": block["label"], **summary(r), "megas": mega_usage(team, r),
                      "picks": [{"leads": p["leads"], "back": p["back"], "runs": p["runs"], "win": p["win"],
                                 "opening": p.get("opening", [])} for p in top]}
        print(style, out[style]["rate"], [(p["leads"], p["back"], p["runs"], p["win"]) for p in top], flush=True)
    # 선출 정책 최적화 전후 (보류 상대에서)
    base = parallel.compare_teams(E, FMT, [team], 40, 5_300_777, "ultra")[0]
    plan, evidence = policy.optimize(E, FMT, team, base, depth="standard")
    hold = parallel.compare_teams(E, FMT, [team, team], 150, 5_311_999, "master", policies=[None, plan or None],
                                  cpu_styles=["balanced", "aggressive", "defensive", "setup", "pivot"])
    out["_policy"] = {"plan": {k: list(v) for k, v in plan.items()}, "evidence": evidence,
                      "holdout": paired_row(hold[0], hold[1])}
    print("policy", out["_policy"]["plan"], out["_policy"]["holdout"], flush=True)
    save("picks", out)


# ---------------------------------------------------------------- 7장: 기여도 (Ablation)
H_SCREEN, H_VAL, H_VAL2 = 6_100_003, 6_200_007, 6_300_011
HOLD_STYLES = ["balanced", "aggressive", "defensive", "setup", "pivot"]


def _hold(teams, games, seed, policies=None, tier="master"):
    return parallel.compare_teams(E, FMT, teams, games, seed, tier, policies=policies,
                                  cpu_styles=HOLD_STYLES if tier == "master" else None)


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda k: xs[k])
    r = [0] * len(xs)
    for pos, k in enumerate(order):
        r[k] = pos
    return r


def _spearman(a, b):
    import statistics

    return round(statistics.correlation(_ranks(a), _ranks(b)), 3) if len(a) > 2 else None


def ablation(screen_games="60", val_games="150"):
    from app.engine import weight
    from app.set_tuner import Tuner

    team = target()
    meta, pool = auto_team._pool(E, FMT)
    weights = [weight(E.rank(f["id"], FMT) or 250) for f in meta]
    cands = [auto_team._candidate(E, FMT, meta, s) for s in team]
    names = [c.species for c in cands]
    base_score = auto_team._score(cands, (), weights)
    out = {"team": [s["id"] for s in team], "draftScore": round(base_score, 3)}
    # 슬롯마다 빌더 자신의 초안 점수로 대체 후보 3마리 (같은 종·같은 도구 제외)
    variants = []
    for i, c in enumerate(cands):
        others = cands[:i] + cands[i + 1:]
        rows = []
        for alt in pool:
            if alt.species in names or not auto_team._eligible(alt, others):
                continue
            trial = others[:i] + [alt] + others[i:]
            if sum(bool(x.resolved["mega"]) for x in trial) > 2:
                continue
            rows.append((auto_team._score(trial, (), weights) - base_score, alt))
        rows.sort(key=lambda r: -r[0])
        picked, seen = [], set()
        for delta, alt in rows:
            if alt.species not in seen:
                seen.add(alt.species)
                picked.append((delta, alt))
            if len(picked) == 3:
                break
        for delta, alt in picked:
            sets = [x.set for x in others[:i]] + [alt.set] + [x.set for x in others[i:]]
            variants.append((i, alt.id, round(delta, 3), sets))
    print("variants", len(variants), flush=True)
    screen = _hold([team] + [v[3] for v in variants], int(screen_games), H_SCREEN)
    base_s = screen[0]
    rows = []
    for v, r in zip(variants, screen[1:]):
        base_by = {b["style"]: b["win"] / b["runs"] for b in base_s["strategies"]}
        rows.append({"slot": v[0], "out": team[v[0]]["id"], "in": v[1], "item": v[3][v[0]].get("item"),
                     "draftDelta": v[2], "screen": paired_row(base_s, r),
                     "byStrategyDelta": {s["style"]: round(s["win"] / s["runs"] - base_by.get(s["style"], 0), 3)
                                         for s in r["strategies"]}})
    print("screened", flush=True)
    best = {}
    for row, v in zip(rows, variants):
        if row["slot"] not in best or row["screen"]["diff"] > best[row["slot"]][0]["screen"]["diff"]:
            best[row["slot"]] = (row, v)
    val = _hold([team] + [v[3] for _, v in best.values()], int(val_games), H_VAL)
    for (row, v), r in zip(best.values(), val[1:]):
        row["validation"] = paired_row(val[0], r)
    out["variants"] = rows
    out["base"] = {"screen": summary(base_s), "validation": summary(val[0])}
    out["spearmanDraftVsBattle"] = _spearman([r["draftDelta"] for r in rows], [r["screen"]["diff"] for r in rows])
    print("validated", out["spearmanDraftVsBattle"], flush=True)
    # A) 팀 유지, 선출만 재최적화
    rep = parallel.compare_teams(E, FMT, [team], 40, 6_500_001, "ultra")[0]
    plan, evidence = policy.optimize(E, FMT, team, rep, depth="standard")
    a_res = _hold([team, team], int(val_games), H_VAL2, policies=[None, plan or None])
    out["A_policyOnly"] = {"plan": {k: list(v) for k, v in plan.items()}, "adopted": len(plan), "evidence": evidence,
                           "holdout": paired_row(a_res[0], a_res[1])}
    print("A", out["A_policyOnly"]["holdout"], flush=True)
    # B) 팀원 유지, 세트만 (standard 튜닝)
    sets, changes, info = Tuner(E, FMT).tune(team, "standard")
    b_res = _hold([team, sets], int(val_games), H_VAL2)
    out["B_setsOnly"] = {"changes": changes, "info": info, "holdout": paired_row(b_res[0], b_res[1])}
    print("B", out["B_setsOnly"]["holdout"], changes, flush=True)
    # C) 검증에서 가장 좋았던 한 자리 교체 + 선출 재최적화
    top_row, top_v = max(best.values(), key=lambda rv: rv[0]["validation"]["diff"])
    rep_c = parallel.compare_teams(E, FMT, [top_v[3]], 40, 6_500_001, "ultra")[0]
    plan_c, _ = policy.optimize(E, FMT, top_v[3], rep_c, depth="standard")
    c_res = _hold([team, top_v[3], top_v[3]], int(val_games), H_VAL2, policies=[None, None, plan_c or None])
    out["C_swapPlusPolicy"] = {"swap": [top_row["out"], top_row["in"]], "plan": {k: list(v) for k, v in plan_c.items()},
                               "swapOnly": paired_row(c_res[0], c_res[1]), "swapAndPolicy": paired_row(c_res[0], c_res[2])}
    print("C", out["C_swapPlusPolicy"], flush=True)
    # 메가: 메가스톤을 떼고 사용률 상위 비메가 도구로
    mega_rows = {}
    for i, s in enumerate(team):
        if not E.resolve({**E.default_set(s["id"], FMT), **s}, FMT)["mega"]:
            continue
        used = {x.get("item") for x in team}
        items = [row["name"] for row in E.P[s["id"]]["usage"][FMT]["items"]
                 if row["name"] not in used and not E.find_mega(E.P[s["id"]], stone=row["name"])]
        alt = [dict(x) for x in team]
        alt[i] = {**s, "item": items[0] if items else "Sitrus Berry", "mega": None}
        mega_rows[s["id"]] = (alt[i]["item"], alt)
    m_res = _hold([team] + [alt for _, alt in mega_rows.values()], int(val_games), H_VAL)
    out["megaStoneRemoved"] = {pid: {"newItem": item, **paired_row(m_res[0], r)}
                               for (pid, (item, _)), r in zip(mega_rows.items(), m_res[1:])}
    out["megaUsage"] = mega_usage(team, val[0])
    save("ablation", out)
    print("mega", out["megaStoneRemoved"], out["megaUsage"], flush=True)


# ---------------------------------------------------------------- 8장: 다양성 / 10장: 비용 / CPU 편향
def diversity(engine="v4", depth="quick"):
    from tools_bench_builder import RUNS

    rows = []
    for originality in ("meta", "balanced", "unique"):
        for styles, kw in RUNS:
            try:
                r, total, stages = timed_build(styles=list(styles), depth=depth, tune="off", rankers=False,
                                               originality=originality, engine=engine, **kw)
            except ValueError as error:  # 조건을 못 맞춘 빌드도 결과로 남긴다
                rows.append({"originality": originality, "styles": styles, "kw": kw, "failed": str(error)})
                print(originality, styles, kw, "FAILED", error, flush=True)
                save(f"diversity_{engine}_{depth}", rows)
                continue
            for c in r["candidates"]:
                m = c.get("metrics") or {}
                rows.append({"originality": originality, "styles": styles, "kw": kw, "seconds": round(total, 1),
                             "stages": stages, "n": len(r["candidates"]),
                             "ids": [x["id"] for x in c["members"]], "sets": team_of(c),
                             "family": m.get("family"), "primary": (c.get("strategy") or {}).get("primary"),
                             "hyper": m.get("winRate"),
                             "leagues": {k: v["rate"] for k, v in (m.get("leagues") or {}).items()},
                             "plans": m.get("plans"), "fromResearch": c.get("fromResearch"),
                             "rankerOverlap": (c.get("rankerOverlap") or {}).get("count")})
            print(originality, styles, kw, round(total, 1), len(r["candidates"]), flush=True)
            save(f"diversity_{engine}_{depth}", rows)


def bias(name="diversity_v4_quick"):
    """빌드에 쓴 CPU(하이퍼볼) 판정과 보류 마스터볼·챔피언 순위가 같은가."""
    import statistics

    rows = [r for r in json.loads((OUT / f"{name}.json").read_text(encoding="utf-8")) if "ids" in r]
    uniq = {}
    for r in rows:
        uniq.setdefault(tuple(sorted(r["ids"])), r)
    teams = list(uniq.values())
    sets = [t["sets"] for t in teams]
    hyper = parallel.compare_teams(E, FMT, sets, 60, 7_100_003, "ultra")
    master = _hold(sets, 60, 7_200_007)
    champ = parallel.compare_teams(E, FMT, sets, 24, 7_300_011, "champion")
    h, m, c = [rate(x) for x in hyper], [rate(x) for x in master], [rate(x) for x in champ]
    built = [t["hyper"] or 0 for t in teams]
    out = {"teams": len(teams),
           "spearman": {"build_vs_hyperFresh": _spearman(built, h), "hyper_vs_master": _spearman(h, m),
                        "hyper_vs_champion": _spearman(h, c), "master_vs_champion": _spearman(m, c),
                        "build_vs_champion": _spearman(built, c)},
           "mean": {"build": round(statistics.mean(built), 3), "hyperFresh": round(statistics.mean(h), 3),
                    "master": round(statistics.mean(m), 3), "champion": round(statistics.mean(c), 3)},
           "rows": [{"ids": t["ids"], "originality": t["originality"], "build": t["hyper"], "hyper": round(a, 3),
                     "master": round(b, 3), "champion": round(d, 3)} for t, a, b, d in zip(teams, h, m, c)]}
    save(f"bias_{name}", out)
    print(json.dumps({k: out[k] for k in ("teams", "spearman", "mean")}), flush=True)


def budget():
    """탐색 예산(quick → standard)을 늘리면 보류 성능도 오르는가 (조건 4개, 균형)."""
    conds = [([], {}), (["rain"], {}), (["trickroom"], {}), (["tailwind"], {})]
    out = {}
    for depth in ("quick", "standard"):
        rows = []
        for styles, kw in conds:
            r, total, stages = timed_build(styles=list(styles), depth=depth, tune="off", rankers=False,
                                           originality="balanced", engine="v4", **kw)
            rows.append({"styles": styles, "seconds": round(total, 1), "stages": stages,
                         "teams": [team_of(c) for c in r["candidates"]],
                         "ids": [[x["id"] for x in c["members"]] for c in r["candidates"]]})
            print(depth, styles, round(total, 1), flush=True)
        out[depth] = rows
    flat = [(d, i, t) for d in ("quick", "standard") for i, row in enumerate(out[d]) for t in row["teams"]]
    res = _hold([t for _, _, t in flat], 80, 7_400_009)
    per = {}
    for (d, i, _), r in zip(flat, res):
        per.setdefault((d, i), []).append(r["outcomes"])
    a, b = [], []
    for i in range(len(conds)):
        if ("quick", i) in per and ("standard", i) in per:
            a += [sum(c) / len(c) for c in zip(*per["quick", i])]
            b += [sum(c) / len(c) for c in zip(*per["standard", i])]
    st = battle_lab.paired(a, b)
    out["holdout"] = {"quick": round(sum(a) / len(a), 3), "standard": round(sum(b) / len(b), 3),
                      "diff": round(st["diff"], 3), "low": round(st["low"], 3), "high": round(st["high"], 3)}
    out["seconds"] = {d: round(sum(r["seconds"] for r in out[d]) / len(out[d]), 1) for d in ("quick", "standard")}
    save("budget", out)
    print(out["holdout"], out["seconds"], flush=True)


# ---------------------------------------------------------------- 4번 요청: 전략이 실제로 작동하는가
SPEED_MODES = ("tailwind", "trickroom")


def _speed_roles(team):
    """빌더의 전략 태그에서 속도 조작 시동·수혜 포켓몬 id."""
    meta, _ = auto_team._pool(E, FMT)
    roster = [auto_team._candidate(E, FMT, meta, s) for s in team]
    analysis = strategy.analyze(E, FMT, roster)
    name_to_id = {(c.resolved["ko"] or c.resolved["name"]): c.id for c in roster}
    roles = {}
    for tag in analysis["tags"]:
        if tag["key"] in SPEED_MODES:
            roles[tag["key"]] = {"setters": [name_to_id[n] for n in tag["setters"] if n in name_to_id],
                                 "payoffs": [name_to_id[n] for n in tag["payoffs"] if n in name_to_id]}
    return roles


def execution_of(team, games=60, seed=8_100_007, tier="master"):
    from random import Random

    from app import simulation

    roles = _speed_roles(team)
    player = battle_lab._resolve(E, FMT, team)
    stats = {mode: Counter() for mode in roles}
    overall = Counter()
    for k, match_seed in enumerate(battle_lab._match_seeds(E, FMT, games, seed)):
        rng = Random(match_seed)
        style, roster = battle_lab._draft(E, FMT, match_seed, rng)
        match = battle_lab._match_against(E, FMT, player, style, roster, rng)
        cpu_style = HOLD_STYLES[k % len(HOLD_STYLES)]
        b = simulation.Battle(E, FMT, [team[i] for i in match.ours], [match.roster[i].set for i in match.theirs],
                              match.battle_seed, log=False, foe_strategy=match.style, difficulty=tier,
                              cpu_style=cpu_style)
        first = {}
        while not b.winner:
            b.advance()
            for mode in roles:
                if mode not in first and mode in b.activated[0]:
                    first[mode] = b.turn
        won = {"win": 1., "draw": .5, "loss": 0.}[b.winner]
        brought = {team[i]["id"] for i in match.ours}
        overall["games"] += 1
        overall["win"] += won
        overall["koBeforeMove"] += b.trace[0]["ko_before_move"]
        for mode, r in roles.items():
            s = stats[mode]
            has_setter = bool(brought & set(r["setters"]))
            has_payoff = bool(brought & set(r["payoffs"]))
            s["games"] += 1
            s["setterBrought"] += has_setter
            s["bothBrought"] += has_setter and has_payoff
            if has_setter:
                used = mode in first
                s["activated"] += used
                s["activatedTurnSum"] += first.get(mode, 0)
                s["winWhenActivated"] += won if used else 0
                s["winWhenNotActivated"] += won if not used else 0
                s["koBeforeMoveActivated"] += b.trace[0]["ko_before_move"] if used else 0
                s["koBeforeMoveNot"] += b.trace[0]["ko_before_move"] if not used else 0
    out = {"roles": roles, "games": overall["games"], "win": round(overall["win"] / overall["games"], 3),
           "koBeforeMovePerGame": round(overall["koBeforeMove"] / overall["games"], 2), "modes": {}}
    for mode, s in stats.items():
        act, setter = s["activated"], s["setterBrought"]
        out["modes"][mode] = {
            "setterBroughtRate": round(setter / s["games"], 3),
            "setterAndPayoffRate": round(s["bothBrought"] / s["games"], 3),
            "activationRateWhenSetterBrought": round(act / setter, 3) if setter else None,
            "meanActivationTurn": round(s["activatedTurnSum"] / act, 2) if act else None,
            "winWhenActivated": round(s["winWhenActivated"] / act, 3) if act else None,
            "winWhenSetterBroughtButNotActivated": round(s["winWhenNotActivated"] / (setter - act), 3)
            if setter - act else None,
            "koBeforeMoveActivated": round(s["koBeforeMoveActivated"] / act, 2) if act else None,
            "koBeforeMoveNotActivated": round(s["koBeforeMoveNot"] / (setter - act), 2) if setter - act else None,
            "counts": dict(s)}
    return out


def execution(games="60"):
    out = {"target": execution_of(target(), int(games))}
    div = OUT / "diversity_v4_quick.json"
    if div.is_file():
        rows = [r for r in json.loads(div.read_text(encoding="utf-8")) if "ids" in r]
        uniq = {}
        for r in rows:
            uniq.setdefault(tuple(sorted(r["ids"])), r)
        sample = list(uniq.values())[:16]
        out["diversity"] = [{"ids": r["ids"], "originality": r["originality"],
                             **execution_of(r["sets"], int(games) // 2, 8_200_011)} for r in sample]
    save("execution", out)
    print(json.dumps(out["target"], ensure_ascii=False), flush=True)


# ---------------------------------------------------------------- 조종 AI 비대칭: 내 팀은 항상 탐욕 판단으로 싸운다
def pilot(games="30", teams="14"):
    """같은 선출·같은 난수로 (a) 원래 방향: 내 팀 = 탐욕(simulation._greedy), 상대 = 마스터볼 탐색 AI
    (b) 뒤집은 방향: 내 팀 = 마스터볼 탐색 AI, 상대 = 탐욕. 팀 순위와 속도 조작 사용률이 바뀌는지 본다."""
    from random import Random

    from app import simulation

    rows = [r for r in json.loads((OUT / "diversity_v4_quick.json").read_text(encoding="utf-8")) if "ids" in r]
    uniq = {}
    for r in rows:
        uniq.setdefault(tuple(sorted(r["ids"])), r)
    sample = list(uniq.values())[:int(teams)]
    out = []
    for r in sample:
        team = r["sets"]
        player = battle_lab._resolve(E, FMT, team)
        c = Counter()
        for k, match_seed in enumerate(battle_lab._match_seeds(E, FMT, int(games), 9_400_001)):
            rng = Random(match_seed)
            style, roster = battle_lab._draft(E, FMT, match_seed, rng)
            match = battle_lab._match_against(E, FMT, player, style, roster, rng)
            mine = [team[i] for i in match.ours]
            theirs = [match.roster[i].set for i in match.theirs]
            for orient in ("normal", "swapped"):
                if orient == "normal":
                    b = simulation.Battle(E, FMT, mine, theirs, match.battle_seed, log=False,
                                          foe_strategy=match.style, difficulty="master")
                    me = 0
                else:
                    b = simulation.Battle(E, FMT, theirs, mine, match.battle_seed, log=False, difficulty="master")
                    me = 1
                while not b.winner:
                    b.advance()
                won = {"win": 1., "draw": .5, "loss": 0.}[b.winner]
                c[orient + "Win"] += won if me == 0 else 1 - won
                c[orient + "TW"] += "tailwind" in b.activated[me]
                c[orient + "TR"] += "trickroom" in b.activated[me]
            c["games"] += 1
        n = c["games"]
        out.append({"ids": r["ids"], "family": r["family"], "games": n,
                    **{k: round(v / n, 3) for k, v in c.items() if k != "games"}})
        print(out[-1], flush=True)
    summary = {
        "spearmanNormalVsSwapped": _spearman([x["normalWin"] for x in out], [x["swappedWin"] for x in out]),
        "mean": {k: round(sum(x.get(k, 0) for x in out) / len(out), 3)
                 for k in ("normalWin", "swappedWin", "normalTW", "swappedTW", "normalTR", "swappedTR")}}
    save("pilot", {"summary": summary, "teams": out})
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
