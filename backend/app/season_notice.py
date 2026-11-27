"""Confirmed official season metadata, independent of the usage-data provider."""
from datetime import datetime, timezone


ROSTER = (
    "wigglytuff", "persian", "persianalola", "farfetchd", "mrmime", "swalot",
    "salamence", "gogoat", "golisopod", "rillaboom", "cinderace", "inteleon",
    "thievul", "toxtricity", "toxtricitylowkey", "grapploct", "perrserker",
    "sirfetchd", "pincurchin", "indeedee", "indeedeef", "pawmot", "arboliva",
    "squawkabilly", "squawkabillyblue", "squawkabillyyellow", "squawkabillywhite",
    "mabosstiff", "baxcalibur",
)
ROSTER_FORMS = {
    "squawkabillyblue": ("Squawkabilly (Blue Plumage)", "시비꼬 (블루 페더)"),
    "squawkabillywhite": ("Squawkabilly (White Plumage)", "시비꼬 (화이트 페더)"),
}


def _roster_entry(e, pid):
    if p := e.P.get(pid):
        return {key: p[key] for key in ("id", "name", "ko", "sprite")}
    if pid in ROSTER_FORMS:
        name, ko = ROSTER_FORMS[pid]
        return {"id": None, "name": name, "ko": ko, "sprite": None}
    return None


def active_notice(e, now=None):
    """지금 공식 시즌·레귤레이션과 그 레귤레이션에서 새로 참가한 포켓몬·메가진화.
    M-8 기간(M-C 후반 추가분)은 아래 고정 목록, 그 뒤로는 공식 레귤레이션 공지(official_news)에서 만든다."""
    now = now or datetime.now(timezone.utc)
    start = datetime(2026, 11, 4, 2, tzinfo=timezone.utc)
    end = datetime(2026, 12, 2, 2, tzinfo=timezone.utc)
    if not start <= now < end:
        return _from_notices(e, now)
    added_megas = {
        "absol": "Mega Absol Z", "salamence": "Mega Salamence",
        "garchomp": "Mega Garchomp Z", "lucario": "Mega Lucario Z",
        "golisopod": "Mega Golisopod", "baxcalibur": "Mega Baxcalibur",
    }
    return {
        "season": "M8", "regulation": "M-C",
        "sources": {
            "season": "https://champions-news.pokemon-home.com/en/page/867.html",
            "regulation": "https://champions-news.pokemon-home.com/en/page/816.html",
            "roster": "https://champions-news.pokemon-home.com/en/page/821.html",
        },
        "roster": [row for pid in ROSTER if (row := _roster_entry(e, pid)) is not None],
        "addedMegas": [
            {"id": pid, **{key: form[key] for key in ("name", "ko", "sprite")}}
            for pid, name in added_megas.items() if pid in e.P
            if (form := e.find_mega(e.P[pid], name=name)) is not None
        ],
    }


def _from_notices(e, now):
    from . import official_news, regulation
    from .collector import tid

    reg = official_news.active_regulation(now)
    if not reg:
        return None
    season = regulation.official_season(now)
    names = reg.get("rules", {}).get("newPokemon", [])
    roster, megas = [], []
    for name in names:
        if name.startswith("Mega "):
            base = name.removeprefix("Mega ").rsplit(" ", 1)
            pid = tid(base[0] if len(base) == 2 and base[1] in "XYZ" else name.removeprefix("Mega "))
            if (p := e.P.get(pid)) and (form := e.find_mega(p, name=name)):
                megas.append({"id": pid, **{k: form[k] for k in ("name", "ko", "sprite")},
                              "provisional": bool(p.get("provisional"))})
        elif (p := e.P.get(tid(name))):
            roster.append({**{k: p[k] for k in ("id", "name", "ko", "sprite")}, "provisional": bool(p.get("provisional"))})
        else:
            roster.append({"id": None, "name": name, "ko": name, "sprite": None})
    return {
        "season": season["id"] if season else None,
        "seasonInferred": bool(season and season.get("inferred")),
        "regulation": reg["regulation"],
        "preview": bool(reg.get("rules", {}).get("preview")),
        "sources": {"regulation": reg["url"], **({"season": season["source"]} if season else {})},
        "roster": roster,
        "addedMegas": megas,
    }
