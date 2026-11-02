"""입력 값 정규화. 추정하지 않고, 확신할 수 없으면 ValidationError 로 차단한다.

업무 규칙(0원·음수 허용, 중복 학번, 식별자 길이 등)은 여기서 판단하지 않는다.
오류에는 규칙 코드와 필드명만 담는다(값 금지, DI-13).
"""
from __future__ import annotations

import math
import re
from decimal import Decimal

from scholarship_payment.errors import ValidationError

_FLOAT_EXACT_LIMIT = 2**53          # 이 값을 넘는 float 은 정수로 정확히 표현된다는 보장이 없다
_HOURS_RE = re.compile(r"(0|[1-9][0-9]*)시간(?:(0|[1-9]|[1-5][0-9])분)?")
_DIGITS_RE = re.compile(r"[0-9]+")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def parse_hours(text: object, field: str = "hours") -> int:
    """`N시간` 또는 `N시간M분`(M=0~59)만 허용해 분 정수로 바꾼다. 그 밖의 표기는 차단한다(추정 금지)."""
    if isinstance(text, str):
        m = _HOURS_RE.fullmatch(text)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2) or 0)
    raise ValidationError("HOURS_FORMAT", field)


def format_minutes(minutes: object, field: str = "minutes") -> str:
    """분 정수를 입력 샘플에서 관찰된 `N시간` / `N시간M분` 표기로 바꾼다."""
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0:
        raise ValidationError("MINUTES_INVALID", field)
    h, m = divmod(minutes, 60)
    return f"{h}시간" if m == 0 else f"{h}시간{m}분"


def normalize_identifier(value: object, field: str, expected_len: int | None = None) -> str:
    """학번 같은 식별자를 문자열로 만든다.

    문자열은 앞뒤 공백만 제거하고 그대로 둔다(선행 0·하이픈 보존).
    숫자 셀(int / 정수형 float)은 str 로 바꾸되, 이미 사라진 선행 0 은 복원하지 않는다.
    길이 규칙은 호출자(Adapter)의 정책이며 기본은 없다.
    """
    if value is None:
        raise ValidationError("ID_EMPTY", field)
    if isinstance(value, bool):
        raise ValidationError("ID_TYPE", field)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValidationError("ID_EMPTY", field)
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer() or abs(value) > _FLOAT_EXACT_LIMIT:
            raise ValidationError("ID_TYPE", field)
        text = str(int(value))
    else:
        raise ValidationError("ID_TYPE", field)
    if expected_len is not None and len(text) != expected_len:
        raise ValidationError("ID_LENGTH", field)
    return text


def normalize_account(value: object, field: str = "account_no") -> str:
    """계좌번호는 **문자열만** 허용한다. 숫자 셀은 선행 0·하이픈이 이미 사라져 검증할 수 없으므로 차단한다(임시 규칙)."""
    if value is None:
        raise ValidationError("ACCOUNT_EMPTY", field)
    if not isinstance(value, str):
        raise ValidationError("ACCOUNT_NOT_TEXT", field)
    text = value.strip()
    if not text:
        raise ValidationError("ACCOUNT_EMPTY", field)
    return text


def parse_amount(value: object, field: str = "pay_amount") -> int:
    """금액을 정수 원으로 바꾼다. 소수·부호 문자열·쉼표 등 해석이 필요한 표기는 차단한다.

    0원·음수의 허용 여부는 판단하지 않는다(업무 규칙, Validator 의 몫).
    """
    if isinstance(value, bool):
        raise ValidationError("AMOUNT_INVALID", field)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer() and abs(value) <= _FLOAT_EXACT_LIMIT:
            return int(value)
        raise ValidationError("AMOUNT_INVALID", field)
    if isinstance(value, Decimal):
        if value.is_finite() and value == value.to_integral_value():
            return int(value)
        raise ValidationError("AMOUNT_INVALID", field)
    if isinstance(value, str) and _DIGITS_RE.fullmatch(value):
        try:
            return int(value)
        except ValueError:      # 자릿수 제한 초과
            pass
    raise ValidationError("AMOUNT_INVALID", field)


def is_formula_like(value: object) -> bool:
    """Excel 이 수식으로 해석할 수 있는 시작 문자(= + - @ 탭 CR)인지 본다. 값은 변형하지 않는다.

    Writer 는 이런 값을 셀에 쓸 때 문자열 타입을 강제해야 한다(DI-14).
    """
    return isinstance(value, str) and value.startswith(_FORMULA_PREFIXES)
