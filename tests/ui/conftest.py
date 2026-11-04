"""UI 테스트 공통: Qt 를 화면 없이(offscreen) 실행한다. PySide6 가 없으면(extra `gui` 미설치) 이 폴더의 테스트는 건너뛴다.
테스트는 완전 합성 데이터만 쓴다(실제 학생·파일 정보 없음)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from scholarship_payment.ui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app
