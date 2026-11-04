"""정책 파일 만들기 대화상자. 생성은 `policy_flow.create_policy`(기존 policy_builder 재사용)가 하며 기존 파일은 덮어쓰지 않는다.
만들어진 파일은 이 대화상자를 닫거나 상위 설정 대화상자를 취소해도 지우지 않는다. 입력값은 정책 파일 외에는 어디에도 남기지 않는다.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout

from scholarship_payment.ui import policy_flow, validators
from scholarship_payment.ui.theme import SPACING
from scholarship_payment.ui.widgets import AppButton, PathField

_WIZARD_MESSAGES = {"POLICY_KEY_MISSING": "필요한 항목을 모두 입력하세요."}


class PolicyWizardDialog(QDialog):
    def __init__(self, program: str, template_path: str, folder: Path, chooser, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("새 정책 만들기")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._program, self._template, self._chooser = program, template_path, chooser
        self.created_path: Path | None = None
        self._target = policy_flow.suggest_path(program, Path(folder))

        col = QVBoxLayout(self)
        m = SPACING["lg"]
        col.setContentsMargins(m, m, m, m)
        col.setSpacing(SPACING["md"])
        intro = QLabel("템플릿에서 읽을 수 있는 항목은 자동으로 채우고, 아래 값만 직접 입력합니다. 입력한 값은 정책 파일에만 저장됩니다.")
        intro.setWordWrap(True)
        intro.setProperty("role", "secondary")
        col.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(SPACING["md"])
        form.setVerticalSpacing(SPACING["sm"])
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.inputs: dict[str, QLineEdit] = {}
        for f in policy_flow.fields_for(program):
            edit = QLineEdit()
            self.inputs[f.key] = edit
            label = QLabel(f.label)
            label.setWordWrap(True)
            form.addRow(label, edit)
        col.addLayout(form)

        row = QHBoxLayout()
        row.addWidget(QLabel("저장 위치"))
        self.path_field = PathField()
        self.path_field.set_path(str(self._target))
        self.change_path_button = AppButton("위치 변경...", "secondary")
        row.addWidget(self.path_field, 1)
        row.addWidget(self.change_path_button)
        col.addLayout(row)

        self.error_label = QLabel("")
        self.error_label.setProperty("role", "error")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        col.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = AppButton("취소", "secondary")
        self.create_button = AppButton("정책 파일 만들기", "primary")
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.create_button)
        col.addLayout(buttons)

        self.change_path_button.clicked.connect(self._change_path)
        self.cancel_button.clicked.connect(self.reject)
        self.create_button.clicked.connect(self._create)
        self.setTabOrder(self.cancel_button, self.create_button)

    def _change_path(self) -> None:
        chosen = self._chooser.save_policy(self, self._target)
        if chosen:
            self._target = Path(chosen)
            self.path_field.set_path(chosen)

    def _show_error(self, codes) -> None:
        text = " ".join(dict.fromkeys(_WIZARD_MESSAGES.get(c) or validators.message(c) for c in codes))
        self.error_label.setText(text)
        self.error_label.show()

    def _create(self) -> None:
        values = {k: e.text() for k, e in self.inputs.items() if k != "rates"}
        rates = self.inputs["rates"].text() if "rates" in self.inputs else None
        result = policy_flow.create_policy(self._template, values, self._target, self._program, rates)
        if not result.ok:
            self._show_error(result.codes or ("POLICY_OUTPUT_IO",))
            return
        self.created_path = result.path
        self.error_label.hide()
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.create_button.hasFocus():
            event.ignore()                      # Enter 로 의도치 않게 파일이 만들어지지 않게 한다
            return
        super().keyPressEvent(event)
