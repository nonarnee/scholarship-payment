"""사업과 독립적인 공통 데이터 모델. 구조·타입만 검증하고 업무 규칙(0원, 중복 학번, 대상자 0명 등)은 판단하지 않는다.

`repr` 에는 행 번호나 건수만 나타나고 학번·성명·계좌·금액 같은 값은 나오지 않는다(DI-13).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from scholarship_payment.errors import ValidationError


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True, kw_only=True)
class PaymentRow:
    """지급 대상자 1명. 금액은 정수 원, 식별자·계좌는 문자열, 시간은 분 정수."""

    source_row: int
    student_id: str = field(repr=False)
    name: str = field(repr=False)
    account_no: str = field(repr=False)
    bank_name: str = field(repr=False)
    pay_amount: int = field(repr=False)          # 재단 승인금액
    minutes: int = field(repr=False)
    department: str = field(default="", repr=False)
    org_name: str = field(default="", repr=False)
    work_place: str = field(default="", repr=False)
    biz_no: str = field(default="", repr=False)
    headcount: int | None = field(default=None, repr=False)
    hourly_rate: int | None = field(default=None, repr=False)
    rate_display: str | None = field(default=None, repr=False)     # 시급이 여럿인 묶음의 표시용 문자열(없으면 hourly_rate)

    def __post_init__(self) -> None:
        if not _is_int(self.source_row):
            raise ValidationError("FIELD_TYPE", "source_row")
        row = self.source_row
        for name in ("student_id", "name", "account_no", "bank_name"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise ValidationError("FIELD_TYPE", name, row)
            if not value.strip():
                raise ValidationError("FIELD_EMPTY", name, row)
        for name in ("department", "org_name", "work_place", "biz_no"):
            if not isinstance(getattr(self, name), str):
                raise ValidationError("FIELD_TYPE", name, row)
        for name in ("pay_amount", "minutes"):
            if not _is_int(getattr(self, name)):
                raise ValidationError("FIELD_TYPE", name, row)
        if self.rate_display is not None and not isinstance(self.rate_display, str):
            raise ValidationError("FIELD_TYPE", "rate_display", row)
        for name in ("headcount", "hourly_rate"):
            value = getattr(self, name)
            if value is not None and not _is_int(value):
                raise ValidationError("FIELD_TYPE", name, row)


@dataclass(frozen=True, kw_only=True, repr=False)
class PaymentBatch:
    """한 사업·한 달의 지급 묶음. 대상자 수는 고정되지 않는다(0명 처리는 Validator 정책)."""

    program_code: str
    year: int
    month: int
    rows: tuple[PaymentRow, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.program_code, str):
            raise ValidationError("FIELD_TYPE", "program_code")
        if not self.program_code.strip():
            raise ValidationError("FIELD_EMPTY", "program_code")
        if not _is_int(self.year):
            raise ValidationError("FIELD_TYPE", "year")
        if self.year < 1:
            raise ValidationError("FIELD_RANGE", "year")
        if not _is_int(self.month):
            raise ValidationError("FIELD_TYPE", "month")
        if not 1 <= self.month <= 12:
            raise ValidationError("FIELD_RANGE", "month")
        if not isinstance(self.rows, (list, tuple)):
            raise ValidationError("FIELD_TYPE", "rows")
        if not all(isinstance(r, PaymentRow) for r in self.rows):
            raise ValidationError("FIELD_TYPE", "rows")
        object.__setattr__(self, "rows", tuple(self.rows))     # 호출자 리스트와 분리

    def total_amount(self) -> int:
        """지급금액 합계(정수 원)."""
        return sum(r.pay_amount for r in self.rows)

    def total_minutes(self) -> int:
        """활동시간 합계(분)."""
        return sum(r.minutes for r in self.rows)

    def __repr__(self) -> str:
        return (f"PaymentBatch(program_code={self.program_code!r}, year={self.year}, "
                f"month={self.month}, rows={len(self.rows)})")
