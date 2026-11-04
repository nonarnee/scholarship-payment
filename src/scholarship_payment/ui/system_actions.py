"""결과 화면의 시스템 동작: 결과 폴더 열기, 경로 복사. 둘 다 사용자가 버튼을 눌렀을 때만 실행하고, 실패해도 예외를 내지 않고 False 를 돌려준다.
경로는 로그에 남기지 않는다. 생성된 파일을 직접 여는 동작은 제공하지 않는다(폴더만 연다).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication


class QtActions:
    def open_folder(self, path) -> bool:
        try:
            folder = Path(path)
            if not folder.is_dir():
                return False
            return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))))
        except Exception:
            return False

    def copy_text(self, text) -> bool:
        try:
            clip = QGuiApplication.clipboard()
            if clip is None:
                return False
            clip.setText(str(text))
            return True
        except Exception:
            return False
