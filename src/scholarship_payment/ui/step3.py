"""Step 3 · 결과 생성 화면. `GenerationSession` 의 상태를 보여 줄 뿐 업무 규칙·파일 처리를 하지 않는다.

- **엔진이 실제로 돌려준 값만** 표시한다: 저장된 파일 이름(이름이 바뀌었으면 실제 이름), 저장 위치, 대상자 수, 지급 합계(`Prepared`), 파일 크기·완료 시각(저장 직후 측정),
  '출력 재검증 통과'(finish() 가 성공했을 때만). 소요시간·진행률 추정, 정확도·계좌 실명 검증 비율, 학생별 정보, 파일 직접 열기는 없다.
- 실패는 종류별로 안내한다: 템플릿(고급 설정·처음부터 다시 확인) / 저장 폴더(폴더 변경 후 같은 확인 결과로 재시도) / 출력 재검증(재시도 불가) / 예기치 않은 오류.
- 이전 실행이 남긴 `.~` 임시 파일은 개수만 알리고 지우지 않는다. 경로는 사용자 화면에만 보이고 로그에는 남기지 않는다.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from scholarship_payment.ui import generation as gn
from scholarship_payment.ui import status_view, validators
from scholarship_payment.ui.step2 import IssueRow
from scholarship_payment.ui.theme import SPACING
from scholarship_payment.ui.widgets import AppButton, Badge, Card, ElidedLabel, PathField

FAILURE_TEXT = {
    gn.KIND_FOLDER: ("저장 폴더에 파일을 만들지 못했습니다",
                     "이번 작업으로 새 파일을 만들지 않았습니다. 저장 폴더를 바꾸거나 문제를 해결한 뒤 같은 확인 결과로 다시 시도할 수 있습니다. 원본·템플릿·정책 파일이 바뀌었는지는 만들기 직전에 다시 확인합니다."),
    gn.KIND_TEMPLATE: ("출력 템플릿의 구조가 맞지 않아 파일을 만들지 못했습니다",
                       "템플릿 구조는 이 단계에서 처음 확인합니다(지급내역 확인에서는 확인하지 않았습니다). 이번 작업으로 새 파일을 만들지 않았습니다. 고급 설정에서 템플릿을 확인한 뒤 파일 선택부터 다시 확인하세요."),
    gn.KIND_VERIFY: ("만든 파일의 출력 재검증에 실패해 결과를 공개하지 않았습니다",
                     "결과 파일을 공개하지 않았습니다(저장 폴더의 기존 파일은 그대로입니다). 같은 확인 결과로는 다시 만들 수 없습니다. 파일 선택부터 다시 확인하고, 반복되면 담당자에게 알려 주세요."),
    gn.KIND_UNEXPECTED: ("예기치 않은 오류가 발생했습니다",
                         "저장 폴더를 확인하세요. 이번 작업으로 만들어진 파일이 있는지 이 화면에서는 알 수 없습니다. 같은 확인 결과로는 다시 만들 수 없으니 파일 선택부터 다시 확인하세요."),
}


class Step3Page(QWidget):
    def __init__(self, generation: gn.GenerationSession, preview, model, context, open_settings, go_file, new_conversion, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.generation, self.preview, self.model, self.ctx = generation, preview, model, context
        self._open_settings, self._go_file, self._new_conversion = open_settings, go_file, new_conversion
        self._selection = None
        root = QVBoxLayout(self)
        m = SPACING["lg"]
        root.setContentsMargins(m, m, m, m)
        root.setSpacing(SPACING["md"])
        title = QLabel("결과 생성")
        title.setProperty("role", "headline")
        root.addWidget(title)

        # 생성 중: 끝을 알 수 없는 진행 표시만(시간·비율 추정 없음)
        self.progress_box = Card()
        self.progress_label = QLabel("지급명단을 만들고 저장하는 중입니다…")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress_hint = QLabel("저장하는 동안에는 이전 단계로 이동하거나 창을 닫을 수 없습니다.")
        self.progress_hint.setProperty("role", "hint")
        self.close_notice = QLabel("")
        self.close_notice.setProperty("role", "error")
        self.close_notice.setWordWrap(True)
        self.close_notice.hide()
        for w in (self.progress_label, self.progress, self.progress_hint, self.close_notice):
            self.progress_box.body.addWidget(w)
        root.addWidget(self.progress_box)

        # 성공
        self.result_box = QWidget()
        rl = QVBoxLayout(self.result_box)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(SPACING["md"])
        self.result_badge = Badge("", "verified")
        rl.addWidget(self.result_badge, 0, Qt.AlignmentFlag.AlignLeft)
        file_card = Card()
        cap = QLabel("저장된 파일")
        cap.setProperty("role", "hint")
        self.file_name_value = QLabel("")
        self.file_name_value.setProperty("role", "headline")
        self.file_name_value.setWordWrap(True)
        self.file_name_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_cap = QLabel("저장 위치")
        folder_cap.setProperty("role", "hint")
        self.folder_value = ElidedLabel("")
        self.name_notice = QLabel("")
        self.name_notice.setWordWrap(True)
        self.name_notice.setProperty("role", "hint")
        self.verify_label = QLabel("")
        self.verify_label.setWordWrap(True)
        for w in (cap, self.file_name_value, folder_cap, self.folder_value, self.name_notice, self.verify_label):
            file_card.body.addWidget(w)
        rl.addWidget(file_card)
        metrics = QHBoxLayout()
        metrics.setSpacing(SPACING["md"])
        self.count_value, self.total_value, self.size_value, self.time_value, self.template_value = (QLabel("") for _ in range(5))
        for caption, value in (("처리 대상자 수", self.count_value), ("지급 합계", self.total_value), ("파일 크기", self.size_value),
                               ("완료 시각", self.time_value), ("적용 템플릿", self.template_value)):
            card = Card()
            c = QLabel(caption)
            c.setProperty("role", "hint")
            value.setProperty("role", "section")
            value.setWordWrap(True)
            card.body.addWidget(c)
            card.body.addWidget(value)
            metrics.addWidget(card, 1)
        rl.addLayout(metrics)
        self.leftover_notice = QLabel("")
        self.leftover_notice.setWordWrap(True)
        self.leftover_notice.setProperty("role", "hint")
        rl.addWidget(self.leftover_notice)
        actions = QHBoxLayout()
        self.open_folder_button = AppButton("결과 폴더 열기", "primary")
        self.copy_path_button = AppButton("경로 복사", "secondary")
        self.action_status = QLabel("")
        self.action_status.setProperty("role", "hint")
        actions.addWidget(self.open_folder_button)
        actions.addWidget(self.copy_path_button)
        actions.addWidget(self.action_status, 1)
        rl.addLayout(actions)
        root.addWidget(self.result_box)

        # 실패
        self.failure_box = QWidget()
        fl = QVBoxLayout(self.failure_box)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(SPACING["md"])
        self.failure_headline = QLabel("")
        self.failure_headline.setProperty("role", "headline")
        self.failure_headline.setWordWrap(True)
        self.failure_note = QLabel("")
        self.failure_note.setWordWrap(True)
        fl.addWidget(self.failure_headline)
        fl.addWidget(self.failure_note)
        self.folder_box = Card("저장 폴더")
        row = QHBoxLayout()
        self.folder_field = PathField()
        self.change_folder_button = AppButton("저장 폴더 변경", "secondary")
        self.retry_button = AppButton("같은 확인 결과로 다시 시도", "primary")
        row.addWidget(self.folder_field, 1)
        row.addWidget(self.change_folder_button)
        self.folder_message = QLabel("")
        self.folder_message.setProperty("role", "error")
        self.folder_message.setWordWrap(True)
        self.folder_message.hide()
        self.folder_box.body.addLayout(row)
        self.folder_box.body.addWidget(self.folder_message)
        self.folder_box.body.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignLeft)
        fl.addWidget(self.folder_box)
        frow = QHBoxLayout()
        self.settings_button = AppButton("고급 설정 열기", "secondary")
        self.restart_button = AppButton("파일 선택부터 다시 확인", "secondary")
        frow.addWidget(self.settings_button)
        frow.addWidget(self.restart_button)
        frow.addStretch(1)
        fl.addLayout(frow)
        root.addWidget(self.failure_box)

        # 경고·참고·오류 목록, 새 변환
        self.issues_box = QVBoxLayout()
        self.issues_box.setSpacing(SPACING["sm"])
        root.addLayout(self.issues_box)
        self.new_button = AppButton("새 변환", "secondary")
        root.addWidget(self.new_button, 0, Qt.AlignmentFlag.AlignLeft)
        root.addStretch(1)

        self.open_folder_button.clicked.connect(self._open_folder)
        self.copy_path_button.clicked.connect(self._copy_path)
        self.new_button.clicked.connect(lambda: self._new_conversion())
        self.change_folder_button.clicked.connect(self._change_folder)
        self.retry_button.clicked.connect(self._retry)
        self.settings_button.clicked.connect(lambda: self._open_settings())
        self.restart_button.clicked.connect(lambda: self._go_file())
        self.generation.on_change(self._render)
        for a, b in ((self.open_folder_button, self.copy_path_button), (self.copy_path_button, self.change_folder_button),
                     (self.change_folder_button, self.retry_button), (self.retry_button, self.settings_button),
                     (self.settings_button, self.restart_button), (self.restart_button, self.new_button)):
            self.setTabOrder(a, b)
        self._render()

    # --- 시작 · 동작 ---
    def enter(self, selection) -> None:
        """Step 2 에서 '지급명단 생성'으로 들어왔다. 확인 결과(`Prepared`)가 있으면 생성을 시작한다(이미 진행·완료·실패한 것이면 시작하지 않고 보여 주기만 한다)."""
        self._selection = selection
        prepared = self.preview.prepared
        if prepared is not None and selection is not None:
            self.generation.start(prepared, selection.out_dir)
        self._render()

    def show_close_blocked(self) -> None:
        self.close_notice.setText("저장 중에는 창을 닫을 수 없습니다. 저장이 끝난 뒤 닫을 수 있습니다.")
        self.close_notice.show()

    def _output(self) -> str | None:
        o = self.generation.outcome
        return o.output_path if o and o.status == "ok" else None

    def _open_folder(self) -> None:
        out = self._output()
        ok = bool(out) and self.ctx.system_actions.open_folder(Path(out).parent)
        self.action_status.setText("" if ok else "폴더를 열지 못했습니다. 저장 위치의 경로를 직접 여세요.")      # 폴더 열기 실패는 생성 실패가 아니다

    def _copy_path(self) -> None:
        out = self._output()
        ok = bool(out) and self.ctx.system_actions.copy_text(out)
        self.action_status.setText("경로를 복사했습니다." if ok else "경로를 복사하지 못했습니다.")

    def _change_folder(self) -> None:
        start = self.generation.out_dir
        path = self.ctx.chooser.choose_folder(self, start)
        if not path:
            return
        st = self.generation.set_out_dir(path)
        self.folder_message.setText(validators.message(st.code) if not st.ok else "")
        self.folder_message.setVisible(not st.ok)
        self._render()

    def _retry(self) -> None:
        self.generation.retry()

    # --- 표시 ---
    def issue_rows(self) -> list[IssueRow]:
        return [self.issues_box.itemAt(i).widget() for i in range(self.issues_box.count())]

    def _clear_issues(self) -> None:
        while self.issues_box.count():
            w = self.issues_box.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _render(self) -> None:
        g = self.generation
        st, o = g.state, g.outcome
        self._clear_issues()
        failed = st == gn.FAILED
        self.progress_box.setVisible(st == gn.GENERATING)
        self.result_box.setVisible(g.done)
        self.failure_box.setVisible(failed)
        self.new_button.setVisible(g.done or failed)
        self.new_button.setEnabled(not g.busy)
        if st != gn.GENERATING:
            self.close_notice.hide()
        if g.done and o is not None:
            self._render_success(o)
        if failed and o is not None:
            self._render_failure(o)

    def _render_success(self, o) -> None:
        warn = len(o.warnings)
        self.result_badge.setText("저장·출력 재검증 통과" + (f" (경고 {warn}종)" if warn else ""))
        self.result_badge.set_kind("caution" if warn else "verified")
        p = Path(o.output_path)
        self.file_name_value.setText(p.name)
        self.folder_value.set_full_text(str(p.parent))
        self.name_notice.setText("같은 이름의 파일이 이미 있어 다른 이름으로 저장했습니다. 기존 파일은 그대로 있습니다." if o.name_changed else "")
        self.name_notice.setVisible(o.name_changed)
        self.verify_label.setText("출력 재검증 통과: 저장하기 전에 만든 파일을 다시 읽어 지급 데이터와 대조했습니다.")
        self.count_value.setText(f"{o.count}명")
        self.total_value.setText(f"{o.total_amount:,}원")
        self.size_value.setText(status_view.human_size(o.size_bytes) if o.size_bytes is not None else "확인하지 못함")
        self.time_value.setText(o.finished_at or "확인하지 못함")
        self.template_value.setText(o.template_name)
        self.leftover_notice.setText(f"저장 폴더에 이전 실행에서 남은 것으로 보이는 임시 파일(.~로 시작하는 .xlsx)이 {o.leftover_temp}개 있습니다. 자동으로 지우지 않으니 필요하면 직접 정리하세요."
                                     if o.leftover_temp else "")
        self.leftover_notice.setVisible(bool(o.leftover_temp))
        self.action_status.setText("")
        for groups in (o.warnings, o.notes):
            for grp in groups:
                self.issues_box.addWidget(IssueRow(grp))

    def _render_failure(self, o) -> None:
        kind = self.generation.failure_kind or gn.KIND_UNEXPECTED
        headline, note = FAILURE_TEXT.get(kind, FAILURE_TEXT[gn.KIND_UNEXPECTED])
        self.failure_headline.setText(headline)
        self.failure_note.setText(note)
        for grp in o.errors:
            self.issues_box.addWidget(IssueRow(grp))
        folder = kind == gn.KIND_FOLDER
        self.folder_box.setVisible(folder)
        self.folder_field.set_path(self.generation.out_dir, "저장 폴더")
        self.retry_button.setVisible(folder and self.generation.can_retry)
        self.retry_button.setEnabled(not self.generation.busy)
        self.change_folder_button.setEnabled(not self.generation.busy)
        self.settings_button.setVisible(kind == gn.KIND_TEMPLATE)
        self.restart_button.setVisible(not folder)
