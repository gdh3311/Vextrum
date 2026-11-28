"""자동 구성 결과 설명: 포켓몬마다 '왜 뽑혔는지'와 세트(도구·특성·성격·능력 포인트·기술)를 고른 이유.

시뮬레이션을 더 돌리지 않고, 구성 단계에서 이미 계산한 값(메타 상위 상대 상성, 타입 약점, 랭커 동시 채용,
모의전 선출률, 사용률 통계)만으로 만든다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .typechart import TYPES, type_multiplier

STAT_KO = {"hp": "HP", "atk": "공격", "def": "방어", "spa": "특공", "spd": "특방", "spe": "스피드"}
TYPE_KO = {"Normal": "노말", "Fire": "불꽃", "Water": "물", "Electric": "전기", "Grass": "풀", "Ice": "얼음",
           "Fighting": "격투", "Poison": "독", "Ground": "땅", "Flying": "비행", "Psychic": "에스퍼", "Bug": "벌레",
           "Rock": "바위", "Ghost": "고스트", "Dragon": "드래곤", "Dark": "악", "Steel": "강철", "Fairy": "페어리"}
# 성격: (오르는 능력, 내리는 능력)
NATURES = {
    "Lonely": ("atk", "def"), "Adamant": ("atk", "spa"), "Naughty": ("atk", "spd"), "Brave": ("atk", "spe"),
    "Bold": ("def", "atk"), "Impish": ("def", "spa"), "Lax": ("def", "spd"), "Relaxed": ("def", "spe"),
    "Modest": ("spa", "atk"), "Mild": ("spa", "def"), "Rash": ("spa", "spd"), "Quiet": ("spa", "spe"),
    "Calm": ("spd", "atk"), "Gentle": ("spd", "def"), "Careful": ("spd", "spa"), "Sassy": ("spd", "spe"),
    "Timid": ("spe", "atk"), "Hasty": ("spe", "def"), "Jolly": ("spe", "spa"), "Naive": ("spe", "spd"),
}
MOVE_WHY = {
    "Protect": "방어 · 집중 공격을 한 턴 피하고 상대 행동을 본다", "Detect": "판별 · 방어와 같은 역할",
    "Spiky Shield": "니들가드 · 방어 + 접촉 반격", "King's Shield": "킹실드 · 방어 + 접촉 시 공격 하락",
    "Tailwind": "순풍 · 4턴 동안 아군 스피드 2배", "Trick Room": "트릭룸 · 5턴 동안 느린 쪽이 먼저 움직인다",
    "Fake Out": "속이다 · 첫 턴 상대 하나를 풀죽게 해 시동·공격 턴을 번다",
    "Follow Me": "날따름 · 공격을 끌어와 아군을 지킨다", "Rage Powder": "분노가루 · 공격을 끌어와 아군을 지킨다",
    "Helping Hand": "도우미 · 아군 기술 위력 1.5배", "Wide Guard": "와이드가드 · 광역 기술을 막는다",
    "Icy Wind": "얼어붙은바람 · 상대 둘의 스피드를 내린다", "Electroweb": "일렉트릭네트 · 상대 둘의 스피드를 내린다",
    "Thunder Wave": "전기자석파 · 마비로 스피드를 묶는다", "Will-O-Wisp": "도깨비불 · 화상으로 물리 화력을 반감",
    "Knock Off": "탁쳐서떨구기 · 상대 도구를 떨군다", "U-turn": "유턴 · 공격하고 교체해 유리하게 이어 간다",
    "Volt Switch": "볼트체인지 · 공격하고 교체", "Parting Shot": "막말내뱉기 · 능력을 내리고 교체",
    "Flip Turn": "퀵턴 · 공격하고 교체", "Taunt": "도발 · 상대 보조 기술(트릭룸 등)을 막는다",
    "Encore": "앙코르 · 상대를 같은 기술에 묶는다", "Spore": "버섯포자 · 확실한 잠듦",
    "Yawn": "하품 · 다음 턴 잠듦을 걸어 교체를 강요", "Swords Dance": "칼춤 · 공격 2랭크 업",
    "Nasty Plot": "나쁜음모 · 특공 2랭크 업", "Calm Mind": "명상 · 특공·특방 업", "Dragon Dance": "용의춤 · 공격·스피드 업",
    "Bulk Up": "벌크업 · 공격·방어 업", "Quiver Dance": "나비춤 · 특공·특방·스피드 업",
    "Belly Drum": "배북 · 체력 절반으로 공격 최대", "Recover": "HP회복", "Roost": "날개쉬기 · 회복",
    "Slack Off": "게으름피우기 · 회복", "Synthesis": "광합성 · 회복", "Moonlight": "달의불빛 · 회복",
    "Strength Sap": "흡수 · 회복 + 상대 공격 하락", "Pain Split": "아픔나누기 · 체력 나눠 회복",
    "Reflect": "리플렉터 · 물리 피해 감소", "Light Screen": "빛의장막 · 특수 피해 감소",
    "Aurora Veil": "오로라베일 · 눈일 때 물리·특수 피해 감소", "Stealth Rock": "스텔스록 · 교체해 오는 상대에게 피해",
    "Sunny Day": "쾌청 · 날씨 시동", "Rain Dance": "비바라기 · 날씨 시동", "Sandstorm": "모래바람 · 날씨 시동",
    "Snowscape": "설경 · 날씨 시동", "Haze": "흑안개 · 상대 랭크업을 지운다", "Clear Smog": "클리어스모그 · 랭크업 해제",
    "Psych Up": "자기암시 · 상대 랭크 변화를 복사", "Wonder Room": "원더룸 · 방어·특방을 바꾼다",
    "Ally Switch": "사이드체인지 · 아군과 자리를 바꿔 공격을 흘린다", "Coaching": "코칭 · 아군 공격·방어 업",
    "Life Dew": "생명의물방울 · 아군과 함께 회복", "Pollen Puff": "꽃가루경단 · 공격 또는 아군 회복",
    "Snarl": "바크아웃 · 상대 둘의 특공 하락", "Struggle Bug": "벌레의저항 · 상대 둘의 특공 하락",
    "Feint": "페인트 · 방어를 뚫는다", "Quash": "순서미루기 · 상대를 맨 나중에 움직이게",
    "Imprison": "봉인 · 같은 기술을 상대가 못 쓰게", "Chilly Reception": "썰렁개그 · 눈을 켜고 교체",
    "Weather Ball": "웨더볼 · 날씨에 맞춰 타입이 바뀌고 위력 2배", "Expanding Force": "와이드포스 · 사이코필드에서 둘 다 공격",
    "Eruption": "분화 · 체력이 많을수록 강하다", "Water Spout": "해수스파우팅 · 체력이 많을수록 강하다",
    "Sucker Punch": "기습 · 상대가 공격할 때 먼저 친다", "Last Respects": "성묘 · 쓰러진 아군이 많을수록 강하다",
    "Solar Beam": "솔라빔 · 쾌청이면 바로 쏜다", "Electro Shot": "일렉트로빔 · 비면 바로 쏜다",
}
ITEM_WHY = {
    "Choice Scarf": "스피드 1.5배 · 한 기술에 묶이는 대신 먼저 공격", "Choice Band": "공격 1.5배 · 한 기술에 묶인다",
    "Choice Specs": "특공 1.5배 · 한 기술에 묶인다", "Life Orb": "기술 위력 1.3배 · 공격할 때마다 체력 10% 감소",
    "Focus Sash": "체력이 가득하면 한 번은 1로 버틴다", "Sitrus Berry": "체력 절반 이하에서 25% 회복",
    "Leftovers": "매 턴 체력 1/16 회복", "Assault Vest": "특방 1.5배 · 공격 기술만 쓸 수 있다",
    "Rocky Helmet": "접촉 공격한 상대에게 피해", "Light Clay": "리플렉터·빛의장막·오로라베일 8턴",
    "Mental Herb": "도발·앙코르를 한 번 풀어 시동 기술을 지킨다", "Safety Goggles": "가루 기술·날씨 피해를 막는다",
    "Clear Amulet": "상대가 내 능력을 못 내린다 (위협 대책)", "Covert Cloak": "기술의 추가 효과(풀죽음 등)를 막는다",
    "Booster Energy": "고대활성·쿼크차지 발동", "Expert Belt": "효과가 굉장한 기술 1.2배", "Heat Rock": "쾌청 8턴",
    "Damp Rock": "비 8턴", "Smooth Rock": "모래바람 8턴", "Icy Rock": "눈 8턴", "Weakness Policy": "약점을 맞으면 공격·특공 2랭크 업",
    "Lum Berry": "상태이상을 한 번 회복", "Black Glasses": "악 기술 1.2배", "Charcoal": "불꽃 기술 1.2배",
    "Mystic Water": "물 기술 1.2배", "Miracle Seed": "풀 기술 1.2배", "Magnet": "전기 기술 1.2배",
    "Never-Melt Ice": "얼음 기술 1.2배", "Black Belt": "격투 기술 1.2배", "Poison Barb": "독 기술 1.2배",
    "Soft Sand": "땅 기술 1.2배", "Sharp Beak": "비행 기술 1.2배", "Twisted Spoon": "에스퍼 기술 1.2배",
    "Silver Powder": "벌레 기술 1.2배", "Hard Stone": "바위 기술 1.2배", "Spell Tag": "고스트 기술 1.2배",
    "Dragon Fang": "드래곤 기술 1.2배", "Metal Coat": "강철 기술 1.2배", "Fairy Feather": "페어리 기술 1.2배",
    "Silk Scarf": "노말 기술 1.2배", "Shell Bell": "준 피해의 1/8 회복", "Scope Lens": "급소율 업",
    "Quick Claw": "가끔 먼저 행동", "King's Rock": "가끔 풀죽게 한다", "Bright Powder": "상대 명중률 하락",
}
ROLE_WHY = [
    ("sun_set", "쾌청 시동"), ("rain_set", "비 시동"), ("sand_set", "모래바람 시동"), ("snow_set", "눈 시동"),
    ("trickroom", "트릭룸 시동"), ("tailwind", "순풍 시동"), ("psychic_set", "사이코필드 시동"),
    ("redirect", "공격 유도"), ("fakeout", "속이다 지원"), ("intimidate", "위협으로 상대 화력 감소"),
    ("setup_attacker", "랭크업 에이스"), ("sun_core", "쾌청 수혜 공격수"), ("rain_core", "비 수혜 공격수"),
    ("sand_core", "모래바람 수혜"), ("snow_core", "눈 수혜"), ("slow_attacker", "트릭룸 아래 공격수"),
    ("fast_attacker", "빠른 공격수"), ("priority", "선공기 마무리"), ("pivot", "교체로 흐름 조절"),
    ("speedcontrol", "스피드 조절"), ("wideguard", "와이드가드"), ("prankster", "짓궂은마음 보조"),
    ("screens", "벽 전개"), ("disrupt", "상태이상·방해"), ("support", "아군 지원"), ("hazard", "설치기"),
    ("bulky", "받아 내는 역할"), ("recovery", "회복으로 오래 버팀"),
    ("physical", "물리 화력"), ("special", "특수 화력"),
]


@lru_cache(maxsize=1)
def _item_text() -> dict:
    try:
        return json.loads((Path(__file__).with_name("item_text.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ko(r) -> str:
    return r.get("ko") or r.get("name")


def _pct(rows, name):
    return next((row["pct"] for row in rows or () if row.get("name") == name), None)


def _join(names, limit=3):
    names = list(names)
    return ", ".join(names[:limit]) + (f" 외 {len(names) - limit}" if len(names) > limit else "")


def _item(e, s, r, usage):
    item = s.get("item")
    if not item:
        return None
    label = e.d["items"].get(item, {}).get("ko") or item
    if r.get("mega"):
        why = f"메가진화 → {r['ko'] or r['name']} (특성 {e.d['abilities'].get(r['ability'], {}).get('ko') or r['ability']})"
    elif item in ITEM_WHY:
        why = ITEM_WHY[item]
    else:
        text = (_item_text().get(item, {}).get("ko") or "").split(".")[0]
        hit = re.search(r"효과가 뛰어난 (\S+) 기술", text)
        why = (f"효과가 굉장한 {hit[1]} 기술 피해를 한 번 줄인다" if hit
               else re.sub(r"^(포켓몬에게 )?지니게 하면 ", "", text) or "도구")
    pct = _pct(usage.get("items"), item)
    return {"part": "도구", "label": label, "text": why + (f" · 실전 채용 {pct:g}%" if pct else "")}


def _ability(e, s, r, usage):
    ability = s.get("ability") or r.get("ability")
    if not ability:
        return None
    label = e.d["abilities"].get(ability, {}).get("ko") or ability
    pct = _pct(usage.get("abilities"), ability)
    if pct is None:
        return {"part": "특성", "label": label, "text": "이 세트에 맞춰 고른 특성"}
    return {"part": "특성", "label": label, "text": f"실전 채용 {pct:g}%" + (" · 거의 모두 이 특성" if pct >= 85 else "")}


def _nature(e, s, r, meta, room):
    nature = s.get("nature")
    points = s.get("points") or r.get("points") or {}
    up, down = NATURES.get(nature, (None, None))
    label = e.d["natures"].get(nature) or nature or "-"
    parts = []
    if up:
        parts.append(f"{STAT_KO[up]}↑ {STAT_KO[down]}↓")
    spread = " · ".join(f"{STAT_KO[k]} {v}" for k, v in points.items() if v)
    if spread:
        parts.append(f"포인트 {spread}")
    speed = r.get("speed")
    foes = [f for f in meta if f.get("id") != r.get("id")]
    room = room and speed is not None and speed <= 100
    if speed and foes:
        speeds = [f["stats"]["spe"] * (1.5 if f.get("item") == "Choice Scarf" else 1) for f in foes]
        if room:
            slower = sum(speed < x for x in speeds)
            parts.append(f"실제 스피드 {round(speed)}: 트릭룸에서 메타 상위 {len(foes)}마리 중 {slower}마리보다 먼저")
        else:
            faster = sum(speed > x for x in speeds)
            parts.append(f"실제 스피드 {round(speed)}: " + (
                f"메타 상위 {len(foes)}마리 모두보다 느림 (빠르기보다 내구·화력에 투자)" if faster == 0
                else f"메타 상위 {len(foes)}마리 모두보다 빠름" if faster == len(foes)
                else f"메타 상위 {len(foes)}마리 중 {faster}마리보다 빠름"))
    return {"part": "성격·포인트", "label": label, "text": " · ".join(parts)}


def _move(e, s, r, move, meta, usage, stab_types):
    m = e.M.get(move, {})
    label = m.get("ko") or move
    pct = _pct(usage.get("moves"), move)
    tail = f" · 실전 채용 {pct:g}%" if pct else ""
    if not m.get("power"):
        return {"part": "기술", "label": label, "type": m.get("type"),
                "text": MOVE_WHY.get(move, "보조 기술").split(" · ", 1)[-1] + tail}
    bits = []
    if m["type"] in stab_types:
        bits.append(f"자속 주력 (위력 {m['power']})")
    if m.get("priority", 0) > 0:
        bits.append("선공기")
    if m.get("target") in ("allAdjacentFoes", "allAdjacent"):
        bits.append("상대 둘 다 공격")
    if move in MOVE_WHY:
        bits.append(MOVE_WHY[move].split(" · ", 1)[-1])
    stab_moves = [x for x in r["moves"] if e.M.get(x, {}).get("power") and e.M[x]["type"] in stab_types]
    if m["type"] not in stab_types and move not in MOVE_WHY:
        hits = [f for f in meta if type_multiplier(m["type"], f["types"], f.get("ability")) >= 2
                and not any(type_multiplier(e.M[x]["type"], f["types"], f.get("ability")) >= 2 for x in stab_moves)]
        bits.append(f"견제 · 자속으로 약점을 못 찌르는 {_join(_ko(f) for f in hits)}에 효과가 굉장함" if hits
                    else f"{TYPE_KO.get(m['type'], m['type'])} 타입 견제")
    return {"part": "기술", "label": label, "type": m.get("type"), "text": " · ".join(bits) + tail}


def explain(e, fmt, roster, meta, weights, report=None, pairs=(), tuning=None, fixed_ids=(), goals=()):
    """roster: auto_team.Candidate 목록. 같은 순서로 [{summary, reasons[], set[], source}]."""
    picked = {m["id"]: m for m in (report or {}).get("memberStats", ())}
    best = {}
    order = sorted(range(len(meta)), key=lambda i: -weights[i])[:12]
    for i in order:
        top = max(roster, key=lambda c: c.matchups[i])
        if top.matchups[i] >= 58:
            best.setdefault(top.id, []).append(meta[i])
    changes = {}
    for row in (tuning or {}).get("changes", ()) or ():
        changes.setdefault(row.get("id"), []).append(row)
    ids = {c.id for c in roster}
    room = "trickroom" in goals or sum("slow_attacker" in c.features for c in roster) >= 2 and any(
        "trickroom" in c.features for c in roster)
    out = []
    for c in roster:
        r, s = c.resolved, c.set
        usage = e.P[c.id]["usage"].get(fmt, {})
        reasons = []
        if c.id in fixed_ids:
            reasons.append({"kind": "fixed", "text": "직접 고정한 포켓몬"})
        roles = [label for key, label in ROLE_WHY if key in c.features
                 and (key != "slow_attacker" or room) and (key != "fast_attacker" or not room)][:2]
        if roles:
            reasons.append({"kind": "role", "text": "역할 · " + " · ".join(roles)})
        if c.id in best:
            reasons.append({"kind": "cover",
                            "text": f"메타 상위 중 팀에서 가장 잘 상대함 · {_join(_ko(f) for f in best[c.id])}"})
        others = [x for x in roster if x is not c]
        patched = [TYPE_KO[t] for i, t in enumerate(TYPES)
                   if sum(x.weak[i] for x in others) >= 2 and c.resist[i]]
        if patched:
            reasons.append({"kind": "defend", "text": f"팀이 약한 {_join(patched, 4)} 공격을 받아 낸다"})
        partners = [b if a == c.id else a for a, b, _ in pairs if c.id in (a, b) and ({a, b} <= ids)]
        if partners:
            names = [_ko(x.resolved) for x in roster if x.id in partners]
            reasons.append({"kind": "partner", "text": f"랭커 파티에서 자주 함께 쓰이는 짝 · {_join(names)}"})
        if c.id in picked and (report or {}).get("runs"):
            st = picked[c.id]
            reasons.append({"kind": "sim", "text": f"모의전 선출 {st.get('pickRate', 0):g}% · 선출 시 승률 "
                                                   f"{st.get('winRate', 0):g}% · 판당 쓰러뜨림 {st.get('koPerGame', 0):g}"})
        rank = usage.get("rank")
        reasons.append({"kind": "usage", "text": f"사용률 {rank}위" if rank and rank <= 60
                        else (f"사용률 {rank}위 · 잘 안 쓰이는 숨은 카드" if rank else "사용률 통계 없음 (임시 데이터)")})
        stab = set(r["types"])
        if r.get("ability") in ("Protean", "Libero"):
            stab = {e.M[m]["type"] for m in r["moves"] if e.M.get(m, {}).get("power")}
        parts = [x for x in (_item(e, s, r, usage), _ability(e, s, r, usage), _nature(e, s, r, meta, room)) if x]
        parts += [_move(e, s, r, move, meta, usage, stab) for move in r["moves"]]
        tuned = changes.get(c.id, [])
        source = ("세트 최적화 · " + "; ".join(f"{row.get('kind', '')} {row.get('change', '')} (모의전 +{row.get('gain', 0):g}%p)".strip()
                                    for row in tuned)
                  if tuned else "실전 사용률 통계의 대표 세트" if usage.get("moves") else "공개 도감 기준 기본 세트")
        summary = " · ".join(x["text"].split(" · ", 1)[-1] for x in reasons
                             if x["kind"] in ("role", "cover"))[:90] or reasons[0]["text"]
        out.append({"summary": summary, "reasons": reasons, "set": parts, "source": source})
    from .guide import polish

    return polish(out)
