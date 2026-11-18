"""학습된 팀 강도 모델 (v7 후보 점수).

근거: Sahovic, "Algorithmic Pokémon Teambuilding" — 팀 승률을 로지스틱 모델로 본다.
    logit p(팀이 메타 상대에게 이김) = b + Σ θ_종 + Σ α_(종, 종)   (같은 팀의 쌍 시너지)
                                     + Σ (γ_(종, 도구) + Σ δ_(종, 기술) + ε_(종, 특성))   (세트, 2판)
세트 항은 멤버마다 더해지므로(멤버 사이 상호작용 없음) 한 마리를 더할 때의 증가분을 정확히 셀 수 있다.
세트 특징은 키가 세트의 포켓몬 id(예: garchomp)다. 데이터에 MIN_SET_TEAMS 팀 이상 나온 것만 쓴다.
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
MIN_SET_TEAMS = 60


def set_features(s: dict | None) -> list[str]:
    """한 멤버의 세트 특징: 도구·기술·특성 (포켓몬 id 별)."""
    if not s or not s.get("id"):
        return []
    pid = s["id"]
    out = [f"m:{pid}|{m}" for m in sorted(set(s.get("moves") or ()))]
    if s.get("item"):
        out.append(f"i:{pid}|{s['item']}")
    if s.get("ability"):
        out.append(f"a:{pid}|{s['ability']}")
    return out


def features(species: list[str], pairs: set, sets=None, vocab=None) -> list[str]:
    names = sorted(set(species))
    out = [f"s:{n}" for n in names]
    out += [f"p:{a}|{b}" for a, b in combinations(names, 2) if (a, b) in pairs]
    for s in sets or ():
        out += [f for f in set_features(s) if vocab is None or f in vocab]
    return out


def load_rows(db: Path, fmt: str = "Doubles"):
    """[(종 목록, 세트 목록, 판 수, 승점)]"""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT species, sets, games, wins FROM teams WHERE fmt=? AND games>=?",
                           (fmt, MIN_GAMES)).fetchall()
    finally:
        con.close()
    return [(json.loads(s), json.loads(st or "[]"), g, w) for s, st, g, w in rows]


def _rows4(rows):
    return [r if len(r) == 4 else (r[0], [], r[1], r[2]) for r in rows]


def train(rows, *, l2: float = 2e-4, epochs: int = 30, lr: float = .15, seed: int = 7,
          sets: bool = False, set_l2: float | None = None):
    """rows: [(종 목록, 세트 목록, 판 수, 승점)] (또는 세트 없이 3칸) → 모델 dict.
    sets=True 면 세트 특징(도구·기술·특성)도 쓴다. 기본은 종·쌍만 (동봉 모델, 1.20.0 과 같다).
    세트 모델은 오프라인 예측은 조금 낫지만 보류 전투 벤치에서 유의한 차이가 없어 기본으로 쓰지 않는다
    (docs/TEAM_BUILDER_RESEARCH.md 6장)."""
    rows = _rows4(rows)
    counts, set_counts = {}, {}
    for sp, st, _, _ in rows:
        for a, b in combinations(sorted(set(sp)), 2):
            counts[(a, b)] = counts.get((a, b), 0) + 1
        if sets:
            for f in {f for s in st for f in set_features(s)}:
                set_counts[f] = set_counts.get(f, 0) + 1
    pairs = {k for k, n in counts.items() if n >= MIN_PAIR_TEAMS}
    vocab = {f for f, n in set_counts.items() if n >= MIN_SET_TEAMS}
    data = [(features(sp, pairs, st if sets else None, vocab), g, w) for sp, st, g, w in rows]
    set_l2 = l2 if set_l2 is None else set_l2
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
                reg = 0. if f == "bias" else (set_l2 if f[1] == ":" and f[0] in "mia" else l2) * weights.get(f, 0.)
                gr = grad - reg
                hist[f] = hist.get(f, 1e-8) + gr * gr
                weights[f] = weights.get(f, 0.) + lr * gr / math.sqrt(hist[f])
    return {"weights": weights, "pairs": sorted(f"{a}|{b}" for a, b in pairs), "rows": len(rows),
            "games": total_g, "base": base, "setFeatures": len(vocab)}


class TeamModel:
    def __init__(self, model: dict):
        self.w = model["weights"]
        self.pairs = {tuple(p.split("|")) for p in model["pairs"]}
        self.meta = {k: v for k, v in model.items() if k not in ("weights", "pairs")}

    def logit(self, species: list[str], sets=None) -> float:
        """sets: 멤버 세트 목록 (없으면 종만). 학습에 없던 세트 특징은 0."""
        return self.w["bias"] + sum(self.w.get(f, 0.) for f in features(species, self.pairs, sets))

    def set_gain(self, s: dict | None) -> float:
        return sum(self.w.get(f, 0.) for f in set_features(s))

    def added(self, group: list[str], new: str, new_set: dict | None = None) -> float:
        """group 에 new 를 더할 때 로짓이 얼마나 오르는가 (종 강도 + 기존 팀원과의 쌍 시너지 + 세트)."""
        if new in group:
            return 0.
        gain = self.w.get(f"s:{new}", 0.) + self.set_gain(new_set)
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


_alt: dict = {}


def load(path: str | None = None) -> TeamModel | None:
    """앱에 동봉된 학습 결과. 없으면 None (그때는 기존 점수만 쓴다). path: 벤치용 다른 파일."""
    global _cached
    if path:
        if path not in _alt and Path(path).is_file():
            _alt[path] = TeamModel(json.loads(Path(path).read_text(encoding="utf-8")))
        return _alt.get(path)
    if _cached is None and MODEL_PATH.is_file():
        _cached = TeamModel(json.loads(MODEL_PATH.read_text(encoding="utf-8")))
    return _cached


def main(argv=None):
    """다시 학습: python -m app.team_model [--sets] [--set-l2 X] [--db 경로] [--out 경로]"""
    import argparse
    import time

    from . import collector

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(collector.DATA_DIR / "research.sqlite"))
    ap.add_argument("--sets", action="store_true", help="도구·기술·특성 특징도 학습 (실험)")
    ap.add_argument("--set-l2", type=float, default=None)
    ap.add_argument("--out", default=str(MODEL_PATH))
    args = ap.parse_args(argv)
    rows = load_rows(Path(args.db))
    t = time.perf_counter()
    model = train(rows, sets=args.sets, set_l2=args.set_l2)
    model["trainedAt"] = time.strftime("%Y-%m-%d")
    model["source"] = "research.sqlite (Doubles, games>=16, all versions)"
    model["setL2"] = args.set_l2
    Path(args.out).write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(rows)} teams, {len(model['weights'])} weights ({model['setFeatures']} set), "
          f"{round(time.perf_counter() - t, 1)}s -> {args.out}")


if __name__ == "__main__":
    main()
