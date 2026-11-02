"""정규화 함수 시험. 값은 모두 합성 예약값이다(가상NNN, 00NNNNNN/90NNNNNN, 000-000-NNNNNN).
기준: DI-04(식별자 문자열), DI-07(시간 분), DI-13(오류에 값 미노출), DI-14(수식 탐지), DI-15(금액 정수).
"""
from decimal import Decimal

import pytest

from scholarship_payment.core.normalize import (
    format_minutes,
    is_formula_like,
    normalize_account,
    normalize_identifier,
    parse_amount,
    parse_hours,
)
from scholarship_payment.errors import ValidationError


def blocked(fn, *args, **kw):
    with pytest.raises(ValidationError) as ei:
        fn(*args, **kw)
    return ei.value


# ------------------------------------------------------------ 시간 (DI-07)
@pytest.mark.parametrize("text,minutes", [
    ("33시간", 33 * 60), ("14시간30분", 14 * 60 + 30), ("0시간", 0), ("10시간0분", 600),
    ("55시간18분", 55 * 60 + 18), ("1586시간", 1586 * 60), ("0시간59분", 59),
])
def test_parse_hours_valid(text, minutes):
    assert parse_hours(text) == minutes


@pytest.mark.parametrize("bad", [
    "", " ", None, 33, 3.5, " 33시간", "33시간 ", "33 시간", "3시간 30분", "1.5시간", "90분", "33시간60분",
    "33시간-1분", "-3시간", "33", "33hours", "33시간30", "시간", "33시간분", "３３시간", "33시간30분1",
])
def test_parse_hours_rejects_anything_not_observed(bad):
    e = blocked(parse_hours, bad)
    assert e.code == "HOURS_FORMAT" and e.field == "hours"


def test_parse_hours_error_never_contains_value():
    secret = "가상001시간"
    e = blocked(parse_hours, secret)
    assert secret not in str(e) and secret not in repr(e)


@pytest.mark.parametrize("minutes,text", [(1980, "33시간"), (870, "14시간30분"), (0, "0시간"), (59, "0시간59분"), (95160, "1586시간")])
def test_format_minutes(minutes, text):
    assert format_minutes(minutes) == text


@pytest.mark.parametrize("bad", [-1, 1.5, True, None, "60"])
def test_format_minutes_rejects_invalid(bad):
    assert blocked(format_minutes, bad).code == "MINUTES_INVALID"


@pytest.mark.parametrize("m", [0, 1, 59, 60, 61, 870, 1980, 95159, 95160])
def test_hours_round_trip(m):
    assert parse_hours(format_minutes(m)) == m


# ------------------------------------------------------------ 식별자 (DI-04)
@pytest.mark.parametrize("value,expected", [
    ("00000001", "00000001"), ("90000001", "90000001"), (" 00000002 ", "00000002"), ("000-000-000001", "000-000-000001"),
    (90000001, "90000001"), (90000001.0, "90000001"),
])
def test_identifier_preserves_text_exactly(value, expected):
    assert normalize_identifier(value, "student_id") == expected


def test_identifier_does_not_restore_lost_leading_zeros():
    assert normalize_identifier(1, "student_id") == "1"   # 숫자 셀은 이미 선행 0이 사라졌다. 복원하지 않는다.


def test_identifier_expected_len_is_caller_policy():
    assert normalize_identifier("00000001", "student_id", expected_len=8) == "00000001"
    assert blocked(normalize_identifier, 1, "student_id", expected_len=8).code == "ID_LENGTH"
    assert blocked(normalize_identifier, "0001", "student_id", expected_len=8).code == "ID_LENGTH"
    assert normalize_identifier("0001", "student_id") == "0001"     # 기본은 길이 규칙 없음


@pytest.mark.parametrize("bad,code", [
    (None, "ID_EMPTY"), ("", "ID_EMPTY"), ("   ", "ID_EMPTY"),
    (True, "ID_TYPE"), (False, "ID_TYPE"), (1.5, "ID_TYPE"), (float("nan"), "ID_TYPE"), (float("inf"), "ID_TYPE"),
    ([], "ID_TYPE"), (b"1", "ID_TYPE"),
])
def test_identifier_rejects(bad, code):
    e = blocked(normalize_identifier, bad, "student_id")
    assert e.code == code and e.field == "student_id"


def test_identifier_error_never_contains_value():
    secret = 1.5
    e = blocked(normalize_identifier, secret, "student_id")
    assert "1.5" not in str(e) and "1.5" not in repr(e)


# ------------------------------------------------------------ 계좌 (DI-04)
def test_account_text_preserved():
    assert normalize_account("000-000-000001") == "000-000-000001"
    assert normalize_account(" 000-000-000001 ") == "000-000-000001"
    assert normalize_account("0001") == "0001"


@pytest.mark.parametrize("bad,code", [
    (None, "ACCOUNT_EMPTY"), ("", "ACCOUNT_EMPTY"), ("  ", "ACCOUNT_EMPTY"),
    (123456, "ACCOUNT_NOT_TEXT"), (1.0, "ACCOUNT_NOT_TEXT"), (True, "ACCOUNT_NOT_TEXT"),
])
def test_account_numeric_or_empty_blocked(bad, code):
    e = blocked(normalize_account, bad)
    assert e.code == code and e.field == "account_no"


# ------------------------------------------------------------ 금액 (DI-15)
@pytest.mark.parametrize("value,expected", [
    (12345, 12345), (0, 0), (-5, -5), (12345.0, 12345), (Decimal("12345"), 12345), (Decimal("12345.00"), 12345),
    ("12345", 12345), ("0012", 12), (10**15, 10**15),
])
def test_parse_amount_valid_returns_int(value, expected):
    out = parse_amount(value)
    assert out == expected and type(out) is int


@pytest.mark.parametrize("bad", [
    True, False, 1.5, 0.1, float("nan"), float("inf"), Decimal("1.5"), Decimal("NaN"), 2.0**60,
    "", " ", "1,234", "-5", "+5", " 5", "5원", "1.0", "abc", None, [], b"5",
])
def test_parse_amount_rejects(bad):
    e = blocked(parse_amount, bad)
    assert e.code == "AMOUNT_INVALID" and e.field == "pay_amount"


def test_parse_amount_does_not_judge_zero_or_negative():
    # 0원·음수 허용 여부는 업무 규칙(OPEN H5)이라 정규화 단계에서 판단하지 않는다.
    assert parse_amount(0) == 0 and parse_amount(-1) == -1


def test_parse_amount_custom_field_name():
    assert blocked(parse_amount, "x", field="rate").field == "rate"


# ------------------------------------------------------------ 수식 탐지 (DI-14 일부)
@pytest.mark.parametrize("text", ["=SUM(A1)", "+1", "-1", "@x", "\t=1", "\r=1", "=1+1"])
def test_formula_like_true(text):
    assert is_formula_like(text) is True


@pytest.mark.parametrize("value", ["가상001", "000-000-000001", "90000001", "", " =x", None, 5])
def test_formula_like_false(value):
    # 앞쪽 공백 뒤의 '='는 Excel이 수식으로 취급하지 않으므로 False. 비문자열은 대상이 아니다.
    assert is_formula_like(value) is False
