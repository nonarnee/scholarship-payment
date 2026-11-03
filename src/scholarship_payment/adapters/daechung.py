"""대청교 `월별지급승인` 입력 Adapter.

입력은 재단에서 내려받은 원본 파일을 **그대로** 읽는다(사용자가 고치지 않는다는 전제).
- 레이아웃 지문(시트명, 헤더 텍스트, 병합)이 다르면 열 번호를 적용하지 않고 차단한다.
- `A·B·V·W·X` 열은 읽지 않으며 지급 대상자 필터에 쓰지 않는다(결정).
- 중복 학번·0원·음수·대상자 0명 같은 업무 규칙은 판단하지 않는다(OPEN H5·M10). 0명은 배치를 만들 수 없어 차단한다.
- 원본은 읽기만 한다(저장하지 않음).
"""
from __future__ import annotations

import re
from pathlib import Path

from openpyxl import load_workbook

from scholarship_payment.adapters.base import AdapterResult, InputValidationFailed, SourceTotals
from scholarship_payment.core.normalize import normalize_account, normalize_identifier, parse_amount, parse_hours
from scholarship_payment.errors import ValidationError
from scholarship_payment.models.payment import PaymentBatch, PaymentRow

SHEET_NAME = "월별지급승인"
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

    def __init__(self, student_id_len: int | None = 8) -> None:
        # 8자리는 샘플에서 관찰된 규칙이다(OPEN M15). 숫자 셀의 학번은 선행 0이 이미 사라져 있어 길이 검사가 안전망이 된다.
        self.student_id_len = student_id_len

    # ------------------------------------------------------------------ 진입점
    def read(self, path: str | Path) -> AdapterResult:
        wb = self._open(Path(path))
        try:
            if SHEET_NAME not in wb.sheetnames:
                raise InputValidationFailed([ValidationError("SHEET_MISSING", "sheet")])
            ws = wb[SHEET_NAME]
            layout = self._check_layout(ws)
            if layout:
                raise InputValidationFailed(layout)       # 레이아웃이 틀리면 데이터를 해석하지 않는다
            return self._read_data(ws)
        finally:
            wb.close()

    # ------------------------------------------------------------------ 파일·레이아웃
    @staticmethod
    def _open(path: Path):
        if not path.is_file():
            raise InputValidationFailed([ValidationError("FILE_NOT_FOUND", "file")])
        try:
            return load_workbook(path, read_only=False, data_only=True)
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
        rows: list[PaymentRow] = []
        year_months: set[tuple[int, int]] = set()

        for r in range(FIRST_DATA_ROW, total_row):
            seq = ws.cell(r, 3).value
            if isinstance(seq, int) and not isinstance(seq, bool):
                row = self._parse_row(ws, r, errors, warnings, year_months)
                if row is not None:
                    rows.append(row)
            elif all(_blank(ws.cell(r, c).value) for c in range(1, LAST_COLUMN + 1)):
                errors.append(ValidationError("ROW_BLANK_IN_DATA", "rows", r))
            else:
                errors.append(ValidationError("ROW_NOT_DATA", "rows", r))
        for r in range(total_row + 1, max_row + 1):
            if any(not _blank(ws.cell(r, c).value) for c in range(1, LAST_COLUMN + 1)):
                errors.append(ValidationError("CONTENT_AFTER_TOTAL", "rows", r))

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
        return AdapterResult(batch=batch, source_totals=totals, warnings=tuple(warnings))

    def _parse_row(self, ws, r, errors, warnings, year_months) -> PaymentRow | None:
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
        year_months.add(ym)
        self._collect_warnings(get, r, pay_amount, warnings)
        return row

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
