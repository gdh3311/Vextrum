"""Windows 배포판 압축 파일을 만든다: 받아서 풀고 Vextrum.exe 를 누르면 바로 실행된다.

    python tools/package_release.py [--skip-build]

1. Flutter Windows 릴리스 빌드
2. 백엔드를 PyInstaller로 얼려 vextrum-backend.exe (파이썬 설치 없이 실행)
3. dist/Vextrum/ 에 앱 + backend/ + backend/data/dataset.json 을 모으고
4. dist/Vextrum-<버전>-beta-windows-x64.zip 으로 묶는다.
5. 앱 안 업데이트용: 파일 목록(manifest.json)과, 최근 버전들과 달라진 파일만 담은 patch.zip 을 만든다.
   지난 버전 목록은 dist/manifests/<버전>.json 에 쌓인다 (없으면 dist 의 지난 전체 압축에서 만든다).
   GitHub 릴리스에 세 파일을 모두 올린다.

자동 연구 DB(research.sqlite)는 넣지 않는다. 받은 사람의 PC에서 처음부터 다시 쌓인다.
"""
import re
import shutil
import subprocess
import sys
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
BACKEND = ROOT / "backend"
DIST = ROOT / "dist"
WORK = DIST / "_build"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
sys.path.insert(0, str(BACKEND))
from app import updater  # noqa: E402 - 설치 폴더와 같은 규칙으로 파일 목록을 만든다

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


PATCH_BASES = 5  # 최근 몇 버전에서 패치로 바로 올라올 수 있게 할지


def _zip_manifest(path: Path, ver: str) -> dict:
    import hashlib

    files = {}
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            rel = i.filename.split("/", 1)[1] if i.filename.startswith("Vextrum/") else i.filename
            if not i.is_dir() and updater.tracked(rel):
                files[rel] = {"sha256": hashlib.sha256(z.read(i)).hexdigest(), "size": i.file_size}
    return {"version": ver, "files": files}


def _key(ver: str):
    return tuple(int(x) for x in ver.split("."))


def previous_manifests(ver: str) -> list[dict]:
    """이번 버전보다 낮은 최근 버전들의 파일 목록."""
    store = DIST / "manifests"
    store.mkdir(parents=True, exist_ok=True)
    for archive in DIST.glob("Vextrum-*-beta-windows-x64.zip"):
        old = re.search(r"Vextrum-([\d.]+)-beta", archive.name)[1]
        if not (store / f"{old}.json").exists():
            (store / f"{old}.json").write_text(json.dumps(_zip_manifest(archive, old)), encoding="utf-8")
    vers = sorted((f.stem for f in store.glob("*.json") if re.fullmatch(r"[\d.]+", f.stem) and _key(f.stem) < _key(ver)),
                  key=_key)[-PATCH_BASES:]
    return [json.loads((store / f"{v}.json").read_text(encoding="utf-8")) for v in vers]


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
             "--collect-submodules", "uvicorn",
             # 학습된 팀 강도 모델 (엔진 v7). 데이터 파일은 PyInstaller 가 자동으로 넣지 않는다.
             "--add-data", f"{BACKEND / 'app' / 'team_model.json'};app",
             "--add-data", f"{BACKEND / 'app' / 'item_text.json'};app"], BACKEND)
    out = DIST / "Vextrum"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(APP / "build" / "windows" / "x64" / "runner" / "Release", out)
    (out / "champions_meta_lab.exe").rename(out / "Vextrum.exe")
    shutil.copytree(WORK / "pyi" / "vextrum-backend", out / "backend")
    data = out / "backend" / "data"
    data.mkdir()
    shutil.copy2(BACKEND / "data" / "dataset.json", data / "dataset.json")
    stamp = json.loads((BACKEND / "data" / "dataset.json").read_text(encoding="utf-8")).get("generatedAt", "?")
    (out / "읽어 주세요.txt").write_text(README.format(version=ver, data_time=stamp), encoding="utf-8-sig")
    manifest = updater.build_manifest(out, ver)
    bases = previous_manifests(ver)
    manifest["patch"] = sorted(rel for rel, meta in manifest["files"].items()
                               if not bases or any(b["files"].get(rel, {}).get("sha256") != meta["sha256"] for b in bases))
    manifest["patchBases"] = [b["version"] for b in bases]
    (out / updater.MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (DIST / "manifests" / f"{ver}.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (DIST / f"Vextrum-{ver}-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    patch_zip = DIST / f"Vextrum-{ver}-patch.zip"
    with zipfile.ZipFile(patch_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel in manifest["patch"]:
            z.write(out / rel, f"Vextrum/{rel}")
    print(f"{patch_zip}  {patch_zip.stat().st_size / 1e6:.1f} MB  ({len(manifest['patch'])} files, "
          f"from {', '.join(manifest['patchBases']) or '-'})", flush=True)
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
