"""Read the public Champions news feed and retain the last available notices."""
from datetime import date, datetime, timedelta, timezone
from html import unescape
import json
import re
from urllib.request import urlopen

from . import collector
from .regulation import BALANCE_BASELINE

BASE = "https://champions-news.pokemon-home.com"
KINDS = {11: "season", 12: "regulation", 15: "roster", 3: "balance"}
UTC_DATE = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4}), at (\d\d:\d\d) UTC")
DATE = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})")
KST = timezone(timedelta(hours=9))
ROSTER_URL = re.compile(r"https://web-view\.app\.pokemonchampions\.jp/battle/pages/events/[a-zA-Z0-9_-]+/en/pokemon\.html")
BALANCE_HEADERS = {
    "The following Pokémon will become able to use the moves listed here.": "learn",
    "Adjustments will be made to the following moves.": "move",
    "Adjustments will be made to the following Abilities.": "ability",
}
MOVE_FIELDS = {"accuracy": "accuracy", "power": "power", "base power": "power",
               "priority": "priority", "chance to make targets flinch": "flinch"}
MONTHS = ("January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")
_notices = None


def notices():
    global _notices
    if _notices is None:
        try:
            _notices = collector.load_json(collector.CACHE / "official-news.json")
        except (OSError, ValueError):
            return []
    return _notices


def _read(url):
    with urlopen(url, timeout=12) as response:
        return response.read().decode("utf-8")


def _lines(html):
    body = re.search(r'class="article-body"[^>]*>(.*?)</article>', html, re.S)
    if not body:
        return []
    content = re.sub(r"</h[1-5]>|<br\s*/?>", "\n", body[1], flags=re.I)
    return [line for raw in unescape(re.sub(r"<[^>]+>", "", content)).splitlines()
            if (line := " ".join(raw.split())) and line != "소식 리스트"]


def _at(day, clock):
    month, number, year = day.replace(",", "").split()
    hour, minute = map(int, clock.split(":"))
    return datetime(int(year), MONTHS.index(month) + 1, int(number), hour, minute, tzinfo=timezone.utc)


def _schedule(lines):
    period = next((line for line in lines if len(UTC_DATE.findall(line)) == 2), "")
    dates = [_at(day, clock) for day, clock in UTC_DATE.findall(period)]
    if len(dates) != 2:
        return {}
    return {"start": dates[0].isoformat(), "end": (dates[1] + timedelta(minutes=1)).isoformat()}


def _balance(lines):
    """한국어 공지 본문 → 화면에 보일 변경 요약 (공지마다 손으로 적지 않는다).
    ・로 시작하는 줄이 묶음 제목(새 기술 / 기술 조정 / 특성 조정), 'X:' 다음 줄들이 그 내용이다."""
    out, label, current = [], None, None
    labels = (("사용할 수 있게", "새로 배움"), ("기술이 조정", "기술"), ("특성이 조정", "특성"))

    def flush():
        nonlocal current
        if current:
            name, body = current
            if "↓" in body:  # 특성 변경 전 → 후: 바뀐 뒤 설명만
                body = body[body.index("↓") + 1:]
            text = " ".join(body).strip()
            if text:
                out.append(f"{label} · {name}: {text}" if label else f"{name}: {text}")
        current = None

    started = False
    for raw in lines:
        line = raw.replace("％", "%")
        if line.startswith(("※", "앞으로도")):
            break
        if line.startswith(("・", "•")):
            flush()
            started = True
            label = next((name for key, name in labels if key in line), None)
            continue
        if not started:
            continue
        if line.endswith(":"):
            flush()
            current = (line[:-1].strip(), [])
        elif ":" in line and "→" in line:
            flush()
            out.append(f"{label} · {line}" if label else line)
        elif current:
            current[1].append(line)
    flush()
    return out


