"""CPU 난이도 벤치마크: 같은 매치업(시드)에서 상대 CPU 난이도만 바꿔 승률과 속도를 잰다.

    .venv/Scripts/python tools_bench_cpu.py [게임 수] [난이도 ...]

내 쪽은 항상 표준(하이퍼볼) 정책이므로, CPU 승률이 높을수록 CPU가 강하다.
"""
import json
import sys
import time

from app import battle_lab, collector
from app.engine import Engine

e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
games = int(sys.argv[1]) if len(sys.argv) > 1 else 40
levels = sys.argv[2:] or ["ultra", "master", "champion"]
for fmt in ("Doubles",):
    team = [{"id": p["id"]} for p in e.ranked(fmt)[:6]]
    seeds = list(battle_lab._match_seeds(e, fmt, games, 20261111))
    for level in levels:
        wins = draws = 0
        start = time.perf_counter()
        for s in seeds:
            match = battle_lab.matchup(e, fmt, team, s)
            b = battle_lab._play(e, fmt, team, match, level)
            wins += b.winner == "loss"  # 내 쪽 패배 = CPU 승리
            draws += b.winner == "draw"
        dt = time.perf_counter() - start
        print(f"{fmt} {level:9s} CPU 승률 {100 * wins / games:5.1f}%  무 {draws}  게임당 {dt / games:.2f}s", flush=True)
