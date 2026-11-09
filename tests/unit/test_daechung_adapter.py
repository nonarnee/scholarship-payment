"""DaechungAdapter 시험. 입력은 합성 생성기가 만든 '재단 다운로드 원본과 같은 형태'의 파일뿐이다.
기준: DI-01/02(입력 측), DI-03/07(합계 대조), DI-04, DI-10(원본 불변), DI-13(오류에 값 미노출), 헤더 변경 시 오인식 금지.
"""
import hashlib
import os

import pytest

from scholarship_payment.adapters.base import AdapterResult, InputValidationFailed, SourceTotals
from scholarship_payment.adapters.daechung import DaechungAdapter

TOTAL_ROW = lambda n: 3 + n  # noqa: E731


def read(path):
    return DaechungAdapter().read(path)


def errors_of(path):
    with pytest.raises(InputValidationFailed) as ei:
        read(path)
    return ei.value


def triples(exc):
    return {(e.code, e.field, e.row) for e in exc.errors}


def codes(exc):
    return {e.code for e in exc.errors}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ 정상 읽기
def test_reads_original_format_45_rows(fixture_45, synthetic):
    res = read(fixture_45)
    assert isinstance(res, AdapterResult)
    recs = synthetic.records(45)
    b = res.batch
    assert b.program_code == "DAECHUNG" and (b.year, b.month) == (9999, 9)
    assert len(b.rows) == 45
    assert res.source_totals == SourceTotals(amount=sum(r["pay"] for r in recs), minutes=sum(r["minutes"] for r in recs))
    assert b.total_amount() == res.source_totals.amount and b.total_minutes() == res.source_totals.minutes
    for row, rec in zip(b.rows, recs):
        assert row.source_row == 2 + rec["seq"]
        assert (row.student_id, row.name, row.account_no, row.bank_name) == (rec["sid"], rec["name"], rec["acct"], rec["bank"])
        assert (row.pay_amount, row.minutes, row.hourly_rate, row.headcount) == (rec["pay"], rec["minutes"], rec["rate"], rec["heads"])
        assert (row.department, row.org_name, row.work_place, row.biz_no) == (rec["dept"], rec["org"], rec["place"], rec["biz"])
    assert res.warnings == ()


def test_numeric_student_id_cells_become_strings(fixture_45):
    ids = [r.student_id for r in read(fixture_45).batch.rows]
    assert all(type(i) is str and len(i) == 8 for i in ids)


def test_text_student_ids_keep_leading_zeros(fixture_3_text_ids):
    ids = [r.student_id for r in read(fixture_3_text_ids).batch.rows]
    assert ids == ["00000001", "00000002", "00000003"]


@pytest.mark.parametrize("n", [1, 32, 70, 120, 1000])
def test_variable_number_of_rows(make_input, synthetic, n):
    res = read(make_input(n=n))
    recs = synthetic.records(n)
    assert len(res.batch.rows) == n
    assert res.batch.total_amount() == sum(r["pay"] for r in recs) == res.source_totals.amount
    assert res.batch.total_minutes() == sum(r["minutes"] for r in recs) == res.source_totals.minutes


def test_original_file_is_never_modified(fixture_45):
    before, mtime = sha(fixture_45), os.stat(fixture_45).st_mtime_ns
    read(fixture_45)
    assert sha(fixture_45) == before and os.stat(fixture_45).st_mtime_ns == mtime


def test_empty_string_cells_in_original_do_not_matter(make_input):
    # 실제 원본의 B·V·X 열과 합계행 일부는 None 이 아니라 빈 문자열이다. make_input 은 이를 그대로 재현한다.
    assert len(read(make_input(n=3)).batch.rows) == 3


# ------------------------------------------------------------------ 필터 금지(결정): A·B·V·W·X 열은 읽지 않는다
def test_ignored_columns_do_not_change_the_result(fixture_45, make_input):
    def mutate(ws):
        for r in range(3, 48):
            ws[f"A{r}"], ws[f"B{r}"], ws[f"V{r}"], ws[f"W{r}"], ws[f"X{r}"] = 5, "불일치", "9999.9.9", "처리완료", "메모"
    assert read(make_input(mutate=mutate)).batch == read(fixture_45).batch


