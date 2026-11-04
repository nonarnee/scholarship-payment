"""메인 창 뼈대: 스테퍼 · (스크롤되는) 단계 본문 · 하단 버튼 바 · 상태 표시줄. 본문은 Phase 2~4에서 채운다(지금은 자리표시 화면).
Windows 기본 제목 표시줄을 쓴다. 업무 처리는 하지 않는다.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from scholarship_payment import __version__
from scholarship_payment.ui.navigation import STEP_TITLES, Navigator, Step
from scholarship_payment.ui.theme import FOOTER_HEIGHT, SPACING, STEPPER_HEIGHT, fit_window_size
from scholarship_payment.ui.widgets import AppButton, Card, StepperBar

PLACEHOLDER_NOTES = {
    Step.FILE: "사업, 원본 파일, 저장 폴더, 기준일을 선택하는 화면입니다(Phase 2).",
    Step.REVIEW: "지급 요약과 검증 결과를 읽기 전용으로 확인하는 화면입니다(Phase 3).",
    Step.RESULT: "변환 결과와 생성된 파일을 보여주는 화면입니다(Phase 4).",
}


def _placeholder(step: Step) -> QWidget:
    page = QWidget()
    lay = QVBoxLayout(page)
    m = SPACING["lg"]
    lay.setContentsMargins(m, m, m, m)
    card = Card(f"{int(step)}. {STEP_TITLES[step]}")
    note = QLabel(PLACEHOLDER_NOTES[step] + " — 개발 중인 자리표시 화면입니다.")
    note.setWordWrap(True)
    card.body.addWidget(note)
    lay.addWidget(card)
    lay.addStretch(1)
    return page


class MainWindow(QMainWindow):
    def __init__(self, available: QSize | None = None) -> None:
        super().__init__()
        self.setWindowTitle(f"장학금 지급명단 변환 v{__version__}")
        if available is None:
            screen = self.screen() or None
            geo = screen.availableGeometry() if screen else None
            available = geo.size() if geo else QSize(1920, 1080)
        (w, h), (min_w, min_h) = fit_window_size(available.width(), available.height())
        self.setMinimumSize(min_w, min_h)
        self.resize(w, h)

        self.navigator = Navigator()
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        col = QVBoxLayout(root)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        band = QFrame()
        band.setObjectName("TopBand")
        band.setFixedHeight(STEPPER_HEIGHT)
        bl = QHBoxLayout(band)
        bl.setContentsMargins(SPACING["xl"], 0, SPACING["xl"], 0)
        self.stepper = StepperBar([STEP_TITLES[s] for s in Step])
        bl.addWidget(self.stepper)
        col.addWidget(band)

        self.stack = QStackedWidget()
        for s in Step:
            self.stack.addWidget(_placeholder(s))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.stack)
        col.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("FooterBar")
        footer.setMinimumHeight(FOOTER_HEIGHT + SPACING["sm"] * 2)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(SPACING["xl"], SPACING["sm"], SPACING["xl"], SPACING["sm"])
        self.back_button = AppButton("이전", "secondary")
        self.next_button = AppButton("다음", "primary")
        fl.addWidget(self.back_button)
        fl.addStretch(1)
        fl.addWidget(self.next_button)
        col.addWidget(footer)
        self.back_button.clicked.connect(self.navigator.back)
        self.next_button.clicked.connect(self.navigator.next)

        version = QLabel(f"v{__version__}")
        notice = QLabel("이 프로그램은 네트워크를 사용하지 않습니다")
        self.statusBar().addWidget(notice, 1)
        self.statusBar().addPermanentWidget(version)
        self.statusBar().setSizeGripEnabled(False)

        self.setTabOrder(self.back_button, self.next_button)
        self.navigator.on_change(self._sync)
        self._sync()

    def set_step_ready(self, step: Step, ready: bool) -> None:
        self.navigator.set_ready(step, ready)

    def _sync(self) -> None:
        nav = self.navigator
        self.stack.setCurrentIndex(int(nav.current) - 1)
        self.stepper.set_state(current=int(nav.current) - 1, done={int(s) - 1 for s in nav.completed})
        self.back_button.setEnabled(nav.can_back())
        self.next_button.setEnabled(nav.can_next())
        self.next_button.setVisible(nav.current < Step.RESULT)
