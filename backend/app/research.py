"""자동 연구: 서버가 켜져 있는 동안 계속 팀을 만들고, 바꾸고, 싸워 보며 더 강하고 다양한 팀을 찾는다.

한 세대마다
  1. 후보를 만든다 — 새 초안(무작위 전략·에이스·개성), 잘하는 팀의 변이(멤버 1마리 교체·세트 변경), 서로 다른 팀의 교배,
     아직 판 수가 적은 유망한 팀의 재검증.
  2. 매 세대 새 난수로 만든 메타 상대군과 싸운다 (같은 상대에 맞춰 굳지 않도록).
  3. 결과를 누적한다 — 팀별 승패, 함께 쓴 포켓몬 쌍의 승률(시너지), 포켓몬별 승률.
  4. '틈새'(전략 성격 × 랭커 파티와 겹치는 정도)마다 가장 믿을 만한(하한 신뢰구간이 높은) 팀을 기록한다.

배운 쌍 시너지는 다음 변이의 교체 후보를 고르는 데 쓰이고, 기록된 팀은 팀 자동 구성의 출발점으로 들어간다.
그래서 오래 돌릴수록 결과가 좋아진다. 결과는 backend/data/research.sqlite 에 남아 다시 켜도 이어진다.

v5: 실험 개체는 '팀 + 선출 계획'이다. 같은 6마리라도 선출 계획이 다르면 다른 개체로 따로 기록하고, 잘하는 팀에는
주기적으로 선출 계획을 붙여 본 새 개체를 만든다. 자식(교체·세트 변경)은 부모의 계획을 물려받는다.
"""
import hashlib
import json
import math
import os
import random
import sqlite3
import threading
import time
from pathlib import Path

from . import auto_team, battle_lab, collector, parallel, regulation, roster_search, simulation
from .parties import RANKERS

DB = Path(os.environ["RESEARCH_DB"]) if os.environ.get("RESEARCH_DB") else collector.DATA_DIR / "research.sqlite"
# 세기: (세대당 팀 수, 팀당 판 수, 세대 사이 쉬는 초)
INTENSITY = {"low": (8, 16, 6.), "normal": (14, 24, 1.5), "max": (24, 24, 0.)}
ARCHETYPES = {
    "rain": "비", "sun": "쾌청", "sand": "모래바람", "snow": "눈", "trickroom": "트릭룸", "tailwind": "순풍",
    "psychic": "사이코필드", "setup": "랭크업", "balance": "균형형",
}
BUCKETS = {"unique": "독창적", "balanced": "균형", "meta": "메타 중심"}
ELITES_PER_NICHE = 5
MAX_TEAMS = 4000


def wilson_low(wins, games, z=1.28):
    if not games:
        return 0.
    p = wins / games
    d = 1 + z * z / games
    centre = p + z * z / (2 * games)
    spread = z * math.sqrt(p * (1 - p) / games + z * z / (4 * games * games))
    return (centre - spread) / d


def signature(sets, policy=None):
    rows = sorted(json.dumps({k: s.get(k) for k in ("id", "item", "ability", "nature", "mega")}
                             | {"moves": sorted(s.get("moves") or []),
                                "points": sorted((s.get("points") or {}).items())}, sort_keys=True)
                  for s in sets)
    if policy:  # 계획이 없는 팀은 예전 서명 그대로 (기존 기록과 이어진다)
        rows.append("policy:" + json.dumps(sorted((k, list(v)) for k, v in policy.items())))
    return hashlib.sha1("|".join(rows).encode()).hexdigest()[:16]


