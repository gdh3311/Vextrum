"""엔진 버전 짝지은 비교 (v5 검증용).

    .venv/Scripts/python tools_bench_versions.py [깊이] [엔진A] [엔진B] [개성]    예) quick v4 v5 balanced

조건 12가지마다 두 엔진으로 팀을 만들고, 모든 팀을 '완전히 보류된' 상대군(탐색·검증에 쓰지 않은 시드)에서
같은 상대·같은 난수로 다시 싸운다. 조건별로 A 팀들 평균과 B 팀들 평균을 판마다 짝지어 차이 자체의 신뢰구간을 낸다.
신뢰구간이 겹친다는 것만으로 '차이 없음'이라고 하지 않기 위해서다. 조건별 최고 팀 승률의 평균·표준편차도 낸다.
"""
import json
import os
import shutil
import statistics
import tempfile
from pathlib import Path

# 앱 백엔드가 쓰고 있는 연구 DB를 잠그지 않도록 복사본으로 벤치한다.
_live = Path(__file__).parent / "data" / "research.sqlite"
_copy = Path(tempfile.gettempdir()) / "vextrum_bench_research.sqlite"
if _live.is_file():
    shutil.copyfile(_live, _copy)
os.environ.setdefault("RESEARCH_DB", str(_copy))
import sys
import time
from collections import Counter

from app import auto_team, battle_lab, collector, parallel
from app.engine import Engine
from tools_bench_builder import RUNS

HOLDOUT = {"champion": (40, 2_468_013), "master": (60, 3_579_111)}


def build_all(e, depth, engine, mode):
    rows, seconds = [], 0.
    for styles, kw in RUNS:
        start = time.perf_counter()
        r = auto_team.build(e, "Doubles", styles, [], [], depth=depth, tune="off", rankers=False,
                            originality=mode, engine=engine, **kw)
        seconds += time.perf_counter() - start
        rows.append([([m["set"] for m in c["members"]],
                      {k: tuple(v) for k, v in (c.get("metrics") or {}).get("policyMap", {}).items()} or None,
                      frozenset(m["id"] for m in c["members"]),
                      (c.get("metrics") or {}).get("family"))
                     for c in r["candidates"]])
    return rows, seconds / len(RUNS)


if __name__ == "__main__":
    # 사용: tools_bench_versions.py 깊이 개성 기준엔진 비교엔진...   (예: quick balanced v4 v5 v5-noquick)
    e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
    depth = sys.argv[1] if len(sys.argv) > 1 else "quick"
    mode = sys.argv[2] if len(sys.argv) > 2 else "balanced"
    names = sys.argv[3:] or ["v4", "v5"]
    base = names[0]
    built = {name: build_all(e, depth, name, mode) for name in names}
    for name, (rows, sec) in built.items():
        teams = [t for cond in rows for t in cond]
        species = Counter(pid for t in teams for pid in t[2])
        families = Counter(t[3] for t in teams)
        print(f"{name}: {sec:.1f}s/build  teams {len(teams)}  distinct {len({t[2] for t in teams})}  "
              f"species {len(species)}  families {dict(families)}", flush=True)
    for league, (games, seed) in HOLDOUT.items():
        flat, index = [], []
        for name, (rows, _) in built.items():
            for ci, cond in enumerate(rows):
                for team in cond:
                    index.append((name, ci))
                    flat.append(team)
        styles = ["balanced", "aggressive", "defensive", "setup", "pivot"] if league == "master" else None
        reports = parallel.compare_teams(e, "Doubles", [t[0] for t in flat], games, seed, league,
                                         policies=[t[1] for t in flat], cpu_styles=styles)
        per = {}  # (엔진, 조건) → 판별 평균 결과
        best = {name: [] for name in names}
        for name in names:
            for ci in range(len(RUNS)):
                outs = [r["outcomes"] for (n, c), r in zip(index, reports) if n == name and c == ci]
                if outs:
                    per[name, ci] = [sum(col) / len(col) for col in zip(*outs)]
                    best[name].append(max(sum(o) / len(o) for o in outs))
        print(f"[{league} 보류 {games}판]", flush=True)
        for name in names:
            vals = best[name]
            line = f"    {name:22s} 조건별 최고 팀 평균 {statistics.mean(vals):.3f} (표준편차 {statistics.pstdev(vals):.3f})"
            if name != base:
                a_out, b_out = [], []
                for ci in range(len(RUNS)):
                    if (base, ci) in per and (name, ci) in per:  # 같은 조건, 같은 판끼리 짝짓기
                        a_out += per[base, ci]
                        b_out += per[name, ci]
                st = battle_lab.paired(a_out, b_out)
                verdict = ("더 나음" if st["low"] > 0 else "더 나쁨" if st["high"] < 0 else "판단 불가")
                line += (f"  팀 평균 {sum(b_out) / len(b_out):.3f} vs {base} {sum(a_out) / len(a_out):.3f}"
                         f"  차이 {st['diff']:+.3f} (95% {st['low']:+.3f}~{st['high']:+.3f}) {verdict}")
            print(line, flush=True)
