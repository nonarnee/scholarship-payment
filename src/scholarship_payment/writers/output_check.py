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
from scholarship_payment.writers.template_writer import LIST_FIRST, LIST_PREFIX, SIDE_FIRST, SPLIT_KINDS, WINS, WRIS

TEXT = "s"


def verify_output(path: str | Path, validated: ValidatedBatch, source_totals: SourceTotals, only: str | None = None) -> None:
    """`only` 가 None 이면 통합본(명단·WINS·WRIS·은행코드 4시트), 아니면 분리 모드 파일 하나(list/wins/wris 중 해당 시트 1개)를 검증한다."""
    errors: list[ValidationError] = []
    if only is not None and only not in SPLIT_KINDS:
        raise ValueError("only")
    try:
        wb = load_workbook(path)
    except Exception:
        raise ValidationFailed([ValidationError("OUTPUT_UNREADABLE", "file")]) from None
    batch, rows = validated.batch, validated.rows
    n = len(rows)
    expected_list = f"{LIST_PREFIX}{batch.month}월)"
    expected_names = [expected_list, WINS, WRIS, BANK_SHEET] if only is None else [{"list": expected_list, "wins": WINS, "wris": WRIS}[only]]
    if wb.sheetnames != expected_names:
        raise ValidationFailed([ValidationError("OUTPUT_SHEETS", "sheets")])
    want = {"list", "wins", "wris"} if only is None else {only}
    L = wb[expected_list] if "list" in want else None
    W = wb[WINS] if "wins" in want else None
    R = wb[WRIS] if "wris" in want else None

    def mismatch(sheet, field, row):
        errors.append(ValidationError("OUTPUT_MISMATCH", f"{'list' if sheet is L else sheet.title}:{field}", row))

    def check(sheet, row, field, cell, expected, text=False):
        if cell.value != expected or type(cell.value) is not type(expected):
            mismatch(sheet, field, row)
        elif text and cell.data_type != TEXT:
            errors.append(ValidationError("OUTPUT_CELL_TYPE", f"{'list' if sheet is L else sheet.title}:{field}", row))

    for i, vr in enumerate(rows):
        p, a, b = vr.row, LIST_FIRST + i, SIDE_FIRST + i
        if L is not None:
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
        if W is not None:
            check(W, b, "student_id", W.cell(b, 4), p.student_id, True)
            check(W, b, "pay_amount", W.cell(b, 7), p.pay_amount)
            check(W, b, "bank_code", W.cell(b, 8), vr.wins_code)
            check(W, b, "account_no", W.cell(b, 9), p.account_no, True)
            check(W, b, "year", W.cell(b, 2), batch.year)
            check(W, b, "month", W.cell(b, 3), batch.month)
        if R is not None:
            check(R, b, "student_id", R.cell(b, 3), p.student_id, True)
            check(R, b, "name", R.cell(b, 4), p.name, True)
            check(R, b, "pay_amount", R.cell(b, 5), p.pay_amount)
            check(R, b, "bank_code", R.cell(b, 6), str(vr.wris_code), True)
            check(R, b, "account_no", R.cell(b, 7), p.account_no, True)

    total_row = LIST_FIRST + n
    side_last = SIDE_FIRST + n - 1
    if L is not None and (L.cell(total_row, 1).value is not None or L.max_row != total_row):
        errors.append(ValidationError("OUTPUT_ROW_COUNT", "rows"))
    if any(x is not None and x.max_row != side_last for x in (W, R)):
        errors.append(ValidationError("OUTPUT_ROW_COUNT", "rows"))
    if L is not None:
        amount = L.cell(total_row, 12).value
        if type(amount) is not int or amount != batch.total_amount() or amount != source_totals.amount:
            errors.append(ValidationError("OUTPUT_TOTAL_MISMATCH", "amount", total_row))
        if L.cell(total_row, 11).value != format_minutes(source_totals.minutes) or batch.total_minutes() != source_totals.minutes:
            errors.append(ValidationError("OUTPUT_TOTAL_MISMATCH", "minutes", total_row))
    for sheet, col in ((W, 7), (R, 5)):
        if sheet is not None and only is not None:           # 분리 파일은 합계 행이 없으므로 금액 열의 합이 배치 총액과 같은지 따로 본다
            values = [sheet.cell(SIDE_FIRST + i, col).value for i in range(n)]
            if not all(type(x) is int for x in values) or sum(values) != batch.total_amount() or batch.total_amount() != source_totals.amount:
                errors.append(ValidationError("OUTPUT_TOTAL_MISMATCH", f"{sheet.title}:amount"))
    for sheet in (L, W, R):
        if sheet is None:
            continue
        for row in sheet.iter_rows():
            for c in row:
                if c.data_type == "f":
                    errors.append(ValidationError("OUTPUT_FORMULA", "list" if sheet is L else sheet.title, c.row))
                    break
    if errors:
        raise ValidationFailed(errors)


def _rows(path, kind: str, n: int):
    ws = load_workbook(path).worksheets[0]
    if kind == "list":
        return [(ws.cell(LIST_FIRST + i, 4).value, ws.cell(LIST_FIRST + i, 12).value, ws.cell(LIST_FIRST + i, 16).value,
                 ws.cell(LIST_FIRST + i, 14).value, ws.cell(LIST_FIRST + i, 15).value) for i in range(n)]
    if kind == "wins":
        return [(ws.cell(SIDE_FIRST + i, 4).value, ws.cell(SIDE_FIRST + i, 7).value, ws.cell(SIDE_FIRST + i, 9).value,
                 ws.cell(SIDE_FIRST + i, 8).value, None) for i in range(n)]
    return [(ws.cell(SIDE_FIRST + i, 3).value, ws.cell(SIDE_FIRST + i, 5).value, ws.cell(SIDE_FIRST + i, 7).value,
             None, ws.cell(SIDE_FIRST + i, 6).value) for i in range(n)]


def verify_split_set(paths: dict, validated: ValidatedBatch, source_totals: SourceTotals) -> None:
    """분리 모드의 세 파일(list/wins/wris)을 각각 검증한 뒤, 다시 읽어 서로 교차 대조한다(행 순서별 학번·금액·계좌, WINS/WRIS 은행코드)."""
    if set(paths) != set(SPLIT_KINDS):
        raise ValidationFailed([ValidationError("OUTPUT_SHEETS", "set")])
    for kind in SPLIT_KINDS:
        verify_output(paths[kind], validated, source_totals, only=kind)
    n = len(validated.rows)
    lst, wins, wris = (_rows(paths[k], k, n) for k in SPLIT_KINDS)
    errors: list[ValidationError] = []
    for i, (a, w, r) in enumerate(zip(lst, wins, wris)):
        if not (a[0] == w[0] == r[0] and a[1] == w[1] == r[1] and a[2] == w[2] == r[2]):
            errors.append(ValidationError("OUTPUT_MISMATCH", "cross:row", SIDE_FIRST + i))
        elif a[3] != w[3] or str(a[4]) != r[4]:
            errors.append(ValidationError("OUTPUT_MISMATCH", "cross:bank", SIDE_FIRST + i))
    if errors:
        raise ValidationFailed(errors)
