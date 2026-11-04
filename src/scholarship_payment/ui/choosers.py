"""파일·폴더 선택 대화상자 모음. 화면은 이 인터페이스만 쓰고, 테스트는 가짜 선택기를 넣는다(실제 대화상자를 열지 않음).
선택한 경로는 호출한 쪽이 화면에 표시하는 데만 쓰며 로그로 남기지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtWidgets import QFileDialog


class Chooser(Protocol):
    def open_source(self, parent, start_dir: str | None = None) -> str | None: ...
    def open_template(self, parent, start_dir: str | None = None) -> str | None: ...
    def open_policy(self, parent, start_dir: str | None = None) -> str | None: ...
    def choose_folder(self, parent, start_dir: str | None = None) -> str | None: ...
    def save_policy(self, parent, suggested: Path) -> str | None: ...


class QtChooser:
    def _open(self, parent, title: str, start: str | None, filt: str) -> str | None:
        path, _ = QFileDialog.getOpenFileName(parent, title, start or "", filt)
        return path or None

    def open_source(self, parent, start_dir=None):
        return self._open(parent, "재단 승인 원본 파일 선택", start_dir, "엑셀 통합 문서 (*.xlsx)")

    def open_template(self, parent, start_dir=None):
        return self._open(parent, "출력 템플릿 선택", start_dir, "엑셀 통합 문서 (*.xlsx)")

    def open_policy(self, parent, start_dir=None):
        return self._open(parent, "정책 파일 선택", start_dir, "정책 파일 (*.json)")

    def choose_folder(self, parent, start_dir=None):
        return QFileDialog.getExistingDirectory(parent, "저장 폴더 선택", start_dir or "") or None

    def save_policy(self, parent, suggested: Path):
        # 덮어쓰기 확인 창을 띄우지 않는다(정책 파일은 덮어쓰지 않으므로, 있는 이름을 고르면 생성 단계에서 안내한다)
        path, _ = QFileDialog.getSaveFileName(parent, "정책 파일 저장 위치", str(suggested), "정책 파일 (*.json)", options=QFileDialog.Option.DontConfirmOverwrite)
        return path or None
