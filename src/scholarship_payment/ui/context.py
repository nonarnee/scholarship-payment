"""화면이 쓰는 외부 자원 묶음(설정 저장소·백그라운드 실행기·파일 선택기·오늘 날짜·기본 탐색 폴더). 테스트는 가짜로 바꿔 넣는다."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from scholarship_payment.ui.state import SettingsStore


@dataclass
class AppContext:
    store: SettingsStore
    runner: object
    chooser: object
    today: Callable[[], date] = date.today
    default_dirs: list | None = None          # None 이면 기본 위치(실행 폴더·%APPDATA%)에서 찾는다

    @classmethod
    def default(cls) -> "AppContext":
        from scholarship_payment.ui.choosers import QtChooser
        from scholarship_payment.ui.qt_runner import QtRunner

        return cls(store=SettingsStore(), runner=QtRunner(), chooser=QtChooser())
