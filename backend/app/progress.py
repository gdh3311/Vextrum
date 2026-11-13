"""긴 계산(팀 자동 구성)의 진행 상황.

단계, 단계 안 진행률, 지금까지 치른 모의전 수, 지금 살펴보는 포켓몬(스포트라이트)과 실제 데이터로 만든 짧은 메모를
기록한다. 앱은 이 값을 주기적으로 받아 로딩 애니메이션과 문구를 만든다.
"""
import time
from threading import Lock

# (단계, 화면 이름, 비중)
STAGES = [
    ("research", "랭커 파티 연구", .03),
    ("draft", "초안 짜기", .07),
    ("screen", "1차 모의전", .18),
    ("refine", "멤버 교체 실험", .23),
    ("tune", "세트 최적화", .22),
    ("final", "최종 검증", .12),
    ("rankers", "랭커 파티와 연습 경기", .12),
    ("report", "결과 정리", .03),
]


class Progress:
    def __init__(self, e, callback=None, skip=()):
        self.e = e
        self.callback = callback
        self.lock = Lock()
        self.start = time.time()
        self.stages = [s for s in STAGES if s[0] not in skip]
        self.state = {"stage": self.stages[0][0], "stageIndex": 0, "done": 0, "total": 0, "battles": 0,
                      "spotlight": [], "notes": [], "fraction": 0.}

    def mon(self, pid):
        p = self.e.P.get(pid)
        return {"id": pid, "name": (p.get("ko") or p["name"]) if p else pid, "sprite": p["sprite"] if p else ""}

    def update(self, stage=None, *, done=None, total=None, spotlight=None, notes=None, battles=0):
        if not self.callback:
            return
        with self.lock:
            s = self.state
            if stage and stage != s["stage"]:
                s.update(stage=stage, done=0, total=0)
            if done is not None:
                s["done"] = done
            if total is not None:
                s["total"] = total
            if spotlight is not None:
                s["spotlight"] = [self.mon(pid) for pid in spotlight][:6]
            if notes is not None:
                s["notes"] = [n for n in notes if n][:8]
            s["battles"] += battles
            keys = [k for k, _, _ in self.stages]
            index = keys.index(s["stage"]) if s["stage"] in keys else 0
            weights = [w for _, _, w in self.stages]
            part = min(1., s["done"] / s["total"]) if s["total"] else 0.
            s["stageIndex"] = index
            s["fraction"] = round((sum(weights[:index]) + weights[index] * part) / sum(weights), 3)
            snapshot = {**s, "elapsed": round(time.time() - self.start, 1),
                        "stages": [{"key": k, "label": label} for k, label, _ in self.stages]}
        self.callback(snapshot)
