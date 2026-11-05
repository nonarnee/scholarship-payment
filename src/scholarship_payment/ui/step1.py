"""Step 1 · 파일 선택 화면. 모델(`Step1Model`)의 상태를 보여 주고 사용자의 선택을 모델에 전달한다. 업무 규칙·파일 파싱은 하지 않는다.
Stitch step-1 구성(사업/기준일 → 원본 파일 → 저장 위치 → 적용 서식·규칙 띠)을 따르되, 이 프로그램이 측정하지 않는 값
(건수 감지, 열 매핑 수, 엔진 버전 표시, 사용자 아이콘 등)은 만들지 않는다.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from scholarship_payment.config import user_settings as us
from scholarship_payment.ui import status_view, validators
from scholarship_payment.ui.settings_dialog import PROGRAM_LABELS, AdvancedSettingsDialog
from scholarship_payment.ui.state import Step1Model
from scholarship_payment.ui.theme import SPACING
from scholarship_payment.ui.widgets import AppButton, Badge, Card, DropZone, ElidedLabel, PathField

STEP1_PROGRAM_LABELS = {"daechung": "대청교 (대학생 청소년교육지원)", "multicultural": "다문화·탈북학생 멘토링", "ai": "AI멘토링"}
BLOCKING_LABELS = {"source": "원본 파일", "out_dir": "저장 폴더", "template": "템플릿", "policy": "정책 파일", "date": "기준일"}
PERSIST_FAILED_NOTICE = "변경 내용을 현재 실행에는 적용했지만 설정 파일에 저장하지 못했습니다. 프로그램을 다시 시작하면 이번 변경이 사라집니다."
_SETTINGS_NOTICES = {
    us.LOAD_RECOVERED: "설정 파일을 읽지 못해 기본값으로 시작했습니다. 손상된 파일은 {name} 이름으로 보존했습니다.",
    us.LOAD_RESET_UNPRESERVED: "설정 파일을 읽지 못해 기본값으로 시작했습니다. 손상된 파일을 따로 보존하지는 못했습니다(원본은 그대로 있습니다).",
    us.LOAD_UNREADABLE: "설정 파일을 읽지 못해 기본값으로 시작했습니다(파일은 그대로 있습니다).",
}


def _head(title: str, badge: Badge | None = None) -> QHBoxLayout:
    row = QHBoxLayout()
    label = QLabel(title)
    label.setProperty("role", "section")
    row.addWidget(label)
    row.addStretch(1)
    if badge is not None:
        row.addWidget(badge)
    return row


def _hint(text: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setProperty("role", "hint")
    lab.setWordWrap(True)
    return lab


class Step1Page(QWidget):
    def __init__(self, model: Step1Model, context, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model, self.ctx = model, context
        self.policy_edit_allowed = lambda: True        # 정책 파일 수정 가능 여부. MainWindow 가 '첫 단계이고 생성 중이 아님'으로 바꿔 끼운다
        root = QVBoxLayout(self)
        m = SPACING["lg"]
        root.setContentsMargins(m, m, m, m)
        root.setSpacing(SPACING["md"])

        # 설정 안내(손상 복구·저장 실패). 평소에는 숨김
        self.notice = QFrame()
        self.notice.setObjectName("Notice")
        nl = QHBoxLayout(self.notice)
        nl.setContentsMargins(SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"])
        self.notice_label = QLabel("")
        self.notice_label.setWordWrap(True)
        self.notice_close = AppButton("닫기", "link")
        nl.addWidget(self.notice_label, 1)
        nl.addWidget(self.notice_close)
        self.notice.hide()
        root.addWidget(self.notice)

        # 머리글
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("장학금 지급명단 변환")
        title.setProperty("role", "headline")
        sub = QLabel("한국장학재단 월별지급승인 파일을 대학 표준 지급명단 엑셀 양식으로 변환합니다.")
        sub.setProperty("role", "secondary")
        sub.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(sub)
        header.addLayout(titles, 1)
        self.settings_button = AppButton("고급 설정", "secondary")
        header.addWidget(self.settings_button, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        # 사업 구분 · 기준일
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])
        c1 = Card()
        c1.body.addLayout(_head("사업 구분", Badge("필수", "info")))
        self.program_combo = QComboBox()
        for code in PROGRAM_LABELS:
            self.program_combo.addItem(STEP1_PROGRAM_LABELS[code], code)
        c1.body.addWidget(self.program_combo)
        c1.body.addWidget(_hint("선택한 사업에 지정된 템플릿·정책 파일이 적용됩니다."))
        c1.body.addStretch(1)
        c2 = Card()
        c2.body.addLayout(_head("기준일자 (작성일)", Badge("기본값: 오늘", "neutral")))
        self.date_edit = QLineEdit(model.base_date)
        self.date_edit.setPlaceholderText("YYYY.MM.DD")
        c2.body.addWidget(self.date_edit)
        self.date_error = QLabel("")
        self.date_error.setProperty("role", "error")
        self.date_error.hide()
        c2.body.addWidget(self.date_error)
        c2.body.addWidget(_hint("지급대상자명단의 작성일로 쓰입니다. 형식: YYYY.MM.DD"))
        c2.body.addStretch(1)
        row.addWidget(c1, 1)
        row.addWidget(c2, 1)
        root.addLayout(row)

        # 원본 파일
        src = Card()
        head = QHBoxLayout()
        label = QLabel("재단 승인 원본 파일 (.xlsx)")
        label.setProperty("role", "section")
        head.addWidget(label)
        head.addStretch(1)
        self.reset_button = AppButton("초기화", "link")
        self.pick_button = AppButton("파일 선택", "secondary")
        head.addWidget(self.reset_button)
        head.addWidget(self.pick_button)
        src.body.addLayout(head)
        self.drop_zone = DropZone()
        info = QHBoxLayout()
        icon = QFrame()
        icon.setObjectName("FileIcon")
        icon.setFixedSize(40, 40)
        il = QVBoxLayout(icon)
        il.setContentsMargins(0, 0, 0, 0)
        tag = QLabel("XLSX")
        tag.setProperty("role", "icon")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        il.addWidget(tag)
        info.addWidget(icon)
        text = QVBoxLayout()
        name_row = QHBoxLayout()
        self.file_name = ElidedLabel("선택된 파일이 없습니다")
        self.file_name.setProperty("role", "filename")
        self.file_size = QLabel("")
        self.file_size.setProperty("role", "hint")
        name_row.addWidget(self.file_name, 1)
        name_row.addWidget(self.file_size)
        text.addLayout(name_row)
        self.file_path = ElidedLabel("")
        self.file_path.setProperty("role", "secondary")
        text.addWidget(self.file_path)
        info.addLayout(text, 1)
        self.source_badge = Badge("", "neutral")
        info.addWidget(self.source_badge)
        self.drop_zone.body.addLayout(info)
        hint = _hint("또는 엑셀(.xlsx) 파일 한 개를 여기에 끌어다 놓으세요. 지급내역 내용은 다음 단계에서 확인합니다.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_zone.body.addWidget(hint)
        src.body.addWidget(self.drop_zone)
        self.source_message = QLabel("")
        self.source_message.setWordWrap(True)
        self.source_message.setProperty("role", "error")
        self.source_message.hide()
        src.body.addWidget(self.source_message)
        root.addWidget(src)

        # 저장 위치
        out = Card()
        out.body.addLayout(_head("결과 파일 저장 위치"))
        orow = QHBoxLayout()
        self.out_dir_field = PathField()
        self.out_dir_button = AppButton("폴더 변경", "secondary")
        orow.addWidget(self.out_dir_field, 1)
        orow.addWidget(self.out_dir_button)
        out.body.addLayout(orow)
        self.out_dir_message = _hint()
        out.body.addWidget(self.out_dir_message)
        root.addWidget(out)

        # 적용 서식·규칙 띠
        self.strip = QFrame()
        self.strip.setObjectName("Strip")
        sl = QVBoxLayout(self.strip)
        sl.setContentsMargins(SPACING["md"], SPACING["sm"], SPACING["md"], SPACING["sm"])
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("적용 서식:"))
        self.template_name = ElidedLabel("")
        self.template_badge = Badge("", "neutral")
        r1.addWidget(self.template_name, 1)
        r1.addWidget(self.template_badge)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("검증 규칙:"))
        self.policy_name = ElidedLabel("")
        self.policy_badge = Badge("", "neutral")
        r2.addWidget(self.policy_name, 1)
        r2.addWidget(self.policy_badge)
        r3 = QHBoxLayout()
        self.config_message = QLabel("")
        self.config_message.setProperty("role", "error")
        self.config_message.setWordWrap(True)
        self.replace_button = AppButton("규정/템플릿 교체", "link")
        r3.addWidget(self.config_message, 1)
        r3.addWidget(self.replace_button)
        sl.addLayout(r1)
        sl.addLayout(r2)
        sl.addLayout(r3)
        root.addWidget(self.strip)
        root.addStretch(1)

        # 연결
        self.program_combo.currentIndexChanged.connect(self._on_program)
        self.date_edit.textChanged.connect(self.model.set_base_date)
        self.pick_button.clicked.connect(self._pick_source)
        self.reset_button.clicked.connect(lambda: self.model.set_source(None))
        self.out_dir_button.clicked.connect(self._pick_out_dir)
        self.settings_button.clicked.connect(self.open_settings)
        self.replace_button.clicked.connect(self.open_settings)
        self.drop_zone.dropped.connect(self.model.set_source)
        self.drop_zone.rejected.connect(self._on_drop_rejected)
        self.notice_close.clicked.connect(self.notice.hide)
        self.model.on_change(self.refresh)

        order = [self.settings_button, self.program_combo, self.date_edit, self.pick_button, self.reset_button, self.out_dir_button, self.replace_button]
        for a, b in zip(order, order[1:]):
            self.setTabOrder(a, b)

        self._notice_kind: str | None = None
        status = model.store.load_status
        if status in _SETTINGS_NOTICES:
            self._show_notice(_SETTINGS_NOTICES[status].format(name=model.store.backup_name or ""), "load")
        self.program_combo.setCurrentIndex(list(PROGRAM_LABELS).index(model.program))
        self.refresh()

    # --- 동작 ---
    def _on_program(self, index: int) -> None:
        code = self.program_combo.itemData(index)
        if code and code != self.model.program:
            self.model.set_program(code)

    def _start_dir(self, field: str) -> str | None:
        cur = self.model.paths.get(field)
        return str(Path(cur).parent) if cur else None

    def _pick_source(self) -> None:
        path = self.ctx.chooser.open_source(self, self._start_dir("source") or self._start_dir("out_dir"))
        if path:
            self.model.set_source(path)

    def _pick_out_dir(self) -> None:
        path = self.ctx.chooser.choose_folder(self, self._start_dir("out_dir"))
        if path:
            self.model.set_out_dir(path)

    def _on_drop_rejected(self, code: str) -> None:
        self._set_message(self.source_message, validators.message(code))

    def build_settings_dialog(self) -> AdvancedSettingsDialog:
        return AdvancedSettingsDialog(self.model, self.ctx, self, policy_edit_allowed=lambda: self.policy_edit_allowed())

    def open_settings(self) -> None:
        self.build_settings_dialog().exec()

    def _show_notice(self, text: str, kind: str) -> None:
        self._notice_kind = kind
        self.notice_label.setText(text)
        self.notice.show()

    def _sync_persist_notice(self) -> None:
        """저장 실패 안내는 모델의 실제 상태(persist_failed)를 따른다: 나중에 저장에 성공하면 사라지고, 사업 전환 중 실패해도 보인다."""
        if self.model.persist_failed:
            self._show_notice(PERSIST_FAILED_NOTICE, "persist")
        elif self._notice_kind == "persist":
            self.notice.hide()
            self._notice_kind = None

    # --- 표시 ---
    @staticmethod
    def _set_message(label: QLabel, text: str) -> None:
        label.setText(text)
        label.setVisible(bool(text))

    def refresh(self) -> None:
        m = self.model
        self._sync_persist_notice()
        idx = list(PROGRAM_LABELS).index(m.program)
        if self.program_combo.currentIndex() != idx:
            self.program_combo.blockSignals(True)
            self.program_combo.setCurrentIndex(idx)
            self.program_combo.blockSignals(False)
        if self.date_edit.text() != m.base_date:
            self.date_edit.blockSignals(True)
            self.date_edit.setText(m.base_date)
            self.date_edit.blockSignals(False)
        ds = m.state("date")
        self._set_message(self.date_error, validators.message(ds.code) if not ds.ok else "")

        src = m.paths["source"]
        st = m.state("source")
        if src:
            p = Path(src)
            self.file_name.set_full_text(p.name)
            self.file_path.set_full_text(src)
            try:
                self.file_size.setText(status_view.human_size(os.stat(p).st_size))
            except OSError:
                self.file_size.setText("")
        else:
            self.file_name.set_full_text("선택된 파일이 없습니다")
            self.file_path.set_full_text("")
            self.file_size.setText("")
        text, kind = status_view.describe("source", st)
        self.source_badge.setText(text)
        self.source_badge.setVisible(bool(text))
        if kind:
            self.source_badge.set_kind(kind)
        self._set_message(self.source_message, status_view.detail(st) or ("선택하지 않았습니다" if st.level == validators.UNSET else ""))
        self.source_message.setProperty("role", "hint" if st.level != validators.ERROR else "error")
        self.source_message.style().unpolish(self.source_message)
        self.source_message.style().polish(self.source_message)

        out = m.paths["out_dir"]
        self.out_dir_field.set_path(out, "저장 폴더를 선택하세요")
        ost = m.state("out_dir")
        self.out_dir_message.setText(validators.message(ost.code) if ost.level == validators.ERROR
                                     else status_view.dir_message(ost) if ost.ok else "저장 폴더를 선택하지 않았습니다.")

        for key, name_label, badge, kind_name in (("template", self.template_name, self.template_badge, "template"), ("policy", self.policy_name, self.policy_badge, "policy")):
            path = m.paths[key]
            name_label.set_full_text(Path(path).name if path else "지정되지 않음")
            name_label.setToolTip(path or "")
            t, k = status_view.describe(kind_name, m.state(key))
            badge.setText(t)
            badge.setVisible(bool(t))
            if k:
                badge.set_kind(k)
        problems = [validators.message(m.state(k).code) for k in ("template", "policy") if m.state(k).level == validators.ERROR]
        self._set_message(self.config_message, " ".join(problems))
