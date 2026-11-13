"""팀 자동 구성 벤치마크: 다양성과 성능을 함께 잰다.

    .venv/Scripts/python tools_bench_builder.py [깊이] [엔진:개성 ...]   예) quick v1:balanced v2:balanced

조건 12가지로 팀을 만들고, 보여 준 팀을 '새 상대군'(만들 때 쓰지 않은 난수)에서 200판씩 다시 싸워
선별 운이 빠진 승률을 잰다. 다양성은 등장한 종 수, 서로 다른 팀 수, 랭커 파티와 4마리 이상 겹친 팀 수로 본다.
"""
import json
import sys
import time
from collections import Counter

from app import auto_team, collector, parallel, strategy
from app.engine import Engine
from app.parties import RANKERS

RUNS = [([], {}), (["speed"], {}), (["bulky"], {}), (["rain"], {}), (["sun"], {}), (["tailwind"], {}),
        (["trickroom"], {}), (["physical"], {}), (["special"], {}), (["sand"], {}), ([], {"joker": "force"}),
        ([], {"core": "fwg"})]

if __name__ == "__main__":
    e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
    depth = sys.argv[1] if len(sys.argv) > 1 else "quick"
    modes = sys.argv[2:] or ["v2:meta", "v2:balanced", "v2:unique"]
    ranker_sets = [frozenset(auto_team.species(e, p) for p in r["ids"] if p in e.P)
                   for r in RANKERS if r["format"] == "Doubles"]
    meta, _ = auto_team._pool(e, "Doubles")
    for token in modes:
        engine, _, mode = token.rpartition(":")
        engine = engine or "v2"
        start = time.perf_counter()
        families_per_build = []
        counter, teams, sets, copies, groups, plans = Counter(), [], [], 0, [], []
        for styles, kw in RUNS:
            r = auto_team.build(e, "Doubles", styles, [], [], depth=depth, tune="off", rankers=False,
                                originality=mode, engine=engine, **kw)
            groups.append(len(r["candidates"]))
            families_per_build.append(len({strategy.family(strategy.analyze(
                e, "Doubles", [auto_team._candidate(e, "Doubles", meta, m["set"]) for m in c["members"]]))
                for c in r["candidates"]}))
            for c in r["candidates"]:
                ids = frozenset(m["id"] for m in c["members"])
                teams.append(ids)
                counter.update(ids)
                sets.append([m["set"] for m in c["members"]])
                plans.append({k: tuple(v) for k, v in (c.get("metrics") or {}).get("policyMap", {}).items()} or None)
                names = {auto_team.species(e, m["id"]) for m in c["members"]}
                copies += max(len(names & t) for t in ranker_sets) >= 4
        built = time.perf_counter() - start
        fresh = parallel.compare_teams(e, "Doubles", sets, 200, 777_001, "ultra", policies=plans)
        other = parallel.compare_teams(e, "Doubles", sets, 60, 991_337, "master", policies=plans,
                                       cpu_styles=["balanced", "aggressive", "defensive", "setup", "pivot"])
        other_rates = [(x["win"] + .5 * x["draw"]) / x["runs"] for x in other]
        champ = parallel.compare_teams(e, "Doubles", sets, 24, 1_337_771, "champion", policies=plans)
        champ_w = sum(x["win"] + .5 * x["draw"] for x in champ)
        champ_n = sum(x["runs"] for x in champ)
        from app.battle_lab import wilson
        champ_ci = wilson(champ_w, champ_n)
        rates = [(x["win"] + .5 * x["draw"]) / x["runs"] for x in fresh]
        best, at = [], 0
        for n in groups:  # 조건마다 보여 준 팀 중 가장 강한 팀
            best.append(max(rates[at:at + n]))
            at += n
        print(f"{token:12s} {built / len(RUNS):5.1f}s/build  families/build {sum(families_per_build) / len(RUNS):.2f}"
              f"  vs-master {sum(other_rates) / len(other_rates):.3f}  vs-champion {champ_w / champ_n:.3f} ({champ_ci[0]}~{champ_ci[1]}%)"
              f"  teams {len(sets)}  species {len(counter):2d}  distinct {len(set(teams))}/{len(teams)}"
              f"  ranker-copies {copies:2d}  fresh avg {sum(rates) / len(rates):.3f}  "
              f"best-of-3 avg {sum(best) / len(best):.3f}  top {counter.most_common(3)}", flush=True)
