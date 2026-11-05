"""산출물(PyInstaller onedir 폴더) 점검: 실제로 들어 있는 Qt 라이브러리·PySide6 모듈·플러그인 목록을 만들고, 필수 파일 누락과 금지 항목을 확인한다.
사용: python tools/ci/inventory_dist.py <폴더> --kind qt|legacy|dev [--platform windows|auto] [--json 출력.json] [--no-pyz]
- 실패(종료 코드 1): 필수 Qt 파일·플랫폼 플러그인·배포 자료 누락, QtNetwork 바인딩, 정책·템플릿·엑셀 파일 포함, (qt) 개발용 모듈이 실행 파일 안에 있음
- 실패가 아닌 '검토 필요': 코드가 직접 쓰지 않는 Qt 라이브러리(예: Qt6Svg, 전이 의존성으로 들어온 Qt6Network)가 들어 있음 — 라이선스 검토 대상 목록(review_qt_libraries)으로 남긴다.
이 목록은 **이 산출물을 만든 플랫폼 기준**이다. Windows 목록은 Windows 러너에서 만든 것만 Windows 산출물의 근거가 된다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ALLOWED_QT = {"Qt6Core", "Qt6Gui", "Qt6Widgets", "Qt6DBus"}                 # 코드가 직접 쓰는 모듈(+리눅스 보조)
ALLOWED_PYSIDE = {"QtCore", "QtGui", "QtWidgets"}
DEV_MODULES = ("scholarship_payment.ui.gallery", "scholarship_payment.ui.e2e_smoke", "scholarship_payment.ui.__main__")
REQUIRED_DOCS_QT = ("README-설치.txt", "BUILD-INFO.txt", "SHA256SUMS.txt", "LICENSES/LGPL-3.0.txt", "LICENSES/GPL-3.0.txt", "LICENSES/THIRD-PARTY-NOTICES.txt",
                    "LICENSES/README-LICENSES.txt", "LICENSES/RELINK-Qt.txt")
REQUIRED_DOCS_LEGACY = ("README-LEGACY.txt", "BUILD-INFO.txt", "SHA256SUMS.txt", "LICENSES/THIRD-PARTY-NOTICES.txt", "LICENSES/README-LICENSES.txt")
PLATFORM_PLUGIN = {"windows": "platforms/qwindows.dll", "darwin": "platforms/libqcocoa.dylib", "linux": "platforms/libqxcb.so"}
QT_LIB = re.compile(r"^(?:lib)?(Qt6\w+?)(?:\.\d+(?:\.\d+)*)?(?:\.dll|\.dylib|\.so(?:\.[\d.]+)?)?$")


def _platform(value: str) -> str:
    if value != "auto":
        return value
    return {"win32": "windows", "darwin": "darwin"}.get(sys.platform, "linux")


FRAMEWORK = re.compile(r"(Qt\w+)\.framework")


def find_executable(root: Path) -> Path | None:
    """배포 폴더 최상위의 실행 파일(Windows: .exe, macOS/Linux: 확장자 없는 파일). 버전 문자열의 점을 확장자로 오해하지 않는다."""
    cands = sorted(p for p in Path(root).iterdir() if p.is_file() and p.name.startswith("ScholarshipPayment") and not p.name.endswith((".txt", ".json")))
    return next((p for p in cands if p.name.endswith(".exe")), cands[0] if cands else None)


def _qt_library_name(path: Path) -> str | None:
    fw = next((FRAMEWORK.fullmatch(part) for part in path.parts if FRAMEWORK.fullmatch(part)), None)
    if fw and path.name == fw.group(1):                       # macOS: QtCore.framework/Versions/A/QtCore
        return "Qt6" + fw.group(1)[2:]
    m = QT_LIB.match(path.name)
    if m and (path.suffix in (".dll", ".dylib") or ".so" in path.name or path.name.startswith("Qt6")):
        return m.group(1)
    return None


def pyz_modules(exe: Path) -> set[str]:
    """실행 파일에 포함된 파이썬 모듈 이름(PyInstaller 아카이브). 읽을 수 없으면 빈 집합."""
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(exe))
    names: set[str] = set()
    for entry in reader.toc:
        if entry.endswith(".pyz") or entry.startswith("PYZ"):
            names |= set(reader.open_embedded_archive(entry).toc)
    return names


def inspect(root, kind: str, platform: str = "auto", check_pyz: bool = True) -> dict:
    root = Path(root)
    plat = _platform(platform)
    files = [p for p in root.rglob("*") if p.is_file()]
    rel = {p.relative_to(root).as_posix(): p for p in files}
    problems: list[str] = []
    qt_libs = sorted({n for p in files if (n := _qt_library_name(p))})
    pyside = sorted({m.group(1) for p in files if (m := re.fullmatch(r"(Qt\w+)(?:\.abi3)?\.(?:pyd|so)", p.name))})
    plugins = sorted(re.split(r"PySide6/(?:Qt/)?plugins/", k, maxsplit=1)[1] for k in rel if re.search(r"PySide6/(?:Qt/)?plugins/", k))
    report = {"kind": kind, "platform": plat, "qt_libraries": qt_libs, "pyside_modules": pyside, "plugins": plugins,
              "review_qt_libraries": sorted(set(qt_libs) - ALLOWED_QT), "review_pyside_modules": sorted(set(pyside) - ALLOWED_PYSIDE), "files": len(files), "problems": problems}
    if kind in ("qt", "dev"):
        for need in ("Qt6Core", "Qt6Gui", "Qt6Widgets"):
            if need not in qt_libs:
                problems.append(f"필수 Qt 라이브러리 없음: {need}")
        for need in ("QtCore", "QtGui", "QtWidgets"):
            if need not in pyside:
                problems.append(f"필수 PySide6 모듈 없음: {need}")
        if not any(k.rsplit("/", 1)[-1].lower().startswith(("shiboken6", "libshiboken6")) for k in rel):
            problems.append("shiboken6 라이브러리 없음")
        wanted = PLATFORM_PLUGIN.get(plat)
        if wanted and wanted not in plugins:
            problems.append(f"Qt 플랫폼 플러그인 없음: {wanted}")
        if "QtNetwork" in pyside:
            problems.append("QtNetwork 바인딩이 들어 있다")
    for k, p in rel.items():
        n = p.name.lower()
        if n.endswith((".xlsx", ".xlsm", ".xls")):
            problems.append(f"엑셀 파일(xlsx)이 들어 있다: {k}")
        if n.startswith("policy_") and n.endswith(".json"):
            problems.append(f"정책 파일이 들어 있다: {k}")
        if n.startswith("template_"):
            problems.append(f"템플릿 파일이 들어 있다: {k}")
    if kind in ("qt", "legacy"):
        for doc in (REQUIRED_DOCS_QT if kind == "qt" else REQUIRED_DOCS_LEGACY):
            if doc not in rel:
                problems.append(f"배포 자료 없음: {doc}")
    notice_file = rel.get("LICENSES/THIRD-PARTY-NOTICES.txt")
    if notice_file is not None and "이 패키지에서 라이선스 파일을 찾지 못했습니다" in notice_file.read_text(encoding="utf-8", errors="replace"):
        problems.append("제3자 고지문에 라이선스 전문이 빠진 패키지가 있다")
    if check_pyz:
        exe = find_executable(root)
        if exe is None:
            problems.append("실행 파일을 찾지 못했다")
        else:
            try:
                names = pyz_modules(exe)
            except Exception as e:
                problems.append(f"실행 파일의 모듈 목록을 읽지 못했다: {type(e).__name__}")
            else:
                report["bundled_modules_checked"] = len(names)
                have = lambda prefix: any(n == prefix or n.startswith(prefix + ".") for n in names)  # noqa: E731
                required = ["openpyxl", "msoffcrypto", "scholarship_payment.app.convert", "scholarship_payment.adapters.daechung", "scholarship_payment.writers.template_writer",
                            "scholarship_payment.io.safe_save"]
                required += ["scholarship_payment.ui.app_main", "scholarship_payment.ui.step3"] if kind == "qt" else ["scholarship_payment.gui.app"] if kind == "legacy" else ["scholarship_payment.ui.e2e_smoke"]
                for mod in required:
                    if not have(mod):
                        problems.append(f"실행 파일에 필요한 모듈이 없다: {mod}")
                if kind == "qt":
                    for mod in DEV_MODULES:
                        if have(mod):
                            problems.append(f"개발용 모듈이 실행 파일에 들어 있다: {mod}")
                    if have("tkinter") or have("scholarship_payment.gui"):
                        problems.append("Tkinter 화면 관련 모듈이 Qt 실행 파일에 들어 있다")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--kind", required=True, choices=("qt", "legacy", "dev"))
    ap.add_argument("--platform", default="auto", choices=("auto", "windows", "darwin", "linux"))
    ap.add_argument("--json")
    ap.add_argument("--no-pyz", action="store_true")
    a = ap.parse_args(argv)
    r = inspect(a.root, a.kind, a.platform, check_pyz=not a.no_pyz)
    if a.json:
        Path(a.json).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Qt 라이브러리: {', '.join(r['qt_libraries']) or '없음'}")
    print(f"PySide6 모듈: {', '.join(r['pyside_modules']) or '없음'}")
    print(f"검토 필요한 Qt 라이브러리: {', '.join(r['review_qt_libraries']) or '없음'}")
    print(f"검토 필요한 PySide6 모듈: {', '.join(r['review_pyside_modules']) or '없음'}")
    for p in r["problems"]:
        print("실패:", p)
    print("산출물 점검 " + ("통과" if not r["problems"] else f"실패({len(r['problems'])}건)"))
    return 1 if r["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
