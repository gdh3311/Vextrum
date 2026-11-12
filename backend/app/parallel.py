"""여러 팀의 시뮬레이션을 CPU 코어에 나눠 돌린다.

compare_teams 는 팀마다 같은 상대·같은 난수로 싸우므로, 팀 목록을 나눠서 따로 돌려도 결과가 그대로다.
작업 프로세스는 데이터셋 파일에서 엔진을 한 번 읽어 두고 재사용한다 (데이터가 갱신되면 새로 만든다).
"""
import json
import os
from concurrent.futures import ProcessPoolExecutor
from threading import Lock

_pool: ProcessPoolExecutor | None = None
_version = None
_lock = Lock()
_engine = None
WORKERS = max(1, min(8, (os.cpu_count() or 2) - 1))


def _init():
    global _engine
    from . import collector
    from .engine import Engine

    _engine = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))


def _compare(fmt, teams, runs, seed, difficulty):
    from . import battle_lab

    return battle_lab.compare_teams(_engine, fmt, teams, runs, seed, difficulty)


def _rankers(fmt, team, games, seed, difficulty):
    from . import recommend

    return recommend.versus_rankers(_engine, fmt, team, games, seed, difficulty)


def _executor(e):
    global _pool, _version
    version = e.d.get("generatedAt")
    with _lock:
        if _pool is None or version != _version:
            if _pool is not None:
                _pool.shutdown(wait=False, cancel_futures=True)
            _pool = ProcessPoolExecutor(max_workers=WORKERS, initializer=_init)
            _version = version
        return _pool


def _serial(e):
    return WORKERS < 2 or os.environ.get("SIM_PARALLEL") == "0" or _engine is not None


def compare_teams(e, fmt, teams, runs, seed, difficulty="ultra"):
    from . import battle_lab

    if _serial(e) or len(teams) < 2 or len(teams) * runs < 240:
        return battle_lab.compare_teams(e, fmt, teams, runs, seed, difficulty)
    chunks = min(WORKERS, len(teams))
    size = -(-len(teams) // chunks)
    parts = [teams[i:i + size] for i in range(0, len(teams), size)]
    try:
        futures = [_executor(e).submit(_compare, fmt, part, runs, seed, difficulty) for part in parts]
        return [row for future in futures for row in future.result()]
    except Exception:  # 프로세스를 못 쓰는 환경에서는 그냥 순서대로 돌린다.
        return battle_lab.compare_teams(e, fmt, teams, runs, seed, difficulty)


def versus_rankers_many(e, fmt, teams, games, seed, difficulty="ultra"):
    from . import recommend

    if _serial(e) or len(teams) < 2:
        return [recommend.versus_rankers(e, fmt, team, games, seed, difficulty) for team in teams]
    try:
        futures = [_executor(e).submit(_rankers, fmt, team, games, seed, difficulty) for team in teams]
        return [future.result() for future in futures]
    except Exception:
        return [recommend.versus_rankers(e, fmt, team, games, seed, difficulty) for team in teams]
