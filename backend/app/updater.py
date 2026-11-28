"""앱 안에서 새 버전으로 업데이트 (바뀐 파일만 받는 패치).

배포판마다 GitHub 릴리스에 세 파일을 올린다 (tools/package_release.py):
  Vextrum-<버전>-manifest.json   파일별 sha256 + 패치에 든 파일 목록
  Vextrum-<버전>-patch.zip       최근 몇 버전과 달라진 파일만
  Vextrum-<버전>-beta-windows-x64.zip  전체

1. 설치 폴더의 파일 해시를 새 목록과 비교해 바꿀 파일을 고른다 (backend/data 는 사용자 데이터라 건드리지 않는다).
2. 바꿀 파일이 모두 패치에 있으면 패치만, 아니면 전체 압축을 받는다. 파일마다 해시를 확인해 update/staged 에 둔다.
3. 앱이 apply 명령(PowerShell 스크립트)을 따로 띄우고 종료한다. 스크립트는 이 폴더의 프로세스가 모두 끝나기를 기다렸다가
   파일을 바꾸고(기존 파일은 백업, 실패하면 되돌림) 앱을 다시 켠다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

MANIFEST = "vextrum-manifest.json"
PLAN = "update-plan.json"
USER_DATA = ("backend/data/",)
RELEASES = os.environ.get("VEXTRUM_RELEASES_URL",
                          "https://api.github.com/repos/gdh3311/Vextrum/releases?per_page=5")
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "Vextrum-update-check"}

_lock = threading.Lock()
_state: dict = {"phase": "idle"}


def install_root() -> Path | None:
    """배포판(얼린 백엔드)이면 Vextrum.exe 가 있는 설치 폴더. 개발 실행이면 None."""
    if not getattr(sys, "frozen", False):
        return None
    root = Path(sys.executable).resolve().parent.parent
    return root if (root / "Vextrum.exe").is_file() else None


def update_dir(root: Path) -> Path:
    return root / "backend" / "data" / "update"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tracked(rel: str) -> bool:
    return not rel.startswith(USER_DATA) and rel != MANIFEST


def build_manifest(folder: Path, version: str) -> dict:
    files = {}
    for f in sorted(folder.rglob("*")):
        rel = f.relative_to(folder).as_posix()
        if f.is_file() and tracked(rel):
            files[rel] = {"sha256": sha256(f), "size": f.stat().st_size}
    return {"version": version, "files": files}


def local_manifest(root: Path) -> dict:
    try:
        return json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def plan(root: Path, manifest: dict) -> dict:
    """새 목록과 비교해 받을 파일·지울 파일과, 패치만으로 되는지."""
    files = manifest["files"]
    need = sorted(rel for rel, meta in files.items()
                  if not (root / rel).is_file() or sha256(root / rel) != meta["sha256"])
    remove = sorted(rel for rel in local_manifest(root).get("files", {})
                    if rel not in files and tracked(rel))
    return {"version": manifest["version"], "files": need, "remove": remove,
            "patch": set(need) <= set(manifest.get("patch", []))}


def _get(url: str, timeout: float = 20):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout)


def latest_release() -> dict | None:
    """GitHub 배포 목록의 최신 버전 (초안 제외). 업데이트 파일이 있으면 그 주소도."""
    with _get(RELEASES, 10) as r:
        rows = json.load(r)
    row = next((x for x in rows if not x.get("draft")), None)
    if not row:
        return None
    m = re.search(r"(\d+\.\d+\.\d+)", row["tag_name"])
    assets = {}
    for a in row.get("assets", []):
        name = a.get("name", "")
        kind = ("manifest" if name.endswith("-manifest.json") else "patch" if name.endswith("-patch.zip")
                else "full" if name.endswith("-windows-x64.zip") else None)
        if kind:
            assets[kind] = {"url": a["browser_download_url"], "size": a.get("size")}
    return {"tag": row["tag_name"], "version": m[1] if m else None, "url": row["html_url"],
            "publishedAt": row.get("published_at"), "title": row.get("name"), "assets": assets}


def status() -> dict:
    root = install_root()
    with _lock:
        state = dict(_state)
    state["supported"] = root is not None
    if root is not None:
        state["installed"] = local_manifest(root).get("version")
    return state


def _set(**kw):
    with _lock:
        _state.update(kw)


def _download(url: str, dest: Path, total: int | None):
    _set(received=0, total=total or 0)
    with _get(url, 30) as r, open(dest, "wb") as f:
        total = total or int(r.headers.get("Content-Length") or 0)
        _set(total=total)
        received = 0
        while chunk := r.read(1 << 18):
            f.write(chunk)
            received += len(chunk)
            _set(received=received)


def _prepare(root: Path, release: dict):
    work = update_dir(root)
    staged = work / "staged"
    try:
        _set(phase="checking", version=release["version"], error=None, received=0, total=0)
        shutil.rmtree(work, ignore_errors=True)
        staged.mkdir(parents=True)
        assets = release["assets"]
        with _get(assets["manifest"]["url"]) as r:
            manifest = json.load(r)
        p = plan(root, manifest)
        mode = "patch" if p["patch"] and "patch" in assets else "full"
        _set(phase="downloading", mode=mode, count=len(p["files"]))
        archive = work / f"{mode}.zip"
        if p["files"]:
            _download(assets[mode]["url"], archive, assets[mode].get("size"))
            _set(phase="verifying")
            with zipfile.ZipFile(archive) as z:
                names = {n.split("/", 1)[1] if n.startswith("Vextrum/") else n: n for n in z.namelist()}
                for rel in p["files"]:
                    target = staged / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(names[rel]) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
                    if sha256(target) != manifest["files"][rel]["sha256"]:
                        raise ValueError(f"파일이 손상됐습니다: {rel}")
            archive.unlink()
        (staged / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        (staged / PLAN).write_text(json.dumps({"version": p["version"], "files": p["files"] + [MANIFEST],
                                               "remove": p["remove"]}, ensure_ascii=False), encoding="utf-8")
        _set(phase="ready")
    except Exception as e:  # noqa: BLE001 - 화면에 이유를 보여 준다
        shutil.rmtree(work, ignore_errors=True)
        _set(phase="error", error=str(e) or type(e).__name__)


def start(release: dict) -> dict:
    root = install_root()
    if root is None:
        raise RuntimeError("배포판에서만 앱 안에서 업데이트할 수 있습니다")
    if "manifest" not in release.get("assets", {}):
        raise RuntimeError("이 버전은 앱 안 업데이트 파일이 없습니다. 다운로드 페이지에서 받아 주세요")
    with _lock:
        if _state.get("phase") in ("checking", "downloading", "verifying"):
            return dict(_state)
        _state.clear()
        _state.update(phase="checking", version=release["version"])
    threading.Thread(target=_prepare, args=(root, release), daemon=True).start()
    return status()


APPLY_PS1 = r"""param([string]$Root)
$ErrorActionPreference = 'Stop'
$update = Join-Path $Root 'backend\data\update'
$staged = Join-Path $update 'staged'
$backup = Join-Path $update 'backup'
$log = Join-Path $update 'apply.log'
function Write-Log($m) { Add-Content -LiteralPath $log -Value ((Get-Date -Format s) + ' ' + $m) -Encoding UTF8 }
function Get-Busy($prefix) {
    @(Get-Process | Where-Object { $p = $null; try { $p = $_.Path } catch {}; $p -and $p.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) })
}
$plan = Get-Content -LiteralPath (Join-Path $staged 'update-plan.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Log ('apply ' + $plan.version + ': ' + $plan.files.Count + ' files')
$prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
$deadline = (Get-Date).AddSeconds(20)
while ((Get-Busy $prefix).Count -gt 0) {
    if ((Get-Date) -gt $deadline) {
        Get-Busy $prefix | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        break
    }
    Start-Sleep -Milliseconds 400
}
$done = New-Object System.Collections.ArrayList
try {
    foreach ($rel in $plan.files) {
        $dest = Join-Path $Root $rel
        $keep = Join-Path $backup $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
        if (Test-Path -LiteralPath $dest) {
            New-Item -ItemType Directory -Force -Path (Split-Path $keep) | Out-Null
            for ($i = 0; ; $i++) {
                try { Move-Item -LiteralPath $dest -Destination $keep -Force; break }
                catch { if ($i -ge 20) { throw }; Start-Sleep -Milliseconds 500 }
            }
        }
        [void]$done.Add($rel)
        Copy-Item -LiteralPath (Join-Path $staged $rel) -Destination $dest -Force
    }
    foreach ($rel in $plan.remove) {
        Remove-Item -LiteralPath (Join-Path $Root $rel) -Force -ErrorAction SilentlyContinue
    }
    Write-Log 'ok'
    Remove-Item -LiteralPath $staged -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    Write-Log ('failed, rolling back: ' + $_)
    foreach ($rel in $done) {
        $dest = Join-Path $Root $rel
        $keep = Join-Path $backup $rel
        Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $keep) { Move-Item -LiteralPath $keep -Destination $dest -Force }
    }
}
Start-Process -FilePath (Join-Path $Root 'Vextrum.exe') -WorkingDirectory $Root
"""


def apply_command() -> list[str]:
    """받아 둔 업데이트를 적용할 명령. 앱이 이 명령을 따로 띄운 뒤 스스로 종료한다."""
    root = install_root()
    if root is None or status().get("phase") != "ready" or not (update_dir(root) / "staged" / PLAN).is_file():
        raise RuntimeError("적용할 업데이트가 없습니다")
    script = update_dir(root) / "apply.ps1"
    script.write_text(APPLY_PS1, encoding="utf-8-sig")
    _set(phase="applying", at=time.time())
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
            "-File", str(script), "-Root", str(root)]
