"""배포 후보 빌드(PyInstaller onedir) 구성: 신규 PySide6 화면(qt, 기본 산출물) / 기존 Tkinter 화면(legacy, 병행) / 개발용 확인 빌드(dev, 합성 E2E 전용).
사용: python packaging/build_release.py --kind qt|legacy|dev [--dist DIR] [--work DIR] [--no-windowed]
- qt/legacy 는 Windows 버전 리소스, 배포 자료(안내문·라이선스·고지문·BUILD-INFO), SHA256SUMS 를 함께 만든다. dev 는 사용자에게 배포하지 않는다.
- qt 는 개발 모드 모듈(갤러리·E2E 스모크·개발용 진입점)과 tkinter 를 실행 파일에서 제외한다.
- 요청한 사실만 기록한다: BUILD-INFO 의 버전은 실제로 설치된 패키지에서 읽는다.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


release_info = _load("release_info")
notices = _load("make_release_notices")

ENTRY = {"qt": "run_gui_qt.py", "legacy": "run_gui.py", "dev": "run_ui_dev.py"}
# 실행 중에 버전·라이선스를 읽을 수 있도록 패키지 메타데이터(dist-info)를 함께 넣는다(정보 화면·--version 이 사용).
METADATA_COMMON = ("openpyxl", "et-xmlfile", "msoffcrypto-tool", "cryptography", "olefile")
METADATA_QT = ("PySide6-Essentials", "shiboken6")
DEV_ONLY_MODULES = ("scholarship_payment.ui.gallery", "scholarship_payment.ui.e2e_smoke", "scholarship_payment.ui.__main__")


def pyinstaller_args(kind: str, version: str, windowed: bool, dist: str = "dist", work: str = "build", version_file: str = "version_info.txt") -> list[str]:
    name = release_info.exe_name(kind, version)
    args = ["--noconfirm", "--onedir", "--name", name, "--distpath", dist, "--workpath", work, "--specpath", work, "--paths", str(ROOT / "src"),
            "--collect-submodules", "msoffcrypto"]
    for dist in METADATA_COMMON + (METADATA_QT if kind in ("qt", "dev") else ()):
        args += ["--copy-metadata", dist]
    if windowed:
        args.append("--windowed")
    if kind in ("qt", "legacy"):
        args += ["--version-file", version_file]
    if kind in ("qt", "dev"):
        args += ["--exclude-module", "PySide6.QtNetwork"]
    if kind == "qt":
        for mod in (*DEV_ONLY_MODULES, "tkinter", "scholarship_payment.gui"):
            args += ["--exclude-module", mod]
    args.append(str(PKG / ENTRY[kind]))
    return args


def write_checksums(app_dir: Path, exe_file: str) -> list[str]:
    """실행 파일, 최상위 안내문, LICENSES 폴더 파일의 SHA-256 을 SHA256SUMS.txt 에 쓴다(_internal 의 수많은 파일은 제외)."""
    targets = [app_dir / exe_file] + sorted(p for p in app_dir.iterdir() if p.is_file() and p.suffix == ".txt" and p.name != "SHA256SUMS.txt")
    lic = app_dir / "LICENSES"
    if lic.is_dir():
        targets += sorted(p for p in lic.rglob("*") if p.is_file())
    lines = []
    for p in targets:
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()} *{p.relative_to(app_dir).as_posix()}")
    (app_dir / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def build_info(kind: str) -> str:
    version = release_info.current_version()

    def dist(n):
        try:
            return metadata.version(n)
        except metadata.PackageNotFoundError:
            return "설치 안 됨"

    rows = [("제품", "장학금 지급명단 변환"), ("버전", version), ("종류", {"qt": "신규 PySide6 화면(기본)", "legacy": "기존 Tkinter 화면(legacy, 병행)", "dev": "개발용 확인 빌드"}[kind]),
            ("커밋", os.environ.get("GITHUB_SHA", "")[:7] or "확인 불가(로컬 빌드)"), ("Python", platform.python_version()), ("빌드 OS", platform.platform()),
            ("PyInstaller", dist("pyinstaller")), ("openpyxl", dist("openpyxl")), ("msoffcrypto-tool", dist("msoffcrypto-tool")), ("cryptography", dist("cryptography"))]
    if kind != "legacy":
        rows += [("PySide6-Essentials", dist("PySide6-Essentials")), ("shiboken6", dist("shiboken6"))]
        try:
            from PySide6.QtCore import qVersion

            rows.append(("Qt", qVersion()))
        except Exception:
            rows.append(("Qt", "확인 불가"))
    return "\n".join(f"{k}: {v}" for k, v in rows) + "\n"


def install_assets(kind: str, app_dir: Path) -> None:
    """배포 자료를 복사하고 고지문·BUILD-INFO 를 생성한다. 실행 파일은 건드리지 않는다."""
    assets = PKG / "dist_assets"
    app_dir.mkdir(parents=True, exist_ok=True)
    if kind == "qt":
        shutil.copy2(assets / "README-설치.txt", app_dir / "README-설치.txt")
    elif kind == "legacy":
        shutil.copy2(assets / "README-LEGACY.txt", app_dir / "README-LEGACY.txt")
    else:
        return
    lic = app_dir / "LICENSES"
    lic.mkdir(exist_ok=True)
    if kind == "qt":
        for f in ("LGPL-3.0.txt", "GPL-3.0.txt", "README-LICENSES.txt", "RELINK-Qt.txt"):
            shutil.copy2(assets / "LICENSES" / f, lic / f)
    else:
        shutil.copy2(assets / "LICENSES" / "README-LICENSES.txt", lic / "README-LICENSES.txt")
    (lic / "THIRD-PARTY-NOTICES.txt").write_text(notices.render(kind), encoding="utf-8")
    (app_dir / "BUILD-INFO.txt").write_text(build_info(kind), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=("qt", "legacy", "dev"))
    ap.add_argument("--dist", default="dist")
    ap.add_argument("--work", default="build")
    ap.add_argument("--no-windowed", action="store_true", help="콘솔 앱으로 빌드(로컬 확인용). Windows 에서는 쓰지 않는다")
    args = ap.parse_args(argv)
    version = release_info.current_version()
    name = release_info.exe_name(args.kind, version)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    version_file = work / f"version_info_{args.kind}.txt"
    if args.kind in ("qt", "legacy"):
        vi = _load("make_version_info")
        vi_text = vi.render(version, name)
        version_file.write_text(vi_text, encoding="utf-8")
    cmd = [sys.executable, "-m", "PyInstaller", *pyinstaller_args(args.kind, version, windowed=not args.no_windowed, dist=args.dist, work=args.work, version_file=str(version_file))]
    subprocess.run(cmd, check=True)
    app_dir = Path(args.dist) / name
    exe_file = name + (".exe" if sys.platform == "win32" else "")
    if args.kind in ("qt", "legacy"):
        install_assets(args.kind, app_dir)
        for line in write_checksums(app_dir, exe_file):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
