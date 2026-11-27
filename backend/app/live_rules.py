"""Compile supported changes from dated, official Champions notices."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from . import provisional
from .collector import tid
from .regulation import BALANCE_BASELINE, RULES_VERSION
from .simulation import move_data_supported

_KST = timezone(timedelta(hours=9))
_BASE_TIMERS = {"total": 1200, "player": 420, "turn": 45, "preview": 90}
_provisional_cache: dict = {}


def _provisional(dataset, notices, now):
    """지금 또는 앞으로 적용될 레귤레이션에서 새로 발표된 포켓몬 중 데이터에 없는 것의 임시 항목 (같은 입력이면 캐시)."""
    names = [n for r in notices if r["kind"] == "regulation" and r.get("end")
             and datetime.fromisoformat(r["end"]) > now for n in r.get("rules", {}).get("newPokemon", [])]
    missing = [n for n in names if n.startswith("Mega ") or tid(n) not in dataset["pokemon"]]
    if missing and not provisional.ready():
        return {}, {}, None  # 공개 도감을 아직 받는 중 (백그라운드) — 알림 대신 '준비 중'
    key = (dataset.get("dataVersion"), tuple(names))
    if key not in _provisional_cache:
        _provisional_cache.clear()
        _provisional_cache[key] = provisional.build(dataset, names) if names else ({}, {}, [])
    return _provisional_cache[key]


_FORM_SUFFIXES = {
    "alolan form": "alola", "galarian form": "galar", "hisuian form": "hisui",
    "male": "", "female": "f", "rotom": "", "medium variety": "", "small variety": "small",
    "large variety": "large", "jumbo variety": "super", "midday form": "",
    "midnight form": "midnight", "dusk form": "dusk", "amped form": "", "low key form": "lowkey",
    "paldean form (combat breed)": "paldeacombat", "paldean form (blaze breed)": "paldeablaze",
    "paldean form (aqua breed)": "paldeaaqua", "curly form": "", "droopy form": "droopy",
    "stretchy form": "stretchy",
}
_ROSTER_ALIASES = {"Floette": ("floetteeternal",), "Vivillon": ("vivillonfancy",),
                   "Maushold": ("maushold", "mausholdfour"),
                   "Squawkabilly": ("squawkabilly", "squawkabillyyellow")}


def _mon_id(name):
    parts = re.fullmatch(r"(.+?) \((.+)\)", name)
    if parts:
        suffix = parts[2].lower()
        if suffix.endswith(" rotom"):
            return tid(parts[1]) + tid(suffix.removesuffix(" rotom"))
        if suffix in _FORM_SUFFIXES:
            return tid(parts[1]) + _FORM_SUFFIXES[suffix]
    return tid(name)


def _active(row, now):
    return row.get("start") and row.get("end") and (
        datetime.fromisoformat(row["start"]) <= now < datetime.fromisoformat(row["end"]))


def _effective(row, maintenance, starts):
    """(적용 시각, 추정 여부). 공지에 시각이 있으면 그대로, 점검 공지가 있으면 점검 종료(실제 > 예정) 시각.
    점검 공지가 아직 없으면 같은 날(한국 시간) 시작하는 공식 시즌·레귤레이션 시각으로 추정한다
    (지금까지 업데이트 점검은 새 시즌 시작 시각에 열렸다: 11월 4일 02:00~04:00 UTC).
    그것도 없으면 그날이 끝날 때(한국 시간 자정)를 늦은 쪽 기준으로 쓴다."""
    if row.get("start"):
        return datetime.fromisoformat(row["start"]), False
    day = row.get("effectiveDate")
    if end := maintenance.get(day):
        return datetime.fromisoformat(end), False
    if not day and not row.get("requiresMaintenance"):
        return datetime.fromisoformat(row["publishedAt"]), False
    if day:
        if same_day := sorted(at for at in starts if at.astimezone(_KST).date().isoformat() == day):
            return same_day[0], True
        return datetime.fromisoformat(day).replace(tzinfo=_KST) + timedelta(days=1), True
    return None, False


def compile_rules(dataset, notices, now=None):
    now = now or datetime.now(timezone.utc)
    profile = {"megaPerBattle": 1, "moveChanges": {}, "learnChanges": {}, "flags": {},
               "allowed": None, "allowedMegas": None}
    new_mons, new_megas, unknown = _provisional(dataset, notices, now)
    profile["provisional"], profile["provisionalMegas"] = new_mons, new_megas
    alerts, notes = [], []  # alerts: 사람이 확인해야 하는 것 (설정 배지) / notes: 자동으로 처리한 것
    current = next((row for row in notices if row["kind"] == "regulation" and _active(row, now)), None)
    roster = {**dataset["pokemon"], **new_mons}
    forms = {tid(m["name"]): m["name"] for p in roster.values() for m in p.get("megas", [])}
    forms |= {tid(m["name"]): m["name"] for ms in new_megas.values() for m in ms}

    def alert(row, title, text):
        alerts.append({"title": title, "text": text, "url": row["url"]})

    def note(row, title, text):
        notes.append({"title": title, "text": text, "url": row["url"]})

    if current:
        source = current.get("rules", {})
        profile["regulation"] = current.get("regulation")
        profile["megaPerBattle"] = source.get("megaPerBattle", 1)
        if names := source.get("eligible"):
            base_names = [n for n in names if not n.startswith("Mega ")]
            mega_names = [n for n in names if n.startswith("Mega ")]
            wanted = {pid for n in base_names for pid in _ROSTER_ALIASES.get(n, (_mon_id(n),))}
            allowed = sorted(wanted & roster.keys())
            if allowed and len(wanted) - len(allowed) <= max(5, len(wanted) // 5):
                profile["allowed"] = allowed
                if mega_names:
                    profile["allowedMegas"] = sorted(set(map(tid, mega_names)) & forms.keys())
            else:
                alert(current, "참가 목록 연결 확인 필요", "공식 참가 목록을 현재 도감과 대조하지 못했습니다.")
        elif not source and current.get("regulation") == "M-C":
            # Older offline caches have the M-C schedule but no machine-readable roster yet.
            pass
        elif not source.get("preview"):
            alert(current, "참가 목록 연결 확인 필요", "공식 참가 목록을 읽을 수 없습니다. 목록을 다시 확인할 때까지 참가 가능 여부를 확정할 수 없습니다.")
        else:
            note(current, "새 규정의 참가 목록 대기 중",
                 "공식 세부 규정이 아직 공개되지 않았습니다. 그동안은 이전 규정의 포켓몬과 새로 발표된 포켓몬을 모두 쓸 수 있게 두고, "
                 "목록이 공개되면 자동으로 반영합니다.")
        names_to_check = dict.fromkeys([*source.get("newPokemon", []), *source.get("eligible", [])])
        missing = [n for n in names_to_check
                   if (tid(n) not in forms if n.startswith("Mega ") else
                       not any(p in roster for p in _ROSTER_ALIASES.get(n, (_mon_id(n),))))]
        provisional = [roster[pid]["name"] for pid in roster if roster[pid].get("provisional")]
        if provisional:
            note(current, "새 포켓몬은 임시 데이터로 사용 중",
                 f"{', '.join(provisional)}: 랭킹 원본에 아직 없어 공개 도감(Showdown)의 능력치·특성·기술로 넣었습니다. "
                 "채용률·랭킹은 원본에 등록되면 자동으로 바뀝니다.")
        if missing and unknown is None:
            note(current, "새 포켓몬 데이터 준비 중",
                 f"{', '.join(missing[:8])}: 공개 도감을 받는 중입니다. 받으면 임시 데이터로 바로 쓸 수 있습니다.")
        elif missing:
            preview = ", ".join(missing[:8])
            suffix = f" 외 {len(missing) - 8}종" if len(missing) > 8 else ""
            alert(current, "새 포켓몬 데이터 없음", f"{preview}{suffix}: 랭킹 원본과 공개 도감 어디에서도 정보를 찾지 못했습니다. "
                  "앱 업데이트가 필요할 수 있습니다.")
        unread_clauses = source and not source.get("preview") and (
            source.get("megaPerBattle") is None or source.get("itemClause") is None)
        changed_timers = any(_BASE_TIMERS[k] != v for k, v in source.get("timers", {}).items())
        if source.get("itemClause") is False or unread_clauses or changed_timers or source.get("review"):
            detail = " · ".join(source.get("review", [])[:3])
            alert(current, "새 배틀 규칙 검토 필요",
                  "도구, 시간 제한 또는 세부 배틀 규칙에 앱에서 자동으로 처리할 수 없는 변경이 있습니다."
                  + (f" {detail}" if detail else ""))

    maintenance = {}
    for row in notices:
        if row["kind"] == "maintenance" and row.get("scheduledEnd"):
            maintenance.setdefault(row["maintenanceDate"], row["scheduledEnd"])
    for row in reversed(notices):
        if row["kind"] == "maintenance" and row.get("completedAt"):
            maintenance[row["maintenanceDate"]] = row["completedAt"]
    balances = [r for r in notices if r["kind"] == "balance" and r["publishedAt"] >= BALANCE_BASELINE.isoformat()]
    starts = [datetime.fromisoformat(r["start"]) for r in notices
              if r["kind"] in {"season", "regulation"} and r.get("start")]
    effective = []
    profile["balance"] = []
    for row in balances:
        at, estimated = _effective(row, maintenance, starts)
        if at is None:
            continue
        local = at.astimezone(_KST).strftime("%m월 %d일 %H:%M")
        if at <= now:
            effective.append((at, row))
            profile["balance"].append({"url": row["url"], "at": at.isoformat(), "estimated": estimated})
            note(row, "밸런스 조정 적용됨",
                 f"{row.get('title', '밸런스 조정')} · {local} (한국 시간){' 기준 (점검 공지가 없어 시즌 시작 시각으로 추정)' if estimated else ''}")
        else:
            note(row, "밸런스 조정 적용 예정",
                 f"{row.get('title', '밸런스 조정')} · {local} (한국 시간){' 예상 · 점검 공지가 나오면 그 시각으로 바꿉니다' if estimated else ''}")
    for _, row in sorted(effective, key=lambda entry: (entry[0], entry[1]["publishedAt"])):
        changes = row.get("changes", {})
        move_changes = profile["moveChanges"]
        learn_changes = profile["learnChanges"]
        missing = set()
        gap = set()
        for name, fields in changes.get("moves", {}).items():
            if name in dataset["moves"]:
                move_changes.setdefault(name, {}).update(fields)
            else:
                missing.add(name)
        for name, mons in changes.get("learn", {}).items():
            if name not in dataset["moves"]:
                missing.add(name)
                continue
            for mon in mons:
                if (pid := _mon_id(mon)) in roster:
                    learn_changes.setdefault(pid, [])
                    if name not in learn_changes[pid]:
                        learn_changes[pid].append(name)
                    if not move_data_supported(name, {**dataset["moves"][name], **move_changes.get(name, {})}):
                        gap.add(name)
                else:
                    missing.add(mon)
        profile["flags"].update(changes.get("flags", {}))
        if missing:
            alert(row, "밸런스 변경 데이터 확인 필요", "현재 데이터에서 찾을 수 없는 변경 항목 · " + ", ".join(sorted(missing)))
        if gap:
            alert(row, "가상 배틀 동작 검토 필요",
                  "습득 목록에 반영했습니다. 가상 배틀에서 효과 구현이 필요한 기술 · " + ", ".join(sorted(gap)))
        if not changes or changes.get("review"):
            details = "; ".join(changes.get("review", [])[:3])
            alert(row, "밸런스 변경 검토 필요", "자동으로 처리할 수 없는 공식 변경 사항이 있습니다."
                  + (f" {details}" if details else ""))

    signature = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()[:12]
    profile["version"] = f"{RULES_VERSION}/{signature}"
    profile["notes"] = notes
    return profile, alerts
