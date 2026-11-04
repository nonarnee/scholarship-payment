"""개발용 컴포넌트 갤러리(시각 검증·DPI 확인용). 실제 업무 화면이 아니며 가상 문구만 쓴다."""
from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from scholarship_payment.ui.navigation import STEP_TITLES, Step
from scholarship_payment.ui.theme import SPACING
from scholarship_payment.ui.widgets import BADGE_KINDS, AppButton, Badge, Card, StepperBar

BADGE_TEXT = {"verified": "통과", "caution": "확인 필요", "error": "차단", "info": "참고", "neutral": "대기"}


def build_gallery() -> QWidget:
    root = QWidget()
    root.setObjectName("AppRoot")
    col = QVBoxLayout(root)
    m = SPACING["lg"]
    col.setContentsMargins(m, m, m, m)
    col.setSpacing(SPACING["lg"])

    title = QLabel("컴포넌트 갤러리 (개발용)")
    title.setProperty("role", "headline")
    col.addWidget(title)

    steps = Card("스테퍼")
    titles = [STEP_TITLES[s] for s in Step]
    for current, done in ((0, set()), (1, {0}), (2, {0, 1})):
        bar = StepperBar(titles)
        bar.set_state(current, done)
        steps.body.addWidget(bar)
    col.addWidget(steps)

    buttons = Card("버튼 (기본 / 비활성)")
    for variant in ("primary", "secondary", "destructive"):
        row = QHBoxLayout()
        enabled, disabled = AppButton("확인", variant), AppButton("비활성", variant)
        disabled.setEnabled(False)
        row.addWidget(enabled)
        row.addWidget(disabled)
        row.addStretch(1)
        buttons.body.addLayout(row)
    col.addWidget(buttons)

    badges = Card("배지")
    row = QHBoxLayout()
    for kind in BADGE_KINDS:
        row.addWidget(Badge(BADGE_TEXT[kind], kind))
    row.addStretch(1)
    badges.body.addLayout(row)
    col.addWidget(badges)

    inputs = Card("입력")
    combo = QComboBox()
    combo.addItems(["가상 사업 A", "가상 사업 B"])
    edit = QLineEdit()
    edit.setPlaceholderText("2099.01.01")
    inputs.body.addWidget(combo)
    inputs.body.addWidget(edit)
    col.addWidget(inputs)
    col.addStretch(1)
    return root