def _balance_changes(lines):
    changes = {"moves": {}, "learn": {}, "flags": {}, "review": []}
    section = name = None
    for line in lines:
        if line.startswith(("Note:", "We hope", "More News")):
            section = None
        elif line.startswith(("• ", "・")):
            section = BALANCE_HEADERS.get(line[2:])
            name = None
            if not section:
                changes["review"].append(line[2:])
        elif section == "move":
            name, colon, fields = line.partition(":")
            if not colon or not name.strip():
                changes["review"].append(line)
                continue
            for field in fields.split(","):
                match = re.fullmatch(r"\s*(-?\d+)%?\s*→\s*(-?\d+)%?\s+([a-z ]+)\s*", field)
                key = MOVE_FIELDS.get(match[3]) if match else None
                if key:
                    new = int(match[2])
                    bounds = {"accuracy": (1, 100), "power": (1, 500), "priority": (-7, 7), "flinch": (0, 100)}
                    if bounds[key][0] <= new <= bounds[key][1]:
                        changes["moves"].setdefault(name, {})[key] = new
                        continue
                changes["review"].append(f"{name}: {field.strip()}")
        elif section in {"learn", "ability"}:
            if line.endswith(":"):
                name = line[:-1]
            elif section == "learn" and name:
                changes["learn"][name] = [p.strip() for p in line.split(",") if p.strip()]
                name = None
            elif name == "Flash Fire" and line.endswith(
                    "The Fire Boost status will persist even if the Pokémon Mega Evolves."):
                changes["flags"]["flashFirePersists"] = True
            elif name == "Stalwart" and line == "When using its moves, the Pokémon ignores the effects of targets' substitutes.":
                changes["flags"]["stalwartBypassesSubstitute"] = True
            elif name != "Stalwart" or line not in {"↓", "The Pokémon ignores the effects of Abilities and moves that draw in moves."}:
                changes["review"].append(f"{name}: {line}" if name else line)
    if not any(changes.values()):
        changes["review"].append("공식 변경 내용을 자동으로 해석할 수 없습니다.")
    return changes


def _maintenance_window(lines):
    for line in lines:
        began = UTC_DATE.search(line)
        ended = re.search(r"was completed at (\d\d:\d\d) UTC", line)
        if began and ended and "maintenance" in line.lower():
            start, end = _at(*began.groups()), _at(began[1], ended[1])
            if end < start:
                end += timedelta(days=1)
            return {"maintenanceDate": start.astimezone(KST).date().isoformat(),
                    "completedAt": end.isoformat()}
        if match := re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4}),? (?:from|at) (\d\d:\d\d) UTC to (\d\d:\d\d) UTC", line):
            start, end = _at(match[1], match[2]), _at(match[1], match[3])
            if end < start:
                end += timedelta(days=1)
            return {"maintenanceDate": start.astimezone(KST).date().isoformat(), "scheduledEnd": end.isoformat()}
    return {}


def _roster(url):
    html = _read(url)
    match = re.search(r"\bconst pokemons\s*=\s*", html)
    if not match:
        raise ValueError("Missing official eligible Pokémon list")
    rows = json.JSONDecoder().raw_decode(html[match.end():])[0]
    if (not isinstance(rows, list) or not rows
            or not all(isinstance(r, list) and len(r) >= 3 and isinstance(r[0], str)
                       and re.fullmatch(r"\d{4}-\d{3}", r[0]) and type(r[1]) is int
                       and isinstance(r[2], str) and r[2] for r in rows)):
        raise ValueError("Invalid official eligible Pokémon list")
    return [r[2] for r in rows if r[1] == 1]


