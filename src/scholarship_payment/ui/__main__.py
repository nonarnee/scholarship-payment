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
from scholarship_payment.ui.theme import apply_theme


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scholarship_payment.ui")
    ap.add_argument("--gallery", action="store_true", help="컴포넌트 갤러리를 연다")
    ap.add_argument("--smoke", action="store_true", help="창을 만들어 그려 본 뒤 종료한다")
    args = ap.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app)
    window = build_gallery() if args.gallery else MainWindow()
    if not args.gallery and not args.smoke:
        for step in (Step.FILE, Step.REVIEW):          # 개발용: 자리표시 화면을 눌러 볼 수 있도록 선행 조건을 열어 둔다
            window.set_step_ready(step, True)
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
