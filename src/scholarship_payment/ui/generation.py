"""생성(지급명단 파일 만들기) 상태 기계(Qt 무관). 미리보기에서 확인한 `Prepared` 를 `finish()` 에 넘겨 전용 워커에서 실행한다.

상태: IDLE → GENERATING → SUCCESS | SUCCESS_WITH_WARNINGS | FAILED(종류별) | INVALIDATED(파일 변경·읽기 불가).
- 중복 실행 차단: 생성 중에는 start/retry/reset 이 무시된다. 성공한 뒤에는 `reset()`(새 변환)으로만 다시 시작할 수 있다.
- 실패 종류: template(템플릿 레이아웃, 같은 Prepared 재시도 불가) / folder(저장 폴더, 같은 Prepared 로 폴더를 바꿔 재시도 가능, 생성 직전에 지문을 다시 확인) /
  verify(출력 재검증 실패, 자동·수동 재시도 불가) / unexpected. 모든 종류에서 이번 작업이 새 최종 파일을 남기지 않는다는 것은 엔진(`safe_save`)이 보장하고 이 계층은 바꾸지 않는다.
- 상태를 먼저 바꾸고 나서 화면에 알린다(화면 쪽 오류가 이미 만들어진 파일을 실패로 분류하지 않게).
- close() 이후에 도착한 결과는 반영하지 않는다(창이 닫힌 뒤 늦은 콜백이 사라진 위젯을 건드리지 않게).
"""
from __future__ import annotations

from typing import Callable

from scholarship_payment.app import workflow
from scholarship_payment.ui import validators as v
from scholarship_payment.ui.runner import Runner

IDLE, GENERATING, SUCCESS, SUCCESS_WITH_WARNINGS, FAILED, INVALIDATED = (
    "idle", "generating", "success", "success_with_warnings", "failed", "invalidated")
KIND_TEMPLATE, KIND_FOLDER, KIND_VERIFY, KIND_UNEXPECTED = workflow.KIND_TEMPLATE, workflow.KIND_FOLDER, workflow.KIND_VERIFY, workflow.KIND_UNEXPECTED
DONE_STATES = (SUCCESS, SUCCESS_WITH_WARNINGS)


class GenerationSession:
    def __init__(self, runner: Runner, finish_fn: Callable = workflow.run_finish, now: Callable | None = None) -> None:
        self._runner, self._finish_fn, self._now = runner, finish_fn, now
        self._listeners: list[Callable[[], None]] = []
        self._token = 0
        self._closed = False
        self._prepared = None            # 같은 Prepared 로 재시도할 수 있는 실패(folder)에서만 보관한다
        self._rejected = None            # 더 이상 쓸 수 없는 Prepared(참조만 보관해 같은 것을 다시 받지 않는다)
        self.out_dir: str | None = None
        self.split = False               # 시트별 3개 파일 저장 여부(이번 실행의 선택; 폴더 오류 재시도에서도 유지)
        self.outcome: workflow.FinishOutcome | None = None
        self.failure_kind: str | None = None
        self.state = IDLE

    def __repr__(self) -> str:
        return f"GenerationSession(state={self.state!r})"

    # --- 구독·읽기 ---
    def on_change(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _set(self, state: str) -> None:
        self.state = state                            # 상태를 먼저 확정한 뒤 알린다
        for fn in list(self._listeners):
            fn()

    @property
    def busy(self) -> bool:
        return self.state == GENERATING

    @property
    def done(self) -> bool:
        return self.state in DONE_STATES

    @property
    def can_retry(self) -> bool:
        return self.state == FAILED and self.failure_kind == KIND_FOLDER and self._prepared is not None

    # --- 실행 ---
    def start(self, prepared, out_dir, split: bool = False) -> bool:
        """생성을 시작한다. 처리 중이거나 이미 성공했거나 이미 쓸 수 없게 된 Prepared 면 무시하고 False."""
        if self._closed or self.state == GENERATING or self.done or prepared is None or prepared is self._rejected or prepared is self._prepared:
            return False
        self._rejected = None
        self.split = bool(split)
        self._begin(prepared, out_dir)
        return True

    def retry(self, out_dir=None) -> bool:
        """저장 폴더 오류 뒤 같은 Prepared 로 다시 시도한다(생성 직전에 원본·템플릿·정책 지문을 다시 확인한다)."""
        if self._closed or not self.can_retry:
            return False
        self._begin(self._prepared, out_dir if out_dir is not None else self.out_dir)
        return True

    def set_out_dir(self, path) -> v.FieldState:
        """저장 폴더를 바꾼다(가벼운 사전 확인만). 미리보기 검증을 대신하지 않으며 상태는 바꾸지 않는다."""
        if self.busy:
            return v.FieldState(v.ERROR, "DIR_MISSING")
        st = v.light("dir", path)
        if st.ok:
            self.out_dir = str(path)
        return st

    def _begin(self, prepared, out_dir) -> None:
        self._token += 1
        token = self._token
        self._prepared = prepared
        self.out_dir = str(out_dir)
        self.outcome, self.failure_kind = None, None
        finish_fn, now, folder, split = self._finish_fn, self._now, self.out_dir, self.split

        def job():
            try:
                return finish_fn(prepared, folder, now, split=True) if split else finish_fn(prepared, folder, now)
            except Exception:
                return None                           # 작업 안의 예상 밖 예외: 문구는 버리고 _done 이 '예기치 않은 오류'로 정리한다

        self._set(GENERATING)
        self._runner.submit(job, lambda outcome: self._done(token, outcome))

    def _done(self, token: int, o: workflow.FinishOutcome) -> None:
        if self._closed or token != self._token or self.state != GENERATING:
            return                                    # 닫힌 뒤·오래된 결과는 반영하지 않는다
        prepared = self._prepared
        if not isinstance(o, workflow.FinishOutcome):
            # 러너가 작업 예외를 다른 객체로 바꿨거나 None 이 왔다. GENERATING 에 갇히지 않도록 '예기치 않은 오류'로 정리한다(종류만, 문구 없음).
            o = workflow.FinishOutcome("failed", KIND_UNEXPECTED, requested_name=getattr(prepared, "filename", ""), count=getattr(prepared, "count", 0),
                                       total_amount=getattr(prepared, "total_amount", 0))
        self.outcome = o
        if o.status == "ok":
            self._prepared, self._rejected = None, prepared
            self._set(SUCCESS_WITH_WARNINGS if o.warnings else SUCCESS)
        elif o.status == "changed":
            self._prepared, self._rejected = None, prepared
            self._set(INVALIDATED)
        else:
            self.failure_kind = o.kind
            if o.kind != KIND_FOLDER:                 # 폴더 오류만 같은 Prepared 재시도를 허용한다
                self._prepared, self._rejected = None, prepared
            self._set(FAILED)

    # --- 초기화 · 종료 ---
    def reset(self) -> bool:
        """새 변환: 결과와 사용한 Prepared 를 모두 버린다. 생성 중에는 거부한다."""
        if self.busy:
            return False
        self._token += 1
        self._prepared = self._rejected = None
        self.outcome, self.failure_kind, self.out_dir, self.split = None, None, None, False
        self._set(IDLE)
        return True

    def close(self) -> None:
        """창이 닫힐 때: 이후에 도착하는 결과를 무시하고 화면 연결을 끊는다."""
        self._closed = True
        self._listeners.clear()
