"""CPU 플레이 스타일 벤치마크: 같은 랭크(기본 마스터볼)에서 스타일마다 표준 정책 상대 승률과 행동 경향을 잰다.

    .venv/Scripts/python tools_bench_styles.py [게임 수] [랭크]
"""
import json
import sys
from random import Random

from app import collector, simulation
from app.engine import Engine

if __name__ == "__main__":
    e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    tier = sys.argv[2] if len(sys.argv) > 2 else "master"
    fmt = "Doubles"
    pool = [p["id"] for p in e.ranked(fmt)[:40]]
    rng = Random(11)
    matches = []
    while len(matches) < games:
        sets = [e.default_set(i, fmt) for i in rng.sample(pool, 4)]
        if sum(bool(s.get("mega")) for s in sets) > 1 or len({s["item"] for s in sets}) < 4:
            continue
        matches.append((sets, rng.randrange(1 << 30)))
    for style in simulation.CPU_STYLES:
        score = turns = 0
        for sets, seed in matches:
            b = simulation.Battle(e, fmt, sets, sets, seed, log=False, difficulty=tier, cpu_style=style)
            while not b.winner:
                b.advance()
            score += {"loss": 1, "draw": .5, "win": 0}[b.winner]
            turns += b.turn - 1
        print(f"{simulation.STYLE_LABELS[style]:5s} {100 * score / games:5.1f}%  평균 {turns / games:.1f}턴", flush=True)
