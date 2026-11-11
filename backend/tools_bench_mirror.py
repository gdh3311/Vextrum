"""미러 매치 벤치마크: 양쪽이 같은 4마리(메타 상위권에서 무작위)로 싸워 순수한 판단력만 비교한다.

    .venv/Scripts/python tools_bench_mirror.py [게임 수] [난이도 ...]

내 쪽은 항상 표준(하이퍼볼) 정책. 같은 정책끼리면 약 50%이고, CPU 승률이 50%보다 높을수록 판단이 낫다.
"""
import json
import sys
import time
from random import Random

from app import collector, simulation
from app.engine import Engine

e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
games = int(sys.argv[1]) if len(sys.argv) > 1 else 100
levels = sys.argv[2:] or ["ultra", "champion"]
fmt = "Doubles"
pool = [p["id"] for p in e.ranked(fmt)[:40]]
rng = Random(7)
matches = []
while len(matches) < games:
    ids = rng.sample(pool, 4)
    sets = [e.default_set(i, fmt) for i in ids]
    if sum(bool(s.get("mega")) for s in sets) > 1 or len({s["item"] for s in sets}) < 4:
        continue
    matches.append((sets, rng.randrange(1 << 30)))

for level in levels:
    wins = losses = 0
    start = time.perf_counter()
    for sets, seed in matches:
        b = simulation.Battle(e, fmt, sets, sets, seed, log=False, difficulty=level)
        while not b.winner:
            b.advance()
        wins += b.winner == "loss"
        losses += b.winner == "win"
    dt = time.perf_counter() - start
    print(f"mirror {level:9s} CPU 승률 {100 * wins / games:5.1f}%  (패 {losses}, 무 {games - wins - losses})"
          f"  게임당 {dt / games:.2f}s", flush=True)
