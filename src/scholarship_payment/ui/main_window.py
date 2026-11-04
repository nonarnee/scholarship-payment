"""메인 창 뼈대: 스테퍼 · (스크롤되는) 단계 본문 · 하단 버튼 바 · 상태 표시줄. 본문은 Phase 2~4에서 채운다(지금은 자리표시 화면).
Windows 기본 제목 표시줄을 쓴다. 업무 처리는 하지 않는다.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from scholarship_payment import __version__
from scholarship_payment.ui.context import AppContext
from scholarship_payment.ui.navigation import STEP_TITLES, Navigator, Step
from scholarship_payment.ui import generation as gn
from scholarship_payment.ui import preview as pv
from scholarship_payment.ui.generation import GenerationSession
from scholarship_payment.ui.preview import PreviewSession
from scholarship_payment.ui.state import Step1Model
from scholarship_payment.ui.step2 import Step2Page
from scholarship_payment.ui.step3 import Step3Page
from scholarship_payment.ui.step1 import BLOCKING_LABELS, Step1Page
from scholarship_payment.ui.theme import FOOTER_HEIGHT, SPACING, STEPPER_HEIGHT, fit_window_size
from scholarship_payment.ui.widgets import AppButton, Card, StepperBar

PLACEHOLDER_NOTES = {
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
    def __init__(self, available: QSize | None = None, context: AppContext | None = None) -> None:
        super().__init__()
        self.context = context or AppContext.default()
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

        self.model = Step1Model(self.context.store, self.context.runner, today=self.context.today, default_dirs=self.context.default_dirs)
        self.step1 = Step1Page(self.model, self.context)
        self.step2 = Step2Page(PreviewSession(self.context.runner), self.context)
        self.generation = GenerationSession(self.context.gen_runner, now=self.context.now)         # 생성 전용 워커
        self.step3 = Step3Page(self.generation, self.step2.session, self.model, self.context, open_settings=lambda: self.step1.open_settings(),
                               go_file=self.restart_from_file_selection, new_conversion=self.start_new_conversion)
        self.stack = QStackedWidget()
        for s in Step:
            self.stack.addWidget({Step.FILE: self.step1, Step.REVIEW: self.step2, Step.RESULT: self.step3}[s])
        self._shown = Step.FILE
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
        self.footer_hint = QLabel("")
        self.footer_hint.setProperty("role", "hint")
        fl.addWidget(self.back_button)
        fl.addStretch(1)
        fl.addWidget(self.footer_hint)
        fl.addSpacing(SPACING["md"])
        fl.addWidget(self.next_button)
        col.addWidget(footer)
        self.back_button.clicked.connect(self.navigator.back)
        self.next_button.clicked.connect(self._on_next)

        version = QLabel(f"v{__version__}")
        notice = QLabel("이 프로그램은 네트워크를 사용하지 않습니다")
        self.statusBar().addWidget(notice, 1)
        self.statusBar().addPermanentWidget(version)
        self.statusBar().setSizeGripEnabled(False)

        self.setTabOrder(self.step1.replace_button, self.back_button)
        self.setTabOrder(self.back_button, self.next_button)
        self.navigator.on_change(self._sync)
        self.model.on_change(self._sync_ready)
        self.step2.session.on_change(self._sync_hint)
        self.step2.session.on_change(self._sync_review_ready)
        self.generation.on_change(self._on_generation_change)
        self._sync_ready()
        self._sync_review_ready()
        self._sync()

    def _on_next(self) -> None:
        if self.navigator.current == Step.RESULT:
            return                                       # 이미 생성 단계다(중복 클릭으로 다시 시작하지 않는다)
        if self.navigator.current == Step.FILE:
            self.model.recheck()                         # 선택 후 파일이 사라졌거나 바뀌었는지 다시 확인하고, 아니면 이동하지 않는다
            if not self.model.ready():
                return
        self.navigator.next()

    def _sync_ready(self) -> None:
        self.navigator.set_ready(Step.FILE, self.model.ready())
        self._sync_hint()

    def _sync_review_ready(self) -> None:
        self.navigator.set_ready(Step.REVIEW, self.step2.session.state == pv.READY)      # 미리보기가 READY 일 때만 '지급명단 생성'을 누를 수 있다

    def _on_generation_change(self) -> None:
        """생성 상태가 바뀔 때의 창 차원 반응: 이동 잠금, 사용한 확인 결과 폐기, 무효화."""
        g = self.generation
        self.navigator.set_locked(g.busy or g.done)                    # 생성 중과 성공 후에는 이동을 막는다(새 변환만 가능)
        if g.done:
            self.step2.session.consume()                               # 같은 확인 결과로 다시 만들 수 없게 한다
            self.navigator.set_ready(Step.RESULT, True)
        elif g.state == gn.INVALIDATED and g.outcome is not None:
            self.step2.session.invalidate(pv.REASON_FILES_CHANGED, g.outcome.changed_codes)
            self.navigator.back()                                      # 지급내역 확인으로 돌려보내 사용자가 다시 확인하게 한다(자동 재생성 없음)
        elif g.state == gn.FAILED and g.failure_kind != gn.KIND_FOLDER:
            self.step2.session.invalidate(pv.REASON_GENERATION_FAILED)  # 폴더 오류가 아니면 같은 확인 결과를 다시 쓰지 않는다
        self._sync()

    def restart_from_file_selection(self) -> None:
        """실패 화면에서: 선택한 파일은 유지한 채 처음 단계로 돌아가 다시 확인한다."""
        if self.generation.busy:
            return
        self.generation.reset()
        self.navigator.go(Step.FILE)

    def start_new_conversion(self) -> None:
        """새 변환: 결과·확인 결과·선택한 원본을 모두 버리고 처음으로 돌아간다(생성 중에는 거부)."""
        if self.generation.busy:
            return
        self.generation.reset()
        self.step2.leave()
        self.navigator.reset()
        self.model.set_source(None)
        self._sync_ready()
        self._sync_review_ready()

    def _sync_hint(self) -> None:
        """다음 버튼이 막힌 이유를 푸터에 보여 준다. 본문이 스크롤되어 상태 줄이 가려져도 알 수 있게 한다."""
        if self.navigator.current == Step.REVIEW:
            self.footer_hint.setText(self.step2.hint_text())
            return
        needed = [BLOCKING_LABELS[f] for f in self.model.blocking()] if self.navigator.current == Step.FILE else []
        self.footer_hint.setText("필요: " + ", ".join(needed) if needed else "")

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() and self.navigator.current == Step.REVIEW:
            self.step2.refresh_freshness()               # 다른 프로그램에서 파일을 고치고 돌아온 경우를 감지한다

    def closeEvent(self, event) -> None:
        if self.generation.busy:
            # 저장 중에는 닫을 수 없다: 워커·세션·위젯을 건드리지 않고 거부만 한다(강제 종료는 지원하지 않는다)
            event.ignore()
            self.statusBar().showMessage("저장 중에는 창을 닫을 수 없습니다. 저장이 끝난 뒤 닫을 수 있습니다.", 8000)
            self.step3.show_close_blocked()
            return
        self.generation.close()                          # 이후에 늦게 도착하는 결과는 무시한다
        self.step2.leave()
        for runner in {id(r): r for r in (self.context.runner, self.context.gen_runner)}.values():
            shutdown = getattr(runner, "shutdown", None)
            if shutdown:
                shutdown()
        super().closeEvent(event)

    def set_step_ready(self, step: Step, ready: bool) -> None:
        self.navigator.set_ready(step, ready)

    def _sync(self) -> None:
        nav = self.navigator
        self.stack.setCurrentIndex(int(nav.current) - 1)
        self.stepper.set_state(current=int(nav.current) - 1, done={int(s) - 1 for s in nav.completed} | ({int(Step.RESULT) - 1} if self.generation.done else set()))
        self.back_button.setEnabled(nav.can_back())
        self.next_button.setEnabled(nav.can_next())
        self.next_button.setVisible(nav.current < Step.RESULT)
        self.next_button.setText({Step.FILE: "다음: 지급내역 확인", Step.REVIEW: "지급명단 생성"}.get(nav.current, "다음"))
        self.next_button.setToolTip("")
        if nav.current != self._shown:
            prev, self._shown = self._shown, nav.current
            if prev == Step.REVIEW and nav.current == Step.FILE:
                self.step2.leave()                       # 처음 단계로: 진행 중 결과와 비밀번호 시도를 모두 버린다
                self.generation.reset()
            elif prev == Step.RESULT and nav.current == Step.FILE:
                self.step2.leave()
                self.generation.reset()
            if nav.current == Step.REVIEW:
                if prev == Step.RESULT:
                    self.step2.enter(self.step2._selection, resume=True)     # 이미 있는 확인 결과를 그대로 보여 준다(다시 읽지 않음)
                else:
                    self.step2.enter(self.model.snapshot())
            elif nav.current == Step.RESULT:
                self.step3.enter(self.step2._selection)  # 확인 결과를 버리지 않고 생성을 시작한다
        self._sync_hint()
