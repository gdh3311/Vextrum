"""미리보기 전략 추정 정확도: 플레이북으로 뽑은 상대 600팀에 대해 추정 분포가 실제 플레이북을 맞히는지."""
import json
import sys
from collections import defaultdict
from random import Random

from app import battle_lab, collector
from app.engine import Engine

TRUE = {"setup": "balance"}  # 랭크업 플레이북은 미리보기에서 균형으로 본다

e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
n = int(sys.argv[1]) if len(sys.argv) > 1 else 700
stats = defaultdict(lambda: [0, 0, 0, 0., 0])  # games, top1, top2, mass, mixkey
for seed in range(n):
    style, roster = battle_lab._draft(e, "Doubles", seed, Random(seed))
    truth = TRUE.get(style, style)
    est = battle_lab.preview_strategy(e, "Doubles", [c.id for c in roster])["scenario"]
    order = list(est)
    row = stats[style]
    row[0] += 1
    row[1] += order[0] == truth
    row[2] += truth in order[:2]
    row[3] += est.get(truth, 0)
    row[4] += battle_lab.preview_key(e, "Doubles", [c.id for c in roster]).startswith("mix:")
for style, (g, t1, t2, mass, mix) in sorted(stats.items()):
    print(f"{style:10s} n={g:3d} top1 {t1/g:5.0%}  top2 {t2/g:5.0%}  p(true) {mass/g:.2f}  mixed-key {mix/g:4.0%}")
