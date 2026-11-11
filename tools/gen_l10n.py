"""app/l10n/translations.tsv → app/lib/l10n_data.dart

    python tools/gen_l10n.py                       # 생성
    python tools/gen_l10n.py --check strings.json  # 추출한 화면 문구 중 번역이 없는 것을 출력
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TSV = ROOT / "app" / "l10n" / "translations.tsv"
OUT = ROOT / "app" / "lib" / "l10n_data.dart"
NL = "\\n"


def load():
    rows, seen = [], set()
    for n, line in enumerate(TSV.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise SystemExit(f"{TSV.name}:{n}: 칸이 3개가 아닙니다 ({len(parts)})")
        ko, en, ja = (p.replace(NL, "\n") for p in parts)
        for lang, t in (("en", en), ("ja", ja)):
            if ko.count("{}") != len(re.findall(r"\{\d*\}", t)):
                raise SystemExit(f"{TSV.name}:{n}: {lang} 보간 자리 수가 다릅니다: {ko!r} → {t!r}")
        if ko not in seen:
            seen.add(ko)
            rows.append((ko, en, ja))
    return rows


def dart(s):
    s = s.replace("\\", "\\\\").replace("'", "\\'").replace("$", "\\$").replace("\n", NL)
    return "'" + s + "'"


def main():
    rows = load()
    body = "\n".join(f"  ({dart(k)}, {dart(e)}, {dart(j)})," for k, e, j in rows)
    OUT.write_text(
        "// 생성 파일: tools/gen_l10n.py 로 app/l10n/translations.tsv 에서 만든다. 직접 고치지 말 것.\n"
        "const l10nEntries = <(String, String, String)>[\n" + body + "\n];\n",
        encoding="utf-8")
    print(f"{len(rows)}개 항목 → {OUT.relative_to(ROOT)}")
    if "--check" in sys.argv:
        have = {r[0] for r in rows}
        extracted = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
        missing = [x["ko"] for x in extracted if x["ko"] not in have]
        print("번역 없음:", len(missing))
        for m in missing:
            print("  ", repr(m))


main()