# ------------------------------------------------------------------ 파일·시트·레이아웃
def test_missing_file(tmp_path):
    assert triples(errors_of(tmp_path / "없는파일.xlsx")) == {("FILE_NOT_FOUND", "file", None)}


def test_not_an_excel_file(tmp_path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"not an excel file")
    assert triples(errors_of(p)) == {("FILE_UNREADABLE", "file", None)}


def test_sheet_name_is_not_a_criterion(make_input, fixture_45):
    """시트명은 판단 기준이 아니다: 이름이 달라도 구조가 맞으면 같은 결과다(자세한 경계는 test_source_sheet_detection.py)."""
    assert read(make_input(mutate=lambda ws: setattr(ws, "title", "다른시트"))).batch == read(fixture_45).batch


def test_changed_header_is_rejected_not_guessed(make_input):
    exc = errors_of(make_input(mutate=lambda ws: ws.__setitem__("F1", "학번2")))
    assert ("LAYOUT_HEADER", "F1", None) in triples(exc)
    assert all(c.startswith("LAYOUT_") for c in codes(exc))        # 레이아웃이 틀리면 데이터를 해석하지 않는다


def test_swapped_columns_are_rejected(make_input):
    def mutate(ws):
        ws["E1"], ws["F1"] = ws["F1"].value, ws["E1"].value
    exc = errors_of(make_input(mutate=mutate))
    assert {("LAYOUT_HEADER", "E1", None), ("LAYOUT_HEADER", "F1", None)} <= triples(exc)


def test_header_whitespace_differences_are_tolerated(make_input):
    assert len(read(make_input(n=2, mutate=lambda ws: ws.__setitem__("F1", " 학 번 "))).batch.rows) == 2


def test_missing_merge_is_rejected(make_input):
    exc = errors_of(make_input(mutate=lambda ws: ws.unmerge_cells("O1:Q1")))
    assert ("LAYOUT_MERGE", "O1:Q1", None) in triples(exc)


# ------------------------------------------------------------------ 데이터 행·합계행
def test_blank_row_inside_data_is_rejected(make_input):
    def mutate(ws):
        for c in ws[10]:
            c.value = None
    assert ("ROW_BLANK_IN_DATA", "rows", 10) in triples(errors_of(make_input(mutate=mutate)))


def test_non_data_row_inside_data_is_rejected(make_input):
    exc = errors_of(make_input(mutate=lambda ws: ws.__setitem__("C12", "메모")))
    assert ("ROW_NOT_DATA", "rows", 12) in triples(exc)


def test_missing_total_row_is_rejected(make_input):
    def mutate(ws):
        ws.unmerge_cells("A48:E48")       # 병합 셀은 값을 직접 지울 수 없다
        ws.unmerge_cells("F48:L48")
        for c in ws[48]:
            c.value = None
    assert ("TOTAL_ROW_MISSING", "total_row", None) in triples(errors_of(make_input(mutate=mutate)))


def test_content_after_total_row_is_rejected(make_input):
    exc = errors_of(make_input(n=5, mutate=lambda ws: ws.__setitem__("E10", "가상추가")))
    assert ("CONTENT_AFTER_TOTAL", "rows", 10) in triples(exc)


def test_no_data_rows_is_blocked_pending_policy(make_input):
    # 대상자 0명 정책은 OPEN M10(임시: 안내 후 중단). 배치를 만들 수 없으므로 차단한다.
    assert triples(errors_of(make_input(n=0))) == {("NO_DATA_ROWS", "rows", None)}


# ------------------------------------------------------------------ 합계 대조 (DI-03, DI-07)
def test_amount_total_mismatch(make_input):
    exc = errors_of(make_input(mutate=lambda ws: ws.__setitem__("O48", ws["O48"].value + 1)))
    assert triples(exc) == {("TOTALS_MISMATCH", "amount", 48)}


def test_minutes_total_mismatch(make_input):
    exc = errors_of(make_input(mutate=lambda ws: ws.__setitem__("M48", "1시간")))
    assert triples(exc) == {("TOTALS_MISMATCH", "minutes", 48)}


def test_unreadable_total_cells(make_input):
    def mutate(ws):
        ws["O48"], ws["M48"] = "abc", "많음"
    assert triples(errors_of(make_input(mutate=mutate))) == {("TOTALS_UNREADABLE", "amount", 48), ("TOTALS_UNREADABLE", "minutes", 48)}


