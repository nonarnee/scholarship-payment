"""입력 Adapter 공통 결과 타입. 오류·경고는 규칙 코드·필드·행 번호만 담는다(DI-13)."""
from __future__ import annotations

from dataclasses import dataclass

from scholarship_payment.errors import ValidationError
from scholarship_payment.models.payment import PaymentBatch

_MAX_LISTED = 50


@dataclass(frozen=True)
class SourceTotals:
    """원본 파일의 합계행 값(대조용). 금액은 정수 원, 시간은 분."""

    amount: int
    minutes: int


@dataclass(frozen=True)
class AdapterResult:
    batch: PaymentBatch
    source_totals: SourceTotals
    warnings: tuple[ValidationError, ...] = ()     # 차단하지 않는 경고(코드·필드·행 번호만)


class InputValidationFailed(Exception):
    """입력 파일을 해석할 수 없을 때 발생한다. 가능한 모든 오류를 모아 한 번에 보고한다."""

    def __init__(self, errors) -> None:
        self.errors: tuple[ValidationError, ...] = tuple(errors)
        super().__init__(len(self.errors))

    def __str__(self) -> str:
        shown = "; ".join(str(e) for e in self.errors[:_MAX_LISTED])
        more = len(self.errors) - _MAX_LISTED
        tail = f" ... 외 {more}건" if more > 0 else ""
        return f"입력 검증 실패 {len(self.errors)}건: {shown}{tail}"

    def __repr__(self) -> str:
        return f"InputValidationFailed(errors={len(self.errors)})"
