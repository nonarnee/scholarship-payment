"""방식 B TemplateWriter. 서식 보존(FP)과 데이터 일치(DI)를 N=1/32/45/70/120/1000에서 확인한다. 합성 템플릿만 사용."""
import dataclasses
import hashlib
from pathlib import Path

import pytest
from openpyxl import load_workbook

from scholarship_payment.adapters.daechung import DaechungAdapter
from scholarship_payment.config.policy import SYNTHETIC_POLICY, OutputPolicy
from scholarship_payment.core.bank_codes import BankCodeTable
from scholarship_payment.core.normalize import format_minutes
from scholarship_payment.errors import ValidationFailed
from scholarship_payment.validation.validator import ValidatedBatch, ValidatedRow, validate
from scholarship_payment.writers.template_writer import build_workbook

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
LIST = "지급대상자명단(9월)"
NS = [1, 2, 32, 45, 70, 120, 1000]


def sig(c):
    f, fl, b, a = c.font, c.fill, c.border, c.alignment
    fg = (fl.fgColor.type, fl.fgColor.rgb if fl.fgColor.type == "rgb" else fl.fgColor.theme) if fl and fl.fill_type else None
    bd = tuple((getattr(b, s).style if getattr(b, s) else None) for s in ("left", "right", "top", "bottom"))
    return (f.name, f.sz, bool(f.b), fg, bd, a.horizontal, a.vertical, bool(a.wrap_text), c.number_format)


def validated(make_input, n, **kw):
    res = DaechungAdapter().read(make_input(n=n, **kw))
    return validate(res.batch, BankCodeTable.from_workbook(load_workbook(TEMPLATE)))


def build(make_input, n=45, policy=SYNTHETIC_POLICY, base_date=None):
    return build_workbook(validated(make_input, n), TEMPLATE, policy, base_date)


@pytest.fixture(scope="module")
def tpl():
    return load_workbook(TEMPLATE)


# ------------------------------------------------------------------ 구조
@pytest.mark.parametrize("n", NS)
def test_sheets_and_total_row_position(make_input, n):
    wb = build(make_input, n)
    assert wb.sheetnames == [LIST, "WINS", "WRIS", "은행코드"]
    ws = wb[LIST]
    assert ws.cell(5 + n, 1).value is None and ws.cell(4 + n, 1).value == n
    assert ws.max_row == 5 + n
    assert wb["WINS"].max_row == wb["WRIS"].max_row == 1 + n


# ------------------------------------------------------------------ 서식 보존 (FP)
@pytest.mark.parametrize("n", NS)
def test_data_and_total_styles_match_template(make_input, tpl, n):
    wb = build(make_input, n)
    to, ts = wb[LIST], tpl[LIST]
    for i in range(n):
        ref = 5 if i == 0 else 6
        for c in range(1, 18):
            assert sig(to.cell(5 + i, c)) == sig(ts.cell(ref, c)), (i, c)
        assert to.row_dimensions[5 + i].height == 14.1
    for c in range(1, 18):
        assert sig(to.cell(5 + n, c)) == sig(ts.cell(50, c))
    assert to.row_dimensions[5 + n].height == 16.5
    for name, ncol in (("WINS", 9), ("WRIS", 10)):
        so, st = wb[name], tpl[name]
        for i in range(n):
            ref = 2 if i == 0 else 3
            for c in range(1, ncol + 1):
                assert sig(so.cell(2 + i, c)) == sig(st.cell(ref, c)), (name, i, c)
            assert so.row_dimensions[2 + i].height == 14.1


