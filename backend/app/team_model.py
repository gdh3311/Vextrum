"""학습된 팀 강도 모델 (v7 후보 점수).

근거: Sahovic, "Algorithmic Pokémon Teambuilding" — 팀 승률을 로지스틱 모델로 본다.
    logit p(팀이 메타 상대에게 이김) = b + Σ θ_종 + Σ α_(종, 종)   (같은 팀의 쌍 시너지)
상대가 무작위 메타 팀이므로(자동 연구의 상대 생성 방식) 상대 항은 상수로 흡수된다.

학습 데이터: 자동 연구 DB(research.sqlite)의 팀별 승패 (팀마다 수십~수백 판).
이항 로지스틱 회귀 + L2 정규화, 희소 특징이라 순수 파이썬 AdaGrad 로 충분하다 (numpy 불필요).

진단(VEXTRUM_V4_DIAGNOSTIC_REPORT.md 4장)에서 사람이 정한 초안 점수와 실제 승률의 순위 상관은 0.067이었다.
이 모델은 그 점수를 대신하거나 보조해 '어떤 후보를 모의전에 올릴지'를 고른다. 결론은 여전히 모의전이 낸다.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from itertools import combinations
from pathlib import Path

MIN_GAMES = 16
MIN_PAIR_TEAMS = 60


def features(species: list[str], pairs: set) -> list[str]:
    names = sorted(set(species))
    out = [f"s:{n}" for n in names]
    out += [f"p:{a}|{b}" for a, b in combinations(names, 2) if (a, b) in pairs]
    return out


def load_rows(db: Path, fmt: str = "Doubles"):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT species, games, wins FROM teams WHERE fmt=? AND games>=?",
                           (fmt, MIN_GAMES)).fetchall()
    finally:
        con.close()
    return [(json.loads(s), g, w) for s, g, w in rows]


def train(rows, *, l2: float = 2e-4, epochs: int = 30, lr: float = .15, seed: int = 7):
    """rows: [(종 목록, 판 수, 승점)] → 모델 dict."""
    counts = {}
    for sp, _, _ in rows:
        for a, b in combinations(sorted(set(sp)), 2):
            counts[(a, b)] = counts.get((a, b), 0) + 1
    pairs = {k for k, n in counts.items() if n >= MIN_PAIR_TEAMS}
    data = [(features(sp, pairs), g, w) for sp, g, w in rows]
    total_g = sum(g for _, g, _ in data)
    base = sum(w for _, _, w in data) / total_g
    weights = {"bias": math.log(base / (1 - base))}
    hist = {}
    rng = random.Random(seed)
    order = list(range(len(data)))
    for _ in range(epochs):
        rng.shuffle(order)
        for i in order:
            feats, g, w = data[i]
            z = weights["bias"] + sum(weights.get(f, 0.) for f in feats)
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            # 이항 로그우도의 기울기 (판 수로 나눠 팀마다 같은 무게): (승점/판 − p)
            grad = w / g - p
            for f in (*feats, "bias"):
                reg = 0. if f == "bias" else l2 * weights.get(f, 0.)
                gr = grad - reg
                hist[f] = hist.get(f, 1e-8) + gr * gr
                weights[f] = weights.get(f, 0.) + lr * gr / math.sqrt(hist[f])
    return {"weights": weights, "pairs": sorted(f"{a}|{b}" for a, b in pairs), "rows": len(rows),
            "games": total_g, "base": base}


class TeamModel:
    def __init__(self, model: dict):
        self.w = model["weights"]
        self.pairs = {tuple(p.split("|")) for p in model["pairs"]}
        self.meta = {k: v for k, v in model.items() if k not in ("weights", "pairs")}

    def logit(self, species: list[str]) -> float:
        return self.w["bias"] + sum(self.w.get(f, 0.) for f in features(species, self.pairs))

    def added(self, group: list[str], new: str) -> float:
        """group 에 new 를 더할 때 로짓이 얼마나 오르는가 (종 강도 + 기존 팀원과의 쌍 시너지)."""
        if new in group:
            return 0.
        gain = self.w.get(f"s:{new}", 0.)
        for other in group:
            a, b = sorted((other, new))
            if (a, b) in self.pairs:
                gain += self.w.get(f"p:{a}|{b}", 0.)
        return gain

    def rate(self, species: list[str]) -> float:
        return 1 / (1 + math.exp(-self.logit(species)))

    def known(self, species: list[str]) -> float:
        """학습 데이터에 있던 종의 비율 (낮으면 예측을 믿기 어렵다)."""
        return sum(f"s:{s}" in self.w for s in species) / max(1, len(species))


MODEL_PATH = Path(__file__).resolve().parent / "team_model.json"
_cached: TeamModel | None = None


def load() -> TeamModel | None:
    """앱에 동봉된 학습 결과. 없으면 None (그때는 기존 점수만 쓴다)."""
    global _cached
    if _cached is None and MODEL_PATH.is_file():
        _cached = TeamModel(json.loads(MODEL_PATH.read_text(encoding="utf-8")))
    return _cached
