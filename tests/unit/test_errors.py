"""DI-13: 오류 객체는 규칙 코드·필드명·행 번호만 노출하고 입력 값을 담지 않는다."""
import pytest

from scholarship_payment.errors import ValidationError


def test_message_contains_only_code_field_row():
    e = ValidationError("ID_EMPTY", "student_id", row=7)
    assert e.code == "ID_EMPTY" and e.field == "student_id" and e.row == 7
    assert str(e) == "ID_EMPTY: student_id (row 7)"


def test_message_without_row():
    assert str(ValidationError("ID_EMPTY", "student_id")) == "ID_EMPTY: student_id"


def test_with_row_returns_new_error_and_keeps_original():
    e = ValidationError("ID_EMPTY", "student_id")
    e2 = e.with_row(12)
    assert e2.row == 12 and e2.code == e.code and e2.field == e.field
    assert e.row is None


def test_is_exception_usable_with_pytest_raises():
    with pytest.raises(ValidationError) as ei:
        raise ValidationError("X", "f", row=1)
    assert ei.value.code == "X"


def test_repr_is_safe_and_informative():
    assert repr(ValidationError("X", "f", row=3)) == "ValidationError(code='X', field='f', row=3)"
