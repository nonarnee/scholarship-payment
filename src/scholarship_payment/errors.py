"""검증 오류. 규칙 코드·필드명·행 번호만 담고 **입력 값은 절대 담지 않는다**(DI-13)."""
from __future__ import annotations


class ValidationError(Exception):
    """데이터가 규칙을 어겼을 때 발생한다. 메시지에 개인정보가 섞이지 않도록 값은 받지 않는다."""

    def __init__(self, code: str, field: str, row: int | None = None) -> None:
        super().__init__(code, field, row)
        self.code = code
        self.field = field
        self.row = row

    def with_row(self, row: int) -> ValidationError:
        """행 번호를 붙인 새 오류를 돌려준다(원본은 그대로)."""
        return ValidationError(self.code, self.field, row)

    def __str__(self) -> str:
        base = f"{self.code}: {self.field}"
        return base if self.row is None else f"{base} (row {self.row})"

    def __repr__(self) -> str:
        return f"ValidationError(code={self.code!r}, field={self.field!r}, row={self.row!r})"


_MAX_LISTED = 50


class ValidationFailed(Exception):
    """검증 규칙 위반을 모아서 한 번에 보고한다. 규칙 코드·필드·행 번호만 담는다."""

    def __init__(self, errors) -> None:
        self.errors: tuple[ValidationError, ...] = tuple(errors)
        super().__init__(len(self.errors))

    def __str__(self) -> str:
        shown = "; ".join(str(e) for e in self.errors[:_MAX_LISTED])
        more = len(self.errors) - _MAX_LISTED
        tail = f" ... 외 {more}건" if more > 0 else ""
        return f"검증 실패 {len(self.errors)}건: {shown}{tail}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(errors={len(self.errors)})"
