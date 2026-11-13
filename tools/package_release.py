"""Windows 배포판 압축 파일을 만든다: 받아서 풀고 Vextrum.exe 를 누르면 바로 실행된다.

    python tools/package_release.py [--skip-build]

1. Flutter Windows 릴리스 빌드
2. 백엔드를 PyInstaller로 얼려 vextrum-backend.exe (파이썬 설치 없이 실행)
3. dist/Vextrum/ 에 앱 + backend/ + backend/data/dataset.json 을 모으고
4. dist/Vextrum-<버전>-beta-windows-x64.zip 으로 묶는다.

자동 연구 DB(research.sqlite)는 넣지 않는다. 받은 사람의 PC에서 처음부터 다시 쌓인다.
"""
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
BACKEND = ROOT / "backend"
DIST = ROOT / "dist"
WORK = DIST / "_build"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"

README = """Vextrum (Champions Meta Lab) {version} 베타 — Windows

실행
  1. 압축을 아무 폴더에나 풉니다 (바탕화면, 문서 등 쓰기 가능한 곳).
  2. Vextrum.exe 를 더블클릭합니다. 파이썬이나 다른 프로그램을 설치할 필요가 없습니다.
     앱이 backend 폴더의 서버를 직접 켜고, 창을 닫으면 함께 끕니다.

처음 실행할 때
  - Windows SmartScreen 이 "알 수 없는 게시자" 경고를 띄울 수 있습니다 (서명하지 않은 베타 빌드).
    '추가 정보' → '실행'을 누르세요.
  - 방화벽 창이 뜨면 허용하지 않아도 됩니다. 서버는 이 PC 안(127.0.0.1)에서만 열립니다.
  - 포켓몬 이미지는 처음 볼 때 내려받아 backend/data/cache 에 저장합니다.

알아 둘 것
  - 승률은 앱의 배틀 엔진과 CPU 기준이며 실제 랭크전 승률이 아닙니다.
  - 동봉한 순위·채용률 데이터 수집 시각: {data_time}. 앱의 설정에서 새로 받을 수 있습니다.
  - 자동 연구 기록은 backend/data/research.sqlite 에 쌓입니다. 폴더를 지우면 함께 지워집니다.
"""


def run(cmd, cwd):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, shell=False)


def version():
    text = (APP / "pubspec.yaml").read_text(encoding="utf-8")
    return re.search(r"^version:\s*([\d.]+)", text, re.M).group(1)


def main():
    skip = "--skip-build" in sys.argv
    ver = version()
    flutter = shutil.which("flutter") or shutil.which("flutter.bat")
    if not skip:
        run([flutter, "build", "windows", "--release"], APP)
        run([PYTHON, "-m", "PyInstaller", "run_server.py", "--name", "vextrum-backend", "--noconsole", "--onedir",
             "--noconfirm", "--clean", "--distpath", WORK / "pyi", "--workpath", WORK / "pyi-build",
             "--specpath", WORK, "--paths", ".", "--collect-submodules", "app",
             "--collect-submodules", "uvicorn"], BACKEND)
    out = DIST / "Vextrum"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(APP / "build" / "windows" / "x64" / "runner" / "Release", out)
    (out / "champions_meta_lab.exe").rename(out / "Vextrum.exe")
    shutil.copytree(WORK / "pyi" / "vextrum-backend", out / "backend")
    data = out / "backend" / "data"
    data.mkdir()
    shutil.copy2(BACKEND / "data" / "dataset.json", data / "dataset.json")
    import json

    stamp = json.loads((BACKEND / "data" / "dataset.json").read_text(encoding="utf-8")).get("generatedAt", "?")
    (out / "읽어 주세요.txt").write_text(README.format(version=ver, data_time=stamp), encoding="utf-8-sig")
    archive = DIST / f"Vextrum-{ver}-beta-windows-x64.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, Path("Vextrum") / f.relative_to(out))
    print(f"{archive}  {archive.stat().st_size / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
