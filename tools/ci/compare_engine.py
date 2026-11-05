"""두 산출물(PyInstaller onedir: 신규 Qt 화면과 legacy Tk 화면)이 **같은 변환 엔진**을 담고 있는지 비교한다.
실행 파일 안의 PYZ 아카이브에서 엔진 모듈(adapters·validation·writers·io·core·models·config·errors·app.convert)을 꺼내 컴파일된 바이트코드의 SHA-256 을 비교한다
(같은 소스·같은 Python 이면 같아야 한다). 화면 코드(ui, gui)와 공용 실행 계층(app.controller, app.workflow)은 비교 대상이 아니다.
사용: python tools/ci/compare_engine.py <qt 폴더> <legacy 폴더>
※ 이것은 '같은 엔진 코드가 들어 있다'는 확인이다. 두 실행 파일이 같은 출력을 만드는지는 골든 동등성 테스트(파이썬 수준)와 합성 E2E 가 따로 확인한다.
"""
from __future__ import annotations

import hashlib
import marshal
import sys
from pathlib import Path

ENGINE_PREFIXES = ("scholarship_payment.adapters", "scholarship_payment.validation", "scholarship_payment.writers", "scholarship_payment.io",
                   "scholarship_payment.core", "scholarship_payment.models", "scholarship_payment.config", "scholarship_payment.errors", "scholarship_payment.app.convert")
# 변환 엔진이 아닌 화면 지원 모듈(신규 화면의 사용자 설정 저장소). Tk 화면은 쓰지 않는다.
EXCLUDED = ("scholarship_payment.config.user_settings",)
sys.path.insert(0, str(Path(__file__).resolve().parent))


def engine_modules(names) -> list[str]:
    return sorted(n for n in names if n not in EXCLUDED and any(n == p or n.startswith(p + ".") for p in ENGINE_PREFIXES))


def compare(qt: dict[str, str], legacy: dict[str, str]) -> list[str]:
    problems = []
    if not qt and not legacy:
        return ["엔진 모듈을 하나도 찾지 못했다"]
    for n in sorted(set(qt) | set(legacy)):
        if n not in legacy:
            problems.append(f"legacy 에 없다: {n}")
        elif n not in qt:
            problems.append(f"Qt 에 없다: {n}")
        elif qt[n] != legacy[n]:
            problems.append(f"내용이 다르다: {n}")
    return problems


def digests(exe: Path) -> dict[str, str]:
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(exe))
    out: dict[str, str] = {}
    for entry in reader.toc:
        if entry.endswith(".pyz") or entry.startswith("PYZ"):
            pyz = reader.open_embedded_archive(entry)
            for name in engine_modules(pyz.toc):
                code = pyz.extract(name)
                out[name] = hashlib.sha256(marshal.dumps(code)).hexdigest() if code is not None else ""
    return out


def main(argv: list[str]) -> int:
    from inventory_dist import find_executable

    qt_exe, legacy_exe = find_executable(Path(argv[1])), find_executable(Path(argv[2]))
    if qt_exe is None or legacy_exe is None:
        print("실패: 실행 파일을 찾지 못했다")
        return 1
    qt, legacy = digests(qt_exe), digests(legacy_exe)
    problems = compare(qt, legacy)
    for p in problems:
        print("실패:", p)
    print(f"엔진 모듈 {len(qt)}개 비교: " + ("두 산출물의 엔진 바이트코드가 같다" if not problems else f"차이 {len(problems)}건"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
