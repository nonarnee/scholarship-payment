"""다문화 Adapter: 학생 묶음/소계, 시급표 검사, 합계 대조, 레이아웃 지문. 합성 입력만 사용."""
import pytest

from scholarship_payment.adapters.base import InputValidationFailed
from scholarship_payment.adapters.multicultural import MulticulturalAdapter

RATES = {"가상A": 1000, "가상B": 1500}


def read(path, rates=RATES):
    return MulticulturalAdapter(rates).read(path)


def fail(path, rates=RATES):
    with pytest.raises(InputValidationFailed) as e:
        read(path, rates)
    return [(x.code, x.row) for x in e.value.errors]


def two_orgs(mk):
    st = mk.mc_students(3)
    st[1]["rows"] = [("가상기관최근", "가상B", 5 * 60), ("가상기관이전", "가상A", 6 * 60 + 30)]
    return st


def test_one_row_per_student(make_mc_input, synthetic):
    res = read(make_mc_input(n=5))
    rows = res.batch.rows
    assert len(rows) == 5 and res.batch.program_code == "MULTICULTURAL" and (res.batch.year, res.batch.month) == (9999, 9)
    st = synthetic.mc_students(5)
    for r, s in zip(rows, st):
        org, wk, m = s["rows"][0]
        assert (r.student_id, r.name, r.org_name, r.work_place, r.minutes) == (s["sid"], s["name"], org, org, m)
        assert r.pay_amount == RATES[wk] * m // 60 and r.hourly_rate == RATES[wk] and r.biz_no == "" and r.headcount == 1
    assert res.source_totals.amount == sum(r.pay_amount for r in rows) and res.source_totals.minutes == sum(r.minutes for r in rows)


def test_multiple_orgs_are_merged_using_the_top_row(make_mc_input, synthetic):
    res = read(make_mc_input(students=two_orgs(synthetic)))
    assert len(res.batch.rows) == 3
    r = res.batch.rows[1]
    assert r.org_name == "가상기관최근" and r.work_place == "가상기관최근"           # 위의 행 = 최근 활동기관
    assert r.minutes == 11 * 60 + 30 and r.pay_amount == 1500 * 5 + 1000 * 6 + 500   # 합계
    assert r.hourly_rate == 1500 and r.source_row == 5                              # 맨 위 행의 시급, 맨 위 행 번호
    assert ("STUDENT_MERGED_ROWS", 5) in [(w.code, w.row) for w in res.warnings]
    assert "RATE_MIXED_IN_GROUP" in [w.code for w in res.warnings]


def test_unknown_work_type_is_blocked(make_mc_input):
    assert fail(make_mc_input(n=3), {"가상A": 1000}) == [("WORK_TYPE_UNKNOWN", 7)]


def test_rates_are_required(make_mc_input):
    assert fail(make_mc_input(n=2), {}) == [("POLICY_RATES_MISSING", None)]


def test_amount_must_match_hours_times_rate(make_mc_input):
    # 데이터 행 3의 금액을 바꾸면 시간×시급 불일치 (소계·합계가 맞아도 차단)
    codes = fail(make_mc_input(n=2, mutate=lambda ws: ws.__setitem__("N3", ws["N3"].value + 1)))
    assert ("AMOUNT_RATE_MISMATCH", 3) in codes


def test_rate_comes_from_the_policy_table_not_calculation(make_mc_input):
    assert fail(make_mc_input(n=2), {"가상A": 1001, "가상B": 1500}) == [("AMOUNT_RATE_MISMATCH", 3), ("AMOUNT_RATE_MISMATCH", 5)]


def test_subtotal_must_match(make_mc_input):
    assert ("SUBTOTAL_MISMATCH", 4) in fail(make_mc_input(n=2, mutate=lambda ws: ws.__setitem__("N4", ws["N4"].value + 10)))


def test_total_row_must_match(make_mc_input):
    codes = fail(make_mc_input(n=2, mutate=lambda ws: ws.__setitem__("N7", ws["N7"].value + 1)))
    assert ("TOTALS_MISMATCH", 7) in codes


def test_group_without_subtotal_is_blocked(make_mc_input, synthetic):
    def mut(ws):
        ws["G4"] = None          # 소계 표시 제거 -> 소계가 아닌 행
    assert ("ROW_NOT_DATA", 4) in fail(make_mc_input(n=2, mutate=mut))


def test_students_in_one_group_must_be_the_same_person(make_mc_input, synthetic):
    st = two_orgs(synthetic)
    def mut(ws):
        ws["F6"] = "90999999"
    assert ("GROUP_STUDENT_MISMATCH", 6) in fail(make_mc_input(students=st, mutate=mut))


