"""고급 설정 대화상자. 기존 설정을 복사한 임시 편집 상태(`SettingsDraft`)로 시작하고, '설정 저장 및 적용'을 눌러 검증을 통과했을 때만
모델·설정 파일에 반영한다. 취소·닫기는 아무것도 바꾸지 않는다(정책 만들기로 이미 만든 파일은 지우지 않는다).
Stitch 의 설정 화면 중 이 프로그램이 측정·수행하지 않는 요소(설정 ID, 열 매핑 수, 쓰기 권한 확정 표시, 캐시 비우기, 오프라인 확인 표시)는 두지 않았다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from scholarship_payment.ui import status_view
from scholarship_payment.ui.policy_editor import PolicyEditDialog
from scholarship_payment.ui.policy_wizard import PolicyWizardDialog
from scholarship_payment.ui.state import ApplyOutcome, SettingsDraft
from scholarship_payment.ui.theme import SPACING
from scholarship_payment.ui.widgets import AppButton, Badge, PathField, SegmentedTabs

EDIT_NOTE = "정책 파일 수정은 '수정 저장'을 누르면 파일에 즉시 반영됩니다. 이 창에서 취소해도 이미 저장한 정책 파일은 되돌아가지 않습니다(선택한 경로만 그대로 유지됩니다)."
PROGRAM_LABELS = {"daechung": "대청교", "multicultural": "다문화·탈북학생 멘토링", "ai": "AI멘토링"}


def _panel(title: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    panel = QFrame()
    panel.setObjectName("Panel")
    lay = QVBoxLayout(panel)
    lay.setContentsMargins(SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"])
    lay.setSpacing(SPACING["sm"])
    head = QHBoxLayout()
    label = QLabel(title)
    label.setProperty("role", "section")
    head.addWidget(label)
    head.addStretch(1)
    lay.addLayout(head)
    return panel, lay, head


class AdvancedSettingsDialog(QDialog):
    def __init__(self, model, context, parent=None, policy_edit_allowed: Callable[[], bool] | None = None) -> None:
        super().__init__(parent)
        self._edit_allowed = policy_edit_allowed or (lambda: True)        # 첫 단계이고 생성 중이 아닐 때만 True (MainWindow 가 판단한다)
        self.setWindowTitle("고급 설정 — 서식 템플릿 및 변환 정책 관리")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.resize(620, 524)
        self._model, self._ctx = model, context
        self.draft = SettingsDraft(model.store.settings, context.runner, default_dirs=context.default_dirs)
        self.outcome: ApplyOutcome | None = None
        self._program = model.program

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(SPACING["lg"], SPACING["md"], SPACING["lg"], SPACING["md"])
        bl.setSpacing(SPACING["md"])
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        col.addWidget(scroll, 1)

        lead = QLabel("적용 사업 유형 (사업별 템플릿·정책 파일·저장 폴더가 따로 저장됩니다)")
        lead.setProperty("role", "section")
        bl.addWidget(lead)
        self.tabs = SegmentedTabs(list(PROGRAM_LABELS.items()))
        self.tabs.set_current(self._program)
        bl.addWidget(self.tabs)

        panel, lay, head = _panel("출력 엑셀 서식 템플릿 (.xlsx)")
        self.template_badge = Badge("", "neutral")
        head.addWidget(self.template_badge)
        row = QHBoxLayout()
        self.template_field = PathField()
        self.template_button = AppButton("템플릿 파일 변경...", "secondary")
        row.addWidget(self.template_field, 1)
        row.addWidget(self.template_button)
        lay.addLayout(row)
        self.template_message = self._hint()
        lay.addWidget(self.template_message)
        bl.addWidget(panel)

        panel, lay, head = _panel("변환 정책 규칙 파일 (.json)")
        self.policy_badge = Badge("", "neutral")
        head.addWidget(self.policy_badge)
        row = QHBoxLayout()
        self.policy_field = PathField()
        self.policy_button = AppButton("정책 파일 변경...", "secondary")
        self.wizard_button = AppButton("새 정책 만들기", "secondary")
        row.addWidget(self.policy_field, 1)
        row.addWidget(self.policy_button)
        row.addWidget(self.wizard_button)
        lay.addLayout(row)
        self.policy_message = self._hint()
        lay.addWidget(self.policy_message)
        edit_row = QHBoxLayout()
        self.edit_button = AppButton("정책 파일 수정...", "secondary")
        edit_row.addStretch(1)
        edit_row.addWidget(self.edit_button)
        lay.addLayout(edit_row)
        self.edit_hint = self._hint()
        lay.addWidget(self.edit_hint)
        self.edit_note = self._hint()
        self.edit_note.setText(EDIT_NOTE)
        lay.addWidget(self.edit_note)
        self.edit_result = self._hint()                      # 정책 수정을 저장한 뒤에만 보인다
        lay.addWidget(self.edit_result)
        self.edit_result.hide()
        bl.addWidget(panel)

        panel, lay, head = _panel("기본 결과 저장 폴더")
        row = QHBoxLayout()
        self.out_dir_field = PathField()
        self.out_dir_button = AppButton("폴더 찾기...", "secondary")
        row.addWidget(self.out_dir_field, 1)
        row.addWidget(self.out_dir_button)
        lay.addLayout(row)
        self.out_dir_message = self._hint()
        lay.addWidget(self.out_dir_message)
        bl.addWidget(panel)

        self.message = QLabel("")
        self.message.setProperty("role", "error")
        self.message.setWordWrap(True)
        self.message.hide()
        bl.addWidget(self.message)
        bl.addStretch(1)

        bar = QFrame()
        bar.setObjectName("FooterBar")
        fl = QHBoxLayout(bar)
        fl.setContentsMargins(SPACING["lg"], SPACING["sm"], SPACING["lg"], SPACING["sm"])
        self.reset_button = AppButton("기본값으로 복원", "secondary")
        self.cancel_button = AppButton("취소", "secondary")
        self.apply_button = AppButton("설정 저장 및 적용", "primary")
        fl.addWidget(self.reset_button)
        fl.addStretch(1)
        fl.addWidget(self.cancel_button)
        fl.addWidget(self.apply_button)
        col.addWidget(bar)

        self.tabs.changed.connect(self._on_tab)
        self.template_button.clicked.connect(lambda: self._choose("template_path", "open_template"))
        self.policy_button.clicked.connect(lambda: self._choose("policy_path", "open_policy"))
        self.out_dir_button.clicked.connect(lambda: self._choose("out_dir", "choose_folder"))
        self.wizard_button.clicked.connect(self._open_wizard)
        self.edit_button.clicked.connect(self._open_editor)
        self.reset_button.clicked.connect(self._restore)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.apply)
        self.draft.on_change(self.refresh)
        for a, b in ((self.tabs.button("ai"), self.template_button), (self.template_button, self.policy_button), (self.policy_button, self.wizard_button),
                     (self.wizard_button, self.edit_button), (self.edit_button, self.out_dir_button), (self.out_dir_button, self.reset_button), (self.reset_button, self.cancel_button),
                     (self.cancel_button, self.apply_button)):
            self.setTabOrder(a, b)
        self.draft.check_displayed(self._program)
        self.refresh()

    @staticmethod
    def _hint() -> QLabel:
        lab = QLabel("")
        lab.setProperty("role", "hint")
        lab.setWordWrap(True)
        return lab

    # --- 화면 ---
    def refresh(self) -> None:
        p = self._program
        for kind, key, field, badge, msg in (("template", "template_path", self.template_field, self.template_badge, self.template_message),
                                             ("policy", "policy_path", self.policy_field, self.policy_badge, self.policy_message)):
            path, auto = self.draft.effective(p, key)
            field.set_path(path, "선택하지 않았습니다")
            st = self.draft.state(p, key)
            text, kind_name = status_view.describe(kind, st)
            badge.setText(text)
            badge.setVisible(bool(text))
            if kind_name:
                badge.set_kind(kind_name)
            note = status_view.detail(st)
            text_msg = note or ("기본 위치에서 자동으로 찾은 파일입니다. 저장하지 않으면 이 자동 탐색이 계속 쓰입니다." if auto and path else "")
            msg.setText(text_msg)
            msg.setVisible(bool(text_msg))
        out = self.draft.value(p, "out_dir")
        self.out_dir_field.set_path(out, "선택하지 않았습니다 — 변환할 때마다 선택합니다")
        st = self.draft.state(p, "out_dir")
        out_msg = status_view.detail(st) if st.level == "error" else (status_view.dir_message(st) if st.ok else "")
        self.out_dir_message.setText(out_msg)
        self.out_dir_message.setVisible(bool(out_msg))
        has_policy = bool(self.draft.effective(p, "policy_path")[0])
        allowed = self._edit_allowed()
        self.edit_button.setEnabled(has_policy and allowed)
        self.edit_note.setVisible(has_policy)
        hint = "" if allowed or not has_policy else "정책 파일 수정은 첫 단계(파일 선택)에서, 생성 중이 아닐 때만 할 수 있습니다."
        self.edit_hint.setText(hint)
        self.edit_hint.setVisible(bool(hint))
        self.apply_button.setEnabled(self.draft.can_apply())

    def _on_tab(self, code: str) -> None:
        self._program = code
        self.message.hide()
        self.draft.check_displayed(code)
        self.refresh()

    def _choose(self, key: str, method: str) -> None:
        start = self.draft.effective(self._program, key)[0]
        start_dir = str(Path(start).parent) if start else None
        path = getattr(self._ctx.chooser, method)(self, start_dir)
        if path:
            self.message.hide()
            self.draft.set_path(self._program, key, path)

    def _restore(self) -> None:
        self.message.hide()
        self.draft.reset_program(self._program)
        self.draft.check_displayed(self._program)
        self.refresh()

    # --- 정책 만들기 ---
    def build_wizard(self) -> PolicyWizardDialog:
        template, _ = self.draft.effective(self._program, "template_path")
        wizard = PolicyWizardDialog(self._program, template, self._model.store.path.parent, self._ctx.chooser, self)
        program = self._program
        wizard.accepted.connect(lambda: self._adopt(program, wizard))
        return wizard

    def _adopt(self, program: str, wizard: PolicyWizardDialog) -> None:
        """만든 정책 파일을 임시 편집 상태에만 반영한다(저장 및 적용 전까지 실제 설정은 그대로)."""
        if wizard.created_path:
            self.message.hide()
            self.draft.set_path(program, "policy_path", str(wizard.created_path))

    def _open_wizard(self) -> None:
        template, _ = self.draft.effective(self._program, "template_path")
        if not template or not self.draft.state(self._program, "template_path").ok:
            self._say("먼저 이 사업의 출력 템플릿을 지정하고 확인되어야 정책 파일을 만들 수 있습니다(머리글을 템플릿에서 읽습니다).")
            return
        self.build_wizard().exec()

    # --- 정책 수정 ---
    def build_editor(self) -> PolicyEditDialog | None:
        """지금 보이는 정책 파일을 수정하는 대화상자. 정책 파일이 없으면 None. 수정은 같은 경로의 파일을 고치며 선택한 경로(설정)는 바꾸지 않는다."""
        path, _ = self.draft.effective(self._program, "policy_path")
        if not path:
            return None
        editor = PolicyEditDialog(self._program, path, self, allowed=self._edit_allowed)
        editor.edited_path = path
        return editor

    def finish_edit(self, editor: PolicyEditDialog) -> None:
        """수정 대화상자를 닫은 뒤: 저장했다면 표시 중인 정책의 검사를 다시 하고(설정값·경로는 그대로) Step 1 모델과 미리보기에 알린다."""
        if not editor.saved:
            return
        self.message.hide()
        self.draft.refresh_same_file("policy_path", editor.edited_path)      # 같은 파일을 쓰는 다른 사업의 이전 검사 결과도 버린다
        self._model.policy_edited(editor.edited_path)
        backup = f" 이전 내용은 '{editor.backup_name}'로 백업했습니다." if editor.backup_name else ""
        self.edit_result.setText(f"정책 파일에 저장했습니다.{backup} 이 창을 취소해도 저장한 정책 파일은 되돌아가지 않습니다.")
        self.edit_result.show()

    def _open_editor(self) -> None:
        if not self._edit_allowed():
            self._say("지금은 정책 파일을 수정할 수 없습니다. 첫 단계(파일 선택)에서 생성 중이 아닐 때만 수정할 수 있습니다.")
            return
        editor = self.build_editor()
        if editor is None:
            self._say("수정할 정책 파일이 없습니다. 먼저 정책 파일을 선택하거나 새로 만드세요.")
            return
        editor.exec()
        self.finish_edit(editor)

    def _say(self, text: str) -> None:
        self.message.setText(text)
        self.message.show()

    # --- 확정 · 취소 ---
    def apply(self) -> None:
        if not self.draft.can_apply():
            self._say("확인되지 않았거나 사용할 수 없는 경로가 있어 적용하지 않았습니다.")
            return
        self.outcome = self._model.apply_settings(self.draft.result())
        self.draft.discard()
        self.accept()

    def done(self, result: int) -> None:
        if result != QDialog.DialogCode.Accepted:
            self.draft.discard()                 # 취소·닫기·Esc: 편집 내용을 버린다
        super().done(result)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.ignore()                       # Enter 로 의도치 않게 적용되지 않게 한다(버튼은 Space 로 누른다)
            return
        super().keyPressEvent(event)

