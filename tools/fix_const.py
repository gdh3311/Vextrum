"""flutter analyze 의 const 관련 오류 위치에서 가장 가까운 앞쪽 `const ` 를 지운다 (번역 함수 tr() 도입 후 정리용).

    flutter analyze --no-pub | python ../tools/fix_const.py   (app 폴더에서)
"""
import re
import sys

fixes = {}
for line in sys.stdin:
    if "error" not in line or "const" not in line.lower():
        continue
    m = re.search(r" - (lib[\\/][^:]+):(\d+):(\d+) - ", line)
    if m:
        fixes.setdefault(m.group(1).replace("\\", "/"), []).append((int(m.group(2)), int(m.group(3))))

for path, locs in fixes.items():
    lines = open(path, encoding="utf-8").read().split("\n")
    for ln, col in sorted(locs, reverse=True):
        row, cut = ln - 1, col - 1
        while row >= 0:
            seg = lines[row] if cut is None else lines[row][:cut]
            k = seg.rfind("const ")
            if k >= 0:
                lines[row] = lines[row][:k] + lines[row][k + 6:]
                break
            row, cut = row - 1, None
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    print("fixed", path, len(locs))