def test_mixed_months_are_blocked(make_mc_input):
    def mut(ws):
        ws["D5"] = "9999-09"
        ws["D3"] = "9999-10"
    assert ("MONTH_MIXED", None) in fail(make_mc_input(n=2, mutate=mut))


@pytest.mark.parametrize("bad", ["9999년09월", "9999-13", "", None])
def test_year_month_format(make_mc_input, bad):
    assert ("YEARMONTH_FORMAT", 3) in fail(make_mc_input(n=1, mutate=lambda ws: ws.__setitem__("D3", bad)))


def test_student_id_must_have_8_chars(make_mc_input):
    assert ("ID_LENGTH", 3) in fail(make_mc_input(n=1, mutate=lambda ws: ws.__setitem__("F3", "2023")))


@pytest.mark.parametrize("coord,value", [("B1", "다른"), ("N1", "금액"), ("I2", "기관")])
def test_layout_fingerprint(make_mc_input, coord, value):
    assert any(c == "LAYOUT_HEADER" for c, _ in fail(make_mc_input(n=1, mutate=lambda ws: ws.__setitem__(coord, value))))


def test_layout_merge_fingerprint(make_mc_input):
    assert any(c == "LAYOUT_MERGE" for c, _ in fail(make_mc_input(n=1, mutate=lambda ws: ws.unmerge_cells("H1:L1"))))


def test_wrong_sheet_and_missing_total(make_mc_input):
    assert fail(make_mc_input(n=1, mutate=lambda ws: setattr(ws, "title", "다른"))) == [("SHEET_MISSING", None)]
    assert fail(make_mc_input(n=1, mutate=lambda ws: ws.__setitem__("A5", "x"))) == [("TOTAL_ROW_MISSING", None)]


def test_content_after_total_and_blank_row(make_mc_input):
    assert ("CONTENT_AFTER_TOTAL", 6) in fail(make_mc_input(n=1, mutate=lambda ws: ws.__setitem__("E6", "x")))


def test_errors_never_contain_values(make_mc_input):
    with pytest.raises(InputValidationFailed) as e:
        read(make_mc_input(n=2, mutate=lambda ws: ws.__setitem__("N3", 7)))
    text = str(e.value) + repr(e.value)
    assert "가상001" not in text and "90000001" not in text and "000-000-" not in text


def test_mixed_rates_are_displayed_top_first_and_same_rates_stay_numeric(make_mc_input, synthetic):
    r = read(make_mc_input(students=two_orgs(synthetic))).batch.rows
    assert r[1].rate_display == "1,500 / 1,000" and r[1].hourly_rate == 1500 and r[0].rate_display is None
    st = synthetic.mc_students(1)
    st[0]["rows"] = [("가상기관X", "가상A", 3 * 60), ("가상기관Y", "가상A", 4 * 60)]
    assert read(make_mc_input(students=st)).batch.rows[0].rate_display is None


def _set_work(ws, coord, text):
    ws[coord] = text


def test_carryover_activity_month_is_a_warning_not_an_error(make_mc_input):
    # 4월 활동분이 9월에 지급되는 이월 행: 근무형태 앞 월이 지급월과 다르다
    res = read(make_mc_input(n=2, mutate=lambda ws: _set_work(ws, "H3", "04월 방문(가상A)")))
    assert ("CARRYOVER_ROW", 3) in [(w.code, w.row) for w in res.warnings]
    assert read(make_mc_input(n=2)).warnings == ()


def test_activity_month_after_payment_month_is_blocked_except_at_school_year_boundary(make_mc_input):
    assert ("ACTIVITY_MONTH_INVALID", 3) in fail(make_mc_input(n=1, mutate=lambda ws: _set_work(ws, "H3", "11월 방문(가상A)")))
    assert ("ACTIVITY_MONTH_INVALID", 3) in fail(make_mc_input(n=1, mutate=lambda ws: _set_work(ws, "H3", "13월 방문(가상A)")))

    def jan(ws):                       # 지급월 1월: 전년도 11월 활동분이 지급될 수 있다
        ws["D3"] = "9999-01"
        ws["H3"] = "11월 방문(가상A)"
    res = read(make_mc_input(n=1, mutate=jan))
    assert (res.batch.year, res.batch.month) == (9999, 1) and [w.code for w in res.warnings] == ["CARRYOVER_ROW"]


def test_work_type_without_a_month_prefix_is_still_accepted_for_the_rate(make_mc_input):
    assert read(make_mc_input(n=1, mutate=lambda ws: _set_work(ws, "H3", "방문(가상A)"))).batch.rows
