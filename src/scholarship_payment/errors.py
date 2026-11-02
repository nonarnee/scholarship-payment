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
