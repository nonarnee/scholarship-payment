"""공통 위젯(표시 전용). 스타일은 theme.build_stylesheet 의 속성 선택자(variant/badge/state)로 정한다."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from scholarship_payment.ui.theme import CONTROL_HEIGHT, SPACING

BUTTON_VARIANTS = ("primary", "secondary", "destructive")
BADGE_KINDS = ("verified", "caution", "error", "info", "neutral")


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Card(QFrame):
    """흰 바탕 + 1px 테두리 + 8px 모서리. `body` 레이아웃에 내용을 넣는다."""

    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._title = None
        self.body = QVBoxLayout(self)
        m = SPACING["lg"]
        self.body.setContentsMargins(m, m, m, m)
        self.body.setSpacing(SPACING["md"])
        if title:
            self._title = QLabel(title)
            self._title.setProperty("role", "section")
            self.body.addWidget(self._title)

    def title_text(self) -> str:
        return self._title.text() if self._title else ""


class Badge(QLabel):
    def __init__(self, text: str, kind: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.set_kind(kind)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_kind(self, kind: str) -> None:
        if kind not in BADGE_KINDS:
            raise ValueError("unknown badge kind")
        self.setProperty("badge", kind)
        _repolish(self)


class AppButton(QPushButton):
    def __init__(self, text: str, variant: str = "secondary", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        if variant not in BUTTON_VARIANTS:
            raise ValueError("unknown button variant")
        self.setProperty("variant", variant)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(CONTROL_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class StepperBar(QWidget):
    """`① 파일 선택 › ② 지급내역 확인 › ③ 결과 생성`. 상태: current / done / todo. 키보드 초점을 받지 않는다."""

    def __init__(self, titles: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACING["sm"])
        self._beads: list[QLabel] = []
        self._labels: list[QLabel] = []
        self._states: list[str] = []
        for i, title in enumerate(titles):
            bead = QLabel(str(i + 1))
            bead.setProperty("bead", True)
            bead.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label = QLabel(title)
            label.setProperty("stepLabel", True)
            for w in (bead, label):
                w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            lay.addWidget(bead)
            lay.addWidget(label)
            if i < len(titles) - 1:
                sep = QLabel("›")
                sep.setProperty("stepSeparator", True)
                sep.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                lay.addSpacing(SPACING["sm"])
                lay.addWidget(sep)
                lay.addSpacing(SPACING["sm"])
            self._beads.append(bead)
            self._labels.append(label)
            self._states.append("todo")
        lay.addStretch(1)
        self.set_state(current=0, done=set())

    def set_state(self, current: int, done: set[int]) -> None:
        for i, (bead, label) in enumerate(zip(self._beads, self._labels)):
            state = "current" if i == current else "done" if i in done else "todo"
            self._states[i] = state
            bead.setText("✓" if state == "done" else str(i + 1))
            for w in (bead, label):
                w.setProperty("state", state)
                _repolish(w)

    def state_of(self, index: int) -> str:
        return self._states[index]

    def label_texts(self) -> list[str]:
        return [w.text() for w in self._labels]

    def bead_texts(self) -> list[str]:
        return [w.text() for w in self._beads]
