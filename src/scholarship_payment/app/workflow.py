"""읽기 전용 미리보기 흐름(Qt 무관): 정책 파일 로드(읽기 전후 해시로 변경 확인) → `convert.prepare()` → 요약·오류 그룹.
파일을 만들지 않고 입력을 바꾸지 않는다(저장 위치·출력 개념이 없다). 결과에는 경로·학생별 값·비밀번호를 담지 않는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from scholarship_payment.adapters.source import PASSWORD_REQUIRED, PASSWORD_WRONG
from scholarship_payment.app.convert import ConversionFailed, FileFingerprint, Issue, PolicySource, Prepared, finish, fingerprint_file, prepare
from scholarship_payment.config.policy_file import load_policy
from scholarship_payment.errors import ValidationError, ValidationFailed

OK, PASSWORD_REQUIRED_STATUS, PASSWORD_WRONG_STATUS, FAILED, CHANGED = "ok", "password_required", "password_wrong", "failed", "changed"


@dataclass(frozen=True)
class IssueGroup:
    """같은 코드의 오류·경고·참고를 묶은 것. 행 번호와 위치 이름만 담는다."""

    code: str
    severity: str                 # "error" | "warning" | "note"
    count: int
    rows: tuple[int, ...] = ()
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreviewSummary:
    """미리보기가 **실제로 확인한** 값만: 지급연월, 대상자 수, 금액 합계(정수 원), 기준일, 경고·참고. 학생별 정보는 없다."""

    program: str
    year: int
    month: int
    count: int
    total_amount: int
    base_date: str
    warnings: tuple[IssueGroup, ...] = ()
    notes: tuple[IssueGroup, ...] = ()


@dataclass(frozen=True, repr=False)
class PrepareOutcome:
    status: str
    prepared: Prepared | None = None
    summary: PreviewSummary | None = None
    errors: tuple[IssueGroup, ...] = ()
    stage: str | None = None
    missing_banks: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return f"PrepareOutcome(status={self.status!r}, errors={len(self.errors)})"


def group_issues(items, severity: str) -> tuple[IssueGroup, ...]:
    """코드별로 묶고 행 번호를 정렬·중복 제거한다. items: ValidationError 또는 Issue."""
    order: dict[str, list] = {}
    for it in items:
        order.setdefault(it.code, []).append(it)
    out = []
    for code, group in order.items():
        rows = tuple(sorted({g.row for g in group if getattr(g, "row", None) is not None}))
        fields = tuple(sorted({g.field for g in group if g.field}))
        out.append(IssueGroup(code, severity, len(group), rows, fields if not rows else ()))
    return tuple(out)


def _summary(p: Prepared) -> PreviewSummary:
    return PreviewSummary(p.program, p.year, p.month, p.count, p.total_amount, p.base_date,
                          group_issues(p.warnings, "warning"), group_issues(p.notes, "note"))


def _failed(stage: str, errors, missing: tuple[str, ...] = ()) -> PrepareOutcome:
    return PrepareOutcome(FAILED, stage=stage, errors=group_issues(errors, "error"), missing_banks=missing)


def _changed(field: str) -> PrepareOutcome:
    return PrepareOutcome(CHANGED, stage="changed", errors=group_issues([ValidationError("INPUT_FILE_CHANGED", field)], "error"))


def _load_policy_checked(path) -> tuple[object, FileFingerprint]:
    """정책 파일을 읽는 동안 바뀌지 않았는지 읽기 전후 해시로 확인한다. 반환: (정책, 지문). 실패는 ValidationFailed/ _PolicyChanged."""
    try:
        before = fingerprint_file(path)
    except FileNotFoundError:
        raise ValidationFailed([ValidationError("POLICY_FILE_MISSING", "file")]) from None
    except (OSError, TypeError, ValueError):                       # 권한·잠금 등: 없는 파일과 구분한다(예외 문구는 버린다)
        raise ValidationFailed([ValidationError("POLICY_UNREADABLE", "file")]) from None
    policy = load_policy(path)
    try:
        after = fingerprint_file(path)
    except OSError:
        raise _PolicyChanged from None
    if after.sha256 != before.sha256:
        raise _PolicyChanged
    return policy, after


class _PolicyChanged(Exception):
    pass


def run_prepare(program: str, source_path, template_path, policy_path, base_date: str | None, password: str | None = None) -> PrepareOutcome:
    """미리보기 준비. 비밀번호는 이 호출에만 쓰이고 결과에 남지 않는다."""
    try:
        policy, policy_fp = _load_policy_checked(policy_path)
    except ValidationFailed as e:
        return _failed("policy", e.errors)
    except _PolicyChanged:
        return _changed("policy")
    try:
        prepared = prepare(program, source_path, template_path, policy, base_date, password=password, policy_source=PolicySource(policy_path, policy_fp))
    except ConversionFailed as e:
        codes = {x.code for x in e.errors}
        if e.stage == "changed":
            return PrepareOutcome(CHANGED, stage="changed", errors=group_issues(e.errors, "error"))
        if PASSWORD_REQUIRED in codes:
            return PrepareOutcome(PASSWORD_REQUIRED_STATUS, stage=e.stage, errors=group_issues(e.errors, "error"))
        if PASSWORD_WRONG in codes:
            return PrepareOutcome(PASSWORD_WRONG_STATUS, stage=e.stage, errors=group_issues(e.errors, "error"))
        return _failed(e.stage, e.errors, e.missing_banks)
    return PrepareOutcome(OK, prepared=prepared, summary=_summary(prepared))


# ---------------------------------------------------------------- 생성(finish) 실행과 결과 분류
FOLDER_CODES = frozenset({"OUTPUT_DIR_MISSING", "OUTPUT_PERMISSION", "OUTPUT_IO", "OUTPUT_NAME_EXHAUSTED"})
KIND_CHANGED, KIND_TEMPLATE, KIND_FOLDER, KIND_VERIFY, KIND_UNEXPECTED = "changed", "template", "folder", "verify", "unexpected"
TEMP_GLOB = ".~*.xlsx"            # safe_save 가 저장 중 임시로 쓰는 이름(남아 있는 것은 이전 실행이 중단된 흔적일 수 있다)
RUN_GLOB = ".~run-*"              # 시트별 저장(분리 모드)의 임시 폴더 이름


@dataclass(frozen=True, repr=False)
class FinishOutcome:
    """`finish()` 한 번의 결과. 값은 엔진이 실제로 돌려준 것(저장된 경로·인원·`Prepared` 의 총액)과 저장 직후 측정한 크기·시각뿐이다.
    repr 에는 상태만 나온다(경로·학생 값 없음)."""

    status: str                                   # "ok" | "failed" | "changed"
    kind: str | None = None                       # failed: template/folder/verify/unexpected, changed: "changed"
    output_path: str | None = None
    requested_name: str = ""
    count: int = 0
    total_amount: int = 0
    size_bytes: int | None = None
    finished_at: str | None = None
    template_name: str = ""
    warnings: tuple[IssueGroup, ...] = ()
    notes: tuple[IssueGroup, ...] = ()
    errors: tuple[IssueGroup, ...] = ()
    changed_codes: dict = field(default_factory=dict)
    leftover_temp: int = 0                        # 저장 폴더에 이미 있던 `.~*.xlsx` 파일과 `.~run-*` 폴더 개수(알리기만 하고 지우지 않는다)
    split: bool = False                           # 시트별 3개 파일로 저장했는가(output_path 는 그 폴더, output_paths 는 파일 3개)
    output_paths: tuple[str, ...] = ()

    @property
    def name_changed(self) -> bool:
        return bool(self.output_path) and Path(self.output_path).name != self.requested_name

    def __repr__(self) -> str:
        return f"FinishOutcome(status={self.status!r}, kind={self.kind!r})"


def _count_leftover(out_dir) -> int:
    try:
        return sum(1 for _ in Path(out_dir).glob(TEMP_GLOB)) + sum(1 for p in Path(out_dir).glob(RUN_GLOB) if p.is_dir())
    except (OSError, TypeError, ValueError):
        return 0


def run_finish(prepared: Prepared, out_dir, now=None, split: bool = False) -> FinishOutcome:
    """`convert.finish()` 를 실행하고 결과를 UI 가 다루기 쉬운 분류로 돌려준다. 어떤 예외도 밖으로 내보내지 않고 문구도 남기지 않는다.
    성공 뒤의 크기·시각 측정이 실패해도 성공은 그대로다(후속 표시 오류를 생성 실패로 분류하지 않는다)."""
    common = dict(requested_name=Path(prepared.filename).stem if split else prepared.filename, count=prepared.count, total_amount=prepared.total_amount,
                  template_name=Path(prepared._template_path).name, split=split)
    try:
        res = finish(prepared, out_dir, split=True) if split else finish(prepared, out_dir)
    except ConversionFailed as e:
        if e.stage == "changed":
            return FinishOutcome("changed", KIND_CHANGED, errors=group_issues(e.errors, "error"), changed_codes={x.field: x.code for x in e.errors}, **common)
        codes = {x.code for x in e.errors}
        if e.stage == "template":
            kind = KIND_TEMPLATE
        elif e.stage == "output":
            kind = KIND_FOLDER if codes and codes <= FOLDER_CODES else KIND_VERIFY
        else:
            kind = KIND_UNEXPECTED
        return FinishOutcome("failed", kind, errors=group_issues(e.errors, "error"), leftover_temp=_count_leftover(out_dir), **common)
    except Exception:                                                    # 예외 문구에는 경로가 들어갈 수 있어 종류만 분류한다
        return FinishOutcome("failed", KIND_UNEXPECTED, leftover_temp=_count_leftover(out_dir), **common)
    try:
        size = sum(os.stat(p).st_size for p in res.output_paths) if split else os.stat(res.output_path).st_size
    except Exception:
        size = None
    try:
        finished_at = (now or datetime.now)().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        finished_at = None
    return FinishOutcome("ok", None, output_path=os.fspath(res.output_path), output_paths=tuple(map(os.fspath, res.output_paths)) if split else (), size_bytes=size, finished_at=finished_at,
                         warnings=group_issues(res.warnings, "warning"), notes=group_issues(res.notes, "note"),
                         leftover_temp=_count_leftover(out_dir), **common)


__all__ = ["IssueGroup", "PreviewSummary", "PrepareOutcome", "run_prepare", "group_issues", "Issue", "FinishOutcome", "run_finish"]
