"""응답 언어 변환: 서버는 이름을 한국어(`ko`, `moveKo` 등)로 만들고, 요청 헤더 `X-Lang` 이 en/ja 면
응답 JSON 안의 한국어 이름을 그 언어의 이름으로 바꿔 보낸다.

- 바꾸는 대상: 포켓몬(폼·메가 포함), 기술, 도구, 특성, 성격 이름과 정확히 같은 문자열 값.
  문장 안에 섞인 이름은 바꾸지 않는다 (서버 문장 다국어화는 로드맵 5단계).
- 일본어 이름은 PokeAPI CSV(언어 11=ja, 1=ja-Hrkt)에서 만든다.
"""
from __future__ import annotations

import csv
import json
import re

from . import collector

# 한국어 폼 표기 → 일본어 폼 표기 (collector.KO_FORM 의 값 기준)
JA_FORM = {
    "알로라": "アローラ", "가라르": "ガラル", "히스이": "ヒスイ", "팔데아": "パルデア",
    "워시": "ウォッシュ", "히트": "ヒート", "프로스트": "フロスト", "스핀": "スピン", "커트": "カット",
    "암컷": "メス", "수컷": "オス", "팔데아 워터종": "パルデア・ウォーター種",
    "팔데아 블레이즈종": "パルデア・ブレイズ種", "팔데아 컴뱃종": "パルデア・コンバット種",
    "황혼": "たそがれ", "한밤중": "まよなか", "로우": "ロー", "블레이드": "ブレード",
    "실드": "シールド", "마이티": "マイティ", "나이브": "ナイーブ", "영원의 꽃": "えいえんのはな",
    "작은 사이즈": "ちいさいサイズ", "큰 사이즈": "おおきいサイズ", "특대 사이즈": "とくだいサイズ",
}
CSV_FILES = ["pokemon_species_names", "move_names", "item_names", "ability_names", "nature_names"]


def _tid(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _csv_maps() -> dict[str, dict[str, tuple[str | None, str | None]]]:
    """파일별: tid(영문) → (한국어, 일본어)"""
    out = {}
    for name in CSV_FILES:
        path = collector.CACHE / f"{name}.csv"
        if not path.exists():
            collector.fetch(f"{collector.POKEAPI_CSV}/{name}.csv", path)
        en, ko, ja, kana = {}, {}, {}, {}
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.reader(f):
                lang = row[1]
                if lang == "9":
                    en[row[0]] = row[2]
                elif lang == "3":
                    ko[row[0]] = row[2]
                elif lang == "11":
                    ja[row[0]] = row[2]
                elif lang == "1":
                    kana[row[0]] = row[2]
        out[name] = {_tid(v): (ko.get(k), ja.get(k) or kana.get(k)) for k, v in en.items()}
    return out


def build(dataset: dict) -> dict[str, dict[str, str]]:
    """{"en": {한국어: 영어}, "ja": {한국어: 일본어}}"""
    maps = _csv_maps()
    species = maps["pokemon_species_names"]
    en_map, ja_map = {}, {}

    def put(ko, en, ja):
        if ko and en and ko != en:
            en_map.setdefault(ko, en)
        if ko and ja:
            ja_map.setdefault(ko, ja)

    species_by_ko = {ko: ja for ko, ja in species.values() if ko}

    def ja_pokemon(ko: str | None) -> str | None:
        if not ko:
            return None
        if ko in species_by_ko:
            return species_by_ko[ko]
        m = re.match(r"^메가(.+?)([XYZ]?)$", ko)
        if m and m.group(1) in species_by_ko:
            return "メガ" + species_by_ko[m.group(1)] + m.group(2)
        m = re.match(r"^(.+?) \((.+)\)$", ko)
        if m and m.group(1) in species_by_ko:
            form = JA_FORM.get(m.group(2), m.group(2))
            return f"{species_by_ko[m.group(1)]}（{form}）"
        return None

    for p in dataset["pokemon"].values():
        put(p.get("ko"), p["name"], ja_pokemon(p.get("ko")))
        for m in p.get("megas", []):
            put(m.get("ko"), m["name"], ja_pokemon(m.get("ko")))
    for kind, table in (("move_names", dataset["moves"]), ("item_names", dataset["items"]),
                        ("ability_names", dataset["abilities"])):
        for name, v in table.items():
            ko = v.get("ko")
            put(ko, name, (maps[kind].get(_tid(name)) or (None, None))[1])
    for name, ko in dataset.get("natures", {}).items():
        put(ko, name, (maps["nature_names"].get(_tid(name)) or (None, None))[1])
    return {"en": en_map, "ja": ja_map}


def translate(obj, table: dict[str, str]):
    if isinstance(obj, str):
        return table.get(obj, obj)
    if isinstance(obj, list):
        return [translate(x, table) for x in obj]
    if isinstance(obj, dict):
        return {k: translate(v, table) for k, v in obj.items()}
    return obj


def translate_body(body: bytes, table: dict[str, str]) -> bytes:
    data = json.loads(body)
    return json.dumps(translate(data, table), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
