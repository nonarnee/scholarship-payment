"""다문화·탈북학생 멘토링 `월별지급부현황` 입력 Adapter.

입력은 재단 원본을 그대로 읽는다. 대청교와 달리 **학생 단위 묶음 + 소계 행** 구조다.
- 데이터 행(B열 순번이 정수)들 뒤에 `소계` 행이 오고, 마지막에 `합계` 행이 있다.
- 한 묶음(데이터 행 1개 이상 + 소계 1개)은 한 학생이다. 기관 변경이나 이월(누적 10시간 미만이던 금액이 이번 달에 지급)로
  데이터 행이 둘 이상일 수 있다. 결과는 **학생당 1행**: 시간·금액은 묶음 합계, 그 밖의 항목은 **맨 위 행**(최근 활동기관)의 값.
- 시급은 계산하지 않는다. 근무형태 끝의 괄호 값(예: 도시/농어촌)으로 정책의 시급표에서 찾는다. 표에 없으면 차단한다.
  각 행의 총금액은 `시간 × 시급`과 정확히 같아야 하며, 다르면 차단한다. 총금액은 원본 값을 쓴다.
- 묶음의 소계 행과 맨 아래 합계 행은 데이터 행 합계와 일치해야 한다.
- 시급이 다른 기관이 섞인 학생은 명단 시급 칸에 `위 행 시급 / 아래 행 시급`(예: `18,000 / 14,000`)으로 문자열 표시한다.
- 근무형태 앞의 활동월(`04월 …`)이 지급월과 다르면 이월로 보고 참고(`CARRYOVER_ROW`, `notes`)만 남긴다. 행 합산도 참고(`STUDENT_MERGED_ROWS`)다. 활동월이 지급월보다 늦은 경우는
  지급월이 1·2월(학년도 경계)일 때만 허용하고 그 밖에는 차단한다. 년월 열은 모든 행이 같아야 한다.
- 사업자등록번호는 원본에 없어 빈 값이다. 멘티 인원은 맨 위 행 기준 1명이다.
- 년월(`YYYY-MM`)·성명·학번·학과는 학생의 행이 둘 이상이면 첫 행에만 있다(둘째 행부터 빈 칸은 첫 행 값을 쓴다). 값이 있으면 학번·성명은 첫 행과 같아야 하고 년월은 모든 행이 같아야 한다.
- 원본은 읽기만 한다.
"""
from __future__ import annotations

import re
from pathlib import Path

from openpyxl import load_workbook

from scholarship_payment.adapters.base import AdapterResult, InputValidationFailed, SourceTotals
from scholarship_payment.adapters.daechung import _blank, _norm, _text
from scholarship_payment.adapters.source import open_source
from scholarship_payment.core.normalize import normalize_account, normalize_identifier, parse_amount, parse_hours
from scholarship_payment.errors import ValidationError
from scholarship_payment.models.payment import PaymentBatch, PaymentRow

SHEET_NAME = "월별지급부현황"
FIRST_DATA_ROW = 3
LAST_COLUMN = 18            # R
EXPECTED_HEADERS = {
    "B1": "순번", "C1": "멘토유형", "D1": "년월", "E1": "성명", "F1": "학번", "G1": "학과", "H1": "멘티현황",
    "M1": "총시간", "N1": "총금액(원)", "O1": "은행정보", "Q1": "지급확인", "R1": "비고",
    "H2": "근무형태", "I2": "기관명", "J2": "학교구분", "K2": "학년", "L2": "멘티명", "O2": "은행명", "P2": "계좌번호",
}
REQUIRED_MERGES = (*(f"{c}1:{c}2" for c in "ABCDEFGMNQ"), "H1:L1", "O1:P1")
_YM = re.compile(r"([0-9]{4})-([0-9]{2})")
_PAREN = re.compile(r"\(([^()]*)\)\s*$")
_ACT_MONTH = re.compile(r"\s*([0-9]{1,2})월")


def _parse_ym(value: object) -> tuple[int, int]:
    if isinstance(value, str):
        m = _YM.fullmatch(value.strip())
        if m and int(m.group(1)) >= 1 and 1 <= int(m.group(2)) <= 12:
            return int(m.group(1)), int(m.group(2))
    raise ValidationError("YEARMONTH_FORMAT", "year_month")


