"""Pokémon Champions Battle Data 수집기.

    python -m app.collector            # 새 데이터가 있으면 수집
    python -m app.collector --force    # 캐시 무시하고 재수집

수집 결과:
  data/dataset.json   분석 엔진이 읽는 정규화된 데이터셋
  data/history.sqlite 수집할 때마다 쌓이는 순위 스냅샷 (추세 계산용)

Battle data provided by Pokémon Champions Battle Data (https://championsbattledata.com)
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://championsbattledata.com"
SHOWDOWN_MOVES = "https://play.pokemonshowdown.com/data/moves.json"
POKEAPI_CSV = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv"
POKEAPI_FILES = ["pokemon_species_names", "move_names", "item_names", "ability_names", "nature_names"]
FORMATS = ["Doubles", "Singles"]

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE = DATA_DIR / "cache"
DATASET = DATA_DIR / "dataset.json"
HISTORY_DB = DATA_DIR / "history.sqlite"

UA = {"User-Agent": "ChampionsMetaLab/0.1 (local meta analysis tool)"}
STONE_RE = re.compile(r"ite( [XYZ])?$")
NOT_STONES = {"Eviolite"}

# 폼 이름 한글 표기 (PokeAPI에 없는 조합용)
KO_FORM = {
    "Alolan": "알로라", "Galarian": "가라르", "Hisuian": "히스이", "Paldean": "팔데아",
    "Wash": "워시", "Heat": "히트", "Frost": "프로스트", "Fan": "스핀", "Mow": "커트",
    "Female": "♀", "Male": "♂", "Paldean Aqua Breed": "팔데아 워터종",
    "Paldean Blaze Breed": "팔데아 블레이즈종", "Paldean Combat Breed": "팔데아 컴뱃종",
    "Dusk Form": "황혼", "Midnight Form": "한밤중", "Low Key Form": "로우", "Blade Forme": "블레이드",
    "Shield Forme": "실드", "Hero Form": "마이티", "Zero Form": "나이브", "Eternal": "영원의 꽃",
    "Small Variety": "작은 사이즈", "Large Variety": "큰 사이즈", "Jumbo Variety": "특대 사이즈",
}


def tid(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def fetch(url: str, dest: Path, retries: int = 3) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            dest.write_bytes(data)
            return
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def ko_maps() -> dict[str, dict[str, str]]:
    """PokeAPI CSV에서 영어 이름 -> 한글 이름 표를 만든다 (언어 id 9=en, 3=ko)."""
    out = {}
    for name in POKEAPI_FILES:
        path = CACHE / f"{name}.csv"
        if not path.exists():
            fetch(f"{POKEAPI_CSV}/{name}.csv", path)
        en, ko = {}, {}
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.reader(f):
                if row[1] == "9":
                    en[row[0]] = row[2]
                elif row[1] == "3":
                    ko[row[0]] = row[2]
        out[name] = {tid(v): ko[k] for k, v in en.items() if k in ko}
    return out


def to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def form_stats(f: dict) -> dict:
    return {"hp": f["hp"], "atk": f["attack"], "def": f["defense"],
            "spa": f["sp_attack"], "spd": f["sp_defense"], "spe": f["speed"]}


def split_abilities(f: dict) -> list[str]:
    raw = [a.strip() for a in (f.get("abilities") or "").split("|")]
    if f.get("hidden_ability"):
        raw.append(f["hidden_ability"].strip())
    return [a for i, a in enumerate(raw) if a and a not in raw[:i]]


def parse_usage(rows: list[dict], name_to_id: dict[str, str]) -> dict | None:
    if not rows:
        return None
    u = {"rank": to_int(rows[0].get("column_position")), "moves": [], "items": [], "abilities": [],
         "natures": [], "spreads": [], "teammates": []}
    for r in sorted(rows, key=lambda r: to_int(r.get("rank"))):
        cat, pct = r.get("category"), r.get("percentage_value") or 0
        if cat == "move":
            u["moves"].append({"name": r["name"], "pct": pct})
        elif cat == "held_item":
            u["items"].append({"name": r["name"], "pct": pct})
        elif cat == "ability":
            u["abilities"].append({"name": r["name"], "pct": pct})
        elif cat == "stat_alignment":
            u["natures"].append({"name": r["name"], "pct": pct})
        elif cat == "stat_points":
            u["spreads"].append({"pct": pct, "hp": to_int(r.get("hp_points")), "atk": to_int(r.get("attack_points")),
                                 "def": to_int(r.get("defense_points")), "spa": to_int(r.get("sp_atk_points")),
                                 "spd": to_int(r.get("sp_def_points")), "spe": to_int(r.get("speed_points"))})
        elif cat == "teammate":
            pid = name_to_id.get(r["name"]) or name_to_id.get(tid(r["name"]))
            if pid:
                u["teammates"].append(pid)
    return u


def ko_pokemon_name(base_ko: str | None, form: dict, is_base_form: bool) -> str | None:
    if not base_ko:
        return None
    kind = form.get("form_kind") or "Base"
    if kind.startswith("Mega"):
        return "메가" + base_ko + kind[4:].strip()
    if kind == "Base" or is_base_form and kind not in KO_FORM:
        return base_ko
    return f"{base_ko} ({KO_FORM.get(kind, kind)})"


def collect(force: bool = False) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    index_path = CACHE / "index.json"
    print("인덱스 내려받는 중…")
    fetch(f"{BASE}/api", index_path)
    index = load_json(index_path)
    version = index["dataVersion"]

    if DATASET.exists() and not force:
        if load_json(DATASET).get("dataVersion") == version:
            print(f"이미 최신입니다 (dataVersion {version}).")
            return load_json(DATASET)

    moves_path = CACHE / "moves.json"
    if not moves_path.exists() or force:
        fetch(SHOWDOWN_MOVES, moves_path)
    sd_moves = load_json(moves_path)
    ko = ko_maps()

    # 포켓몬·포맷별 상세 행 (요청 526건, 버전별 캐시)
    battle_dir = CACHE / "battle" / version
    jobs = []
    for p in index["pokemon"]:
        for fmt in FORMATS:
            dest = battle_dir / fmt / f"{p['showdownId']}.json"
            if not dest.exists():
                jobs.append((f"{BASE}/api/battle/{fmt}/{urllib.parse.quote(p['showdownId'])}", dest))
    if jobs:
        print(f"배틀 데이터 {len(jobs)}건 내려받는 중…")
        failed = []

        def run(job):
            try:
                fetch(*job)
            except Exception as e:  # 데이터가 없는 포켓몬은 404
                failed.append((job[0], str(e)))

        with ThreadPoolExecutor(max_workers=6) as ex:
            list(ex.map(run, jobs))
        if failed:
            print(f"  {len(failed)}건 실패 (해당 포맷 데이터 없음으로 처리)")
    for old in (CACHE / "battle").iterdir():
        if old.name != version:
            shutil.rmtree(old, ignore_errors=True)

    name_to_id = {}
    for p in index["pokemon"]:
        for key in (p["name"], p["battleName"], p["showdownName"], p["slug"]):
            name_to_id[key] = p["showdownId"]
            name_to_id[tid(key)] = p["showdownId"]

    pokemon, used_moves, used_items, used_abilities = {}, set(), set(), set()
    for p in index["pokemon"]:
        s = p["summary"]
        forms = s["forms"]
        own = next((f for f in forms if f.get("showdown_name") == p["showdownName"]), None) or s["primary"]
        base_species = own.get("pokemon_name") or p["name"]
        base_ko = ko["pokemon_species_names"].get(tid(base_species))
        is_base_form = own.get("form_kind") in (None, "", "Base")

        # 메가스톤 후보: 전 시즌에서 이 포켓몬이 지닌 적 있는 도구 중 이름이 ~ite 인 것
        stones = set()
        for by_fmt in s.get("battleSummary", {}).values():
            for b in by_fmt.values():
                for it in b.get("values", {}).get("held_item", []):
                    if STONE_RE.search(it) and it not in NOT_STONES:
                        stones.add(it)
        megas = []
        if is_base_form or len([f for f in forms if not (f.get("form_kind") or "").startswith("Mega")]) == 1:
            for f in forms:
                kind = f.get("form_kind") or ""
                if not kind.startswith("Mega"):
                    continue
                suffix = kind[4:].strip()  # "", "X", "Y", "Z"
                stone = next((st for st in sorted(stones)
                              if (st.endswith(" " + suffix) if suffix else not re.search(r" [XYZ]$", st))), None)
                megas.append({"name": f["form_name"], "ko": ko_pokemon_name(base_ko, f, False), "kind": kind,
                              "types": f["types"], "abilities": split_abilities(f), "stats": form_stats(f),
                              "sprite": f["saved_name"], "stone": stone})

        usage = {}
        for fmt in FORMATS:
            path = battle_dir / fmt / f"{p['showdownId']}.json"
            if path.exists():
                u = parse_usage(load_json(path).get("rows", []), name_to_id)
                if u and u["rank"]:
                    usage[fmt] = u
                    used_moves.update(m["name"] for m in u["moves"])
                    used_items.update(i["name"] for i in u["items"])
                    used_abilities.update(a["name"] for a in u["abilities"])

        ranks = {}
        for season, by_fmt in s.get("battleSummary", {}).items():
            ranks[season] = {fmt: b.get("position") for fmt, b in by_fmt.items() if b.get("position")}

        learnset = sorted(set(p.get("learnableMoveNames") or []))
        used_moves.update(learnset)
        abilities = split_abilities(own)
        used_abilities.update(abilities)
        for m in megas:
            used_abilities.update(m["abilities"])
        pokemon[p["showdownId"]] = {
            "id": p["showdownId"], "name": p["name"], "ko": ko_pokemon_name(base_ko, own, is_base_form),
            "slug": p["slug"], "types": own["types"], "abilities": abilities, "stats": form_stats(own),
            "sprite": own["saved_name"], "megas": megas, "learnset": learnset, "ranks": ranks, "usage": usage,
        }

    moves = {}
    for name in sorted(used_moves):
        m = sd_moves.get(tid(name))
        if not m:
            moves[name] = {"type": "Normal", "category": "Status", "power": 0, "accuracy": 100, "priority": 0,
                           "target": "normal", "ko": None, "unknown": True}
            continue
        hits = m.get("multihit")
        moves[name] = {
            "type": m["type"], "category": m["category"], "power": m.get("basePower", 0),
            "accuracy": 100 if m.get("accuracy") is True else m.get("accuracy", 100),
            "priority": m.get("priority", 0), "target": m.get("target", "normal"),
            "hits": (3.1 if hits == [2, 5] else sum(hits) / 2) if isinstance(hits, list) else (hits or 1),
            "flags": [k for k in ("contact", "sound", "punch", "slicing", "bite") if k in m.get("flags", {})],
            "selfdestruct": bool(m.get("selfdestruct")), "recharge": "recharge" in m.get("flags", {}),
            "ko": ko["move_names"].get(tid(name)),
        }

    dataset = {
        "dataVersion": version, "generatedAt": index["generatedAt"], "seasons": index["seasons"],
        "formats": FORMATS, "source": BASE,
        "attribution": "Battle data provided by Pokémon Champions Battle Data",
        "pokemon": pokemon, "moves": moves,
        "items": {n: {"ko": ko["item_names"].get(tid(n))} for n in sorted(used_items)},
        "abilities": {n: {"ko": ko["ability_names"].get(tid(n))} for n in sorted(used_abilities)},
        "natures": {tid(k).capitalize(): v for k, v in ko["nature_names"].items()},
    }
    DATASET.write_text(json.dumps(dataset, ensure_ascii=False), encoding="utf-8")
    save_snapshot(dataset)
    n_usage = {fmt: sum(1 for p in pokemon.values() if fmt in p["usage"]) for fmt in FORMATS}
    print(f"완료: 포켓몬 {len(pokemon)}종, 기술 {len(moves)}개, 도구 {len(dataset['items'])}개, 사용 데이터 {n_usage}")
    return dataset


def save_snapshot(dataset: dict) -> None:
    """오늘 순위를 SQLite에 쌓는다. 며칠 뒤부터 7일/14일 추세를 계산할 수 있다."""
    day = dataset["generatedAt"][:10]
    con = sqlite3.connect(HISTORY_DB)
    con.execute("CREATE TABLE IF NOT EXISTS rank_snapshots (day TEXT, format TEXT, pokemon_id TEXT, rank INTEGER,"
                " PRIMARY KEY (day, format, pokemon_id))")
    rows = [(day, fmt, pid, u["rank"]) for pid, p in dataset["pokemon"].items() for fmt, u in p["usage"].items()]
    con.executemany("INSERT OR REPLACE INTO rank_snapshots VALUES (?,?,?,?)", rows)
    con.commit()
    con.close()


if __name__ == "__main__":
    collect(force="--force" in sys.argv)
