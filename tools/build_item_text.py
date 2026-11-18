"""도구 설명 표 (backend/app/item_text.json) 를 만든다.

    backend/.venv/Scripts/python tools/build_item_text.py

PokeAPI CSV(item_flavor_text, item_names)에서 데이터셋의 도구마다 가장 최신 게임의 설명(한국어·영어·일본어)을 고른다.
설명이 없는 새 메가스톤은 메가진화 대상 이름으로 설명을 만든다. 앱 배포판에 함께 들어간다.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import collector  # noqa: E402

LANG = {"9": "en", "3": "ko", "11": "ja", "1": "ja"}
MANUAL = {  # PokeAPI 에 아직 설명이 없는 도구
    "Fairy Feather": {"ko": "지니게 하면 페어리타입 기술의 위력이 올라간다.",
                      "en": "An item to be held by a Pokémon. It boosts the power of Fairy-type moves.",
                      "ja": "持たせると フェアリータイプの 技の 威力が あがる。"},
}


def main():
    cache = collector.CACHE
    for name in ("item_flavor_text", "item_names"):
        if not (cache / f"{name}.csv").exists():
            collector.fetch(f"{collector.POKEAPI_CSV}/{name}.csv", cache / f"{name}.csv")
    ids = {}
    with (cache / "item_names.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if row[1] == "9":
                ids[collector.tid(row[2])] = row[0]
    best = {}  # (item_id, lang) -> (version_group, text)
    with (cache / "item_flavor_text.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader)
        for item_id, vg, lang, text in reader:
            key = LANG.get(lang)
            if not key:
                continue
            vg = int(vg) + (1000 if lang == "11" else 0)  # 일본어는 한자 표기(11)를 가나(1)보다 우선
            if (item_id, key) not in best or vg > best[item_id, key][0]:
                best[item_id, key] = (vg, " ".join(text.split()))
    data = json.loads(collector.DATASET.read_text(encoding="utf-8"))
    mega_of = {}
    for p in data["pokemon"].values():
        for m in p.get("megas", []):
            if m.get("stone"):
                mega_of[m["stone"]] = (p.get("ko") or p["name"], m.get("ko") or m["name"], p["name"], m["name"])
    out, missing = {}, []
    for name in data["items"]:
        item_id = ids.get(collector.tid(name))
        row = {k: best[item_id, k][1] for k in ("ko", "en", "ja") if item_id and (item_id, k) in best}
        row = {**MANUAL.get(name, {}), **row}
        if name in mega_of:
            ko, mega_ko, en, mega_en = mega_of[name]
            row.setdefault("ko", f"{ko}에게 지니게 하면 배틀 중 {mega_ko}(으)로 메가진화할 수 있다.")
            row.setdefault("en", f"Lets {en} Mega Evolve into {mega_en} during battle.")
        if row:
            out[name] = row
        else:
            missing.append(name)
    dest = ROOT / "backend" / "app" / "item_text.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"{len(out)}/{len(data['items'])} items -> {dest}; missing: {missing}")


if __name__ == "__main__":
    main()
