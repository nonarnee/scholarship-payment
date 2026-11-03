"""저장된 출력 파일을 **다시 읽어** 검증된 배치와 교차 대조한다(Writer 와 독립 계산).
오류에는 규칙 코드·필드·출력 행 번호만 담는다(값 금지, DI-13).
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from scholarship_payment.adapters.base import SourceTotals
from scholarship_payment.core.bank_codes import SHEET_NAME as BANK_SHEET
from scholarship_payment.core.normalize import format_minutes
from scholarship_payment.errors import ValidationError, ValidationFailed
from scholarship_payment.validation.validator import ValidatedBatch
from scholarship_payment.writers.template_writer import LIST_FIRST, LIST_PREFIX, SIDE_FIRST, WINS, WRIS

TEXT = "s"


def verify_output(path: str | Path, validated: ValidatedBatch, source_totals: SourceTotals) -> None:
    errors: list[ValidationError] = []
    try:
        wb = load_workbook(path)
    except Exception:
        raise ValidationFailed([ValidationError("OUTPUT_UNREADABLE", "file")]) from None
    batch, rows = validated.batch, validated.rows
    n = len(rows)
    expected_list = f"{LIST_PREFIX}{batch.month}월)"
    if wb.sheetnames != [expected_list, WINS, WRIS, BANK_SHEET]:
        raise ValidationFailed([ValidationError("OUTPUT_SHEETS", "sheets")])
    L, W, R = wb[expected_list], wb[WINS], wb[WRIS]

    def mismatch(sheet, field, row):
        errors.append(ValidationError("OUTPUT_MISMATCH", f"{sheet.title if sheet is not L else 'list'}:{field}", row))

    def check(sheet, row, field, cell, expected, text=False):
        if cell.value != expected or type(cell.value) is not type(expected):
            mismatch(sheet, field, row)
        elif text and cell.data_type != TEXT:
            errors.append(ValidationError("OUTPUT_CELL_TYPE", f"{'list' if sheet is L else sheet.title}:{field}", row))

    for i, vr in enumerate(rows):
        p, a, b = vr.row, LIST_FIRST + i, SIDE_FIRST + i
        check(L, a, "seq", L.cell(a, 1), i + 1)
        check(L, a, "student_id", L.cell(a, 4), p.student_id, True)
        check(L, a, "name", L.cell(a, 3), p.name, True)
        check(L, a, "pay_amount", L.cell(a, 12), p.pay_amount)
        check(L, a, "bank_name", L.cell(a, 13), p.bank_name, True)
        check(L, a, "wins_code", L.cell(a, 14), vr.wins_code)
        check(L, a, "wris_code", L.cell(a, 15), vr.wris_code)
        check(L, a, "account_no", L.cell(a, 16), p.account_no, True)
        check(L, a, "hours", L.cell(a, 11), format_minutes(p.minutes))
        check(L, a, "hourly_rate", L.cell(a, 10), p.rate_display if p.rate_display is not None else p.hourly_rate)
        check(W, b, "student_id", W.cell(b, 4), p.student_id, True)
        check(W, b, "pay_amount", W.cell(b, 7), p.pay_amount)
        check(W, b, "bank_code", W.cell(b, 8), vr.wins_code)
        check(W, b, "account_no", W.cell(b, 9), p.account_no, True)
        check(W, b, "year", W.cell(b, 2), batch.year)
        check(W, b, "month", W.cell(b, 3), batch.month)
        check(R, b, "student_id", R.cell(b, 3), p.student_id, True)
        check(R, b, "name", R.cell(b, 4), p.name, True)
        check(R, b, "pay_amount", R.cell(b, 5), p.pay_amount)
        check(R, b, "bank_code", R.cell(b, 6), str(vr.wris_code), True)
        check(R, b, "account_no", R.cell(b, 7), p.account_no, True)

    total_row = LIST_FIRST + n
    if L.cell(total_row, 1).value is not None or L.max_row != total_row or W.max_row != SIDE_FIRST + n - 1 or R.max_row != SIDE_FIRST + n - 1:
        errors.append(ValidationError("OUTPUT_ROW_COUNT", "rows"))
    amount = L.cell(total_row, 12).value
    if type(amount) is not int or amount != batch.total_amount() or amount != source_totals.amount:
        errors.append(ValidationError("OUTPUT_TOTAL_MISMATCH", "amount", total_row))
    if L.cell(total_row, 11).value != format_minutes(source_totals.minutes) or batch.total_minutes() != source_totals.minutes:
        errors.append(ValidationError("OUTPUT_TOTAL_MISMATCH", "minutes", total_row))
    for sheet in (L, W, R):
        for row in sheet.iter_rows():
            for c in row:
                if c.data_type == "f":
                    errors.append(ValidationError("OUTPUT_FORMULA", sheet.title if sheet is not L else "list", c.row))
                    break
    if errors:
        raise ValidationFailed(errors)
