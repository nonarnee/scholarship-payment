"""대청교 `월별지급승인` 입력 Adapter.

입력은 재단에서 내려받은 원본 파일을 **그대로** 읽는다(사용자가 고치지 않는다는 전제).
- 데이터 시트는 시트명이 아니라 구조(머리글 텍스트·위치, 병합)로 찾는다: 구조가 일치하는 시트가 정확히 1개일 때만 쓰고, 없거나 2개 이상이면 차단한다(`adapters.sheets`).
- 레이아웃 지문(헤더 텍스트, 병합)이 다르면 열 번호를 적용하지 않고 차단한다.
- `A·B·V·W·X` 열은 읽지 않으며 지급 대상자 필터에 쓰지 않는다(결정).
- 중복 학번·0원·음수·대상자 0명 같은 업무 규칙은 판단하지 않는다(OPEN H5·M10). 0명은 배치를 만들 수 없어 차단한다.
- 원본은 읽기만 한다(저장하지 않음).
- **이월·기관 변경으로 한 학생이 연속 여러 행**이면(같은 학번) 학생당 1행으로 합산한다(M29·M30): 시간·금액은 합계, 나머지는 맨 위 행.
  성명·은행·계좌가 다르거나 시급이 다르면 차단한다. 지급월은 맨 위 행의 년월이며, 아래 행의 년월이 더 늦으면 차단한다.
  이월(더 이른 년월)과 합산은 차단하지 않는 **참고**(`AdapterResult.notes`)로만 남긴다. 연속하지 않은 같은 학번은 합치지 않는다(Validator 가 중복으로 차단).
- AI멘토링은 같은 양식이며 `fixed_rate`(시급 고정)를 주면 각 행의 시급이 같아야 하고, 합산 금액 × 60 = 합산 분 × 시급 이어야 한다.
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from openpyxl import load_workbook

from scholarship_payment.adapters.base import AdapterResult, InputValidationFailed, SourceTotals
from scholarship_payment.adapters.sheets import select_data_sheet
from scholarship_payment.adapters.source import open_source
from scholarship_payment.core.normalize import normalize_account, normalize_identifier, parse_amount, parse_hours
from scholarship_payment.errors import ValidationError
from scholarship_payment.models.payment import PaymentBatch, PaymentRow

FIRST_DATA_ROW = 3
LAST_COLUMN = 24            # X
# 레이아웃 지문: 좌표 -> 기대 텍스트(공백 제거 후 비교). 머리글이 병합된 칸은 좌상단 셀만 지문으로 쓴다.
EXPECTED_HEADERS = {
    "C1": "순번", "D1": "년월", "E1": "성명", "F1": "학번", "G1": "학과", "H1": "사업자등록번호", "I1": "활동기관",
    "J1": "근로지", "K1": "멘토인원", "L1": "시급", "M1": "시간", "N1": "기준금액(시급X총시간)", "O1": "재단장학금",
    "R1": "대학자체장학금", "T1": "계좌번호",
    "O2": "계", "P2": "교부금집행액", "Q2": "이자수익집행액", "R2": "대응투자장학금(기본금)",
    "S2": "별도추가장학금(추가금)", "T2": "은행명", "U2": "계좌번호",
}
REQUIRED_MERGES = (
    *(f"{c}1:{c}2" for c in "CDEFGHIJKLMN"), "O1:Q1", "R1:S1", "T1:U1",
)
_YEAR_MONTH_RE = re.compile(r"([0-9]{4})년([0-9]{2})월")
_WS_RE = re.compile(r"\s+")


def _norm(value: object) -> str | None:
    return _WS_RE.sub("", value) if isinstance(value, str) else None


def _blank(value: object) -> bool:
    """None 과 빈 문자열(실제 원본은 빈 칸을 빈 문자열로 가진다)은 모두 빈 칸이다."""
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value: object) -> object:
    """문자열은 앞뒤 공백만 제거한다. 빈 칸은 ''. 그 밖의 타입은 그대로 두어 모델 검증이 거부하게 한다."""
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else value


def _parse_year_month(value: object) -> tuple[int, int]:
    if isinstance(value, str):
        m = _YEAR_MONTH_RE.fullmatch(value)
        if m and int(m.group(1)) >= 1 and 1 <= int(m.group(2)) <= 12:
            return int(m.group(1)), int(m.group(2))
    raise ValidationError("YEARMONTH_FORMAT", "year_month")


class DaechungAdapter:
    PROGRAM_CODE = "DAECHUNG"

    def __init__(self, student_id_len: int | None = 8, program_code: str = "DAECHUNG", fixed_rate: int | None = None) -> None:
        self.PROGRAM_CODE = program_code
        self.fixed_rate = fixed_rate
        # 8자리는 샘플에서 관찰된 규칙이다(OPEN M15). 숫자 셀의 학번은 선행 0이 이미 사라져 있어 길이 검사가 안전망이 된다.
        self.student_id_len = student_id_len

    # ------------------------------------------------------------------ 진입점
    def read(self, path: str | Path, password: str | None = None) -> AdapterResult:
        wb = self._open(Path(path), password)
        try:
            ws = select_data_sheet(wb, self._check_layout)      # 구조가 맞는 시트가 정확히 1개일 때만. 레이아웃이 틀리면 데이터를 해석하지 않는다
            return self._read_data(ws)
        finally:
            wb.close()

    # ------------------------------------------------------------------ 파일·레이아웃
    @staticmethod
    def _open(path: Path, password: str | None = None):
        if not path.is_file():
            raise InputValidationFailed([ValidationError("FILE_NOT_FOUND", "file")])
        try:
            return load_workbook(open_source(path, password), read_only=False, data_only=True)
        except InputValidationFailed:
            raise
        except Exception:                                  # 암호·손상·형식 오류. 원인 메시지는 노출하지 않는다.
            raise InputValidationFailed([ValidationError("FILE_UNREADABLE", "file")]) from None

    @staticmethod
    def _check_layout(ws) -> list[ValidationError]:
        errors = [ValidationError("LAYOUT_HEADER", coord)
                  for coord, expected in EXPECTED_HEADERS.items() if _norm(ws[coord].value) != expected]
        merged = {str(m) for m in ws.merged_cells.ranges}
        errors += [ValidationError("LAYOUT_MERGE", rng) for rng in REQUIRED_MERGES if rng not in merged]
        return errors

    # ------------------------------------------------------------------ 데이터
    def _read_data(self, ws) -> AdapterResult:
        max_row = ws.max_row
        total_row = next((r for r in range(FIRST_DATA_ROW, max_row + 1) if _norm(ws.cell(r, 6).value) == "합계"), None)
        if total_row is None:
            raise InputValidationFailed([ValidationError("TOTAL_ROW_MISSING", "total_row")])

        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []
        parsed: list[tuple[PaymentRow, tuple[int, int]]] = []

        for r in range(FIRST_DATA_ROW, total_row):
            seq = ws.cell(r, 3).value
            if isinstance(seq, int) and not isinstance(seq, bool):
                got = self._parse_row(ws, r, errors, warnings)
                if got is not None:
                    parsed.append(got)
            elif all(_blank(ws.cell(r, c).value) for c in range(1, LAST_COLUMN + 1)):
                errors.append(ValidationError("ROW_BLANK_IN_DATA", "rows", r))
            else:
                errors.append(ValidationError("ROW_NOT_DATA", "rows", r))
        for r in range(total_row + 1, max_row + 1):
            if any(not _blank(ws.cell(r, c).value) for c in range(1, LAST_COLUMN + 1)):
                errors.append(ValidationError("CONTENT_AFTER_TOTAL", "rows", r))

        rows, year_months, notes = self._merge_students(parsed, errors)

        if total_row == FIRST_DATA_ROW and not errors:
            errors.append(ValidationError("NO_DATA_ROWS", "rows"))      # 0명 정책 미확정(M10): 배치를 만들 수 없어 차단
        if len(year_months) > 1:
            errors.append(ValidationError("MONTH_MIXED", "year_month"))

        totals = None
        if not errors:      # 행 오류가 있으면 합계 대조는 의미가 없다
            totals = self._compare_totals(ws, total_row, rows, errors)
        if errors:
            raise InputValidationFailed(errors)

        (year, month), = year_months
        batch = PaymentBatch(program_code=self.PROGRAM_CODE, year=year, month=month, rows=rows)
        warnings.sort(key=lambda w: (w.row or 0, w.code))
        notes.sort(key=lambda w: (w.row or 0, w.code))
        return AdapterResult(batch=batch, source_totals=totals, warnings=tuple(warnings), notes=tuple(notes))

    def _merge_students(self, parsed, errors):
        """같은 학번이 연속된 행을 학생당 1행으로 합친다. 반환: (학생 행, 지급월 집합, 참고)."""
        groups: list[list] = []
        for item in parsed:
            if groups and groups[-1][0][0].student_id == item[0].student_id:
                groups[-1].append(item)
            else:
                groups.append([item])
        rows: list[PaymentRow] = []
        months: set[tuple[int, int]] = set()
        notes: list[ValidationError] = []
        for g in groups:
            top, top_ym = g[0]
            bad = False
            for row, ym in g[1:]:
                if row.name != top.name:
                    errors.append(ValidationError("GROUP_STUDENT_MISMATCH", "name", row.source_row))
                    bad = True
                if (row.bank_name, row.account_no) != (top.bank_name, top.account_no):
                    errors.append(ValidationError("GROUP_ACCOUNT_MISMATCH", "account_no", row.source_row))
                    bad = True
                if row.hourly_rate != top.hourly_rate:
                    errors.append(ValidationError("GROUP_RATE_MISMATCH", "hourly_rate", row.source_row))
                    bad = True
                if ym > top_ym:
                    errors.append(ValidationError("CARRYOVER_MONTH_INVALID", "year_month", row.source_row))
                    bad = True
                elif ym < top_ym:
                    notes.append(ValidationError("CARRYOVER_ROW", "year_month", row.source_row))
            if bad:
                continue
            minutes = sum(x.minutes for x, _ in g)
            amount = sum(x.pay_amount for x, _ in g)
            if self.fixed_rate is not None and amount * 60 != minutes * self.fixed_rate:
                errors.append(ValidationError("AMOUNT_RATE_MISMATCH", "pay_amount", top.source_row))
                continue
            if len(g) > 1:
                notes.append(ValidationError("STUDENT_MERGED_ROWS", "rows", top.source_row))
                top = replace(top, minutes=minutes, pay_amount=amount)
            months.add(top_ym)
            rows.append(top)
        return rows, months, notes

    def _parse_row(self, ws, r, errors, warnings) -> tuple[PaymentRow, tuple[int, int]] | None:
        failed = False

        def get(col):
            return ws[f"{col}{r}"].value

        def attempt(fn, *args, **kwargs):
            nonlocal failed
            try:
                return fn(*args, **kwargs)
            except ValidationError as e:
                errors.append(e.with_row(r))
                failed = True
                return None

        def optional_int(col, field):
            return None if _blank(get(col)) else attempt(parse_amount, get(col), field)

        student_id = attempt(normalize_identifier, get("F"), "student_id", expected_len=self.student_id_len)
        account_no = attempt(normalize_account, get("U"))
        minutes = attempt(parse_hours, get("M"))
        pay_amount = attempt(parse_amount, get("O"), "pay_amount")
        hourly_rate = optional_int("L", "hourly_rate")
        headcount = optional_int("K", "headcount")
        ym = attempt(_parse_year_month, get("D"))
        if self.fixed_rate is not None and hourly_rate != self.fixed_rate:
            errors.append(ValidationError("RATE_NOT_FIXED", "hourly_rate", r))
            failed = True
        if failed:
            return None
        try:
            row = PaymentRow(
                source_row=r, student_id=student_id, name=_text(get("E")), account_no=account_no,
                bank_name=_text(get("T")), pay_amount=pay_amount, minutes=minutes,
                department=_text(get("G")), org_name=_text(get("I")), work_place=_text(get("J")),
                biz_no=_text(get("H")), headcount=headcount, hourly_rate=hourly_rate,
            )
        except ValidationError as e:
            errors.append(e)
            return None
        self._collect_warnings(get, r, pay_amount, warnings)
        return row, ym

    @staticmethod
    def _collect_warnings(get, r, pay_amount, warnings) -> None:
        """차단하지 않는 경고. 업무 규칙 판단이 아니라 '확인해 볼 만한 사실'만 코드로 남긴다."""
        try:
            grant = 0 if _blank(get("P")) else parse_amount(get("P"))
            interest = 0 if _blank(get("Q")) else parse_amount(get("Q"))
        except ValidationError:
            warnings.append(ValidationError("SPLIT_AMOUNT_UNREADABLE", "grant_interest", r))
        else:
            if grant + interest != pay_amount:
                warnings.append(ValidationError("SPLIT_AMOUNT_MISMATCH", "grant_interest", r))
        for col in "RS":
            if _blank(get(col)):
                continue
            try:
                present = parse_amount(get(col)) != 0
            except ValidationError:
                warnings.append(ValidationError("UNIVERSITY_FUNDS_UNREADABLE", "university_funds", r))
                break
            if present:
                warnings.append(ValidationError("UNIVERSITY_FUNDS_PRESENT", "university_funds", r))
                break

    @staticmethod
    def _compare_totals(ws, total_row, rows, errors) -> SourceTotals | None:
        amount = minutes = None
        try:
            amount = parse_amount(ws[f"O{total_row}"].value, "amount")
        except ValidationError:
            errors.append(ValidationError("TOTALS_UNREADABLE", "amount", total_row))
        try:
            minutes = parse_hours(ws[f"M{total_row}"].value, "minutes")
        except ValidationError:
            errors.append(ValidationError("TOTALS_UNREADABLE", "minutes", total_row))
        if amount is not None and amount != sum(r.pay_amount for r in rows):
            errors.append(ValidationError("TOTALS_MISMATCH", "amount", total_row))
        if minutes is not None and minutes != sum(r.minutes for r in rows):
            errors.append(ValidationError("TOTALS_MISMATCH", "minutes", total_row))
        return None if errors else SourceTotals(amount=amount, minutes=minutes)
