"""미리보기 세션(Qt 무관 상태 기계): Step 2 에서 `run_prepare` 를 백그라운드로 실행하고 결과·비밀번호 시도·변경 감지를 관리한다.

- 처리 중에는 중복 실행을 무시한다. 이전 단계로 가거나 취소(discard)하면 진행 중이던 결과를 모두 버린다(토큰).
- 비밀번호는 암호 파일일 때만 묻고 최대 3번까지 받는다(세션 동안 누적, discard 로 초기화). 비밀번호는 작업 직전까지만 `_PasswordBox` 에 있고
  작업이 시작되면 꺼내 쓰고 비운다. 세션·결과에는 보관하지 않는다.
- 파일 변경이 감지되면 미리보기를 무효화(INVALIDATED)하고 **자동으로 다시 읽지 않는다**(사용자가 명시적으로 다시 시작).
- 파일을 만들지 않는다(`finish` 는 Phase 4).
"""
from __future__ import annotations

from typing import Callable

from scholarship_payment.app import workflow
from scholarship_payment.app.convert import Prepared, diagnose_changes
from scholarship_payment.ui.runner import Runner

IDLE, PREPARING, NEED_PASSWORD, READY, FAILED, INVALIDATED, CANCELLED, LOCKED = (
    "idle", "preparing", "need_password", "ready", "failed", "invalidated", "cancelled", "locked")
MAX_ATTEMPTS = 3


class _PasswordBox:
    """대기 중인 작업이 쓸 비밀번호를 한 번만 꺼낼 수 있게 담는다."""

    def __init__(self, value: str | None) -> None:
        self.value = value

    def take(self) -> str | None:
        v, self.value = self.value, None
        return v

    def clear(self) -> None:
        self.value = None


class PreviewSession:
    def __init__(self, runner: Runner, prepare_fn: Callable = workflow.run_prepare) -> None:
        self._runner, self._prepare_fn = runner, prepare_fn
        self._listeners: list[Callable[[], None]] = []
        self._token = 0
        self._selection = None
        self._box: _PasswordBox | None = None
        self.attempts = 0
        self._reset_result()
        self.state = IDLE

    # --- 구독·읽기 ---
    def on_change(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _set(self, state: str) -> None:
        self.state = state
        for fn in list(self._listeners):
            fn()

    def _reset_result(self) -> None:
        self.prepared: Prepared | None = None
        self.summary: workflow.PreviewSummary | None = None
        self.errors: tuple[workflow.IssueGroup, ...] = ()
        self.missing_banks: tuple[str, ...] = ()
        self.changed: tuple[str, ...] = ()
        self.changed_codes: dict[str, str] = {}           # 파일 이름 → INPUT_FILE_CHANGED(바뀜·삭제) | INPUT_FILE_UNREADABLE(읽을 수 없음)
        self.last_password_wrong = False

    @property
    def busy(self) -> bool:
        return self.state == PREPARING

    # --- 시작·중단 ---
    def start(self, selection) -> None:
        """Step 2 진입(또는 사용자가 '다시 확인'을 눌렀을 때). 처리 중이거나 비밀번호 3회 실패로 잠겼으면 무시한다."""
        if self.busy or self.state == LOCKED:
            return
        self._selection = selection
        self._reset_result()
        self._run(None)

    def discard(self) -> None:
        """이전 단계로 이동·취소: 진행 중 결과를 버리고 모든 상태를 초기화한다."""
        self._token += 1
        if self._box is not None:
            self._box.clear()
            self._box = None
        self._selection = None
        self.attempts = 0
        self._reset_result()
        self._set(IDLE)

    def _run(self, password: str | None) -> None:
        self._token += 1
        token, sel = self._token, self._selection
        box = self._box = _PasswordBox(password)
        password = None

        def job():
            pw = box.take()                                    # 꺼내 쓰고 바로 비운다
            return self._prepare_fn(sel.program, sel.source_path, sel.template_path, sel.policy_path, sel.base_date, pw)

        self._set(PREPARING)
        self._runner.submit(job, lambda outcome: self._done(token, outcome))

    # --- 비밀번호 ---
    def submit_password(self, password: str) -> None:
        if self.state != NEED_PASSWORD or self._selection is None:
            return
        self._run(password)

    def cancel_password(self) -> None:
        if self.state == NEED_PASSWORD:
            self._reset_result()
            self._set(CANCELLED)

    # --- 결과 ---
    def _done(self, token: int, o: workflow.PrepareOutcome) -> None:
        if token != self._token or self.state != PREPARING:
            return                                             # 이전 단계로 갔거나 새 실행이 시작됨 → 오래된 결과 폐기
        self._box = None
        self._reset_result()
        if o.status == workflow.OK:
            self.prepared, self.summary = o.prepared, o.summary
            self._set(READY)
        elif o.status == workflow.PASSWORD_REQUIRED_STATUS:
            self._set(NEED_PASSWORD)
        elif o.status == workflow.PASSWORD_WRONG_STATUS:
            self.attempts += 1
            self.last_password_wrong = True
            self.errors = o.errors
            self._set(LOCKED if self.attempts >= MAX_ATTEMPTS else NEED_PASSWORD)
        elif o.status == workflow.CHANGED:
            self.errors, self.changed = o.errors, tuple(f for g in o.errors for f in g.fields)
            self.changed_codes = {f: g.code for g in o.errors for f in g.fields}
            self._set(INVALIDATED)
        else:
            self.errors, self.missing_banks = o.errors, o.missing_banks
            self._set(FAILED)

    # --- 변경 감지(미리보기 이후) ---
    def verify_fresh(self) -> None:
        """READY 일 때 원본·템플릿·정책의 SHA-256 을 백그라운드에서 다시 확인한다. 달라졌으면 미리보기를 무효화한다."""
        if self.state != READY or self.prepared is None:
            return
        token, prepared = self._token, self.prepared
        self._runner.submit(lambda: diagnose_changes(prepared), lambda changed: self._verified(token, prepared, changed))

    def _verified(self, token: int, prepared: Prepared, changed: dict[str, str]) -> None:
        if token != self._token or self.state != READY or self.prepared is not prepared or not changed:
            return
        self._reset_result()
        self.changed, self.changed_codes = tuple(changed), dict(changed)
        self._set(INVALIDATED)
