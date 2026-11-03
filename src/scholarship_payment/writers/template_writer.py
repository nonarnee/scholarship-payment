"""방식 B TemplateWriter: 템플릿의 시트 속성은 그대로 두고, 데이터·합계 영역만 서식을 복제해 N행으로 다시 만든다.

- 첫 데이터 행 / 둘째 데이터 행(중간 행) / 합계 행의 서식을 **템플릿에서** 스냅샷으로 복사한다(하드코딩 없음).
- WINS·WRIS·명단 모두 값으로 기록한다(결정). 학번·계좌 등 식별자는 문자열 셀로 강제한다(수식 주입 방어, DI-04/14).
- 템플릿 파일은 읽기만 한다. 결과는 메모리의 Workbook 으로 돌려주고 저장은 호출자가 한다.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.utils import column_index_from_string, get_column_letter

from scholarship_payment.config.policy import OutputPolicy
from scholarship_payment.core.bank_codes import SHEET_NAME as BANK_SHEET
from scholarship_payment.core.normalize import format_minutes
from scholarship_payment.errors import ValidationError, ValidationFailed
from scholarship_payment.validation.validator import ValidatedBatch

LIST_PREFIX = "지급대상자명단("
WINS, WRIS = "WINS", "WRIS"
LIST_FIRST = 5                  # 명단 첫 데이터 행
SIDE_FIRST = 2                  # WINS/WRIS 첫 데이터 행
LIST_COLS, WINS_COLS, WRIS_COLS = 17, 9, 10
_WS = re.compile(r"\s+")
LIST_HEADERS = {"A3": "순번", "B3": "년월", "C3": "성명", "D3": "학번", "E3": "학과", "F3": "사업자등록번호", "G3": "활동기관",
                "H3": "근로지", "I3": "멘티인원", "J3": "시급", "K3": "시간", "L3": "재단장학금", "M4": "은행명",
                "N4": "은행코드(WINS)", "O4": "은행코드(WRIS)", "P4": "계좌번호", "Q3": "비고"}
WINS_HEADERS = ("근로구분명", "년도", "월", "학번", "근무부서코드", "근무일수", "재단장학금", "은행코드", "계좌번호")


def _norm(v: object) -> str | None:
    return _WS.sub("", v) if isinstance(v, str) else None


def _put(ws, coord: str, value: object) -> None:
    cell = ws[coord]
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"          # '=' 로 시작해도 수식이 아닌 문자열로 저장


def _snap(ws, r: int, ncol: int):
    return [copy.copy(ws.cell(r, c)._style) for c in range(1, ncol + 1)], ws.row_dimensions[r].height


def _apply(ws, r: int, snap) -> None:
    styles, height = snap
    for c, st in enumerate(styles, 1):
        ws.cell(r, c)._style = copy.copy(st)
    if height is not None:
        ws.row_dimensions[r].height = height


def _wipe_from(ws, first_row: int) -> None:
    ws.delete_rows(first_row, ws.max_row - first_row + 1)
    for r in [r for r in ws.row_dimensions if r >= first_row]:
        del ws.row_dimensions[r]


def _first_rule(ws):
    for cf in ws.conditional_formatting:
        for rule in cf.rules:
            return rule
    return None


def _reset_conditional_format(ws, rule, rng: str) -> None:
    ws.conditional_formatting = ConditionalFormattingList()
    if rule is not None:
        ws.conditional_formatting.add(rng, copy.copy(rule))


def _hide_column(ws, letter: str) -> None:
    """열 하나를 숨긴다. 템플릿이 열 너비를 여러 열 묶음으로 갖고 있으면 그 열만 분리해서 숨긴다."""
    idx = column_index_from_string(letter)
    for key, dim in list(ws.column_dimensions.items()):
        lo, hi = dim.min or column_index_from_string(key), dim.max or column_index_from_string(key)
        if lo <= idx <= hi:
            if lo != hi:
                ws.column_dimensions.pop(key)
                for part in range(lo, hi + 1):
                    if part != idx:
                        clone = copy.copy(dim)
                        clone.index = get_column_letter(part)
                        clone.min = clone.max = part
                        ws.column_dimensions[clone.index] = clone
                dim.index = letter
                dim.min = dim.max = idx
                ws.column_dimensions[letter] = dim
            dim.hidden = True
            return
    ws.column_dimensions[letter].hidden = True


def _layout_errors(wb, policy: OutputPolicy) -> list[ValidationError]:
    errs: list[ValidationError] = []
    list_names = [n for n in wb.sheetnames if n.startswith(LIST_PREFIX)]
    allowed = {WINS, WRIS, BANK_SHEET, *policy.excluded_sheets, *list_names}
    if len(list_names) != 1:
        errs.append(ValidationError("TEMPLATE_LAYOUT", "list_sheet"))
    for name in (WINS, WRIS, BANK_SHEET):
        if name not in wb.sheetnames:
            errs.append(ValidationError("TEMPLATE_LAYOUT", f"sheet:{name}"))
    for name in wb.sheetnames:
        if name not in allowed:
            errs.append(ValidationError("TEMPLATE_LAYOUT", "unexpected_sheet"))
    if errs:
        return errs
    ws = wb[list_names[0]]
    errs += [ValidationError("TEMPLATE_LAYOUT", f"list:{c}") for c, h in LIST_HEADERS.items()
             if _norm(ws[c].value) != h]
    if not (isinstance(ws.cell(LIST_FIRST, 1).value, int) and isinstance(ws.cell(LIST_FIRST + 1, 1).value, int)):
        errs.append(ValidationError("TEMPLATE_LAYOUT", "list:sample_rows"))
    wins, wris = wb[WINS], wb[WRIS]
    errs += [ValidationError("TEMPLATE_LAYOUT", f"{WINS}:{c}") for c, h in enumerate(WINS_HEADERS, 1) if _norm(wins.cell(1, c).value) != h]
    errs += [ValidationError("TEMPLATE_LAYOUT", f"{WRIS}:{c}") for c, h in enumerate(policy.wris_headers, 1) if _norm(wris.cell(1, c).value) != h]
    for sheet in (wins, wris):
        if sheet.max_row < SIDE_FIRST + 1 or sheet.cell(SIDE_FIRST + 1, 1).value is None:
            errs.append(ValidationError("TEMPLATE_LAYOUT", f"{sheet.title}:sample_rows"))
    return errs


def _list_total_row(ws) -> int:
    r = LIST_FIRST
    while isinstance(ws.cell(r, 1).value, int):
        r += 1
    return r


def build_workbook(validated: ValidatedBatch, template_path: str | Path, policy: OutputPolicy, base_date: str | None = None):
    """템플릿을 읽어 검증된 배치를 쓴 Workbook 을 돌려준다(저장하지 않음)."""
    wb = load_workbook(template_path)
    errors = _layout_errors(wb, policy)
    if errors:
        raise ValidationFailed(errors)
    for name in policy.excluded_sheets:
        if name in wb.sheetnames:
            wb.remove(wb[name])

    batch = validated.batch
    rows = validated.rows
    n = len(rows)
    year, month = batch.year, batch.month

    # ---------------- 명단
    ws = wb[next(s for s in wb.sheetnames if s.startswith(LIST_PREFIX))]
    total_src = _list_total_row(ws)
    first, mid, total = _snap(ws, LIST_FIRST, LIST_COLS), _snap(ws, LIST_FIRST + 1, LIST_COLS), _snap(ws, total_src, LIST_COLS)
    rule = _first_rule(ws)
    _wipe_from(ws, LIST_FIRST)
    ym = f"{year:04d}년{month:02d}월"
    for i, vr in enumerate(rows):
        r, p = LIST_FIRST + i, vr.row
        _apply(ws, r, first if i == 0 else mid)
        values = {"A": i + 1, "B": ym, "C": p.name, "D": p.student_id, "E": p.department, "F": p.biz_no, "G": p.org_name,
                  "H": p.work_place, "I": p.headcount, "J": p.hourly_rate, "K": format_minutes(p.minutes), "L": p.pay_amount,
                  "M": p.bank_name, "N": vr.wins_code, "O": vr.wris_code, "P": p.account_no}
        for col, v in values.items():
            _put(ws, f"{col}{r}", v)
    t = LIST_FIRST + n
    _apply(ws, t, total)
    _put(ws, f"K{t}", format_minutes(batch.total_minutes()))
    _put(ws, f"L{t}", batch.total_amount())
    _reset_conditional_format(ws, rule, f"D{LIST_FIRST}:D{t - 1}")
    for letter in policy.hidden_list_columns:
        _hide_column(ws, letter)
    ws["A1"] = policy.title(year, month)
    if base_date is not None:
        _put(ws, "Q2", f"*기준 : {base_date}")
    ws.title = f"{LIST_PREFIX}{month}월)"

    # ---------------- WINS / WRIS
    for name, ncol, id_col in ((WINS, WINS_COLS, "D"), (WRIS, WRIS_COLS, "C")):
        sheet = wb[name]
        f, m = _snap(sheet, SIDE_FIRST, ncol), _snap(sheet, SIDE_FIRST + 1, ncol)
        rule = _first_rule(sheet)
        _wipe_from(sheet, SIDE_FIRST)
        for i, vr in enumerate(rows):
            r, p = SIDE_FIRST + i, vr.row
            _apply(sheet, r, f if i == 0 else m)
            if name == WINS:
                values = {"A": policy.wins_work_name, "B": year, "C": month, "D": p.student_id, "G": p.pay_amount,
                          "H": vr.wins_code, "I": p.account_no}
            else:
                values = {"A": policy.wris_gub_a, "B": policy.wris_gub_b, "C": p.student_id, "D": p.name, "E": p.pay_amount,
                          "F": str(vr.wris_code), "G": p.account_no, "H": p.name, "I": policy.remittance(year, month)}
            for col, v in values.items():
                _put(sheet, f"{col}{r}", v)
        _reset_conditional_format(sheet, rule, f"{id_col}{SIDE_FIRST}:{id_col}{SIDE_FIRST + n - 1}")
    return wb
