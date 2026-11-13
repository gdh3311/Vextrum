"""CPU 랭크(몬스터볼~챔피언) 벤치마크 — 명세 6.5.

    .venv/Scripts/python tools_bench_tiers.py [게임 수]

같은 4마리 미러 매치에서 각 랭크 CPU(상대편)가 표준 정책(하이퍼볼, 내 편 자동 플레이)을 상대로 얼마나 이기는지,
무승부(턴 제한)와 평균 턴으로 끝없는 방어·교체가 없는지 본다. 높은 랭크일수록 승률이 높아야 한다.
"""
import json
import math
import sys
import time
from random import Random

from app import collector, simulation
from app.engine import Engine

TIERS = ["poke", "great", "ultra", "master", "champion"]
LABEL = {"poke": "몬스터볼", "great": "슈퍼볼", "ultra": "하이퍼볼", "master": "마스터볼", "champion": "챔피언"}


def wilson(w, n, z=1.96):
    if not n:
        return 0, 0
    p = w / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - s) / d, (c + s) / d


if __name__ == "__main__":
    e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    fmt = "Doubles"
    pool = [p["id"] for p in e.ranked(fmt)[:40]]
    rng = Random(11)
    matches = []
    while len(matches) < games:
        sets = [e.default_set(i, fmt) for i in rng.sample(pool, 4)]
        if sum(bool(s.get("mega")) for s in sets) > 1 or len({s["item"] for s in sets}) < 4:
            continue
        matches.append((sets, rng.randrange(1 << 30)))
    for tier in TIERS:
        wins = losses = draws = turns = 0
        start = time.perf_counter()
        for sets, seed in matches:
            b = simulation.Battle(e, fmt, sets, sets, seed, log=False, difficulty=tier)
            while not b.winner:
                b.advance()
            wins += b.winner == "loss"
            losses += b.winner == "win"
            draws += b.winner == "draw"
            turns += b.turn - 1
        low, high = wilson(wins + .5 * draws, games)
        print(f"{LABEL[tier]:5s} 승률 {100 * (wins + .5 * draws) / games:5.1f}% (95% {100 * low:.0f}~{100 * high:.0f}%)"
              f"  무 {draws}  평균 {turns / games:.1f}턴  판당 {(time.perf_counter() - start) / games:.2f}s", flush=True)
