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
    now = now or datetime.now(timezone.utc)
    start = datetime(2026, 11, 4, 2, tzinfo=timezone.utc)
    end = datetime(2026, 12, 2, 2, tzinfo=timezone.utc)
    if not start <= now < end:
        return None
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
