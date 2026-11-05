"""기존 정책 파일 수정 대화상자. 저장은 `policy_flow.save_edit`(같은 검증 + 충돌 확인 + 백업 + 원자 교체)가 하고, 같은 경로의 파일을 고친다.
- 취소·닫기·Enter 는 아무것도 쓰지 않는다. 저장 실패·충돌·검증 실패에서도 기존 파일은 그대로다(오류는 코드에 대응하는 고정 문구만 보여 준다).
- 추가 시급 키가 있어 수정할 수 없는 정책은 입력칸을 잠그고 이유를 안내한다(기존 키를 지우지 않는다).
- 생성이 진행 중이거나 첫 단계가 아니면 저장하지 않는다(`allowed`는 열 때와 저장 직전에 확인한다).
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout

from scholarship_payment.ui import policy_flow, validators
from scholarship_payment.ui.theme import SPACING
from scholarship_payment.ui.widgets import AppButton

_MESSAGES = {"POLICY_KEY_MISSING": "필요한 항목을 모두 입력하세요."}


class PolicyEditDialog(QDialog):
    def __init__(self, program: str, path, parent=None, allowed: Callable[[], bool] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("정책 파일 수정")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._program, self._path = program, Path(path)
        self._allowed = allowed or (lambda: True)
        self.saved = False
        self.backup_name: str | None = None
        self._load = policy_flow.load_edit(self._path, program)

        col = QVBoxLayout(self)
        m = SPACING["lg"]
        col.setContentsMargins(m, m, m, m)
        col.setSpacing(SPACING["md"])
        intro = QLabel("같은 위치의 정책 파일을 수정합니다. '수정 저장'을 누르면 파일에 즉시 반영되며, 이후 고급 설정에서 취소해도 "
                       "이미 저장한 정책 파일은 되돌아가지 않습니다. 저장하지 않고 이 창을 취소하면 파일은 바뀌지 않습니다. "
                       "저장하면 이전 내용은 같은 폴더에 백업 파일(.bak)로 남고, 백업은 지우거나 덮어쓰지 않습니다.")
        intro.setWordWrap(True)
        intro.setProperty("role", "secondary")
        col.addWidget(intro)
        self.path_label = QLabel(str(self._path))
        self.path_label.setProperty("role", "hint")
        self.path_label.setWordWrap(True)
        col.addWidget(self.path_label)

        form = QFormLayout()
        form.setHorizontalSpacing(SPACING["md"])
        form.setVerticalSpacing(SPACING["sm"])
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.inputs: dict[str, QLineEdit] = {}
        filled = {**self._load.values, **self._load.rate_values}
        for f in policy_flow.edit_fields_for(program):
            edit = QLineEdit(filled.get(f.key, ""))
            self.inputs[f.key] = edit
            label = QLabel(f.label)
            label.setWordWrap(True)
            form.addRow(label, edit)
        col.addLayout(form)

        self.notice_label: QLabel | None = None                    # 시급 칸이 있는 사업(다문화·탈북학생 멘토링)에만 만든다
        if "rate_urban" in self.inputs:
            self.notice_label = QLabel(policy_flow.RATE_NOTE)
            self.notice_label.setProperty("role", "hint")
            self.notice_label.setWordWrap(True)
            col.addWidget(self.notice_label)

        self.error_label = QLabel("")
        self.error_label.setProperty("role", "error")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        col.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = AppButton("취소", "secondary")
        self.save_button = AppButton("수정 저장", "primary")
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        col.addLayout(buttons)

        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save)
        self.setTabOrder(self.cancel_button, self.save_button)

        if not self._load.ok:
            for e in self.inputs.values():
                e.setEnabled(False)
            self.save_button.setEnabled(False)
            self._show_error(self._load.codes)
        elif not self._allowed():
            for e in self.inputs.values():
                e.setEnabled(False)
            self.save_button.setEnabled(False)
            self._show_error(("POLICY_EDIT_NOT_ALLOWED",))

    def _show_error(self, codes) -> None:
        text = " ".join(dict.fromkeys(_MESSAGES.get(c) or validators.message(c) for c in codes))
        self.error_label.setText(text)
        self.error_label.show()

    def _save(self) -> None:
        if not self._load.ok or self._load.session is None:
            return
        if not self._allowed():                                    # 대화상자를 연 뒤 생성이 시작된 경우
            self._show_error(("POLICY_EDIT_NOT_ALLOWED",))
            return
        values = {k: e.text() for k, e in self.inputs.items() if not k.startswith("rate_")}
        rates = {k: e.text() for k, e in self.inputs.items() if k.startswith("rate_")}
        result = policy_flow.save_edit(self._load.session, values, rates or None)
        if not result.ok:
            self._show_error(result.codes or ("POLICY_EDIT_IO",))
            return
        self.saved, self.backup_name = result.changed, result.backup_name
        self.error_label.hide()
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.save_button.hasFocus():
            event.ignore()                                          # Enter 로 의도치 않게 저장되지 않게 한다
            return
        super().keyPressEvent(event)
