"""PaymentRow / PaymentBatch 시험. 합성 값만 사용. 기준: DI-01 일부(가변 N), DI-03 일부(정수 합), DI-13(repr)."""
import dataclasses

import pytest

from scholarship_payment.errors import ValidationError
from scholarship_payment.models.payment import PaymentBatch, PaymentRow


def make_row(i=1, **over):
    base = dict(
        source_row=2 + i, student_id=f"00{i:06d}", name=f"가상{i:03d}", account_no=f"000-000-{i:06d}",
        bank_name="가상은행01", pay_amount=1000 * i, minutes=60 * i,
    )
    base.update(over)
    return PaymentRow(**base)


def blocked(**over):
    with pytest.raises(ValidationError) as ei:
        make_row(**over)
    return ei.value


# ---------------------------------------------------------------- PaymentRow
def test_row_valid_and_optional_defaults():
    r = make_row(1)
    assert r.student_id == "00000001" and r.pay_amount == 1000 and r.minutes == 60
    assert r.department == "" and r.biz_no == "" and r.headcount is None and r.hourly_rate is None


def test_row_with_all_optional_fields():
    r = make_row(2, department="가상학과01", org_name="가상기관01", work_place="가상근로지01",
                 biz_no="000-00-00002", headcount=3, hourly_rate=1000)
    assert r.biz_no == "000-00-00002" and r.headcount == 3 and r.hourly_rate == 1000


def test_row_is_frozen():
    r = make_row(1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.pay_amount = 5


def test_row_requires_keyword_arguments():
    with pytest.raises(TypeError):
        PaymentRow(3, "00000001", "가상001", "000-000-000001", "가상은행01", 1000, 60)


@pytest.mark.parametrize("field", ["student_id", "name", "account_no", "bank_name"])
@pytest.mark.parametrize("empty", ["", "   "])
def test_row_required_text_cannot_be_blank(field, empty):
    e = blocked(**{field: empty})
    assert e.code == "FIELD_EMPTY" and e.field == field and e.row == 3


@pytest.mark.parametrize("field,bad", [
    ("student_id", 123), ("student_id", None), ("name", 1), ("account_no", 12345), ("bank_name", None),
    ("pay_amount", 1.0), ("pay_amount", True), ("pay_amount", "1000"), ("pay_amount", None),
    ("minutes", 1.5), ("minutes", True), ("minutes", "60"), ("source_row", "3"), ("source_row", True),
    ("headcount", 1.5), ("headcount", True), ("hourly_rate", 1000.0), ("biz_no", 123), ("department", 5),
])
def test_row_type_validation(field, bad):
    e = blocked(**{field: bad})
    assert e.code == "FIELD_TYPE" and e.field == field


def test_row_does_not_judge_zero_or_negative_amount():
    # 0원·음수 처리는 업무 규칙(OPEN H5). 모델은 정수 여부만 확인한다.
    assert make_row(1, pay_amount=0).pay_amount == 0
    assert make_row(1, pay_amount=-1).pay_amount == -1


def test_row_error_never_contains_value():
    secret = "가상비밀이름"
    e = blocked(pay_amount=secret)
    assert secret not in str(e) and secret not in repr(e)


def test_row_repr_hides_every_personal_value():
    r = make_row(7, department="가상학과07", org_name="가상기관07", work_place="가상근로지07", biz_no="000-00-00007")
    text = repr(r)
    for hidden in ("가상007", "00000007", "000-000-000007", "가상은행01", "7000", "420", "가상학과07",
                   "가상기관07", "가상근로지07", "000-00-00007"):
        assert hidden not in text, hidden
    assert "source_row=9" in text


# ---------------------------------------------------------------- PaymentBatch
def make_batch(n, **over):
    kw = dict(program_code="SYN-A", year=2099, month=9, rows=[make_row(i) for i in range(1, n + 1)])
    kw.update(over)
    return PaymentBatch(**kw)


@pytest.mark.parametrize("n", [1, 32, 45, 70, 120, 1000])
def test_batch_supports_variable_n_with_exact_integer_totals(n):
    b = make_batch(n)
    assert len(b.rows) == n and isinstance(b.rows, tuple)
    assert b.total_amount() == sum(1000 * i for i in range(1, n + 1))
    assert b.total_minutes() == sum(60 * i for i in range(1, n + 1))
    assert type(b.total_amount()) is int and type(b.total_minutes()) is int


def test_batch_total_exact_for_very_large_amounts():
    rows = [make_row(i, pay_amount=10**15 + i) for i in range(1, 4)]
    assert make_batch(3, rows=rows).total_amount() == 3 * 10**15 + 6


def test_batch_total_is_pure_integer_arithmetic_beyond_float_precision():
    # float 은 2**53 을 넘으면 정수를 정확히 표현하지 못한다. 합계가 float 연산이면 이 시험이 실패한다(DI-15).
    base = 2**60
    rows = [make_row(i, pay_amount=base + 1) for i in range(1, 4)]
    assert make_batch(3, rows=rows).total_amount() == 3 * base + 3


def test_empty_batch_is_constructible_and_judged_elsewhere():
    # 0명 정책은 OPEN M10. 모델은 빈 batch를 거부하지 않는다(판단은 Validator).
    b = make_batch(0)
    assert b.rows == () and b.total_amount() == 0 and b.total_minutes() == 0


def test_batch_is_frozen_and_rows_immutable():
    b = make_batch(2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.month = 1
    with pytest.raises(AttributeError):
        b.rows.append(make_row(3))


def test_batch_copies_input_list():
    src = [make_row(1)]
    b = make_batch(0, rows=src)
    src.append(make_row(2))
    assert len(b.rows) == 1


@pytest.mark.parametrize("over", [
    dict(program_code=""), dict(program_code="  "), dict(program_code=None),
    dict(year=0), dict(year=True), dict(year="2099"), dict(month=0), dict(month=13), dict(month=True), dict(month=9.0),
    dict(rows=[object()]), dict(rows="abc"), dict(rows=None),
])
def test_batch_structure_validation(over):
    with pytest.raises(ValidationError):
        make_batch(1, **over)


def test_batch_repr_shows_no_personal_data():
    text = repr(make_batch(3))
    for hidden in ("가상001", "00000001", "000-000-000001", "1000"):
        assert hidden not in text
    assert "SYN-A" in text and "rows=3" in text
