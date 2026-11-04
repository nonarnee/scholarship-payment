"""공통 위젯(표시 전용). 스타일은 theme.build_stylesheet 의 속성 선택자(variant/badge/state)로 정한다."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from scholarship_payment.ui import validators
from scholarship_payment.ui.theme import CONTROL_HEIGHT, SPACING

BUTTON_VARIANTS = ("primary", "secondary", "destructive", "link")
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


class ElidedLabel(QLabel):
    """긴 문자열(경로·파일 이름)을 가운데를 줄여 한 줄로 보이고, 전체는 툴팁으로 보여 준다."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._elide()

    def full_text(self) -> str:
        return self._full

    def _elide(self) -> None:
        width = max(self.width(), 1)
        self.setText(QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideMiddle, width))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()


class PathField(QLineEdit):
    """읽기 전용 경로 표시줄. 전체 경로는 툴팁으로, 앞부분부터 보이게 한다."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setProperty("role", "path")

    def set_path(self, text: str | None, placeholder: str = "") -> None:
        self.setText(text or "")
        self.setToolTip(text or "")
        self.setPlaceholderText(placeholder)
        self.setCursorPosition(0)


class DropZone(QFrame):
    """엑셀 파일 한 개를 끌어다 놓는 영역. 파일 종류·개수 판단은 validators.classify_drop 이 한다.
    들어오는 동안 상태 속성이 active(받을 수 있음)/reject(받을 수 없음)로 바뀌고, 놓으면 dropped(경로) 또는 rejected(코드)를 낸다.
    키보드 사용자는 같은 카드의 '파일 선택' 버튼을 쓴다(이 영역은 초점을 받지 않는다).
    """

    dropped = Signal(str)
    rejected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"])
        self.body.setSpacing(SPACING["sm"])
        self._set_state("idle")

    def _set_state(self, state: str) -> None:
        self.setProperty("state", state)
        _repolish(self)

    @staticmethod
    def _paths(mime) -> list[str]:
        return [u.toLocalFile() for u in mime.urls()] if mime.hasUrls() else []

    def dragEnterEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        _, code = validators.classify_drop(self._paths(event.mimeData()))
        self._set_state("reject" if code else "active")
        event.acceptProposedAction()                         # 거부 사유를 놓을 때 알려 주기 위해 일단 받는다

    def dragMoveEvent(self, event) -> None:
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._set_state("idle")
        event.accept()

    def dropEvent(self, event) -> None:
        self._set_state("idle")
        path, code = validators.classify_drop(self._paths(event.mimeData()))
        event.acceptProposedAction()
        if code:
            self.rejected.emit(code)
        else:
            self.dropped.emit(path)


class SegmentedTabs(QFrame):
    """사업 선택용 분할 탭(배타 선택). 키보드: Tab 으로 이동, Space/Enter 로 선택."""

    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SegTabs")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(SPACING["xs"], SPACING["xs"], SPACING["xs"], SPACING["xs"])
        lay.setSpacing(SPACING["xs"])
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for code, label in items:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setProperty("seg", True)
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(b)
            lay.addWidget(b, 1)
            self._buttons[code] = b
            b.clicked.connect(lambda _=False, c=code: self.changed.emit(c))

    def set_current(self, code: str) -> None:
        self._buttons[code].setChecked(True)

    def current(self) -> str | None:
        return next((c for c, b in self._buttons.items() if b.isChecked()), None)

    def button(self, code: str) -> QPushButton:
        return self._buttons[code]