class Context:
    """한 데이터 버전·형식에 대한 준비물 (후보 풀, 메타 상대, 랭커 파티 종 집합)."""

    def __init__(self, e, fmt):
        self.e, self.fmt = e, fmt
        self.meta, pool = auto_team._pool(e, fmt)
        jokers = auto_team._joker_candidates(e, fmt, self.meta)
        seen, self.pool = set(), []
        for c in (*pool, *jokers):
            key = (c.id, c.set.get("item"), c.set.get("ability"), tuple(c.set.get("moves") or []))
            if key not in seen:
                seen.add(key)
                self.pool.append(c)
        w = [auto_team.weight(e.rank(f["id"], fmt) or 250) for f in self.meta]
        self.weights = [x / sum(w) for x in w]
        self.rankers = [frozenset(auto_team.species(e, p) for p in r["ids"] if p in e.P)
                        for r in RANKERS if r["format"] == fmt]
        self.pairs = auto_team.ranker_pairs(e, fmt)
        self.styles = [s for s in auto_team.DISCOVERY_STYLES + ("sand", "snow", "psychic", "setup")
                       if fmt == "Doubles" or not auto_team.STYLES[s].doubles_only]

    def candidate(self, s):
        return auto_team._candidate(self.e, self.fmt, self.meta, s)

    def overlap(self, roster):
        names = {c.species for c in roster}
        return max((len(names & t) for t in self.rankers), default=0)

    def niche(self, roster):
        features = set().union(*(c.features for c in roster))
        weather = ("rain", "sun", "sand", "snow")
        archetype = next((w for w in weather if {f"{w}_set", f"{w}_core"} <= features), None)
        if not archetype:
            if "trickroom" in features and sum("slow_attacker" in c.features for c in roster) >= 2:
                archetype = "trickroom"
            elif "tailwind" in features:
                archetype = "tailwind"
            elif "psychic_set" in features:
                archetype = "psychic"
            elif sum("setup_attacker" in c.features for c in roster) >= 2:
                archetype = "setup"
            else:
                archetype = "balance"
        n = self.overlap(roster)
        bucket = "meta" if n >= 4 else "balanced" if n == 3 else "unique"
        return archetype, bucket

    def valid(self, roster):
        megas = sum(bool(c.resolved["mega"]) for c in roster)
        return (len(roster) == 6 and megas <= 2
                and all(auto_team._eligible(c, roster[:i]) and not simulation.unsupported(self.e, self.fmt, c.set)
                        for i, c in enumerate(roster)))


