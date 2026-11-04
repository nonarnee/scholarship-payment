"""화면이 쓰는 외부 자원 묶음(설정 저장소·백그라운드 실행기·파일 선택기·오늘 날짜·기본 탐색 폴더). 테스트는 가짜로 바꿔 넣는다."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from scholarship_payment.ui.state import SettingsStore


@dataclass
class AppContext:
    store: SettingsStore
    runner: object
    chooser: object
    today: Callable[[], date] = date.today
    default_dirs: list | None = None          # None 이면 기본 위치(실행 폴더·%APPDATA%)에서 찾는다
    generation_runner: object | None = None   # 지급명단 생성 전용 워커(None 이면 runner 를 함께 쓴다 — 테스트용)
    actions: object | None = None             # 결과 폴더 열기·경로 복사(None 이면 아무것도 하지 않는 기본 동작)
    now: Callable[[], datetime] = datetime.now

    @property
    def gen_runner(self):
        return self.generation_runner if self.generation_runner is not None else self.runner

    @property
    def system_actions(self):
        return self.actions if self.actions is not None else _NoActions()

    @classmethod
    def default(cls) -> "AppContext":
        from scholarship_payment.ui.choosers import QtChooser
        from scholarship_payment.ui.qt_runner import QtRunner
        from scholarship_payment.ui.system_actions import QtActions

        # 검사·미리보기용 워커와 생성 전용 워커를 분리한다(생성이 해시 계산 뒤에 밀리지 않고, 닫기 처리도 생성 워커만 보면 된다)
        return cls(store=SettingsStore(), runner=QtRunner(), chooser=QtChooser(), generation_runner=QtRunner(), actions=QtActions())


class _NoActions:
    def open_folder(self, path) -> bool:
        return False

    def copy_text(self, text) -> bool:
        return False
