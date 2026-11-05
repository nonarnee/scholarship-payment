"""개발용 진입점: `python -m scholarship_payment.ui [--gallery] [--smoke]`.
--smoke: 창을 만들고 이벤트를 한 번 처리한 뒤 화면을 그려 보고 종료한다(종료 코드 0). CI 패키징 확인용이며 창을 계속 띄우지 않는다.
"""
from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from scholarship_payment.ui.gallery import build_gallery
from scholarship_payment.ui.main_window import MainWindow
from scholarship_payment.ui.navigation import Step
from scholarship_payment.ui.safety import install_safe_excepthook  # noqa: F401  (기존 이름 유지)
from scholarship_payment.ui.theme import apply_theme


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scholarship_payment.ui")
    ap.add_argument("--gallery", action="store_true", help="컴포넌트 갤러리를 연다")
    ap.add_argument("--smoke", action="store_true", help="창을 만들어 그려 본 뒤 종료한다")
    ap.add_argument("--synthetic-e2e-smoke", action="store_true", help="합성 입력으로 Step 1→2→3 생성 경로를 끝까지 실행한다(CI 의 패키징 검증용)")
    ap.add_argument("--work-dir", help="--synthetic-e2e-smoke: tools/ci/prepare_e2e_inputs.py 가 만든 작업 폴더")
    ap.add_argument("--result-json", help="--synthetic-e2e-smoke: 결과를 쓸 JSON 파일")
    args = ap.parse_args(argv)
    if args.synthetic_e2e_smoke and not (args.work_dir and args.result_json):
        print("--synthetic-e2e-smoke 에는 --work-dir 과 --result-json 이 필요합니다", file=sys.stderr)
        return 2

    install_safe_excepthook()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app)
    if args.synthetic_e2e_smoke:
        from pathlib import Path

        from scholarship_payment.ui.e2e_smoke import run

        return run(Path(args.work_dir), Path(args.result_json))
    window = build_gallery() if args.gallery else MainWindow()
    if not args.gallery and not args.smoke:
        pass
    window.show()
    app.processEvents()
    if args.smoke:
        ok = not window.grab().isNull()
        window.close()
        print("ui smoke ok" if ok else "ui smoke FAILED")
        return 0 if ok else 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
