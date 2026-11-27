"""공식 공지로 새로 참가가 발표됐지만 랭킹 원본(Champions Battle Data)에 아직 없는 포켓몬의 임시 데이터.

랭킹 원본은 실제 랭크배틀에서 쓰인 포켓몬만 싣는다. 새 레귤레이션이 시작되는 날에는 새 포켓몬이 아직 없어서,
팀 빌더·계산기·모의전에서 쓸 수 없게 된다. 그동안은 공개 도감(Pokémon Showdown)의 종족값·타입·특성·메가진화와
9세대 습득 기술로 임시 항목을 만든다. 랭킹 원본에 들어오면 원본 데이터가 그대로 이긴다 (임시 항목은 없는 것만 채운다).

능력치는 데이터셋과 같은 레벨 50 실수치(능력 포인트 0)로 바꾼다: HP = 종족값 + 75, 나머지 = 종족값 + 20.
"""
from __future__ import annotations

import re
from functools import lru_cache

from . import collector
from .collector import tid

SD = "https://play.pokemonshowdown.com/data"
SPRITE_PREFIX = "sd-"  # 이미지 프록시가 Showdown 스프라이트로 받아 온다


FILES = ("pokedex", "learnsets")


def _sd(name: str) -> dict:
    # 내려받기는 prefetch() (백그라운드 공지 확인 스레드)에서만 한다. 규칙 계산은 엔진 잠금 안에서 돌기 때문이다.
    return collector.load_json(collector.CACHE / f"{name}.json")


def ready() -> bool:
    return all((collector.CACHE / f"{name}.json").exists() for name in FILES)


def prefetch() -> bool:
    """공개 도감 파일을 받아 둔다 (없을 때만). 받았으면 True."""
    got = False
    for name in FILES:
        path = collector.CACHE / f"{name}.json"
        if not path.exists():
            collector.fetch(f"{SD}/{name}.json", path)
            got = True
    if got:
        _pokedex.cache_clear()
        _learnsets.cache_clear()
    return got


@lru_cache(maxsize=1)
def _pokedex() -> dict:
    return _sd("pokedex")


@lru_cache(maxsize=1)
def _learnsets() -> dict:
    return _sd("learnsets")


@lru_cache(maxsize=1)
def _korean() -> dict:
    """영어 종 이름 → 한국어 (PokeAPI CSV, 데이터 수집과 같은 캐시)"""
    try:
        return collector.ko_maps()["pokemon_species_names"]
    except Exception:  # noqa: BLE001 - 이름은 없어도 된다
        return {}


def _stats(base: dict) -> dict:
    return {k: v + (75 if k == "hp" else 20) for k, v in base.items()}


def _mega_formes(dex: dict, name: str) -> list[str]:
    """기본 모습의 메가진화 (예: Tatsugiri 는 기본이 Curly 라 Tatsugiri-Curly-Mega 만)"""
    base = dex.get("baseForme")
    out = []
    for forme in dex.get("otherFormes") or []:
        rest = forme[len(name) + 1:] if forme.startswith(f"{name}-") else ""
        if re.fullmatch(r"Mega(-[XYZ])?", rest) or base and re.fullmatch(rf"{re.escape(base)}-Mega(-[XYZ])?", rest):
            out.append(forme)
    return out


def _mega(form_name: str, base_ko: str | None, sprite: str) -> dict | None:
    form = _pokedex().get(tid(form_name))
    if not form or not form.get("requiredItem"):
        return None
    suffix = re.search(r"-Mega(?:-([XYZ]))?$", form_name)
    letter = suffix[1] if suffix and suffix[1] else ""
    species = form.get("baseSpecies") or form_name.split("-")[0]
    name = f"Mega {species}" + (f" {letter}" if letter else "")
    return {"name": name, "ko": f"메가{base_ko}{letter}" if base_ko else None, "kind": f"Mega{letter and ' ' + letter}",
            "types": form["types"], "abilities": list(dict.fromkeys(form["abilities"].values())),
            "stats": _stats(form["baseStats"]), "sprite": sprite, "stone": form["requiredItem"]}


def _learnset(key: str, moves: dict) -> list[str]:
    by_id = {tid(name): name for name in moves}
    learned = set()
    for entry in filter(None, (key, _pokedex().get(key, {}).get("changesFrom") and tid(_pokedex()[key]["changesFrom"]))):
        for move_id, sources in ((_learnsets().get(entry) or {}).get("learnset") or {}).items():
            if any(src.startswith("9") for src in sources) and move_id in by_id:
                learned.add(by_id[move_id])
    return sorted(learned)


def entry(name: str, dataset: dict) -> dict | None:
    """영어 이름 하나 → 데이터셋과 같은 모양의 임시 포켓몬 (도감에 없으면 None)."""
    key = tid(name)
    dex = _pokedex().get(key)
    if not dex or dex.get("forme"):
        return None
    ko = _korean().get(key)
    sprite = SPRITE_PREFIX + key
    megas = [m for forme in _mega_formes(dex, dex["name"]) if (m := _mega(forme, ko, sprite))]
    return {
        "id": key, "name": dex["name"], "ko": ko, "slug": key, "types": dex["types"],
        "abilities": list(dict.fromkeys(dex["abilities"].values())), "stats": _stats(dex["baseStats"]),
        "sprite": sprite, "megas": megas, "learnset": _learnset(key, dataset["moves"]),
        "ranks": {}, "usage": {}, "provisional": True,
    }


def mega_entry(name: str, dataset: dict) -> tuple[str, dict] | None:
    """'Mega Dragonite' 처럼 이미 있는 포켓몬의 새 메가진화 → (포켓몬 id, 메가 항목)"""
    match = re.fullmatch(r"Mega (.+?)(?: ([XYZ]))?", name)
    if not match:
        return None
    pid = tid(match[1])
    p = dataset["pokemon"].get(pid)
    dex = _pokedex().get(pid)
    if not p or not dex:
        return None
    for forme in _mega_formes(dex, dex["name"]):
        mega = _mega(forme, p.get("ko"), p["sprite"])
        if mega and mega["name"] == name:
            return pid, mega
    return None


def build(dataset: dict, names: list[str]) -> tuple[dict, dict, list[str]]:
    """(새 포켓몬 {id: 항목}, 기존 포켓몬의 새 메가 {id: [메가]}, 도감에서도 못 찾은 이름)"""
    mons, megas, unknown = {}, {}, []
    for name in dict.fromkeys(names):
        if name.startswith("Mega "):
            base = re.fullmatch(r"Mega (.+?)(?: [XYZ])?", name)[1]
            if tid(base) in mons:  # 새 포켓몬의 메가는 항목에 이미 들어 있다
                if not any(m["name"] == name for m in mons[tid(base)]["megas"]):
                    unknown.append(name)
                continue
            have = dataset["pokemon"].get(tid(base))
            if have and any(m["name"] == name for m in have.get("megas", [])):
                continue
            try:
                found = mega_entry(name, dataset)
            except Exception:  # noqa: BLE001 - 도감을 못 받으면 그냥 '없음'
                found = None
            if found:
                megas.setdefault(found[0], []).append(found[1])
            else:
                unknown.append(name)
            continue
        if tid(name) in dataset["pokemon"]:
            continue
        try:
            made = entry(name, dataset)
        except Exception:  # noqa: BLE001
            made = None
        if made:
            mons[made["id"]] = made
        else:
            unknown.append(name)
    return mons, megas, unknown