def _regulation_rules(english, html):
    rules = {}
    if "You can use Mega Evolution only one time per battle." in english:
        rules["megaPerBattle"] = 1
    elif any(re.fullmatch(r"Mega Evolution (?:is not allowed|cannot be used)\.", ln) for ln in english):
        rules["megaPerBattle"] = 0
    if "Duplicate held items are not allowed." in english:
        rules["itemClause"] = True
    elif "Duplicate held items are allowed." in english:
        rules["itemClause"] = False
    if "Full details of this regulation set will be announced at a later date." in " ".join(english):
        rules["preview"] = True
    rules["newPokemon"] = [line[2:] for line in english if line.startswith(("• ", "・"))]
    # The list is published separately on the game's official web-view host.
    url = next((u for u in re.findall(r'href="([^"]+)"', html) if ROSTER_URL.fullmatch(u)), None)
    if url:
        rules["rosterUrl"] = url
        try:
            rules["eligible"] = _roster(url)
        except (OSError, ValueError):
            pass
    section = None
    for line in english:
        if line in {"Mechanics", "Held Items", "Timers"}:
            section = line
            continue
        if line.startswith("What Are Regulations?"):
            break
        if match := re.fullmatch(r"(Total|Player|Turn|Preview) Time: (\d+) (minute|second)s?", line):
            rules.setdefault("timers", {})[match[1].lower()] = int(match[2]) * (60 if match[3] == "minute" else 1)
        elif section == "Mechanics" and not line.startswith((
                "Certain Pokémon can Mega Evolve", "You can use Mega Evolution only one time per battle.",
                "Mega Evolution is not allowed.", "Mega Evolution cannot be used.",
                "The following Mega Evolutions are newly allowed", "Mega Evolutions newly allowed", "• Mega ")):
            rules.setdefault("review", []).append(line)
        elif section in {"Held Items", "Timers"} and line not in {
                "Duplicate held items are not allowed.", "Duplicate held items are allowed."}:
            rules.setdefault("review", []).append(line)
    return rules


def _regulation_details(lines):
    bullets = [line.lstrip("・• ") for line in lines if line.startswith(("・", "•")) and len(line) < 50]
    megas = [line for line in lines if re.fullmatch(r"메가[가-힣A-Z]+", line)]
    return list(dict.fromkeys([
        *bullets, *megas,
        *[line for line in lines if "선택 시간:" in line or "종합 시간:" in line],
    ]))


def _reuse_cached(entry, now, latest):
    if not entry:
        return False
    kind = entry["kind"]
    published = datetime.fromisoformat(entry["publishedAt"])
    if kind == "season":
        return bool(entry.get("end") and datetime.fromisoformat(entry["end"]) <= now)
    if kind == "regulation":
        return bool(not latest and entry.get("rules", {}).get("eligible") and entry.get("end")
                    and datetime.fromisoformat(entry["end"]) <= now)
    if kind == "maintenance":
        return bool(entry.get("completedAt") or (entry.get("scheduledEnd") and published + timedelta(days=3) < now))
    if kind == "balance" and entry.get("changes"):
        date_text = entry.get("effectiveDate", "")
        return bool(date_text and date.fromisoformat(date_text) + timedelta(days=7) < now.astimezone(KST).date())
    return False


