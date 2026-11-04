"""AI멘토링·이월 종단 변환(합성). 이월 2행 학생은 명단·WINS·WRIS에 1명으로, 합산 금액으로 반영된다."""
from pathlib import Path

import pytest
from openpyxl import load_workbook

from scholarship_payment import __main__ as cli
from scholarship_payment.app import convert as conv
from scholarship_payment.app.controller import run_conversion
from scholarship_payment.app.convert import ConversionFailed, convert
from scholarship_payment.gui.app import PROGRAMS

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
CARRY = ((2, 8 * 60, "9999년08월"), (3, 90, "9999년08월"))


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture
def synthetic_ai_rate(monkeypatch):
    monkeypatch.setattr(conv, "AI_HOURLY_RATE", 1000)      # 합성 입력의 시급


def occurrences(wb, sheet_prefix, value):
    return sum(1 for ws in wb.worksheets if ws.title.startswith(sheet_prefix) for row in ws.iter_rows() for c in row if str(c.value) == value)


@pytest.mark.parametrize("program", ["daechung", "ai"])
def test_carryover_student_is_one_row_in_every_sheet_with_merged_amount(make_input, out, synthetic_ai_rate, program):
    plain = convert(program, make_input(n=4), out, TEMPLATE)
    res = convert(program, make_input(n=4, extra=CARRY), out, TEMPLATE)
    assert res.count == 4 == plain.count
    assert [n.code for n in res.notes].count("STUDENT_MERGED_ROWS") == 2 and res.warnings == plain.warnings
    wb, wb0 = load_workbook(res.output_path), load_workbook(plain.output_path)
    for sheet in ("지급대상자명단", "WINS", "WRIS"):
        assert occurrences(wb, sheet, "90000002") == occurrences(wb0, sheet, "90000002") >= 1       # 학번이 한 번만(중복 없음)
    # 합산 금액(원)이 세 시트에 반영: 8시간 이월분 8000원이 더해진 값
    base = {r.value for ws in wb0.worksheets for row in ws.iter_rows() for r in row if isinstance(r.value, int)}
    merged = {r.value for ws in wb.worksheets for row in ws.iter_rows() for r in row if isinstance(r.value, int)} - base
    assert any(v > 8000 for v in merged) and len(merged) >= 2


def test_ai_program_is_selectable_from_cli_and_screen(make_input, out, synthetic_ai_rate):
    assert PROGRAMS["AI멘토링"] == "ai"
    code = cli.main(["convert", "--program", "ai", "--input", str(make_input(n=3, extra=CARRY[:1])), "--out-dir", str(out), "--template", str(TEMPLATE)])
    assert code == 0 and len(list(out.iterdir())) == 1


def test_ai_output_filename_uses_ai_program_code(make_input, out, synthetic_ai_rate):
    assert "_AI_9999_09" in convert("ai", make_input(n=3), out, TEMPLATE).output_path.name


def test_ai_blocks_a_rate_that_is_not_18000_by_default(make_input, out):
    with pytest.raises(ConversionFailed) as e:
        convert("ai", make_input(n=3), out, TEMPLATE)             # 합성 입력 시급 1000 != 18000
    assert e.value.stage == "input" and any(x.code == "RATE_NOT_FIXED" for x in e.value.errors) and list(out.iterdir()) == []


def test_notes_are_shown_by_the_controller(make_input, out, synthetic_ai_rate):
    o = run_conversion("ai", make_input(n=3, extra=CARRY[:1]), out, TEMPLATE)
    assert o.ok and any(w.startswith("참고: CARRYOVER_ROW") for w in o.details) and not any(w.startswith("경고:") for w in o.details)