# ------------------------------------------------------------------ 년월
def test_mixed_months_rejected(make_input):
    exc = errors_of(make_input(mutate=lambda ws: ws.__setitem__("D5", "9999년10월")))
    assert ("MONTH_MIXED", "year_month", None) in triples(exc)


@pytest.mark.parametrize("bad", ["99990901", "9999년13월", "9999년00월", "9999-09", 99990901, None, ""])
def test_year_month_format_is_strict(make_input, bad):
    exc = errors_of(make_input(mutate=lambda ws: ws.__setitem__("D5", bad)))
    assert ("YEARMONTH_FORMAT", "year_month", 5) in triples(exc)


# ------------------------------------------------------------------ 행 단위 오류는 모아서 보고(값 없이)
def test_row_errors_are_collected_with_row_numbers(make_input):
    def mutate(ws):
        ws["U5"] = 12345            # 숫자 계좌
        ws["M6"] = "1.5시간"        # 시간 표기
        ws["O7"] = 1.5              # 소수 금액
        ws["F8"] = 123              # 학번 길이
        ws["E9"] = ""               # 필수값 공란
    assert triples(errors_of(make_input(mutate=mutate))) == {
        ("ACCOUNT_NOT_TEXT", "account_no", 5), ("HOURS_FORMAT", "hours", 6), ("AMOUNT_INVALID", "pay_amount", 7),
        ("ID_LENGTH", "student_id", 8), ("FIELD_EMPTY", "name", 9),
    }


def test_error_report_never_contains_input_values(make_input):
    def mutate(ws):
        ws["E5"], ws["U5"] = "가상비밀이름", 7777777
        ws["F6"] = "비밀학번"
    exc = errors_of(make_input(mutate=mutate))
    text = str(exc) + repr(exc) + " ".join(str(e) + repr(e) for e in exc.errors)
    for secret in ("가상비밀이름", "7777777", "비밀학번"):
        assert secret not in text
    assert "row 5" in str(exc)


# ------------------------------------------------------------------ 경고(차단 아님)와 판단하지 않는 항목
def test_warnings_do_not_block(make_input):
    def mutate(ws):
        ws["P5"] = ws["P5"].value + 1       # 교부금 + 이자 != 재단 장학금 계
        ws["R6"] = 100                      # 대학 자체 장학금 존재
        ws["Q7"] = "x"                      # 읽을 수 없는 보조 금액
    res = read(make_input(mutate=mutate))
    got = {(w.code, w.field, w.row) for w in res.warnings}
    assert got == {("SPLIT_AMOUNT_MISMATCH", "grant_interest", 5), ("UNIVERSITY_FUNDS_PRESENT", "university_funds", 6),
                   ("SPLIT_AMOUNT_UNREADABLE", "grant_interest", 7)}
    assert len(res.batch.rows) == 45


def test_duplicate_ids_and_zero_amounts_are_not_judged_here(make_input):
    # 중복 학번·0원 처리는 업무 규칙(OPEN H5)이라 Adapter 가 판단하지 않는다. 합계행은 맞춰 둔다.
    def mutate(ws):
        paid = ws["O7"].value
        ws["F7"] = ws["F5"].value       # 중복 학번(연속하지 않은 행: 연속 행은 이월로 합산한다)
        ws["O7"] = 0                    # 0원
        ws["O48"] = ws["O48"].value - paid
    rows = read(make_input(mutate=mutate)).batch.rows
    assert len(rows) == 45
    assert rows[4].student_id == rows[2].student_id          # 행 7 == 행 5
    assert rows[4].pay_amount == 0                           # 행 7


# ---- 이월 2행 학생(대청교·AI멘토링 공통, M29·M30) ------------------------------------------------
PREV = "9999년08월"
CARRY = ((2, 8 * 60, PREV), (3, 90, PREV))          # 2·3번째 대상자 아래에 이월 행


