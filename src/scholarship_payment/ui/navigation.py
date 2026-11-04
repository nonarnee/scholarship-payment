"""화면 네비게이션 로직(Qt 무관): 3단계, 선행 조건(ready)이 충족돼야 다음 단계로 간다. 이전 단계로는 언제든 돌아갈 수 있다."""
from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum


class Step(IntEnum):
    FILE = 1
    REVIEW = 2
    RESULT = 3


STEP_TITLES = {Step.FILE: "파일 선택", Step.REVIEW: "지급내역 확인", Step.RESULT: "결과 생성"}


class Navigator:
    def __init__(self) -> None:
        self.current = Step.FILE
        self._ready = {s: False for s in Step}
        self._listeners: list[Callable[[], None]] = []
        self.locked = False                            # 생성 중·성공 후에는 모든 이동을 막는다(새 변환은 reset)

    def on_change(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in self._listeners:
            fn()

    def set_ready(self, step: int, ready: bool) -> None:
        self._ready[Step(step)] = bool(ready)      # 잘못된 값이면 ValueError
        self._notify()

    @property
    def completed(self) -> set[Step]:
        return {s for s in Step if s < self.current}

    def set_locked(self, locked: bool) -> None:
        if self.locked != bool(locked):
            self.locked = bool(locked)
            self._notify()

    def reset(self) -> None:
        """새 변환: 잠금을 풀고 처음 단계로 돌아간다(준비 상태는 호출한 쪽이 다시 설정한다)."""
        self.locked = False
        self.current = Step.FILE
        self._ready = {s: False for s in Step}
        self._notify()

    def can_next(self) -> bool:
        return not self.locked and self.current < Step.RESULT and self._ready[self.current]

    def can_back(self) -> bool:
        return not self.locked and self.current > Step.FILE

    def next(self) -> bool:
        if not self.can_next():
            return False
        self.current = Step(self.current + 1)
        self._notify()
        return True

    def back(self) -> bool:
        if not self.can_back():
            return False
        self.current = Step(self.current - 1)
        self._notify()
        return True

    def go(self, step: int) -> bool:
        """이전 단계로는 자유롭게, 앞으로는 바로 다음 단계(현재 단계가 ready)로만 이동한다. 잠겨 있으면 이동하지 않는다."""
        target = Step(step)
        if self.locked and target != self.current:
            return False
        if target < self.current:
            while self.current > target:
                if not self.back():                       # 이동할 수 없으면(잠금 등) 멈춘다. 무한 반복하지 않는다.
                    return False
            return True
        if target == self.current:
            return True
        if target == self.current + 1:
            return self.next()
        return False
