"""Qt 백그라운드 실행기: 검사 함수를 작업 스레드에서 실행하고 결과를 **화면(메인) 스레드**의 콜백으로 돌려준다.
스레드는 1개로 제한한다(무거운 검사를 차례로 처리). 작업 함수가 예외를 내도 내용은 남기지 않고 고정 오류 코드로 바꾼다.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from scholarship_payment.ui import validators as v


class _Job(QRunnable):
    def __init__(self, fn, number: int, signal) -> None:
        super().__init__()
        self._fn, self._number, self._signal = fn, number, signal

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception:
            result = v.FieldState(v.ERROR, "CHECK_FAILED")
        try:
            self._signal.emit(self._number, result)
        except RuntimeError:                      # 창이 이미 닫혀 신호 대상이 사라졌다
            pass


class QtRunner(QObject):
    _done = Signal(int, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._callbacks: dict[int, object] = {}
        self._n = 0
        self._done.connect(self._deliver)

    def submit(self, fn, callback) -> None:
        self._n += 1
        self._callbacks[self._n] = callback
        self._pool.start(_Job(fn, self._n, self._done))

    @Slot(int, object)
    def _deliver(self, number: int, result) -> None:
        cb = self._callbacks.pop(number, None)
        if cb is not None:
            cb(result)

    def pending(self) -> int:
        return len(self._callbacks)

    def shutdown(self, timeout_ms: int = 3000) -> bool:
        self._callbacks.clear()                   # 닫는 중이면 남은 결과는 쓰지 않는다
        return self._pool.waitForDone(timeout_ms)
