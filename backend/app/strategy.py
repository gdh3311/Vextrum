"""전략 연구: 팀을 한 단어로 분류하지 않고, 실제 구성 요소(시동·수혜·대응)로 여러 전략 태그와 승리 조건을 만든다.

관계 그래프(명세 2.2)의 엣지는 auto_team._candidate 가 만든 features 로 표현된다.
  날씨 시동(rain_set) → 수혜(rain_core·rain_attack), 순풍(tailwind) → 빠른 공격수(fast_attacker),
  트릭룸(trickroom) → 느린 공격수(slow_attacker), 사이코메이커(psychic_set) → 와이드포스(psychic_attack),
  날따름(redirect) → 시동 보호, 와이드가드(wideguard) → 광역기 대응 …
태그는 '시동 + 수혜'가 함께 있을 때만 붙고(근거 포함), 충돌(날씨 둘, 트릭룸 없는 저속 다수 등)은 경고로 남긴다.
"""
from . import auto_team, simulation

FAMILIES = {
    "rain": "비", "sun": "쾌청", "sand": "모래바람", "snow": "눈", "tailwind": "순풍", "trickroom": "트릭룸",
    "psychic": "사이코필드", "spread": "광역 공격", "setup": "랭크업", "pivot": "교체 운영",
    "redirect": "날따름 보호", "wideguard": "와이드가드", "fakeout": "속이다 압박", "anti_tr": "트릭룸 대응",
    "balance": "균형형",
}
# 명세 4.2의 하이브리드 블루프린트: (주 전략, 보조 전략). auto_team.STYLES 의 키로 초안을 만든다.
BLUEPRINTS = [
    ("rain", "tailwind"), ("sun", "tailwind"), ("sun", "trickroom"), ("trickroom", "psychic"),
    ("tailwind", "setup"), ("trickroom", "setup"), ("rain", "pivot"), ("sand", "setup"), ("snow", "tailwind"),
    ("tailwind", "pivot"), ("psychic", "tailwind"), ("bulky", "setup"),
]
SPREAD_TARGETS = {"allAdjacentFoes", "allAdjacent"}
ANTI_TR = {"Taunt", "Imprison", "Trick Room", "Encore"}


def blueprint_groups(fmt):
    out = []
    for a, b in BLUEPRINTS:
        styles = (auto_team.STYLES[a], auto_team.STYLES[b])
        if fmt != "Doubles" and any(s.doubles_only for s in styles):
            continue
        out.append((a, b))
    return out


def _names(members):
    return [c.resolved["ko"] or c.resolved["name"] for c in members]


