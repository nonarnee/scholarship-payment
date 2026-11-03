"""출력 재검증: 저장된 파일을 다시 읽어 검증된 배치·원본 합계와 교차 대조한다. 어긋나면 반드시 잡아야 한다."""
from pathlib import Path

import pytest
from openpyxl import load_workbook

from scholarship_payment.adapters.daechung import DaechungAdapter
from scholarship_payment.config.policy import SYNTHETIC_POLICY
from scholarship_payment.core.bank_codes import BankCodeTable
from scholarship_payment.errors import ValidationFailed
from scholarship_payment.validation.validator import validate
from scholarship_payment.writers.output_check import verify_output
from scholarship_payment.writers.template_writer import build_workbook
TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
LIST = "지급대상자명단(9월)"


@pytest.fixture
def good(make_input, tmp_path):
    res = DaechungAdapter().read(make_input(n=5))
    v = validate(res.batch, BankCodeTable.from_workbook(load_workbook(TEMPLATE)))
    path = tmp_path / "out.xlsx"
    build_workbook(v, TEMPLATE, SYNTHETIC_POLICY).save(path)
    return v, res.source_totals, path


def mutated(good, tmp_path, fn):
    v, totals, path = good
    wb = load_workbook(path)
    fn(wb)
    p = tmp_path / "mut.xlsx"
    wb.save(p)
    return v, totals, p


def codes(v, totals, p):
    with pytest.raises(ValidationFailed) as ei:
        verify_output(p, v, totals)
    return {(e.code, e.field, e.row) for e in ei.value.errors}


def test_good_output_passes(good):
    verify_output(good[2], good[0], good[1])


def test_unreadable_file(good, tmp_path):
    bad = tmp_path / "x.xlsx"
    bad.write_bytes(b"nope")
    assert codes(good[0], good[1], bad) == {("OUTPUT_UNREADABLE", "file", None)}


def test_sheet_list_mismatch(good, tmp_path):
    assert codes(*mutated(good, tmp_path, lambda wb: wb.create_sheet("x"))) == {("OUTPUT_SHEETS", "sheets", None)}


@pytest.mark.parametrize("sheet,cell,field", [
    (LIST, "L7", "list:pay_amount"), (LIST, "D7", "list:student_id"), (LIST, "P7", "list:account_no"),
    (LIST, "N7", "list:wins_code"), (LIST, "O7", "list:wris_code"), (LIST, "C7", "list:name"),
    ("WINS", "G4", "WINS:pay_amount"), ("WINS", "H4", "WINS:bank_code"), ("WINS", "D4", "WINS:student_id"),
    ("WRIS", "E4", "WRIS:pay_amount"), ("WRIS", "F4", "WRIS:bank_code"), ("WRIS", "G4", "WRIS:account_no"), ("WRIS", "D4", "WRIS:name"),
])
def test_value_tampering_is_detected(good, tmp_path, sheet, cell, field):
    def tamper(wb):
        c = wb[sheet][cell]
        c.value = (c.value + 1) if isinstance(c.value, int) else f"{c.value}x"
    got = codes(*mutated(good, tmp_path, tamper))
    assert any(f == field for _, f, _ in got), got


def test_amount_stored_as_text_is_detected(good, tmp_path):
    assert codes(*mutated(good, tmp_path, lambda wb: wb["WRIS"].__setitem__("E2", str(wb["WRIS"]["E2"].value))))


def test_student_id_stored_as_number_is_detected(good, tmp_path):
    assert codes(*mutated(good, tmp_path, lambda wb: wb["WINS"].__setitem__("D2", int(wb["WINS"]["D2"].value))))


def test_total_row_and_row_count_checks(good, tmp_path):
    assert ("OUTPUT_TOTAL_MISMATCH", "amount", 10) in codes(*mutated(good, tmp_path, lambda wb: wb[LIST].__setitem__("L10", 1)))
    assert ("OUTPUT_TOTAL_MISMATCH", "minutes", 10) in codes(*mutated(good, tmp_path, lambda wb: wb[LIST].__setitem__("K10", "1시간")))
    assert ("OUTPUT_ROW_COUNT", "rows", None) in codes(*mutated(good, tmp_path, lambda wb: wb["WINS"].__setitem__("A9", "x")))


def test_total_must_equal_source_totals(good, tmp_path):
    from scholarship_payment.adapters.base import SourceTotals
    v, totals, path = good
    assert ("OUTPUT_TOTAL_MISMATCH", "amount", 10) in codes(v, SourceTotals(amount=totals.amount + 1, minutes=totals.minutes), path)
    assert ("OUTPUT_TOTAL_MISMATCH", "minutes", 10) in codes(v, SourceTotals(amount=totals.amount, minutes=totals.minutes + 60), path)


def test_formula_cell_is_detected(good, tmp_path):
    assert any(c == "OUTPUT_FORMULA" for c, _, _ in codes(*mutated(good, tmp_path, lambda wb: wb["WINS"].__setitem__("A5", "=1+1"))))


def test_report_has_no_values(good, tmp_path):
    v, totals, p = mutated(good, tmp_path, lambda wb: wb["WRIS"].__setitem__("D2", "가상비밀이름"))
    with pytest.raises(ValidationFailed) as ei:
        verify_output(p, v, totals)
    assert "가상비밀이름" not in str(ei.value) + repr(ei.value)


def test_text_expected_but_stored_as_formula_is_detected(good, tmp_path):
    # 검증을 우회해 '=...' 로 시작하는 이름이 들어온 경우: Writer 는 문자열로 저장하지만, 수식으로 저장된 파일은 잡아야 한다.
    import dataclasses

    from scholarship_payment.validation.validator import ValidatedBatch, ValidatedRow
    v, totals, _ = good
    r0 = v.rows[0]
    v2 = ValidatedBatch(batch=v.batch, rows=(ValidatedRow(row=dataclasses.replace(r0.row, name="=1+1"), wins_code=r0.wins_code,
                                                           wris_code=r0.wris_code), *v.rows[1:]))
    path = tmp_path / "f.xlsx"
    build_workbook(v2, TEMPLATE, SYNTHETIC_POLICY).save(path)
    verify_output(path, v2, totals)                     # 문자열로 저장되었으므로 통과
    wb = load_workbook(path)
    wb["WRIS"]["D2"].value = "=1+1"                     # 같은 문자열이 수식 셀로 바뀐 경우
    wb["WRIS"]["D2"].data_type = "f"
    bad = tmp_path / "g.xlsx"
    wb.save(bad)
    got = codes(v2, totals, bad)
    assert ("OUTPUT_CELL_TYPE", "WRIS:name", 2) in got
