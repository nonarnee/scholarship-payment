"""Step 1 · 고급 설정의 상태 관리(Qt 무관). 위젯은 이 상태만 읽고 바꾼다. 업무 규칙은 두지 않고 기존 검증기·정책 로더를 호출만 한다.

- `Step1Model`: 사업·기준일·원본·저장 폴더·템플릿·정책의 현재 값과 필드별 상태. 모든 필드가 OK 일 때만 `ready()`.
- `SettingsStore`: 사용자 설정(`config.user_settings`) 보관과 저장 결과 구분(세션 적용 / 영구 저장).
- `SettingsDraft`: 고급 설정 대화상자의 임시 편집 상태(트랜잭션). 취소하면 아무것도 바뀌지 않는다.
- 백그라운드 검증은 선택이 바뀌면 이전 결과를 버린다(필드별 토큰).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from scholarship_payment.config import user_settings as us
from scholarship_payment.config.default_paths import default_policy_path, default_template_path
from scholarship_payment.ui import validators as v
from scholarship_payment.ui.runner import Runner

PROGRAM_CODES = us.PROGRAMS
FIELDS = ("source", "out_dir", "template", "policy")
_KIND = {"source": "source", "out_dir": "dir", "template": "template", "policy": "policy"}
_DRAFT_KIND = {"template_path": "template", "policy_path": "policy", "out_dir": "dir"}
_DRAFT_TO_FIELD = {"template_path": "template", "policy_path": "policy", "out_dir": "out_dir"}


@dataclass(frozen=True)
class Step1Selection:
    """Step 2(Phase 3)로 넘기는 입력. 비밀번호는 포함하지 않는다(필요하면 실행 단계에서 메모리로만 받는다)."""
    program: str
    base_date: str
    source_path: str
    out_dir: str
    template_path: str
    policy_path: str


@dataclass(frozen=True)
class ApplyOutcome:
    applied: bool          # 현재 실행(세션)에 적용했는가
    persisted: bool        # 설정 파일에 저장했는가 — 둘을 구분해서 안내한다
    code: str | None = None


class SettingsStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else us.settings_path()
        r = us.load(self.path)
        self.settings: us.UserSettings = r.settings
        self.load_status: str = r.status
        self.backup_name: str | None = r.backup_name

    def commit(self, new: us.UserSettings) -> ApplyOutcome:
        self.settings = new
        res = us.save(new, self.path)
        return ApplyOutcome(True, res.ok, res.code)


def _signature(path: str | None):
    """검사 시점의 파일 상태(크기·수정 시각). 같은 경로의 파일 내용이 바뀌었는지 알아보는 데만 쓴다."""
    try:
        s = os.stat(path)
        return (s.st_size, s.st_mtime_ns)
    except (OSError, TypeError, ValueError):
        return None


class _Checks:
    """키별 경로·검증 상태·토큰. 가벼운 검사는 즉시, 구조 검사는 runner 로 보내고 토큰이 달라진 결과는 버린다.
    어떤 검사도 예외 문구를 밖으로 내보내지 않는다(고정 오류 코드로 바꿈)."""

    def __init__(self, runner: Runner, notify: Callable[[], None]) -> None:
        self.runner, self.notify = runner, notify
        self.paths: dict = {}
        self.states: dict = {}
        self._tokens: dict = {}
        self._kinds: dict = {}
        self._sigs: dict = {}

    def set(self, key, kind: str, path) -> None:
        path = str(path) if path is not None and str(path).strip() else None
        token = self._tokens[key] = self._tokens.get(key, 0) + 1
        self.paths[key] = path
        self._kinds[key] = kind
        self._sigs[key] = _signature(path) if path else None
        try:
            first = v.light(kind, path)
        except Exception:
            self.states[key] = v.FieldState(v.ERROR, "CHECK_FAILED")
            return
        if not first.ok or kind == "dir":
            self.states[key] = first
            return
        self.states[key] = v.CHECKING_STATE
        self.runner.submit(lambda: v.heavy(kind, path), lambda res: self._done(key, token, path, res))

    def _done(self, key, token: int, path: str, res) -> None:
        if token != self._tokens.get(key) or path != self.paths.get(key):
            return                                           # 선택이 바뀌었다 → 이전 결과 무시
        self.states[key] = res
        self.notify()

    def clear(self, key) -> None:
        self._tokens[key] = self._tokens.get(key, 0) + 1     # 진행 중인 검사 결과를 무효화
        self.paths[key] = None
        self._sigs[key] = None
        self.states[key] = v.UNSET_STATE

    def recheck(self, key) -> None:
        """이미 선택한 경로를 다시 확인한다: 존재·종류가 달라졌거나 파일이 바뀌었으면 검사를 처음부터 다시 한다(이전 성공 무효화).
        바뀐 것이 없고 검사가 끝났거나 진행 중이면 그대로 둔다."""
        path = self.paths.get(key)
        if not path:
            return
        kind = self._kinds[key]
        if kind == "dir" or _signature(path) != self._sigs.get(key) or not self._light_ok(kind, path):
            self.set(key, kind, path)

    @staticmethod
    def _light_ok(kind: str, path: str) -> bool:
        try:
            return v.light(kind, path).ok
        except Exception:
            return False


def _same_file(a, b) -> bool:
    try:
        return os.path.samefile(a, b)
    except (OSError, TypeError, ValueError):
        return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


class Step1Model:
    def __init__(self, store: SettingsStore, runner: Runner, today: Callable[[], date] = date.today, default_dirs: list | None = None) -> None:
        self.store, self._today, self._dirs = store, today, default_dirs
        self._listeners: list[Callable[[], None]] = []
        self._policy_listeners: list[Callable[[str], None]] = []
        self._checks = _Checks(runner, self._notify)
        self.persist_failed = False
        self.program = store.settings.last_program or PROGRAM_CODES[0]
        self.base_date = today().strftime("%Y.%m.%d")
        self._date_state = v.check_date(self.base_date)
        for f in FIELDS:
            self._checks.clear(f)
        self._load_program_paths(reset_out_dir=True)

    # --- 구독 ---
    def on_change(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in list(self._listeners):
            fn()

    # --- 읽기 ---
    @property
    def paths(self) -> dict:
        return {f: self._checks.paths.get(f) for f in FIELDS}

    def state(self, field: str) -> v.FieldState:
        return self._date_state if field == "date" else self._checks.states.get(field, v.UNSET_STATE)

    def blocking(self) -> list[str]:
        return [f for f in (*FIELDS, "date") if not self.state(f).ok]

    def ready(self) -> bool:
        return not self.blocking()

    def snapshot(self) -> Step1Selection | None:
        if not self.ready():
            return None
        p = self.paths
        return Step1Selection(self.program, self.base_date, p["source"], p["out_dir"], p["template"], p["policy"])

    # --- 쓰기 ---
    def _load_program_paths(self, reset_out_dir: bool) -> None:
        saved = self.store.settings.paths(self.program)
        tpl = saved.template_path or (str(p) if (p := default_template_path(self.program, self._dirs)) else None)
        pol = saved.policy_path or (str(p) if (p := default_policy_path(self.program, self._dirs)) else None)
        self._checks.set("template", "template", tpl)
        self._checks.set("policy", "policy", pol)
        if reset_out_dir:
            self._checks.set("out_dir", "dir", saved.out_dir)

    def set_program(self, code: str) -> None:
        if code not in PROGRAM_CODES:
            raise ValueError("unknown program")
        if code != self.program:
            self.program = code
            self._checks.clear("source")                   # 사업이 바뀌면 이전 원본 선택은 버린다(사업 간 경로가 섞이지 않게)
            self._load_program_paths(reset_out_dir=True)
            self.persist_failed = not self.store.commit(self.store.settings.with_last_program(code)).persisted
        self._notify()

    def recheck(self) -> None:
        """다음 단계로 넘어가기 직전에 호출한다: 선택 이후 파일이 사라지거나 바뀌었으면 상태를 되돌려 이동을 막는다."""
        for f in FIELDS:
            self._checks.recheck(f)
        self._notify()

    def set_base_date(self, text: str) -> None:
        self.base_date = text
        self._date_state = v.check_date(text)
        self._notify()

    def set_source(self, path) -> None:
        self._checks.set("source", "source", path)
        self._notify()

    def set_out_dir(self, path) -> None:
        self._checks.set("out_dir", "dir", path)          # 이번 실행에만 적용(기본 폴더 설정은 고급 설정에서)
        self._notify()

    def on_policy_edited(self, fn: Callable[[str], None]) -> None:
        self._policy_listeners.append(fn)

    def policy_edited(self, path) -> None:
        """정책 파일이 수정·저장되었다. 지금 선택된 정책 파일이면 검사를 처음부터 다시 하고(이전 성공 결과를 쓰지 않는다) 구독자에게 알린다.
        파일의 크기·수정 시각이 같아도 다시 검사한다. 다른 파일이면 아무것도 하지 않는다."""
        current = self._checks.paths.get("policy")
        if not current or not _same_file(current, path):
            return
        self._checks.set("policy", "policy", current)
        self._notify()
        for fn in list(self._policy_listeners):
            fn(current)

    def apply_settings(self, new: us.UserSettings) -> ApplyOutcome:
        before = self.store.settings.paths(self.program).out_dir
        outcome = self.store.commit(new)
        self.persist_failed = not outcome.persisted
        self._load_program_paths(reset_out_dir=new.paths(self.program).out_dir != before)
        self._notify()
        return outcome


class SettingsDraft:
    """고급 설정 대화상자의 임시 편집 상태. 원본 설정을 복사해 시작하고, 저장 및 적용 때만 호출자가 `result()`를 반영한다."""

    def __init__(self, original: us.UserSettings, runner: Runner, default_dirs: list | None = None) -> None:
        self._original, self._settings, self._dirs = original, original, default_dirs
        self._listeners: list[Callable[[], None]] = []
        self._closed = False
        self._checks = _Checks(runner, self._notify)

    def on_change(self, fn) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        if not self._closed:
            for fn in list(self._listeners):
                fn()

    def value(self, program: str, key: str) -> str | None:
        return getattr(self._settings.paths(program), key)

    def effective(self, program: str, key: str) -> tuple[str | None, bool]:
        """화면에 보여 줄 경로와 자동 탐색 여부. 저장값이 없으면 기본 위치에서 찾은 파일을 보여 주되 저장하지는 않는다."""
        saved = self.value(program, key)
        if saved or key == "out_dir":
            return saved, False
        found = (default_template_path if key == "template_path" else default_policy_path)(program, self._dirs)
        return (str(found), True) if found else (None, False)

    def set_path(self, program: str, key: str, path) -> None:
        path = str(path) if path is not None and str(path).strip() else None
        self._settings = self._settings.with_paths(program, **{key: path})
        self._checks.set((program, key), _DRAFT_KIND[key], path)
        self._notify()

    def check_displayed(self, program: str) -> None:
        """대화상자에 보이는 경로(저장값 또는 자동 탐색)의 상태를 확인한다. 적용 여부 판단에는 쓰지 않는다."""
        for key in _DRAFT_KIND:
            if (program, key) in self._checks.states:
                continue
            path, _ = self.effective(program, key)
            self._checks.set((program, key), _DRAFT_KIND[key], path)

    def refresh_check(self, program: str, key: str) -> None:
        """설정값은 그대로 두고 표시 중인 경로의 검사만 다시 한다(파일 내용이 바뀐 뒤). 자동 탐색한 경로를 저장값으로 만들지 않는다."""
        path, _ = self.effective(program, key)
        self._checks.set((program, key), _DRAFT_KIND[key], path)
        self._notify()

    def refresh_same_file(self, key: str, path) -> None:
        """같은 파일을 가리키는 **모든** 사업의 검사를 다시 한다(여러 사업이 같은 정책 JSON 경로를 쓰는 경우, 한 탭에서 수정하면
        다른 탭의 이전 검사 결과가 수정 전 상태로 남지 않게). 설정값은 바꾸지 않는다. 아직 확인한 적 없는 사업은 보여 줄 때 새로 검사하므로 건드리지 않는다."""
        for program, k in list(self._checks.states):
            if k != key:
                continue
            shown, _ = self.effective(program, key)
            if shown and _same_file(shown, path):
                self._checks.set((program, key), _DRAFT_KIND[key], shown)
        self._notify()

    def state(self, program: str, key: str) -> v.FieldState:
        return self._checks.states.get((program, key), v.UNSET_STATE)

    def reset_program(self, program: str) -> None:
        self._settings = self._settings.clear_program(program)
        for key in _DRAFT_KIND:
            self._checks.clear((program, key))
        self._notify()

    def changed(self) -> list[tuple[str, str]]:
        return [(p, k) for p in PROGRAM_CODES for k in _DRAFT_KIND if self.value(p, k) != getattr(self._original.paths(p), k)]

    def can_apply(self) -> bool:
        """바꾼 경로만 검증 대상이다(건드리지 않은 기존 값이 깨져 있어도 다른 변경을 막지 않는다). 확인 중이거나 오류인 변경이 있으면 막는다."""
        for program, key in self.changed():
            if self.value(program, key) is None:
                continue
            if not self.state(program, key).ok:
                return False
        return True

    def result(self) -> us.UserSettings:
        return self._settings

    def discard(self) -> None:
        self._closed = True
        for k in list(self._checks.states):
            self._checks.clear(k)
