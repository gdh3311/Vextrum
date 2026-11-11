"""시뮬레이터가 실제 메타와 얼마나 맞는지 검사한다.

상위 N마리로 무작위 팀을 만들어 CPU끼리 싸우게 한 뒤, 포켓몬별 승률(시뮬 강도)과
실제 사용률 순위의 스피어만 상관을 본다. 실제 게임과 비슷하게 돌아갈수록 상관이 양수로 커진다.
사용: python tools_validate_meta.py [Doubles|Singles] [games]
"""
import json
import random
import sys
from collections import defaultdict

from app import collector, simulation
from app.engine import Engine


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for k, i in enumerate(order):
            r[i] = k
        return r
    a, b = ranks(xs), ranks(ys)
    n = len(xs)
    return 1 - 6 * sum((p - q) ** 2 for p, q in zip(a, b)) / (n * (n * n - 1))


def main(fmt="Doubles", games=600, top=40, realistic=True):
    e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
    ranked = e.ranked(fmt)[:top]
    pool = [p["id"] for p in ranked]
    rank = {p["id"]: e.rank(p["id"], fmt) for p in ranked}
    wins, plays = defaultdict(float), defaultdict(int)
    size = 4 if fmt == "Doubles" else 3
    def real_team(r, core):
        """실제 팀원 통계(teammates)를 따라 만든 팀 — 무작위 조합보다 실제 대전에 가깝다."""
        team = [core]
        while len(team) < size:
            mega = any(e.default_set(f, fmt)["mega"] for f in team)  # 메가진화는 팀에 하나만
            mates = [m for f in team for m in e.P[f]["usage"].get(fmt, {}).get("teammates", [])[:6]
                     if m in e.P and fmt in e.P[m]["usage"] and m not in team
                     and not (mega and e.default_set(m, fmt)["mega"])]
            team.append(r.choice(mates) if mates else r.choice([
                i for i in pool if i not in team and not (mega and e.default_set(i, fmt)["mega"])]))
        return team

    for seed in range(games):
        r = random.Random(seed)
        if realistic:
            a = real_team(r, r.choice(pool))
            b = real_team(r, r.choice([i for i in pool if i not in a]))
        else:
            picks = r.sample(pool, size * 2)
            a, b = picks[:size], picks[size:]
        battle = simulation.Battle(e, fmt, [e.default_set(i, fmt) for i in a], [e.default_set(i, fmt) for i in b],
                                   seed, log=False)
        while not battle.winner:
            battle.advance()
        score = {"win": 1., "loss": 0., "draw": .5}[battle.winner]
        for i in a:
            wins[i] += score
            plays[i] += 1
        for i in b:
            wins[i] += 1 - score
            plays[i] += 1
    ids = [i for i in pool if plays[i] >= 20]
    rates = [wins[i] / plays[i] for i in ids]
    rho = spearman(rates, [-rank[i] for i in ids])
    print(f"{fmt} ({'real teams' if realistic else 'random teams'}): {games} games, top {top}, spearman(sim win rate, usage) = {rho:+.3f}")
    for i, rate in sorted(zip(ids, rates), key=lambda row: -row[1])[:8]:
        print(f"  {e.P[i]['name']:<22} usage #{rank[i]:<3} sim {100 * rate:.1f}%")
    for i, rate in sorted(zip(ids, rates), key=lambda row: row[1])[:5]:
        print(f"  {e.P[i]['name']:<22} usage #{rank[i]:<3} sim {100 * rate:.1f}%")
    return rho


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Doubles", int(sys.argv[2]) if len(sys.argv) > 2 else 600,
         realistic="random" not in sys.argv)
