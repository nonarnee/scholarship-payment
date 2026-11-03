"""PaymentBatch 검증. 구조·타입은 모델이 이미 확인했고, 여기서는 지급 전 업무 규칙을 확인한다.

업무 정책(중복 학번, 0원·음수, 0명)은 **임시 규칙**이다(OPEN H5·M10). 위반이 하나라도 있으면 아무 것도 만들지 않고
모든 위반을 규칙 코드·필드·행 번호로만 모아서 보고한다(값 금지, DI-13).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from scholarship_payment.core.bank_codes import BankCodeTable
from scholarship_payment.core.normalize import is_formula_like
from scholarship_payment.errors import ValidationError, ValidationFailed
from scholarship_payment.models.payment import PaymentBatch, PaymentRow

TEXT_FIELDS = ("student_id", "name", "department", "org_name", "work_place", "biz_no", "bank_name", "account_no")


@dataclass(frozen=True)
class ValidatedRow:
    row: PaymentRow = field(repr=False)
    wins_code: int | str = field(repr=False)
    wris_code: int | str = field(repr=False)


@dataclass(frozen=True, repr=False)
class ValidatedBatch:
    """검증을 통과한 배치와 행별 시스템 은행코드. Writer 는 이 타입만 받는다."""

    batch: PaymentBatch
    rows: tuple[ValidatedRow, ...]

    def __repr__(self) -> str:
        return f"ValidatedBatch(rows={len(self.rows)})"


def validate(batch: PaymentBatch, banks: BankCodeTable) -> ValidatedBatch:
    errors: list[ValidationError] = []
    if not batch.rows:
        raise ValidationFailed([ValidationError("NO_DATA_ROWS", "rows")])

    id_counts = Counter(r.student_id for r in batch.rows)
    rows: list[ValidatedRow] = []
    for r in batch.rows:
        n = r.source_row
        if id_counts[r.student_id] > 1:
            errors.append(ValidationError("DUPLICATE_STUDENT_ID", "student_id", n))
        if r.pay_amount <= 0:
            errors.append(ValidationError("AMOUNT_NOT_POSITIVE", "pay_amount", n))
        if r.minutes < 0:
            errors.append(ValidationError("MINUTES_INVALID", "minutes", n))
        for name in TEXT_FIELDS:
            if is_formula_like(getattr(r, name)):
                errors.append(ValidationError("FORMULA_LIKE_TEXT", name, n))
        codes = {}
        for system in ("wins", "wris"):
            try:
                codes[system] = banks.resolve(r.bank_name, system)
            except ValidationError as e:
                errors.append(e.with_row(n))
        if len(codes) == 2:
            rows.append(ValidatedRow(row=r, wins_code=codes["wins"], wris_code=codes["wris"]))
    if errors:
        raise ValidationFailed(errors)
    return ValidatedBatch(batch=batch, rows=tuple(rows))