@pytest.mark.parametrize("n", [1, 45, 120])
def test_sheet_level_properties_are_inherited(make_input, tpl, n):
    wb = build(make_input, n)
    for name in (LIST, "WINS", "WRIS"):
        so, st = wb[name], tpl[name]
        assert sorted(map(str, so.merged_cells.ranges)) == sorted(map(str, st.merged_cells.ranges))
        assert {k: v.width for k, v in so.column_dimensions.items()} == {k: v.width for k, v in st.column_dimensions.items()}
        assert (so.page_setup.orientation, so.page_setup.paperSize, so.page_margins.left) == (
            st.page_setup.orientation, st.page_setup.paperSize, st.page_margins.left)
        assert (so.sheet_properties.tabColor and so.sheet_properties.tabColor.rgb) == (st.sheet_properties.tabColor and st.sheet_properties.tabColor.rgb)
        assert so.auto_filter.ref == st.auto_filter.ref
    for r in range(1, 5):
        assert wb[LIST].row_dimensions[r].height == tpl[LIST].row_dimensions[r].height
        assert all(sig(wb[LIST].cell(r, c)) == sig(tpl[LIST].cell(r, c)) for c in range(1, 18))
    assert all(sig(wb["WINS"].cell(1, c)) == sig(tpl["WINS"].cell(1, c)) for c in range(1, 10))


def test_bank_sheet_is_untouched(make_input, tpl):
    wb = build(make_input, 5)
    rows = lambda w: [[c.value for c in r] for r in w["은행코드"].iter_rows()]      # noqa: E731
    assert rows(wb) == rows(tpl)


@pytest.mark.parametrize("n", [1, 45, 120])
def test_conditional_format_covers_exactly_the_data_ids(make_input, tpl, n):
    wb = build(make_input, n)
    last = f"D{4 + n}"
    assert [str(cf.sqref) for cf in wb[LIST].conditional_formatting] == ["D5" if n == 1 else f"D5:{last}"]
    # 템플릿에 규칙이 없는 시트에는 규칙을 새로 만들지 않는다(서식 추가 금지)
    assert [len(list(tpl[s].conditional_formatting)) for s in ("WINS", "WRIS")] == [0, 0]
    assert [len(list(wb[s].conditional_formatting)) for s in ("WINS", "WRIS")] == [0, 0]


def test_no_leftover_cells_below_data(make_input):
    for n in (1, 2, 45):
        wb = build(make_input, n)
        assert not [c for row in wb[LIST].iter_rows(min_row=6 + n) for c in row if c.value is not None]
        for name in ("WINS", "WRIS"):
            assert not [c for row in wb[name].iter_rows(min_row=2 + n) for c in row if c.value is not None]


def test_template_file_is_never_modified(make_input):
    before = hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()
    build(make_input, 70)
    assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == before


# ------------------------------------------------------------------ 데이터 일치 (DI)
@pytest.mark.parametrize("n", [1, 45, 120])
def test_every_value_matches_the_validated_rows(make_input, n):
    v = validated(make_input, n)
    wb = build_workbook(v, TEMPLATE, SYNTHETIC_POLICY)
    L, W, R = wb[LIST], wb["WINS"], wb["WRIS"]
    for i, vr in enumerate(v.rows):
        p, a, b = vr.row, 5 + i, 2 + i
        assert [L.cell(a, c).value for c in range(1, 17)] == [
            i + 1, "9999년09월", p.name, p.student_id, p.department, p.biz_no, p.org_name, p.work_place, p.headcount,
            p.hourly_rate, format_minutes(p.minutes), p.pay_amount, p.bank_name, vr.wins_code, vr.wris_code, p.account_no]
        assert [W.cell(b, c).value for c in range(1, 10)] == [
            "SYN-근로구분", 9999, 9, p.student_id, None, None, p.pay_amount, vr.wins_code, p.account_no]
        assert [R.cell(b, c).value for c in range(1, 11)] == [
            "SYN-GUB-A", "SYN-GUB-B", p.student_id, p.name, p.pay_amount, str(vr.wris_code), p.account_no, p.name, "가상사업(9월)", None]
    t = 5 + n
    assert L[f"L{t}"].value == v.batch.total_amount() == sum(vr.row.pay_amount for vr in v.rows)
    assert L[f"K{t}"].value == format_minutes(v.batch.total_minutes())


