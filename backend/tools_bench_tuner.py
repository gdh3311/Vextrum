"""세트 조정(set_tuner) 짝지은 비교: 기존 순서 vs 학습 모델(세트 특징) 사용.

    .venv/Scripts/python tools_bench_tuner.py 세트모델.json [깊이]

12조건마다 v7 quick 으로 조정 없이 만든 최고 팀을 각 조정기로 같은 시드에서 조정하고,
조정에 쓰지 않은 시드(챔피언·마스터볼 혼합 스타일)에서 같은 상대·난수로 싸워 판별 차이의 95% 신뢰구간을 낸다.
"""
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

_live = Path(__file__).parent / "data" / "research.sqlite"
_copy = Path(tempfile.gettempdir()) / "vextrum_bench_research.sqlite"
if _live.is_file():
    shutil.copyfile(_live, _copy)
os.environ.setdefault("RESEARCH_DB", str(_copy))

from app import auto_team, collector, parallel, team_model  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.set_tuner import Tuner  # noqa: E402
from tools_bench_builder import RUNS  # noqa: E402

HOLDOUT = {"champion": (200, 5_791_003), "master": (200, 6_802_117)}


def diff(a, b):
    d = [y - x for x, y in zip(a, b)]
    m, se = statistics.mean(d), statistics.pstdev(d) / len(d) ** .5
    verdict = "더 나음" if m - 1.96 * se > 0 else "더 나쁨" if m + 1.96 * se < 0 else "판단 불가"
    return f"{m:+.3f} (95% {m - 1.96 * se:+.3f}~{m + 1.96 * se:+.3f}) {verdict}"


if __name__ == "__main__":
    e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
    model = team_model.load(sys.argv[1])
    depth = sys.argv[2] if len(sys.argv) > 2 else "quick"
    teams = []
    for styles, kw in RUNS:
        r = auto_team.build(e, "Doubles", styles, [], [], depth="quick", tune="off", rankers=False, **kw)
        teams.append([m["set"] for m in r["candidates"][0]["members"]])
    print(f"built {len(teams)} teams", flush=True)
    tuners = {"base": Tuner(e, "Doubles"), "model": Tuner(e, "Doubles", model=model)}
    tuned = {name: [] for name in tuners}
    for name, tuner in tuners.items():
        start, changed, tried = time.perf_counter(), 0, 0
        for team in teams:
            sets, changes, info = tuner.tune(team, depth)
            tuned[name].append(sets)
            changed += bool(changes)
            tried += info["tried"]
        print(f"{name}: {time.perf_counter() - start:.0f}s, teams changed {changed}/{len(teams)}, trials {tried}", flush=True)
    for league, (games, seed) in HOLDOUT.items():
        styles = ["balanced", "aggressive", "defensive", "setup", "pivot"] if league == "master" else None
        flat = teams + tuned["base"] + tuned["model"]
        reports = parallel.compare_teams(e, "Doubles", flat, games, seed, league, cpu_styles=styles)
        outs = [r["outcomes"] for r in reports]
        n = len(teams)
        col = lambda k: [sum(o[g] for o in outs[k * n:(k + 1) * n]) / n for g in range(games)]
        raw, base, mod = col(0), col(1), col(2)
        print(f"[{league} 보류 {games}판] 조정 없음 {statistics.mean(raw):.3f}  기존 조정 {statistics.mean(base):.3f}  "
              f"모델 조정 {statistics.mean(mod):.3f}", flush=True)
        print(f"    기존 조정 vs 없음  {diff(raw, base)}")
        print(f"    모델 조정 vs 없음  {diff(raw, mod)}")
        print(f"    모델 조정 vs 기존  {diff(base, mod)}", flush=True)
