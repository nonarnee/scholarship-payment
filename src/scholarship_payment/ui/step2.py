"""Step 2 · 지급내역 확인(읽기 전용 미리보기). `PreviewSession` 의 상태를 보여 줄 뿐 업무 규칙·파싱은 하지 않는다. 파일을 만들지 않는다.

- **확인한 범위만** 표시한다: 지급연월·대상자 수·금액 합계(정수 원)·기준일, 그리고 확인한 것/아직 확인하지 않은 것을 나눠서 적는다.
  출력 템플릿 구조, 엑셀 생성·저장, 저장 폴더 쓰기 가능 여부는 '아직 확인하지 않음'으로 표시한다(최종 생성 단계에서 확인).
- 학생별 표·점수·분포는 없다. 오류 코드는 한국어 설명과 조치 안내로 보여 주고 코드 이름은 작게 덧붙인다.
- 처리 중에는 끝을 알 수 없는 진행 표시만 보이며 경과 시간·남은 시간 추정은 없다. 비밀번호는 필요할 때만 입력받고 입력창은 제출 즉시 비운다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QVBoxLayout, QWidget

from scholarship_payment.ui import issue_text, preview as pv
from scholarship_payment.ui.settings_dialog import PROGRAM_LABELS  # noqa: F401  (사업 코드 순서)
from scholarship_payment.ui.step1 import STEP1_PROGRAM_LABELS
from scholarship_payment.ui.theme import SPACING
from scholarship_payment.ui.widgets import AppButton, Badge, Card

_SEVERITY_BADGE = {"error": "error", "warning": "caution", "note": "info"}
_CHANGED_NAMES = {"source": "원본 파일", "template": "출력 템플릿", "policy": "정책 파일"}
CHECKED_TEXT = "· 원본 파일 열기와 구조(시트·머리글·합계 행)\n· 행별 필수 항목, 학번 중복, 금액·시간 형식\n· 은행코드 표 대조(WINS·WRIS)"
UNCHECKED_TEXT = "· 출력 템플릿의 구조(시트·머리글)\n· 엑셀 파일 생성과 저장\n· 저장 폴더에 실제로 쓸 수 있는지"
MESSAGES = {
    pv.CANCELLED: "비밀번호 입력을 취소했습니다. 다시 확인하려면 '다시 확인'을 누르세요.",
    pv.CONSUMED: "이 확인 결과로는 이미 지급명단을 만들었습니다. 다시 만들려면 새 변환을 시작하세요.",
    pv.LOCKED: "비밀번호를 3번 틀려 입력을 막았습니다. 이전 단계로 돌아갔다가 다시 시도하세요.",
}
HINTS = {
    pv.IDLE: "", pv.PREPARING: "원본을 확인하는 중입니다", pv.NEED_PASSWORD: "필요: 비밀번호", pv.READY: "지급명단 생성을 누르면 저장을 시작합니다", pv.CONSUMED: "이미 사용한 확인 결과입니다",
    pv.FAILED: "차단 오류를 해결한 뒤 다시 확인하세요", pv.INVALIDATED: "파일이 바뀌어 미리보기를 무효화했습니다",
    pv.CANCELLED: "비밀번호 입력을 취소했습니다", pv.LOCKED: "비밀번호 입력이 막혔습니다. 이전 단계로 돌아가세요",
}


class IssueRow(QFrame):
    def __init__(self, group) -> None:
        super().__init__()
        self.setObjectName("IssueRow")
        self.code, self.severity = group.code, group.severity
        self.setProperty("severity", group.severity)
        text = issue_text.describe(group.code)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"])
        lay.setSpacing(SPACING["xs"])
        head = QHBoxLayout()
        self.badge = Badge(issue_text.SEVERITY_LABEL[group.severity], _SEVERITY_BADGE[group.severity])
        self.title = QLabel(text.title)
        self.title.setWordWrap(True)
        self.title.setProperty("role", "filename")
        head.addWidget(self.badge)
        head.addWidget(self.title, 1)
        lay.addLayout(head)
        self.action = QLabel(text.action)
        self.action.setWordWrap(True)
        lay.addWidget(self.action)
        loc = issue_text.location_text(group.rows, group.fields)
        self.location = QLabel(loc + (f" ({group.count}건)" if loc and group.count > 1 and not group.rows else ""))
        self.location.setProperty("role", "hint")
        self.location.setVisible(bool(loc))
        self.code_label = QLabel(f"코드: {group.code}")
        self.code_label.setProperty("role", "hint")
        lay.addWidget(self.location)
        lay.addWidget(self.code_label)


class Step2Page(QWidget):
    def __init__(self, session: pv.PreviewSession, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session, self.ctx = session, context
        root = QVBoxLayout(self)
        m = SPACING["lg"]
        root.setContentsMargins(m, m, m, m)
        root.setSpacing(SPACING["md"])

        title = QLabel("지급내역 확인")
        title.setProperty("role", "headline")
        sub = QLabel("읽기 전용 확인입니다. 이 단계에서는 파일을 만들지 않습니다.")
        sub.setProperty("role", "secondary")
        root.addWidget(title)
        root.addWidget(sub)

        # 안내(취소·잠금·변경 무효화)
        self.message_box = QFrame()
        self.message_box.setObjectName("Notice")
        ml = QVBoxLayout(self.message_box)
        ml.setContentsMargins(SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"])
        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        self.retry_button = AppButton("다시 확인", "secondary")
        ml.addWidget(self.message_label)
        ml.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self.message_box)

        # 처리 중: 끝을 알 수 없는 진행 표시(시간·비율 추정 없음)
        self.progress_box = Card()
        self.progress_label = QLabel("원본 파일을 읽고 확인하는 중입니다…")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress_box.body.addWidget(self.progress_label)
        self.progress_box.body.addWidget(self.progress)
        root.addWidget(self.progress_box)

        # 비밀번호(암호 파일일 때만)
        self.password_box = Card("비밀번호 입력")
        self.password_hint = QLabel("암호가 걸린 파일입니다. 비밀번호는 이 확인에만 쓰이고 저장하지 않습니다.")
        self.password_hint.setWordWrap(True)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("비밀번호")
        row = QHBoxLayout()
        self.password_ok = AppButton("확인", "primary")
        self.password_cancel = AppButton("취소", "secondary")
        row.addWidget(self.password_edit, 1)
        row.addWidget(self.password_ok)
        row.addWidget(self.password_cancel)
        self.password_error = QLabel("")
        self.password_error.setProperty("role", "error")
        self.password_attempts = QLabel("")
        self.password_attempts.setProperty("role", "hint")
        for w in (self.password_hint,):
            self.password_box.body.addWidget(w)
        self.password_box.body.addLayout(row)
        self.password_box.body.addWidget(self.password_error)
        self.password_box.body.addWidget(self.password_attempts)
        root.addWidget(self.password_box)

        # 결과 요약(읽기 전용)
        self.result_box = QWidget()
        rl = QVBoxLayout(self.result_box)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(SPACING["md"])
        cards = QHBoxLayout()
        cards.setSpacing(SPACING["md"])
        self.program_value, self.month_value, self.count_value, self.total_value = (QLabel("") for _ in range(4))
        self.date_value = QLabel("")
        for caption, value, extra in (("지원 사업", self.program_value, None), ("지급연월", self.month_value, ("기준일(작성일)", self.date_value)),
                                      ("대상자 수", self.count_value, None), ("지급 합계", self.total_value, None)):
            card = Card()
            cap = QLabel(caption)
            cap.setProperty("role", "hint")
            value.setProperty("role", "section" if value is self.program_value else "headline")
            value.setWordWrap(True)
            card.body.addWidget(cap)
            card.body.addWidget(value)
            if extra:
                small = QLabel(extra[0])
                small.setProperty("role", "hint")
                card.body.addWidget(small)
                card.body.addWidget(extra[1])
            # 값이 줄바꿈된 카드가 행 높이를 정해도 다른 카드의 제목이 밀리지 않게, 글자는 위에 붙이고 남는 높이는 아래 빈 공간으로 보낸다.
            for label in (cap, value) + (() if extra is None else (small, extra[1])):
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            card.body.addStretch(1)
            cards.addWidget(card, 1)
        rl.addLayout(cards)
        self.result_badge = Badge("확인한 범위에서 차단 오류 없음", "verified")
        rl.addWidget(self.result_badge, 0, Qt.AlignmentFlag.AlignLeft)
        scope = QHBoxLayout()
        scope.setSpacing(SPACING["md"])
        for heading, attr, text in (("이번에 확인한 것", "scope_checked", CHECKED_TEXT), ("아직 확인하지 않은 것(지급명단을 만들 때 확인합니다)", "scope_unchecked", UNCHECKED_TEXT)):
            card = Card(heading)
            label = QLabel(text)
            label.setWordWrap(True)
            setattr(self, attr, label)
            card.body.addWidget(label)
            scope.addWidget(card, 1)
        rl.addLayout(scope)
        root.addWidget(self.result_box)

        # 오류·경고·참고
        self.headline = QLabel("")
        self.headline.setProperty("role", "section")
        self.bank_label = QLabel("")
        self.bank_label.setWordWrap(True)
        self.bank_label.setProperty("role", "error")
        self.issues_box = QVBoxLayout()
        self.issues_box.setSpacing(SPACING["sm"])
        root.addWidget(self.headline)
        root.addLayout(self.issues_box)
        root.addWidget(self.bank_label)
        root.addStretch(1)

        self.password_ok.clicked.connect(self._submit_password)
        self.password_edit.returnPressed.connect(self._submit_password)
        self.password_cancel.clicked.connect(self.session.cancel_password)
        self.retry_button.clicked.connect(self._retry)
        self.session.on_change(self._render)
        self.setTabOrder(self.password_edit, self.password_ok)
        self.setTabOrder(self.password_ok, self.password_cancel)
        self.setTabOrder(self.password_cancel, self.retry_button)
        self._selection = None
        self._render()

    # --- 동작 ---
    def enter(self, selection, resume: bool = False) -> None:
        """Step 2 로 들어온다. resume=True(Step 3 에서 돌아옴)이면 이미 있는 확인 결과를 그대로 보여 주고 다시 읽지 않는다(변경 감지만 한다)."""
        self._selection = selection
        if resume and self.session.state != pv.IDLE:
            self.refresh_freshness()
            return
        if selection is not None:
            self.session.start(selection)

    def leave(self) -> None:
        self.password_edit.clear()
        self.session.discard()
        self._selection = None

    def refresh_freshness(self) -> None:
        self.session.verify_fresh()

    def _retry(self) -> None:
        if self._selection is not None:
            self.session.start(self._selection)

    def _submit_password(self) -> None:
        text = self.password_edit.text()
        self.password_edit.clear()                               # 제출 즉시 입력창을 비운다
        if text:
            self.session.submit_password(text)
        del text

    def hint_text(self) -> str:
        return HINTS.get(self.session.state, "")

    # --- 표시 ---
    def issue_rows(self) -> list[IssueRow]:
        return [self.issues_box.itemAt(i).widget() for i in range(self.issues_box.count())]

    def _clear_issues(self) -> None:
        while self.issues_box.count():
            w = self.issues_box.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _headline_text(self, errors, warnings, notes) -> str:
        parts = []
        for label, groups in (("차단 오류", errors), ("경고", warnings), ("참고", notes)):
            if groups:
                parts.append(f"{label} {len(groups)}종({sum(g.count for g in groups)}건)")
        return " · ".join(parts)

    def _render(self) -> None:
        s = self.session
        st = s.state
        self._clear_issues()
        self.progress_box.setVisible(st == pv.PREPARING)
        self.password_box.setVisible(st in (pv.NEED_PASSWORD, pv.LOCKED))
        self.result_box.setVisible(st == pv.READY)
        locked = st == pv.LOCKED
        self.password_edit.setEnabled(not locked)
        self.password_ok.setEnabled(not locked)
        self.password_cancel.setEnabled(not locked)
        self.retry_button.setEnabled(not s.busy)
        retry_visible = st in (pv.FAILED, pv.INVALIDATED, pv.CANCELLED)
        self.retry_button.setVisible(retry_visible)
        self.password_attempts.setText(f"남은 입력 횟수: {max(pv.MAX_ATTEMPTS - s.attempts, 0)}회 (최대 {pv.MAX_ATTEMPTS}회)")
        self.password_error.setText(issue_text.describe("INPUT_PASSWORD_WRONG").title if s.last_password_wrong and st == pv.NEED_PASSWORD else "")
        self.password_error.setVisible(bool(self.password_error.text()))

        message = MESSAGES.get(st, "")
        if st == pv.INVALIDATED:
            blocks = []
            for code, label in (("INPUT_FILE_CHANGED", "바뀐 파일"), ("INPUT_FILE_UNREADABLE", "읽을 수 없는 파일")):
                names = ", ".join(_CHANGED_NAMES.get(n, n) for n in s.changed if s.changed_codes.get(n, "INPUT_FILE_CHANGED") == code)
                if names:
                    t = issue_text.describe(code)
                    blocks.append(f"{t.title}\n{label}: {names}\n{t.action}")
            message = "\n".join(blocks) or issue_text.describe("INPUT_FILE_CHANGED").title
            if s.invalid_reason == pv.REASON_GENERATION_FAILED:
                message = "지급명단을 만들지 못해 이전 확인 결과를 폐기했습니다. 파일을 확인한 뒤 '다시 확인'을 누르세요."
            elif s.invalid_after_generation:
                message = "지급명단은 만들지 않았습니다.\n" + message
        self.message_label.setText(message)
        self.message_label.setVisible(bool(message))
        self.message_box.setVisible(bool(message) or retry_visible)         # 안내가 없어도 '다시 확인' 버튼은 보인다(오류 해결 후 사용자가 직접 다시 확인)

        errors = s.errors if st in (pv.FAILED,) else ()
        warnings = s.summary.warnings if s.summary else ()
        notes = s.summary.notes if s.summary else ()
        self.headline.setText(self._headline_text(errors, warnings, notes) if st in (pv.READY, pv.FAILED) else "")
        self.headline.setVisible(bool(self.headline.text()))
        for groups in (errors, warnings, notes):
            for g in groups:
                self.issues_box.addWidget(IssueRow(g))
        banks = ", ".join(s.missing_banks) if st == pv.FAILED else ""
        self.bank_label.setText(f"은행코드를 채워야 하는 은행: {banks}" if banks else "")
        self.bank_label.setVisible(bool(banks))

        if st == pv.READY and s.summary:
            sm = s.summary
            self.program_value.setText(STEP1_PROGRAM_LABELS.get(sm.program, sm.program))
            self.month_value.setText(f"{sm.year}년 {sm.month:02d}월")
            self.count_value.setText(f"{sm.count}명")
            self.total_value.setText(f"{sm.total_amount:,}원")
            self.date_value.setText(sm.base_date)