def analyze(e, fmt, roster):
    """태그(근거 포함), 승리 조건 2개, 일관성 경고."""
    has = lambda key: [c for c in roster if key in c.features]
    moves = lambda c: set(c.resolved["moves"])
    tags = []

    def tag(key, setters, payoffs, why):
        unique = list({id(c): c for c in payoffs}.values())
        payoffs = [c for c in unique if all(c is not s for s in setters)] or unique
        tags.append({"key": key, "label": FAMILIES[key], "setters": _names(setters)[:2], "payoffs": _names(payoffs)[:3],
                     "why": why})

    for weather in ("rain", "sun", "sand", "snow"):
        setters, payoffs = has(f"{weather}_set"), has(f"{weather}_core") + has(f"{weather}_attack")
        if setters and payoffs:
            tag(weather, setters, payoffs, f"{FAMILIES[weather]} 시동과 그 날씨에서 강해지는 공격수")
    fast, slow = has("fast_attacker"), has("slow_attacker")
    if has("tailwind") and len(fast) + len(has("attacker")) >= 3:
        tag("tailwind", has("tailwind"), fast or has("attacker"), "순풍 뒤 먼저 때릴 공격수")
    if has("trickroom") and len(slow) >= 2:
        tag("trickroom", has("trickroom"), slow, "트릭룸 안에서 먼저 움직이는 느린 공격수")
    if has("psychic_set") and has("psychic_attack"):
        tag("psychic", has("psychic_set"), has("psychic_attack"), "사이코필드와 광역 와이드포스")
    spread = [c for c in roster if any(e.M.get(m, {}).get("target") in SPREAD_TARGETS and e.M.get(m, {}).get("power")
                                       for m in moves(c))]
    if fmt == "Doubles" and len(spread) >= 3:
        tag("spread", [], spread, "광역기로 두 마리를 동시에 압박")
    if has("setup_attacker"):
        tag("setup", [], has("setup_attacker"), "랭크업 후 일소")
    redirect = [c for c in roster if moves(c) & simulation.REDIRECT]
    if fmt == "Doubles" and redirect:
        tag("redirect", redirect, [], "날따름·분노가루로 시동·랭크업 보호")
    wide = [c for c in roster if "Wide Guard" in moves(c)]
    if wide:
        tag("wideguard", wide, [], "상대 광역기를 막는 와이드가드")
    fake = [c for c in roster if "Fake Out" in moves(c)]
    if fmt == "Doubles" and fake:
        tag("fakeout", fake, [], "속이다로 첫 턴 행동 봉쇄")
    if any(moves(c) & ANTI_TR for c in roster) and not has("trickroom") or len(has("trickroom")) and len(fast) >= 2:
        anti = [c for c in roster if moves(c) & ANTI_TR]
        if anti:
            tag("anti_tr", anti, [], "도발·앙코르·트릭룸 되돌리기로 상대 트릭룸 대응")
    if len(has("pivot")) >= 2:
        tag("pivot", has("pivot"), [], "교체 기술로 유리한 대면 만들기")
    if not tags:
        tag("balance", [], has("attacker"), "역할을 나눈 정면 승부")

    # 승리 조건: 주 전략 + 그 전략이 막혔을 때의 보조 플랜
    attackers = sorted(has("attacker"), key=lambda c: -c.resolved["stats"]["atk"] - c.resolved["stats"]["spa"])
    main = next((t for t in tags if t["key"] in ("rain", "sun", "sand", "snow", "trickroom", "tailwind", "psychic")),
                tags[0])
    primary = f"{main['label']}: " + (" + ".join(main["setters"][:1] + main["payoffs"][:2]) or "핵심 공격수")
    outside = [c for c in attackers if (c.resolved["ko"] or c.resolved["name"]) not in main["payoffs"]]
    backup_tag = next((t for t in tags if t is not main and t["key"] in ("setup", "spread", "pivot", "tailwind",
                                                                        "trickroom", "fakeout")), None)
    if backup_tag:
        secondary = f"{backup_tag['label']}: " + " + ".join((backup_tag["payoffs"] or backup_tag["setters"])[:2])
    elif outside:
        secondary = "전략 없이 정면 화력: " + " + ".join(_names(outside[:2]))
    else:
        secondary = None

    warnings = []
    setters = {w for w in ("rain", "sun", "sand", "snow") if has(f"{w}_set")}
    if len(setters) > 1:
        warnings.append("날씨 시동이 둘 이상입니다. 선출을 날씨별로 나누지 않으면 서로 날씨를 덮습니다.")
    very_slow = [c for c in has("attacker") if c.resolved["speed"] <= 60]
    if len(very_slow) >= 2 and not has("trickroom"):
        warnings.append("트릭룸 없이 아주 느린 공격수가 여럿입니다.")
    if has("tailwind") and not fast and len(has("attacker")) < 3:
        warnings.append("순풍을 걸어도 득을 볼 공격수가 적습니다.")
    if has("trickroom") and len(slow) < 2:
        warnings.append("트릭룸 시동은 있지만 느린 공격수가 부족합니다.")
    return {"tags": tags, "primary": primary, "secondary": secondary, "warnings": warnings,
            "families": [t["key"] for t in tags]}


def family(analysis):
    """다양성 판정에 쓰는 대표 전략 (주 전략 태그)."""
    keys = analysis["families"]
    return next((k for k in keys if k in ("rain", "sun", "sand", "snow", "trickroom", "tailwind", "psychic")),
                keys[0] if keys else "balance")