def test_amounts_are_int_and_ids_accounts_are_text_cells(make_input):
    wb = build(make_input, 45)
    L, W, R = wb[LIST], wb["WINS"], wb["WRIS"]
    for r in range(5, 50):
        assert type(L[f"L{r}"].value) is int and L[f"L{r}"].data_type == "n"
        assert L[f"D{r}"].data_type == "s" and L[f"P{r}"].data_type == "s" and L[f"F{r}"].data_type == "s"
    for r in range(2, 47):
        assert W[f"D{r}"].data_type == "s" and W[f"I{r}"].data_type == "s" and R[f"C{r}"].data_type == "s" and R[f"G{r}"].data_type == "s"
        assert type(W[f"G{r}"].value) is int and type(R[f"E{r}"].value) is int


def test_leading_zero_student_ids_are_preserved(make_input):
    v = validated(make_input, 3, id_mode="text")
    wb = build_workbook(v, TEMPLATE, SYNTHETIC_POLICY)
    assert [wb[LIST][f"D{r}"].value for r in (5, 6, 7)] == ["00000001", "00000002", "00000003"]
    assert wb["WINS"]["D2"].value == "00000001" and wb["WRIS"]["C4"].value == "00000003"


def test_no_formulas_anywhere_in_data_areas(make_input):
    wb = build(make_input, 45)
    for name in (LIST, "WINS", "WRIS"):
        assert not [c.coordinate for row in wb[name].iter_rows() for c in row if c.data_type == "f"]


def test_formula_like_text_is_forced_to_text_even_if_validation_is_bypassed(make_input):
    v = validated(make_input, 2)
    r0 = v.rows[0]
    bad = ValidatedRow(row=dataclasses.replace(r0.row, name="=1+1", account_no="@SUM(1)"), wins_code=r0.wins_code, wris_code=r0.wris_code)
    wb = build_workbook(ValidatedBatch(batch=v.batch, rows=(bad, v.rows[1])), TEMPLATE, SYNTHETIC_POLICY)
    for coord in ("C5", "P5"):
        assert wb[LIST][coord].data_type == "s"
    assert wb["WRIS"]["D2"].data_type == "s" and wb["WRIS"]["H2"].data_type == "s" and wb["WINS"]["I2"].data_type == "s"


# ------------------------------------------------------------------ 제목·기준일·정책
def test_title_sheet_name_and_policy_constants(make_input):
    policy = OutputPolicy(list_title="가상 {year}-{month}", wins_work_name="W", wris_gub_a="GA", wris_gub_b="GB", remit_info="R{month}")
    wb = build(make_input, 2, policy=policy)
    assert wb[LIST]["A1"].value == "가상 9999-9"
    assert wb["WINS"]["A2"].value == "W" and wb["WRIS"]["A2"].value == "GA" and wb["WRIS"]["B3"].value == "GB" and wb["WRIS"]["I2"].value == "R9"


def test_base_date_only_written_when_given(make_input, tpl):
    assert build(make_input, 2)[LIST]["Q2"].value == tpl[LIST]["Q2"].value
    assert build(make_input, 2, base_date="2099.10.07")[LIST]["Q2"].value == "*기준 : 2099.10.07"


# ------------------------------------------------------------------ 템플릿 레이아웃 지문
def _bad_template(tmp_path, mutate):
    wb = load_workbook(TEMPLATE)
    mutate(wb)
    p = tmp_path / "bad_template.xlsx"
    wb.save(p)
    return p


@pytest.mark.parametrize("mutate", [
    lambda wb: setattr(wb["WINS"], "title", "다른시트"),
    lambda wb: wb.remove(wb["은행코드"]),
    lambda wb: wb.create_sheet("끼어든시트"),
    lambda wb: wb["WINS"].__setitem__("D1", "학번2"),
    lambda wb: wb["WRIS"].__setitem__("A1", "다른머리글"),
    lambda wb: wb[LIST].__setitem__("C3", "이름"),
    lambda wb: wb[LIST].__setitem__("A6", None),
])
def test_unexpected_template_is_rejected(make_input, tmp_path, mutate):
    v = validated(make_input, 2)
    with pytest.raises(ValidationFailed) as ei:
        build_workbook(v, _bad_template(tmp_path, mutate), SYNTHETIC_POLICY)
    assert all(e.code == "TEMPLATE_LAYOUT" for e in ei.value.errors)