def test_carryover_rows_are_merged_into_one_student_row_using_the_top_row(make_input):
    res = read(make_input(n=4, extra=CARRY))
    assert len(res.batch.rows) == 4 and (res.batch.year, res.batch.month) == (9999, 9)
    base = DaechungAdapter().read(make_input(n=4)).batch.rows
    for k, add in ((1, 8 * 60), (2, 90)):
        got = res.batch.rows[k]
        assert got.minutes == base[k].minutes + add and got.pay_amount == base[k].pay_amount + add * 1000 // 60
        assert got.source_row == (4, 6)[k - 1] and got.student_id == base[k].student_id    # 맨 위 행 기준
        assert got.headcount == base[k].headcount
    assert res.batch.rows[0] == base[0] and res.batch.rows[3].minutes == base[3].minutes


def test_carryover_is_a_note_not_a_warning(make_input):
    res = read(make_input(n=4, extra=CARRY))
    assert [w.code for w in res.warnings] == []
    assert {(n.code, n.row) for n in res.notes} == {("CARRYOVER_ROW", 5), ("STUDENT_MERGED_ROWS", 4),
                                                    ("CARRYOVER_ROW", 7), ("STUDENT_MERGED_ROWS", 6)}


def test_carryover_row_with_a_later_month_than_the_top_row_is_blocked(make_input):
    exc = errors_of(make_input(n=3, extra=((2, 60, "9999년10월"),)))
    assert ("CARRYOVER_MONTH_INVALID", "year_month", 5) in triples(exc)


def test_different_months_between_students_are_still_blocked(make_input):
    assert "MONTH_MIXED" in codes(errors_of(make_input(n=3, mutate=lambda ws: ws.__setitem__("D4", PREV))))


@pytest.mark.parametrize("col,value,code", [("E", "다른사람", "GROUP_STUDENT_MISMATCH"), ("U", "999-999-1", "GROUP_ACCOUNT_MISMATCH"),
                                            ("T", "다른은행", "GROUP_ACCOUNT_MISMATCH")])
def test_rows_of_one_student_must_have_the_same_person_and_account(make_input, col, value, code):
    exc = errors_of(make_input(n=3, extra=((2, 60, PREV),), mutate=lambda ws: ws.__setitem__(f"{col}5", value)))
    assert (code, 5) in {(e.code, e.row) for e in exc.errors}


def test_non_adjacent_duplicate_student_is_not_merged(make_input):
    def mut(ws):
        for c in "EFGHIJTU":
            ws[f"{c}5"] = ws[f"{c}3"].value
    res = read(make_input(n=3, mutate=mut))
    assert len(res.batch.rows) == 3 and res.batch.rows[0].student_id == res.batch.rows[2].student_id    # Validator 가 중복으로 차단한다


def test_merged_totals_still_match_the_source_total_row(make_input):
    assert read(make_input(n=4, extra=CARRY)).source_totals.amount == sum(r.pay_amount for r in read(make_input(n=4, extra=CARRY)).batch.rows)


# ---- AI멘토링: 시급 고정 -------------------------------------------------------------------------
def ai():
    return DaechungAdapter(program_code="AI", fixed_rate=1000)


def test_ai_uses_its_own_program_code_and_accepts_the_fixed_rate(make_input):
    assert ai().read(make_input(n=3, extra=CARRY[:1])).batch.program_code == "AI"


def test_ai_blocks_a_row_whose_rate_is_not_the_fixed_rate(make_input):
    with pytest.raises(InputValidationFailed) as ei:
        ai().read(make_input(n=3, mutate=lambda ws: ws.__setitem__("L4", 2000)))
    assert ("RATE_NOT_FIXED", 4) in {(e.code, e.row) for e in ei.value.errors}


def test_ai_blocks_when_amount_differs_from_rate_times_total_hours(make_input):
    def mut(ws):
        for c in "NOP":
            ws[f"{c}4"] = ws[f"{c}4"].value + 1
        for c in "NOP":
            ws[f"{c}6"] = ws[f"{c}6"].value + 1           # 합계행도 맞춰 합계 불일치와 구분
    with pytest.raises(InputValidationFailed) as ei:
        ai().read(make_input(n=3, mutate=mut))
    assert "AMOUNT_RATE_MISMATCH" in {e.code for e in ei.value.errors}


def test_daechung_does_not_apply_the_ai_rate_rule(make_input):
    assert DaechungAdapter().read(make_input(n=3, mutate=lambda ws: ws.__setitem__("L4", 2000))).batch.rows
