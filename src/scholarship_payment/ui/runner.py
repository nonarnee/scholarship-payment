"""백그라운드 실행기 인터페이스(Qt 무관). `submit(fn, callback)`: fn() 을 (다른 스레드에서) 실행하고 결과를 callback(result)에 **호출한 쪽 스레드로** 돌려준다.
- InlineRunner: 즉시 실행(테스트·단순 경로). ManualRunner: 대기열에 쌓아 두고 테스트가 순서를 정해 실행한다.
- 실제 Qt 구현은 `qt_runner.QtRunner`.
"""
from __future__ import annotations

from typing import Callable, Protocol


class Runner(Protocol):
    def submit(self, fn: Callable[[], object], callback: Callable[[object], None]) -> None: ...


class InlineRunner:
    def submit(self, fn, callback) -> None:
        callback(fn())


class ManualRunner:
    def __init__(self) -> None:
        self.pending: list[tuple[Callable, Callable]] = []

    def submit(self, fn, callback) -> None:
        self.pending.append((fn, callback))

    def run(self, index: int) -> None:
        fn, callback = self.pending[index]
        callback(fn())

    def run_all(self) -> None:
        for i in range(len(self.pending)):
            self.run(i)
        self.pending.clear()
