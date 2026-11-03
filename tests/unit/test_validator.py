"""Validator. 업무 규칙(0명·중복 학번·0원/음수·은행코드·수식 접두)을 한 번에 모아서 보고한다(값 없이)."""
import pytest

from scholarship_payment.core.bank_codes import BankCodeTable
from scholarship_payment.errors import ValidationError, ValidationFailed
from scholarship_payment.models.payment import PaymentBatch, PaymentRow
from scholarship_payment.validation.validator import ValidatedBatch, validate

BANKS = BankCodeTable([("가상은행A", "111", "990001"), ("가상은행B", 22, "990002"),
                       ("가상은행C", None, "990003"), ("가상은행D", "4", "9"), ("가상은행D", "5", "9")])


def row(n=1, **kw):
    base = dict(source_row=2 + n, student_id=f"9000000{n}", name=f"가상{n:03d}", account_no=f"000-000-00000{n}",
                bank_name="가상은행A", pay_amount=1000 * n, minutes=60 * n)
    base.update(kw)
    return PaymentRow(**base)


def batch(*rows):
    return PaymentBatch(program_code="DAECHUNG", year=9999, month=9, rows=rows)


def fail(b, banks=BANKS):
    with pytest.raises(ValidationFailed) as ei:
        validate(b, banks)
    return ei.value


def triples(exc):
    return {(e.code, e.field, e.row) for e in exc.errors}


def test_valid_batch_gets_codes_for_both_systems():
    v = validate(batch(row(1), row(2, bank_name="가상은행B")), BANKS)
    assert isinstance(v, ValidatedBatch) and len(v.rows) == 2
    assert (v.rows[0].wins_code, v.rows[0].wris_code) == ("111", "990001")
    assert (v.rows[1].wins_code, v.rows[1].wris_code) == (22, "990002")
    assert v.rows[0].row is not None and v.batch.total_amount() == 3000


def test_empty_batch_is_blocked():
    assert triples(fail(batch())) == {("NO_DATA_ROWS", "rows", None)}


def test_duplicate_student_ids_are_flagged_on_every_involved_row():
    b = batch(row(1), row(2, student_id="90000001"), row(3))
    assert triples(fail(b)) == {("DUPLICATE_STUDENT_ID", "student_id", 3), ("DUPLICATE_STUDENT_ID", "student_id", 4)}


@pytest.mark.parametrize("amount", [0, -1000])
def test_non_positive_amounts_are_blocked(amount):
    assert triples(fail(batch(row(1), row(2, pay_amount=amount)))) == {("AMOUNT_NOT_POSITIVE", "pay_amount", 4)}


def test_negative_minutes_are_blocked():
    assert triples(fail(batch(row(1, minutes=-1)))) == {("MINUTES_INVALID", "minutes", 3)}


def test_missing_and_ambiguous_codes_are_reported_per_system():
    b = batch(row(1, bank_name="가상은행C"), row(2, bank_name="가상은행D"), row(3, bank_name="가상은행없음"))
    assert triples(fail(b)) == {
        ("BANK_CODE_MISSING", "wins_bank_code", 3), ("BANK_CODE_AMBIGUOUS", "wins_bank_code", 4),
        ("BANK_CODE_MISSING", "wins_bank_code", 5), ("BANK_CODE_MISSING", "wris_bank_code", 5),
    }


@pytest.mark.parametrize("field", ["name", "department", "org_name", "work_place", "biz_no", "bank_name", "account_no", "student_id"])
@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_formula_like_text_is_blocked(field, prefix):
    exc = fail(batch(row(1, **{field: prefix + "1+1"})), BankCodeTable([("가상은행A", "1", "2"), (prefix + "1+1", "1", "2")]))
    assert ("FORMULA_LIKE_TEXT", field, 3) in triples(exc)


def test_all_errors_are_collected_in_one_report():
    b = batch(row(1, pay_amount=0), row(2, student_id="90000001", bank_name="가상은행C"))
    assert len(fail(b).errors) == 4          # 중복 2 + 0원 1 + 코드 1


def test_validation_does_not_modify_the_batch():
    b = batch(row(1), row(2))
    before = b.rows
    validate(b, BANKS)
    assert b.rows == before


def test_report_never_contains_values():
    b = batch(row(1, name="가상비밀이름", bank_name="가상비밀은행", pay_amount=-7777, account_no="=비밀계좌"))
    exc = fail(b)
    text = str(exc) + repr(exc) + " ".join(str(e) + repr(e) for e in exc.errors)
    for secret in ("가상비밀이름", "가상비밀은행", "7777", "비밀계좌"):
        assert secret not in text
    assert "ValidatedBatch" in repr(validate(batch(row(1)), BANKS)) and "가상001" not in repr(validate(batch(row(1)), BANKS))


def test_scales_to_many_rows():
    rows = [row(1, source_row=2 + i, student_id=f"9{i:07d}", name=f"가상{i}", account_no=f"0-{i}") for i in range(1000)]
    assert len(validate(batch(*rows), BANKS).rows) == 1000