def refresh(now=None):
    global _notices
    now = now or datetime.now(timezone.utc)
    feed = json.loads(_read(f"{BASE}/ko/json/list.json"))["data"]
    previous = {row["url"]: row for row in notices()}
    by_kind = {}
    for row in sorted(feed, key=lambda row: row["pubAt"], reverse=True):
        kind = KINDS.get(row["infoKind"])
        # 공지 종류 3 은 밸런스 조정 / 점검 / 업데이트 배포가 섞여 있다. '밸런스'가 없는 제목은 본문에서
        # 점검 시각을 읽는다 (예: 「업데이트 데이터 배포 안내」 본문이 '점검 종료' 안내인 경우).
        if kind == "balance" and "밸런스" not in row["title"]:
            kind = "maintenance"
        link = row["link"]
        published = datetime.fromtimestamp(row["pubAt"], timezone.utc)
        if (not kind
                or kind == "roster" and not re.search(r"스탠다드\s*셀렉트 M-[A-Z]", row["title"])
                or kind in {"balance", "maintenance"} and published.date() < BALANCE_BASELINE
                or published > now or not re.fullmatch(r"page/\d+\.html", link)):
            continue
        bucket = by_kind.setdefault(kind, [])
        if kind in {"season", "regulation", "roster"} and len(bucket) >= (1 if kind == "roster" else 3):
            continue
        url = f"{BASE}/ko/{link}"
        if _reuse_cached(previous.get(url), now, not bucket):
            bucket.append(previous[url])
            continue
        entry = {"title": row["title"], "kind": kind, "url": url, "publishedAt": published.isoformat()}
        if kind == "balance" and (match := re.search(r"(\d{1,2})월\s*(\d{1,2})일", row["title"])):
            year = published.year + (int(match[1]) < published.month)
            try:
                entry["effectiveDate"] = date(year, *map(int, match.groups())).isoformat()
            except ValueError:
                pass
        try:
            lines = _lines(_read(url))
            english_html = _read(f"{BASE}/en/{link}")
            english = _lines(english_html)
            if not english:
                raise ValueError("Missing official article contents")
            entry.update(_schedule(english))
            if match := re.search(r"Regulation Set (M-[A-Z]+)\b", " ".join(english)):
                entry["regulation"] = match[1]
            if kind == "season" and (match := re.search(r"\bM-(\d+)\b", row["title"])):
                entry["season"] = f"M{match[1]}"
            if kind == "regulation":
                entry["details"] = _regulation_details(lines)
                entry["rules"] = _regulation_rules(english, english_html)
                if not entry["rules"].get("eligible") and entry["rules"].get("rosterUrl") == previous.get(url, {}).get("rules", {}).get("rosterUrl"):
                    eligible = previous.get(url, {}).get("rules", {}).get("eligible")
                    if eligible:
                        entry["rules"]["eligible"] = eligible
            elif kind == "balance":
                entry["changes"] = _balance_changes(english)
                entry["requiresMaintenance"] = any("during scheduled maintenance" in line for line in english)
                entry["details"] = _balance(lines)
                for line in english:
                    if entry["requiresMaintenance"] and "during scheduled maintenance" in line:
                        if match := DATE.search(line):
                            entry.setdefault("effectiveDate", _at(match[1], "00:00").date().isoformat())
                    elif re.search(r"will (?:take effect|be applied|be implemented)|are effective", line):
                        if match := UTC_DATE.search(line):
                            entry["start"] = _at(*match.groups()).isoformat()
            elif kind == "maintenance":
                window = _maintenance_window(english)
                if not window:  # 점검 시각이 없는 일반 안내는 버린다
                    continue
                entry.update(window)
        except (OSError, ValueError):
            entry = previous.get(url, entry)
        bucket.append(entry)
    updated = {row["url"]: row for bucket in by_kind.values() for row in bucket}
    if not updated:
        raise ValueError("No official Champions notices")
    for url, row in previous.items():
        if (row["kind"] in {"balance", "maintenance"} and url not in updated
                and row["publishedAt"] >= BALANCE_BASELINE.isoformat()):
            updated[url] = row
    updated = sorted(updated.values(), key=lambda row: row["publishedAt"], reverse=True)
    if updated != notices():
        collector.write_json(collector.CACHE / "official-news.json", updated)
        _notices = updated
    return updated


def active_season(now):
    seasons = [row for row in notices() if row["kind"] == "season" and row.get("season") and row.get("start")
               and row.get("end")]
    for row in seasons:
        if row.get("regulation") and datetime.fromisoformat(row["start"]) <= now < datetime.fromisoformat(row["end"]):
            return {"id": row["season"], "regulation": row["regulation"].replace("-", ""),
                    "start": row["start"], "end": row["end"], "source": row["url"]}
    # 새 시즌 공지는 보통 시즌이 시작한 뒤에 올라온다. 그 사이에는 '직전 시즌 다음 번호'로 추정한다
    # (시즌은 이어서 열린다: M-7 10/7 → M-8 11/4). 공지가 올라오면 위에서 공지 값으로 바뀐다.
    ended = [row for row in seasons if datetime.fromisoformat(row["end"]) <= now]
    regulation = active_regulation(now)
    if ended and regulation:
        last = max(ended, key=lambda row: row["end"])
        if (match := re.fullmatch(r"M(\d+)", last["season"])) and now - datetime.fromisoformat(last["end"]) < timedelta(days=40):
            return {"id": f"M{int(match[1]) + 1}", "regulation": regulation["regulation"].replace("-", ""),
                    "start": last["end"], "end": None, "source": regulation["url"], "inferred": True}
    return None


def active_regulation(now):
    return next((row for row in notices() if row["kind"] == "regulation" and row.get("regulation")
                 and row.get("start") and row.get("end")
                 and datetime.fromisoformat(row["start"]) <= now < datetime.fromisoformat(row["end"])), None)


def public_notices():
    public = {"title", "kind", "url", "publishedAt", "start", "end", "regulation", "season", "details", "effectiveDate"}
    return [{k: v for k, v in row.items() if k in public} for row in notices() if row["kind"] != "maintenance"]
