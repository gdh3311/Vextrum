"""시즌·레귤레이션과 데이터 출처(provenance).

공식 일정과 원본 데이터의 시즌 표기를 섞지 않는다. 원본 API(Champions Battle Data)는 지금도 일별 데이터를
'M7' 폴더에 쌓고 있으므로, 순위·채용률은 '원본이 M7로 표기한 표본'으로만 부른다.
"""
from datetime import datetime, timezone

# 결과가 의존하는 버전 (명세 3.1): 규칙·시뮬레이터·CPU 정책이 바뀌면 이전 성적을 그대로 잇지 않는다.
SIMULATOR_VERSION = "sim-2026.11.14-r2"  # 봉인·사슬묶기 및 M-C 수치 보정
POLICY_VERSION = "cpu-tiers-v6"  # 공개 정보로 양쪽이 같은 탐색기를 사용
RULES_VERSION = "champions-mc-2026.11-r2"
OPPONENT_VERSION = "synthetic-core-split-v1"


def versions(dataset):
    return {"simulator": SIMULATOR_VERSION, "policy": POLICY_VERSION, "rules": RULES_VERSION,
            "opponents": OPPONENT_VERSION, "data": dataset.get("generatedAt")}


def version_key(dataset):
    return "|".join(str(v) for v in versions(dataset).values())


# 공식 발표 기준 (출처 URL 함께 보관). 확인되지 않은 시즌은 넣지 않는다.
SEASONS = [
    {"id": "M8", "regulation": "MC", "start": "2026-11-04T02:00:00Z", "end": "2026-12-02T01:59:00Z",
     "source": "https://champions-news.pokemon-home.com/en/page/867.html"},
]
REGULATIONS = {
    "MC": {"start": "2026-09-09", "end": "2026-12-02", "megaPerBattle": 1, "itemClause": True,
           "pick": "6 → 4 (더블 선봉 2·후발 2)",
           "source": "https://champions-news.pokemon-home.com/en/page/816.html"},
}


def _at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def official_season(now=None):
    now = now or datetime.now(timezone.utc)
    return next((s for s in SEASONS if _at(s["start"]) <= now <= _at(s["end"])), None)


def provenance(dataset, now=None):
    """dataset.json 을 어떻게 믿어야 하는지: 원본 표기 시즌, 공식 시즌, 수집 시각, 순위의 의미."""
    seasons = [s for s in dataset.get("seasons", []) if s != "Current"]
    official = official_season(now)
    source_season = seasons[0] if seasons else None
    return {
        "source": dataset.get("source"),
        "sourceSeason": source_season,
        "sourceGeneratedAt": dataset.get("generatedAt"),
        "officialSeason": official["id"] if official else None,
        "regulation": official["regulation"] if official else None,
        "rules": REGULATIONS.get(official["regulation"]) if official else None,
        "seasonMismatch": bool(official and source_season and official["id"] != source_season),
        "versions": versions(dataset),
        "rankMeaning": "순위(position)만 제공됨 — 사용률(%)로 바꾸지 않고 가중치 1/√순위로만 쓴다",
        "note": ("원본 데이터가 아직 새 시즌 폴더를 열지 않아, 공식 시즌과 원본 표기 시즌이 다릅니다. "
                 "순위·채용률은 원본이 표기한 시즌의 표본입니다.")
        if official and source_season and official["id"] != source_season else None,
    }


# 시즌 신뢰도 가중치 (v5): 공식 시즌과 멀어진 시즌의 랭커 표본일수록 덜 믿는다.
SEASON_CONFIDENCE = {0: 1., 1: .75, 2: .5}
STALE_DAYS = 3


def _season_number(season):
    try:
        return int(str(season).lstrip("Mm"))
    except ValueError:
        return None


def season_weight(season, now=None, reference=None):
    """표본 시즌이 기준 시즌보다 몇 시즌 늦은지에 따른 가중치 (같으면 1, 1시즌 0.75, 2시즌 0.5).

    reference: 기준 시즌. 주지 않으면 공식 시즌. 팀 구성에서는 '가진 데이터 중 가장 새 시즌'을 기준으로 쓴다:
    M8 표본이 없을 때 M7을 깎아도 M8 정보가 생기지는 않고 근거만 줄어든다 (벤치에서 승률이 떨어짐)."""
    official = {"id": reference} if reference else official_season(now)
    a, b = _season_number(season), _season_number(official["id"]) if official else None
    if a is None or b is None:
        return 1.
    return SEASON_CONFIDENCE.get(max(0, b - a), .35)


def data_warnings(dataset, now=None):
    """빌드 결과에 함께 보여 줄 데이터 경고 (오래된 시즌·오래된 수집)."""
    now = now or datetime.now(timezone.utc)
    info = provenance(dataset, now)
    out = []
    if info["seasonMismatch"]:
        out.append({"key": "season", "level": "warn",
                    "text": f"공식 시즌은 {info['officialSeason']}인데 순위·채용률은 {info['sourceSeason']} 표본입니다. "
                            f"{info['officialSeason']} 메타 변화는 아직 반영되지 않았습니다. "
                            f"랭커 팀은 가장 새 표본 시즌({info['sourceSeason']})을 1로, 그 이전 시즌을 낮춰 반영합니다."})
    generated = dataset.get("generatedAt")
    if generated:
        try:
            age = (now - _at(generated)).days
        except ValueError:
            age = None
        if age is not None and age >= STALE_DAYS:
            out.append({"key": "age", "level": "info", "text": f"데이터를 {age}일 전에 수집했습니다. 새로고침을 권장합니다."})
    return out
