"""시뮬레이터 구현 감사: 팀 후보·상대 풀이 실제로 쓰는 기술·특성·도구 중 엔진 코드에 효과가 없는 것.

    .venv/Scripts/python tools_audit_sim.py

판정 기준
- 기술: 위력이 있으면 기본 피해는 계산된다. 부가 효과(능력 변화·상태·필드 등)는 기술 이름이 엔진 코드(simulation·mechanics·
  engine·battle_ai)에 나오거나 표준 효과 표(mechanics 의 사전)에 있을 때만 '구현'으로 본다. 위력 0 기술은 이름이 없으면 '효과 없음'.
- 특성·도구: 이름이 엔진 코드나 효과 표에 없으면 '효과 없음'.
- 가중치: 상위 90종의 종별 채용률(%) × 종 가중치(1/√순위). 그래서 '자주 나오는데 효과가 없는' 것이 위로 온다.
- 한국어: 기술·특성·도구의 한국어 이름이 비어 있거나 영어와 같으면 '번역 없음'.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from app import collector, mechanics
from app.engine import Engine, weight

ROOT = Path(__file__).parent / "app"
CODE = "\n".join((ROOT / f).read_text(encoding="utf-8") for f in
                 ("simulation.py", "mechanics.py", "engine.py", "battle_ai.py", "battle_lab.py"))
TABLES = set()
for name in dir(mechanics):
    value = getattr(mechanics, name)
    if isinstance(value, (dict, set, frozenset, tuple)):
        TABLES |= {k for k in value if isinstance(k, str)}


def mentioned(name):
    return name in TABLES or re.search(r"[\"']" + re.escape(name) + r"[\"']", CODE) is not None


def main(top=90):
    e = Engine(json.loads(collector.DATASET.read_text(encoding="utf-8")))
    fmt = "Doubles"
    rows = {"moves": defaultdict(float), "abilities": defaultdict(float), "items": defaultdict(float)}
    for p in e.ranked(fmt)[:top]:
        w = weight(e.rank(p["id"], fmt) or 250)
        u = p["usage"][fmt]
        for kind in rows:
            for r in u.get(kind, []):
                rows[kind][r["name"]] += w * r["pct"] / 100
    out = {}
    for kind, table in rows.items():
        total = sum(table.values())
        missing = []
        for name, w in sorted(table.items(), key=lambda kv: -kv[1]):
            if kind == "moves":
                m = e.M.get(name)
                if not m:
                    missing.append({"name": name, "share": round(100 * w / total, 2), "why": "기술 데이터 없음"})
                    continue
                if m["power"]:
                    continue  # 기본 피해는 계산된다 (부가 효과는 아래 별도 목록)
            if kind == "items" and (name.endswith("ite") or " ite " in name or name.endswith("ite X")
                                    or name.endswith("ite Y") or name.endswith("ite Z")):
                continue  # 메가스톤은 메가 폼으로 처리
            if not mentioned(name):
                missing.append({"name": name, "share": round(100 * w / total, 2)})
        out[kind] = {"total": len(table), "missing": missing,
                     "missingShare": round(sum(r["share"] for r in missing), 1)}
    # 위력이 있는데 부가 효과가 있을 법한 기술(데이터에 부가 정보가 없으므로 이름이 코드에 없는 것만 표시)
    effects = []
    for name, w in sorted(rows["moves"].items(), key=lambda kv: -kv[1]):
        m = e.M.get(name)
        if m and m["power"] and not mentioned(name):
            effects.append({"name": name, "share": round(100 * w / sum(rows["moves"].values()), 2)})
    out["damagingMovesWithoutSpecialCode"] = effects[:40]
    # 한국어 번역
    untranslated = {"moves": [], "abilities": [], "items": []}
    for name in rows["moves"]:
        ko = (e.M.get(name) or {}).get("ko")
        if not ko or ko == name:
            untranslated["moves"].append(name)
    for kind in ("abilities", "items"):
        table = e.d.get(kind, {})
        for name in rows[kind]:
            ko = (table.get(name) or {}).get("ko")
            if not ko or ko == name:
                untranslated[kind].append(name)
    out["untranslated"] = {k: v[:30] for k, v in untranslated.items()}
    out["untranslatedCount"] = {k: len(v) for k, v in untranslated.items()}
    path = Path(__file__).parent / "diag_out" / "sim_audit.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for kind in ("moves", "abilities", "items"):
        o = out[kind]
        print(kind, "total", o["total"], "missing", len(o["missing"]), "share", o["missingShare"], "%",
              [(r["name"], r["share"]) for r in o["missing"][:15]])
    print("damaging w/o special code", [(r["name"], r["share"]) for r in effects[:25]])
    print("untranslated", out["untranslatedCount"], {k: v[:8] for k, v in untranslated.items()})


if __name__ == "__main__":
    main(*map(int, sys.argv[1:]))
