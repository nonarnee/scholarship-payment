"""읽기 전용 미리보기 흐름(Qt 무관): 정책 파일 로드(읽기 전후 해시로 변경 확인) → `convert.prepare()` → 요약·오류 그룹.
파일을 만들지 않고 입력을 바꾸지 않는다(저장 위치·출력 개념이 없다). 결과에는 경로·학생별 값·비밀번호를 담지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass

from scholarship_payment.adapters.source import PASSWORD_REQUIRED, PASSWORD_WRONG
from scholarship_payment.app.convert import ConversionFailed, FileFingerprint, Issue, PolicySource, Prepared, fingerprint_file, prepare
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


__all__ = ["IssueGroup", "PreviewSummary", "PrepareOutcome", "run_prepare", "group_issues", "Issue"]
