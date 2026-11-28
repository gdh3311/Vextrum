import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app import updater


def write(root: Path, files: dict):
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)


def make_zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for rel, data in files.items():
            z.writestr("Vextrum/" + rel, data)
    return buf.getvalue()


class Response(io.BytesIO):
    headers: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


OLD = {"Vextrum.exe": b"exe", "data/app.so": b"app-1", "backend/vextrum-backend.exe": b"be-1", "old.txt": b"x",
       "backend/data/research.sqlite": b"mine"}
NEW = {"Vextrum.exe": b"exe", "data/app.so": b"app-2", "backend/vextrum-backend.exe": b"be-2",
       "읽어 주세요.txt": "1.24".encode()}


class UpdaterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "Vextrum"
        write(self.root, OLD)
        old = updater.build_manifest(self.root, "1.23.0")
        (self.root / updater.MANIFEST).write_text(json.dumps(old), encoding="utf-8")
        new_dir = self.tmp / "new"
        write(new_dir, NEW)
        self.manifest = updater.build_manifest(new_dir, "1.24.0")
        self.manifest["patch"] = ["data/app.so", "backend/vextrum-backend.exe", "읽어 주세요.txt"]
        self.served = {
            "m": json.dumps(self.manifest).encode(),
            "p": make_zip({rel: NEW[rel] for rel in self.manifest["patch"]}),
            "f": make_zip(NEW),
        }
        self.release = {"version": "1.24.0", "assets": {"manifest": {"url": "m"}, "patch": {"url": "p"},
                                                        "full": {"url": "f"}}}
        updater._state.clear()
        updater._state["phase"] = "idle"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fetch(self, url, timeout=20):
        return Response(self.served[url])

    def test_plan_skips_user_data_and_unchanged_files(self):
        p = updater.plan(self.root, self.manifest)
        self.assertEqual(p["files"], ["backend/vextrum-backend.exe", "data/app.so", "읽어 주세요.txt"])
        self.assertEqual(p["remove"], ["old.txt"])
        self.assertTrue(p["patch"])
        self.assertNotIn("backend/data/research.sqlite", updater.build_manifest(self.root, "x")["files"])

    def prepare(self):
        with patch.object(updater, "_get", side_effect=self.fetch):
            updater._prepare(self.root, self.release)
        return updater._state

    def test_prepare_stages_verified_patch(self):
        state = self.prepare()
        self.assertEqual((state["phase"], state["mode"]), ("ready", "patch"), state.get("error"))
        staged = updater.update_dir(self.root) / "staged"
        self.assertEqual((staged / "data/app.so").read_bytes(), b"app-2")
        plan = json.loads((staged / updater.PLAN).read_text(encoding="utf-8"))
        self.assertIn(updater.MANIFEST, plan["files"])

    def test_full_archive_when_patch_does_not_cover_local_files(self):
        (self.root / "Vextrum.exe").write_bytes(b"tampered")
        state = self.prepare()
        self.assertEqual((state["phase"], state["mode"]), ("ready", "full"))

    def test_corrupt_download_is_rejected(self):
        self.served["p"] = make_zip({rel: b"bad" for rel in self.manifest["patch"]})
        state = self.prepare()
        self.assertEqual(state["phase"], "error")
        self.assertFalse(updater.update_dir(self.root).exists())

    @unittest.skipUnless(sys.platform == "win32", "PowerShell apply script")
    def test_apply_script_swaps_files_and_keeps_user_data(self):
        shutil.copy(Path(r"C:\Windows\System32\whoami.exe"), self.root / "Vextrum.exe")  # 다시 켜는 대상
        self.manifest["files"]["Vextrum.exe"] = {"sha256": updater.sha256(self.root / "Vextrum.exe"), "size": 1}
        self.served["m"] = json.dumps(self.manifest).encode()
        self.assertEqual(self.prepare()["phase"], "ready")
        with patch.object(updater, "install_root", return_value=self.root):
            cmd = updater.apply_command()
        subprocess.run(cmd, check=True, timeout=120)
        self.assertEqual((self.root / "data/app.so").read_bytes(), b"app-2")
        self.assertEqual((self.root / "읽어 주세요.txt").read_bytes(), "1.24".encode())
        self.assertFalse((self.root / "old.txt").exists())
        self.assertEqual((self.root / "backend/data/research.sqlite").read_bytes(), b"mine")
        self.assertEqual(updater.local_manifest(self.root)["version"], "1.24.0")
        self.assertFalse((updater.update_dir(self.root) / "staged").exists())
        time.sleep(.5)

    @unittest.skipUnless(sys.platform == "win32", "PowerShell apply script")
    def test_apply_script_rolls_back_when_a_file_cannot_be_copied(self):
        shutil.copy(Path(r"C:\Windows\System32\whoami.exe"), self.root / "Vextrum.exe")
        self.manifest["files"]["Vextrum.exe"] = {"sha256": updater.sha256(self.root / "Vextrum.exe"), "size": 1}
        self.served["m"] = json.dumps(self.manifest).encode()
        self.prepare()
        (updater.update_dir(self.root) / "staged" / "data/app.so").unlink()  # 복사 중 실패
        with patch.object(updater, "install_root", return_value=self.root):
            subprocess.run(updater.apply_command(), check=True, timeout=120)
        self.assertEqual((self.root / "data/app.so").read_bytes(), b"app-1")
        self.assertEqual((self.root / "backend/vextrum-backend.exe").read_bytes(), b"be-1")
        self.assertIn("rolling back", (updater.update_dir(self.root) / "apply.log").read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