class Lab:
    def __init__(self):
        self.lock = threading.Lock()
        self.db_lock = threading.Lock()
        self.thread = None
        self.running = False
        self.busy = 0  # 사용자의 팀 구성 작업이 돌고 있으면 잠시 쉰다
        self.activity = ""
        self.generation = 0
        self.session_battles = 0
        self.started = None
        self.error = None
        self.engine_getter = None
        self.contexts = {}
        self.planned = set()
        self.rng = random.Random()
        self._db = None

    # ---------- 저장소
    def db(self):
        if self._db is None:
            DB.parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(DB, check_same_thread=False, timeout=30)  # 다른 프로세스(앱 백엔드)가 쓰는 중이면 기다린다
            con.executescript("""
                CREATE TABLE IF NOT EXISTS teams (
                    sig TEXT, fmt TEXT, version TEXT, sets TEXT, species TEXT, archetype TEXT, bucket TEXT,
                    overlap INTEGER, origin TEXT, parent TEXT, games INTEGER DEFAULT 0, wins REAL DEFAULT 0,
                    report TEXT, created REAL, updated REAL, PRIMARY KEY (sig, fmt, version));
                CREATE TABLE IF NOT EXISTS pairs (
                    fmt TEXT, version TEXT, a TEXT, b TEXT, games INTEGER, wins REAL, PRIMARY KEY (fmt, version, a, b));
                CREATE TABLE IF NOT EXISTS species (
                    fmt TEXT, version TEXT, id TEXT, games INTEGER, wins REAL, PRIMARY KEY (fmt, version, id));
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL, fmt TEXT, kind TEXT, text TEXT, sig TEXT);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS holdouts (
                    sig TEXT, fmt TEXT, version TEXT, result TEXT, PRIMARY KEY (sig, fmt, version));
            """)
            # WAL: 쓰는 중에도 다른 프로세스가 읽을 수 있다 (벤치·테스트·앱 백엔드가 같은 파일을 쓴다)
            con.execute("PRAGMA journal_mode=WAL")
            columns = {row[1] for row in con.execute("PRAGMA table_info(teams)")}
            if "policy" not in columns:
                con.execute("ALTER TABLE teams ADD COLUMN policy TEXT")
            self._db = con
        return self._db

    def setting(self, key, default=None):
        with self.db_lock:
            row = self.db().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db_lock:
            self.db().execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))
            self.db().commit()

    # ---------- 실행 제어
    def start(self, engine_getter=None):
        if engine_getter:
            self.engine_getter = engine_getter
        with self.lock:
            if self.running:
                return
            self.running = True
            self.started = time.time()
            self.set_setting("enabled", True)
            self.thread = threading.Thread(target=self._loop, daemon=True, name="auto-research")
            self.thread.start()

    def stop(self):
        self.running = False
        self.set_setting("enabled", False)

    def _loop(self):
        time.sleep(3)  # 서버가 먼저 응답할 수 있게 잠깐 기다린다
        while self.running:
            if self.busy:
                self.activity = "팀 자동 구성이 끝날 때까지 잠시 쉬는 중"
                time.sleep(1)
                continue
            try:
                e = self.engine_getter()
                fmt = "Singles" if self.rng.random() < .25 else "Doubles"
                self.step(e, fmt)
                self.error = None
            except Exception as error:  # noqa: BLE001 - 연구가 멈추지 않게 기록만 하고 계속한다
                import traceback

                traceback.print_exc()
                self.error = str(error)
                time.sleep(5)
            time.sleep(INTENSITY[self.intensity()][2])
        self.activity = "멈춤"

    def intensity(self):
        value = self.setting("intensity", "low")
        return value if value in INTENSITY else "normal"

    def context(self, e, fmt):
        key = (regulation.version_key(e.d), fmt)
        if key not in self.contexts:
            self.contexts = {k: v for k, v in self.contexts.items() if k[0] == key[0]}
            self.contexts[key] = Context(e, fmt)
        return self.contexts[key]

    # ---------- 한 세대
    def step(self, e, fmt):
        ctx = self.context(e, fmt)
        version = regulation.version_key(e.d)
        count, games, _ = INTENSITY[self.intensity()]
        rng = self.rng
        self.generation += 1
        rows = self.rows(fmt, version)
        elites = self.elites(rows)
        batch = []  # (roster, origin, parent)
        # 1) 유망하지만 판 수가 적은 팀은 다시 싸워 신뢰도를 높인다.
        promising = sorted((r for r in rows if r["games"] < 200),
                           key=lambda r: -(r["wins"] + 2) / (r["games"] + 4))[:max(1, count // 4)]
        for r in promising:
            batch.append(([ctx.candidate(s) for s in r["sets"]], "retest", r["sig"], r["policy"]))
        parents = [r for rows_ in elites.values() for r in rows_] or rows[:20]
        attempts = 0
        while len(batch) < count and attempts < count * 6:
            attempts += 1
            roll = rng.random()
            parent = rng.choice(parents) if parents else None
            if parent is None or roll < .22:
                roster, origin = self.fresh(ctx), "draft"
            elif roll < .62:
                roster, origin = self.swap(ctx, parent, fmt, version), "swap"
            elif roll < .82:
                roster, origin = self.retune(ctx, parent["sets"]), "sets"
            else:
                other = rng.choice(parents)
                roster, origin = self.cross(ctx, parent, other, fmt, version), "cross"
            if roster and ctx.valid(roster):
                ids = {c.id for c in roster}
                inherited = {key: pick for key, pick in ((parent or {}).get("policy") or {}).items()
                             if len(pick) == len(set(pick)) == battle_lab.limit(fmt) and set(pick) <= ids}
                batch.append((roster, origin, parent["sig"] if parent else None, inherited or None))
        # 선출 계획 붙이기: 계획 없는 상위 엘리트 하나에 간이 선출 최적화를 돌려 '팀 + 계획' 새 개체를 만든다.
        if self.generation % 3 == 0:
            bare = next((r for group in elites.values() for r in group
                         if not r["policy"] and r["sig"] not in self.planned), None)
            if bare:
                from . import policy as pick_policy

                self.planned.add(bare["sig"])
                sets = bare["sets"]
                report = parallel.compare_teams(e, fmt, [sets], 16, rng.randrange(1 << 30), "ultra",
                                                cpu_styles=auto_team.SELECT_STYLES)[0]
                plan = pick_policy.quick(e, fmt, sets, report, seed=rng.randrange(1 << 30))
                if plan:
                    batch.append(([ctx.candidate(x) for x in sets], "policy", bare["sig"],
                                  {k: list(v) for k, v in plan.items()}))
        if not batch:
            return
        archetypes = [ARCHETYPES[ctx.niche(r)[0]] for r, _, _, _ in batch]
        self.activity = (f"{'더블' if fmt == 'Doubles' else '싱글'} · {self.generation}세대 · "
                         f"{len(batch)}팀 × {games}판 ({', '.join(dict.fromkeys(archetypes))})")
        seed = rng.randrange(1 << 30)
        reports = parallel.compare_teams(e, fmt, [[c.set for c in r] for r, _, _, _ in batch], games, seed, "ultra",
                                         policies=[pol for _, _, _, pol in batch],
                                         cpu_styles=auto_team.SELECT_STYLES)
        self.session_battles += len(batch) * games
        self.record(ctx, fmt, version, batch, reports)
        if self.generation % 4 == 0:
            self.evaluate_holdout(e, fmt, version)

    def evaluate_holdout(self, e, fmt, version):
        with self.db_lock:
            tested = {r[0] for r in self.db().execute("SELECT sig FROM holdouts WHERE fmt=? AND version=?", (fmt, version))}
        top = next((r for r in self.rows(fmt, version)[:12] if r["games"] >= 40 and r["sig"] not in tested), None)
        if top is None:
            return
        report = parallel.compare_teams(e, fmt, [top["sets"]], 18, 20_915_003, "master",
                                        policies=[top["policy"]], cpu_styles=(*auto_team.SELECT_STYLES, "counter"),
                                        split="holdout")[0]
        result = json.dumps(battle_lab.holdout_summary(report), ensure_ascii=False)
        with self.db_lock:
            with self.db() as db:
                db.execute("INSERT OR IGNORE INTO holdouts VALUES (?, ?, ?, ?)", (top["sig"], fmt, version, result))
        self.session_battles += report["runs"]

    def rows(self, fmt, version):
        with self.db_lock:
            cur = self.db().execute(
                "SELECT sig, sets, species, archetype, bucket, overlap, origin, games, wins, report, policy "
                "FROM teams WHERE fmt=? AND version=?", (fmt, version))
            out = [{"sig": a, "sets": json.loads(b), "species": json.loads(c), "archetype": d, "bucket": f,
                    "overlap": g, "origin": h, "games": i, "wins": j, "report": json.loads(k) if k else None,
                    "policy": json.loads(pol) if pol else None}
                   for a, b, c, d, f, g, h, i, j, k, pol in cur.fetchall()]
        for r in out:
            r["low"] = wilson_low(r["wins"], r["games"])
        out.sort(key=lambda r: -r["low"])
        return out

    @staticmethod
    def elites(rows, minimum=40):
        niches = {}
        for r in rows:
            if r["games"] >= minimum:
                group = niches.setdefault((r["archetype"], r["bucket"]), [])
                if len(group) < ELITES_PER_NICHE:
                    group.append(r)
        return niches

    # ---------- 후보 만들기
    def fresh(self, ctx):
        """무작위 전략·에이스·개성으로 새 초안."""
        rng = self.rng
        style = rng.choice(ctx.styles)
        group = (style,)
        weather = style if style in auto_team.WEATHER_STYLES else None
        conflicting = {f"{w}_set" for w in auto_team.WEATHER_STYLES - {weather}} if weather else set()
        available = tuple(c for c in ctx.pool if not c.features & conflicting)
        keys = {f for f, _ in auto_team.STYLES[style].requirements}
        aces = [c for c in available if c.features & keys]
        aces.sort(key=lambda c: -sum(w * m for w, m in zip(ctx.weights, c.matchups)))
        if not aces:
            return None
        ace = rng.choice(aces[:40])
        extra = auto_team.Extra(pairs=ctx.pairs, popularity=rng.uniform(-1.2, 1.5), ranker_teams=tuple(ctx.rankers),
                                overlap=rng.choice([0., 4., 8., 12.]), core=rng.choice(["", "", "fwg", "dsf", "resist"]))
        rows = auto_team._draft(available, [], [[ace]], group, ctx.weights, limit=5, extra=extra)
        return list(rng.choice(rows[:3])) if rows else None

    def synergy(self, fmt, version):
        with self.db_lock:
            pairs = {(a, b): (g, w) for a, b, g, w in self.db().execute(
                "SELECT a, b, games, wins FROM pairs WHERE fmt=? AND version=?", (fmt, version))}
            singles = {i: (g, w) for i, g, w in self.db().execute(
                "SELECT id, games, wins FROM species WHERE fmt=? AND version=?", (fmt, version))}
        return pairs, singles

    def addition(self, ctx, others, fmt, version):
        """팀에 넣을 한 마리. 배운 쌍 시너지와 포켓몬 승률로 점수를 매기고, 상위권에서 무작위로 고른다."""
        rng = self.rng
        pairs, singles = self.synergy(fmt, version)
        names = {c.species for c in others}

        def rate(table, key, prior=.55, strength=20):
            g, w = table.get(key, (0, 0))
            return (w + prior * strength) / (g + strength)

        scored = []
        for c in ctx.pool:
            if c.species in names or not auto_team._eligible(c, others):
                continue
            value = rate(singles, c.species) + sum(
                rate(pairs, tuple(sorted((c.species, m.species)))) - .55 for m in others) / max(1, len(others))
            scored.append((value + rng.gauss(0, .03), c))
        if not scored:
            return None
        scored.sort(key=lambda row: -row[0])
        return rng.choice(scored[:12])[1]

    def swap(self, ctx, parent, fmt, version):
        """패배한 상대에 대응할 멤버를 우선 시험한다."""
        roster = tuple(ctx.candidate(s) for s in parent["sets"])
        report = parent["report"] or {}
        if report.get("strategies") and report.get("runs"):
            group = (parent["archetype"],)
            branch = roster_search.Branch(group, roster, report)
            extra = auto_team.Extra(pairs=ctx.pairs)
            _, proposals = roster_search._proposals(
                ctx.e, fmt, branch, ctx.pool, set(), ctx.valid, ctx.weights, extra, 4, set())
            if proposals:
                return list(self.rng.choice(proposals))
        slot = self.rng.randrange(6)
        others = roster[:slot] + roster[slot + 1:]
        pick = self.addition(ctx, others, fmt, version)
        return [*others[:slot], pick, *others[slot:]] if pick else None

    def retune(self, ctx, sets):
        from .set_tuner import Tuner

        tuner = self.__dict__.setdefault("_tuners", {}).get(ctx.fmt) or Tuner(ctx.e, ctx.fmt)
        self._tuners[ctx.fmt] = tuner
        trials = tuner.candidates([dict(s) for s in sets], per_member=4)
        if not trials:
            return None
        i, v = self.rng.choice(trials)
        return [ctx.candidate(v.set if j == i else s) for j, s in enumerate(sets)]

    def cross(self, ctx, a, b, fmt, version):
        """두 팀에서 3마리씩 (부족하면 시너지로 채운다)."""
        rng = self.rng
        left = rng.sample(a["sets"], 3)
        roster = [ctx.candidate(s) for s in left]
        for s in rng.sample(b["sets"], 6):
            if len(roster) == 6:
                break
            c = ctx.candidate(s)
            if c.species not in {m.species for m in roster} and auto_team._eligible(c, roster):
                roster.append(c)
        while len(roster) < 6:
            pick = self.addition(ctx, roster, fmt, version)
            if not pick:
                return None
            roster.append(pick)
        return roster

    # ---------- 기록
    def record(self, ctx, fmt, version, batch, reports):
        e = ctx.e
        now = time.time()
        before = {k: v[0]["sig"] for k, v in self.elites(self.rows(fmt, version), 72).items()}
        with self.db_lock:
            con = self.db()
            try:
                self._write(ctx, con, fmt, version, batch, reports, now)
            except Exception:
                # 중간에 실패한 쓰기를 열어 두면 파일 전체가 잠긴다 → 반드시 되돌린다
                con.rollback()
                raise
        self._after_record(e, fmt, version, before)

    def _write(self, ctx, con, fmt, version, batch, reports, now):
        if True:
            for (roster, origin, parent, plan), report in zip(batch, reports):
                sets = [c.set for c in roster]
                sig = signature(sets, plan)
                wins = report["win"] + .5 * report["draw"]
                archetype, bucket = ctx.niche(roster)
                worst = min(report["strategies"], key=lambda r: (r["win"] + .5 * r["draw"]) / max(1, r["runs"]),
                            default=None)
                summary = json.dumps({
                    "strategies": [{k: r[k] for k in ("style", "label", "win", "loss", "draw", "runs", "picks", "lossFoes")}
                                   for r in report["strategies"]],
                    "lead": report.get("lead"),
                    "runs": report["runs"],
                    "memberStats": [{"id": row["id"], "picked": row["picked"]} for row in report["memberStats"]],
                    "difficulty": report["difficulty"],
                    "strategyEvidence": report.get("strategyEvidence", {}),
                    "worst": worst["style"] if worst else None,
                }, ensure_ascii=False)
                row = con.execute("SELECT games, wins FROM teams WHERE sig=? AND fmt=? AND version=?",
                                  (sig, fmt, version)).fetchone()
                if row:
                    con.execute("UPDATE teams SET games=games+?, wins=wins+?, report=?, updated=? "
                                "WHERE sig=? AND fmt=? AND version=?",
                                (report["runs"], wins, summary, now, sig, fmt, version))
                else:
                    con.execute("INSERT INTO teams (sig, fmt, version, sets, species, archetype, bucket, overlap, "
                                "origin, parent, games, wins, report, created, updated, policy) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (sig, fmt, version, json.dumps(sets, ensure_ascii=False),
                                 json.dumps(sorted(c.species for c in roster)), archetype, bucket, ctx.overlap(roster),
                                 origin, parent, report["runs"], wins, summary, now, now,
                                 json.dumps(plan) if plan else None))
                names = sorted({c.species for c in roster})
                for i, a in enumerate(names):
                    con.execute("INSERT INTO species VALUES (?,?,?,?,?) ON CONFLICT(fmt, version, id) DO UPDATE "
                                "SET games=games+excluded.games, wins=wins+excluded.wins",
                                (fmt, version, a, report["runs"], wins))
                    for b in names[i + 1:]:
                        con.execute("INSERT INTO pairs VALUES (?,?,?,?,?,?) ON CONFLICT(fmt, version, a, b) DO UPDATE "
                                    "SET games=games+excluded.games, wins=wins+excluded.wins",
                                    (fmt, version, a, b, report["runs"], wins))
            con.commit()

    def _after_record(self, e, fmt, version, before):
        after = self.elites(self.rows(fmt, version), 72)
        for niche, group in after.items():
            best = group[0]
            if before.get(niche) != best["sig"]:
                names = ", ".join(e.P[s["id"]]["ko"] or e.P[s["id"]]["name"] for s in best["sets"][:3])
                self.event(fmt, "elite",
                           f"{ARCHETYPES[niche[0]]} · {BUCKETS[niche[1]]} 새 1위 — {names} 외 · "
                           f"{100 * best['wins'] / best['games']:.0f}% ({best['games']}판)", best["sig"])
        self.prune(fmt, version)

    def event(self, fmt, kind, text, sig=None):
        with self.db_lock:
            self.db().execute("INSERT INTO events (t, fmt, kind, text, sig) VALUES (?,?,?,?,?)",
                              (time.time(), fmt, kind, text, sig))
            self.db().commit()

    def prune(self, fmt, version):
        with self.db_lock:
            n = self.db().execute("SELECT COUNT(*) FROM teams WHERE fmt=? AND version=?", (fmt, version)).fetchone()[0]
        if n <= MAX_TEAMS:
            return
        rows = self.rows(fmt, version)
        keep = {r["sig"] for group in self.elites(rows, 0).values() for r in group}
        drop = [r["sig"] for r in reversed(rows) if r["sig"] not in keep and r["games"] >= 32][:n - MAX_TEAMS]
        with self.db_lock:
            self.db().executemany("DELETE FROM teams WHERE sig=? AND fmt=? AND version=?",
                                  [(sig, fmt, version) for sig in drop])
            self.db().commit()

    # ---------- 바깥에서 쓰는 조회
    def status(self, e, fmt):
        version = regulation.version_key(e.d)
        rows = self.rows(fmt, version)
        with self.db_lock:
            events = [{"t": t, "text": text, "kind": kind} for t, text, kind in self.db().execute(
                "SELECT t, text, kind FROM events WHERE fmt=? ORDER BY id DESC LIMIT 12", (fmt,))]
        total = sum(r["games"] for r in rows)
        return {"running": self.running, "busy": bool(self.busy), "activity": self.activity, "error": self.error,
                "intensity": self.intensity(), "generation": self.generation,
                "sessionBattles": self.session_battles, "uptime": round(time.time() - self.started) if self.started and self.running else 0,
                "teams": len(rows), "battles": total, "niches": len(self.elites(rows)), "events": events}

    def team_view(self, e, fmt, r):
        from .guide import team_guide
        from .parties import _member

        members = [_member(e, s, fmt) for s in r["sets"]]
        guide = team_guide(e, r["sets"], fmt, report=r["report"])
        lead = guide["lead"]["lead"]
        label = ARCHETYPES[r["archetype"]]
        report = r["report"] or {"runs": 0}
        execution = [auto_team.strategy_status(report, key) for key in report.get("strategyEvidence", {})]
        return {"id": r["sig"], "format": fmt, "complete": True,
                "name": " + ".join(m["ko"] or m["name"] for m in lead),
                "archetype": r["archetype"], "archetypeLabel": ARCHETYPES[r["archetype"]],
                "bucket": r["bucket"], "bucketLabel": BUCKETS[r["bucket"]], "overlap": r["overlap"],
                "how": r["origin"], "games": r["games"], "wins": round(r["wins"], 1), "warnings": [],
                "origin": {"label": f"{label} 구성 · {BUCKETS[r['bucket']]}",
                           "detail": f"승률 {100 * r['wins'] / max(1, r['games']):.0f}% · {r['games']}판 · "
                                     f"랭커 파티와 {r['overlap']}마리 겹침"},
                "rate": round(r["wins"] / r["games"], 3) if r["games"] else 0, "low": round(r["low"], 3),
                "members": members, "report": r["report"], "guide": guide,
                "rulesCoverage": simulation.rules_report(e, fmt, r["sets"]),
                "operation": {"execution": execution, "unconfirmed": [], "basis": "latest"}}

    def leaderboard(self, e, fmt, bucket=None, archetype=None, limit=24, minimum=40):
        version = regulation.version_key(e.d)
        with self.db_lock:
            holdouts = dict(self.db().execute("SELECT sig, result FROM holdouts WHERE fmt=? AND version=?", (fmt, version)))
        rows = [r for r in self.rows(fmt, version) if r["games"] >= minimum
                and (not bucket or r["bucket"] == bucket) and (not archetype or r["archetype"] == archetype)]
        out, seen = [], set()
        for r in rows:  # 같은 6마리(세트만 다름)는 가장 좋은 하나만
            key = tuple(r["species"])
            if key in seen:
                continue
            seen.add(key)
            view = self.team_view(e, fmt, r)
            if r["sig"] in holdouts:
                view["holdout"] = json.loads(holdouts[r["sig"]])
                sample = view["holdout"]
                view["operation"] = {"execution": [auto_team.strategy_status(sample, key)
                                                   for key in sample.get("strategyEvidence", {})],
                                     "unconfirmed": [], "basis": "holdout"}
            out.append(view)
            if len(out) == limit:
                break
        return out

    def insights(self, e, fmt, limit=10):
        version = regulation.version_key(e.d)
        pairs, singles = self.synergy(fmt, version)

        def rate(g, w):
            return w / g if g else 0

        def name(pid):
            p = e.P.get(pid) or next((x for x in e.P.values() if auto_team.species(e, x["id"]) == pid), None)
            return {"id": pid, "name": (p.get("ko") or p["name"]) if p else pid, "sprite": p["sprite"] if p else ""}

        rows = []
        for (a, b), (g, w) in pairs.items():
            if g < 150 or a not in singles or b not in singles:
                continue
            expected = (rate(*singles[a]) + rate(*singles[b])) / 2
            rows.append({"a": name(a), "b": name(b), "games": g, "rate": round(rate(g, w), 3),
                         "lift": round(rate(g, w) - expected, 3)})
        rows.sort(key=lambda r: -r["lift"])
        top_species = sorted(((pid, g, w) for pid, (g, w) in singles.items() if g >= 300),
                             key=lambda row: -rate(row[1], row[2]))[:limit]
        return {"pairs": rows[:limit],
                "species": [{**name(pid), "games": g, "rate": round(rate(g, w), 3)} for pid, g, w in top_species]}

    def seeds(self, e, fmt, valid, limit=10, minimum=48, originality=None, with_policy=False):
        """팀 자동 구성의 출발점: 조건(valid)을 만족하는 연구 기록 상위 팀.

        originality (v5): 팀 개성 설정마다 그 겹침 구간(메타 중심 / 균형 / 독창적) 팀을 먼저 고른다.
        설정이 달라도 같은 시드가 들어가 결과가 비슷해지는 문제를 줄인다. 나머지 자리는 전체 상위 팀이 채운다."""
        ctx = self.context(e, fmt)
        out, seen = [], set()
        rows = self.rows(fmt, regulation.version_key(e.d))
        if originality in BUCKETS:
            # 절반은 그 설정의 구간에서 먼저, 나머지는 구간과 상관없이 가장 믿을 만한 팀으로 (벤치: 완전히 거르면 약해짐)
            # 독창적 설정만 그 구간 팀으로 한정한다 (벤치: 종 다양성 +6, 대신 보류 승률 약 -2%p — 사용자가 고른 교환).
            own = [r for r in rows if r["bucket"] == originality]
            if originality == "unique":
                rows = own
            else:
                own = own[:max(1, limit // 2)]
                taken = {r["sig"] for r in own}
                rows = own + [r for r in rows if r["sig"] not in taken]
        for r in rows:
            if r["games"] < minimum or tuple(r["species"]) in seen:
                continue
            try:
                roster = tuple(ctx.candidate(s) for s in r["sets"])
            except Exception:  # noqa: BLE001 - 데이터가 바뀌어 못 쓰는 세트는 건너뛴다
                continue
            if valid(roster):
                seen.add(tuple(r["species"]))
                out.append((r["archetype"], roster, r["policy"]) if with_policy else (r["archetype"], roster))
            if len(out) == limit:
                break
        return out


LAB = Lab()