class MulticulturalAdapter:
    PROGRAM_CODE = "MULTICULTURAL"

    def __init__(self, rates: dict[str, int] | None = None, student_id_len: int | None = 8) -> None:
        self.rates = dict(rates or {})
        self.student_id_len = student_id_len

    def read(self, path: str | Path, password: str | None = None) -> AdapterResult:
        if not self.rates:
            raise InputValidationFailed([ValidationError("POLICY_RATES_MISSING", "hourly_rates")])
        wb = self._open(Path(path), password)
        try:
            if SHEET_NAME not in wb.sheetnames:
                raise InputValidationFailed([ValidationError("SHEET_MISSING", "sheet")])
            ws = wb[SHEET_NAME]
            errors = [ValidationError("LAYOUT_HEADER", c) for c, h in EXPECTED_HEADERS.items() if _norm(ws[c].value) != h]
            merged = {str(m) for m in ws.merged_cells.ranges}
            errors += [ValidationError("LAYOUT_MERGE", r) for r in REQUIRED_MERGES if r not in merged]
            if errors:
                raise InputValidationFailed(errors)
            return self._read_data(ws)
        finally:
            wb.close()

    @staticmethod
    def _open(path: Path, password):
        if not path.is_file():
            raise InputValidationFailed([ValidationError("FILE_NOT_FOUND", "file")])
        try:
            return load_workbook(open_source(path, password), read_only=False, data_only=True)
        except InputValidationFailed:
            raise
        except Exception:
            raise InputValidationFailed([ValidationError("FILE_UNREADABLE", "file")]) from None

    # ------------------------------------------------------------------
    def _read_data(self, ws) -> AdapterResult:
        total_row = next((r for r in range(FIRST_DATA_ROW, ws.max_row + 1) if _norm(ws.cell(r, 1).value) == "합계"), None)
        if total_row is None:
            raise InputValidationFailed([ValidationError("TOTAL_ROW_MISSING", "total_row")])
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []
        notes: list[ValidationError] = []
        group: list[dict] = []
        students: list[PaymentRow] = []
        src_minutes = src_amount = 0
        yms: set[tuple[int, int]] = set()

        for r in range(FIRST_DATA_ROW, total_row):
            seq = ws.cell(r, 2).value
            if isinstance(seq, int) and not isinstance(seq, bool):
                rec = self._parse_data_row(ws, r, errors, yms, group[0] if group else None)
                if rec is not None:
                    group.append(rec)
                else:
                    group.append({"bad": True, "row": r})
            elif _norm(ws.cell(r, 7).value) == "소계":
                row = self._close_group(ws, r, group, errors, warnings, notes)
                if row is not None:
                    students.append(row)
                    src_minutes += row.minutes
                    src_amount += row.pay_amount
                group = []
            elif all(_blank(ws.cell(r, c).value) for c in range(1, LAST_COLUMN + 1)):
                errors.append(ValidationError("ROW_BLANK_IN_DATA", "rows", r))
            else:
                errors.append(ValidationError("ROW_NOT_DATA", "rows", r))
        if group:
            errors.append(ValidationError("GROUP_NO_SUBTOTAL", "rows", group[-1]["row"]))
        for r in range(total_row + 1, ws.max_row + 1):
            if any(not _blank(ws.cell(r, c).value) for c in range(1, LAST_COLUMN + 1)):
                errors.append(ValidationError("CONTENT_AFTER_TOTAL", "rows", r))
        if not errors and not students:
            errors.append(ValidationError("NO_DATA_ROWS", "rows"))
        if len(yms) > 1:
            errors.append(ValidationError("MONTH_MIXED", "year_month"))

        totals = None
        if not errors:
            totals = self._compare_totals(ws, total_row, students, errors)
        if errors:
            raise InputValidationFailed(errors)
        (year, month), = yms
        batch = PaymentBatch(program_code=self.PROGRAM_CODE, year=year, month=month, rows=students)
        warnings.sort(key=lambda w: (w.row or 0, w.code))
        notes.sort(key=lambda w: (w.row or 0, w.code))
        return AdapterResult(batch=batch, source_totals=totals, warnings=tuple(warnings), notes=tuple(notes))

    def _parse_data_row(self, ws, r, errors, yms, top=None) -> dict | None:
        failed = False

        def attempt(fn, *a, **kw):
            nonlocal failed
            try:
                return fn(*a, **kw)
            except ValidationError as e:
                errors.append(e.with_row(r))
                failed = True
                return None

        g = lambda col: ws[f"{col}{r}"].value                                      # noqa: E731
        # 한 학생의 행이 둘 이상이면 년월·성명·학번·학과는 첫 행에만 나온다(원본 특성). 둘째 행부터 비어 있으면 첫 행의 값을 쓴다.
        # 첫 행이 이미 오류(top["bad"])면 그 오류만 보고하고 여기서는 추가 오류를 만들지 않는다.
        inherit = lambda col, key: top is not None and _blank(g(col)) and key        # noqa: E731
        if inherit("F", "student_id"):
            student_id = top.get("student_id")
        else:
            student_id = attempt(normalize_identifier, g("F"), "student_id", expected_len=self.student_id_len)
        account = attempt(normalize_account, g("P"))
        minutes = attempt(parse_hours, g("M"))
        amount = attempt(parse_amount, g("N"), "pay_amount")
        ym = top.get("ym") if inherit("D", "ym") else attempt(_parse_ym, g("D"))
        work = _text(g("H"))
        m = _PAREN.search(work) if isinstance(work, str) else None
        rate = self.rates.get(m.group(1).strip()) if m else None
        if rate is None:
            errors.append(ValidationError("WORK_TYPE_UNKNOWN", "work_type", r))
            failed = True
        if minutes is not None and amount is not None and rate is not None and amount * 60 != minutes * rate:
            errors.append(ValidationError("AMOUNT_RATE_MISMATCH", "pay_amount", r))
            failed = True
        carry = False
        mm = _ACT_MONTH.match(work) if isinstance(work, str) else None
        if mm and ym is not None:
            act = int(mm.group(1))
            if not 1 <= act <= 12 or (act > ym[1] and ym[1] not in (1, 2)):
                # 활동월이 지급월보다 늦을 수 있는 경우는 학년도 경계(지급월 1·2월, 전년도 활동분)뿐이다
                errors.append(ValidationError("ACTIVITY_MONTH_INVALID", "work_type", r))
                failed = True
            carry = act != ym[1]
        if failed:
            return None
        yms.add(ym)
        return {"ym": ym, "carry": carry, "row": r, "student_id": student_id,
                "name": top.get("name") if inherit("E", "name") else _text(g("E")),
                "dept": top.get("dept") if inherit("G", "dept") else _text(g("G")), "org": _text(g("I")),
                "bank": _text(g("O")), "account": account, "minutes": minutes, "amount": amount, "rate": rate}

    def _close_group(self, ws, r, group, errors, warnings, notes) -> PaymentRow | None:
        if not group:
            errors.append(ValidationError("SUBTOTAL_WITHOUT_DATA", "rows", r))
            return None
        if any(rec.get("bad") for rec in group):
            return None                                    # 행 오류가 이미 보고되었다
        top = group[0]
        for rec in group[1:]:
            if any(rec[k] != top[k] for k in ("student_id", "name")):
                errors.append(ValidationError("GROUP_STUDENT_MISMATCH", "student_id", rec["row"]))
                return None
        distinct = list(dict.fromkeys(rec["rate"] for rec in group))          # 위(최근) 행부터, 중복 제거
        if len(distinct) > 1:
            notes.append(ValidationError("RATE_MIXED_IN_GROUP", "hourly_rate", r))
        if any(rec["carry"] for rec in group):
            notes.append(ValidationError("CARRYOVER_ROW", "work_type", top["row"]))
        minutes = sum(rec["minutes"] for rec in group)
        amount = sum(rec["amount"] for rec in group)
        try:
            sub_minutes = parse_hours(ws[f"M{r}"].value, "minutes")
            sub_amount = parse_amount(ws[f"N{r}"].value, "amount")
        except ValidationError:
            errors.append(ValidationError("SUBTOTAL_UNREADABLE", "subtotal", r))
            return None
        if sub_minutes != minutes or sub_amount != amount:
            errors.append(ValidationError("SUBTOTAL_MISMATCH", "subtotal", r))
            return None
        if len(group) > 1:
            notes.append(ValidationError("STUDENT_MERGED_ROWS", "rows", top["row"]))
        try:
            return PaymentRow(
                source_row=top["row"], student_id=top["student_id"], name=top["name"], account_no=top["account"],
                bank_name=top["bank"], pay_amount=amount, minutes=minutes, department=top["dept"],
                org_name=top["org"], work_place=top["org"], biz_no="", headcount=1, hourly_rate=top["rate"],
                rate_display=" / ".join(f"{x:,}" for x in distinct) if len(distinct) > 1 else None,
            )
        except ValidationError as e:
            errors.append(e)
            return None

    @staticmethod
    def _compare_totals(ws, total_row, students, errors) -> SourceTotals | None:
        amount = minutes = None
        try:
            amount = parse_amount(ws[f"N{total_row}"].value, "amount")
        except ValidationError:
            errors.append(ValidationError("TOTALS_UNREADABLE", "amount", total_row))
        try:
            minutes = parse_hours(ws[f"M{total_row}"].value, "minutes")
        except ValidationError:
            errors.append(ValidationError("TOTALS_UNREADABLE", "minutes", total_row))
        if amount is not None and amount != sum(s.pay_amount for s in students):
            errors.append(ValidationError("TOTALS_MISMATCH", "amount", total_row))
        if minutes is not None and minutes != sum(s.minutes for s in students):
            errors.append(ValidationError("TOTALS_MISMATCH", "minutes", total_row))
        return None if errors else SourceTotals(amount=amount, minutes=minutes)
