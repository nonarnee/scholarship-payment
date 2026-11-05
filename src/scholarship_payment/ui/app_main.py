"""정식 PySide6 화면의 진입점(`packaging/run_gui_qt.py` 가 호출). 사용자용 옵션만 받는다:
  --smoke    창을 만들어 그려 보고 필요한 모듈이 모두 있는지 확인한 뒤 종료(기본 기동 확인, 설치 확인용)
  --version  앱과 주요 라이브러리 버전을 출력하고 종료
개발용 옵션(--gallery, --synthetic-e2e-smoke 등)은 **받지 않는다**(종료 코드 2, 아무 것도 실행하지 않음). 개발용 모듈은 이 파일에서 import 하지 않는다 —
그래서 정식 exe 에는 개발용 모듈이 들어가지 않는다(PyInstaller 도 이 진입점에서 출발한다).
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import platform
import sys

from scholarship_payment import __version__
from scholarship_payment.ui.safety import install_safe_excepthook


def _version_of(dist: str) -> str:
    """설치 메타데이터에서 읽고, 없으면(패키징 환경 등) 로드된 모듈의 __version__ 으로 대신한다. 둘 다 없으면 '확인 불가'."""
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        pass
    import importlib

    for mod in (dist.replace("-", "_"), dist.split("-")[0]):
        try:
            v = getattr(importlib.import_module(mod), "__version__", None)
        except Exception:
            v = None
        if isinstance(v, str) and v:
            return v
    return "확인 불가"


def version_text() -> str:
    """앱과 주요 라이브러리 버전(정보 화면·--version 공용 정본). 값은 실제로 로드된 모듈에서 읽는다."""
    import PySide6
    from PySide6.QtCore import qVersion

    rows = [("장학금 지급명단 변환", __version__), ("Python", platform.python_version()), ("PySide6", PySide6.__version__), ("Qt", qVersion()),
            ("openpyxl", _version_of("openpyxl")), ("msoffcrypto-tool", _version_of("msoffcrypto-tool")), ("cryptography", _version_of("cryptography"))]
    return "\n".join(f"{name}: {value}" for name, value in rows)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ScholarshipPayment", allow_abbrev=False, add_help=False)
    ap.add_argument("--smoke", action="store_true", help="창을 만들어 그려 보고 종료한다(기동 확인)")
    ap.add_argument("--version", action="store_true", help="버전을 출력하고 종료한다")
    return ap


def create_window(context=None):
    from scholarship_payment.ui.main_window import MainWindow

    return MainWindow(context=context)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:                                   # 알 수 없는 옵션(개발용 옵션 포함): 아무 것도 실행하지 않고 종료
        return int(e.code or 2)
    if args.version:
        print(version_text())
        return 0
    install_safe_excepthook()
    from PySide6.QtWidgets import QApplication

    from scholarship_payment.ui.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app)
    if args.smoke:
        from scholarship_payment.ui import runtime_check

        missing = runtime_check.missing_modules()
        window = create_window()
        window.show()
        app.processEvents()
        ok = not window.grab().isNull() and not missing
        window.close()
        print("ui smoke ok" if ok else "ui smoke FAILED")
        return 0 if ok else 1
    window = create_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
