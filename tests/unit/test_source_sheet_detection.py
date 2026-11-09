"""재단 원본의 데이터 시트 자동 탐색: 시트명은 판단 기준이 아니다. 머리글(값과 위치)·병합 구조가 일치하는 시트가 **정확히 1개**일 때만 쓴다.
후보가 없으면 구조 오류, 2개 이상이면 모호한 입력으로 차단한다. 시트명을 추정하거나 첫 시트를 무조건 쓰지 않는다. 완전 합성 입력만 쓴다.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference

from scholarship_payment import __main__ as cli
from scholarship_payment.adapters.base import InputValidationFailed
from scholarship_payment.adapters.daechung import DaechungAdapter
from scholarship_payment.adapters.multicultural import MulticulturalAdapter
from scholarship_payment.app.controller import run_conversion
from scholarship_payment.app.convert import convert
from xlsx_dump import diff

from test_golden_equivalence import BASE_DATE, CASES, GOLDEN_DIR, TEMPLATE, build_case, load_golden, snapshot

RATES = {"가상A": 1000, "가상B": 1500}
MARK = "가상시트-비공개-QZ"                       # 오류·repr 에 나오면 안 되는 시트명


# ---------------------------------------------------------------- 도구
def reshape(src, dst, fn):
    """저장된 합성 입력을 다시 열어 시트 구성을 바꾼다(데이터 시트는 항상 첫 시트로 시작). 파일 내용은 그대로이고 시트만 바뀐다."""
    wb = load_workbook(src)
    fn(wb)
    wb.save(dst)
    return dst


def guide_sheet(wb, title="안내", index=None):
    """사업 양식과 무관한 안내 시트. 학번·성명·합계 같은 낱말은 일부러 넣는다(낱말만으로는 일치 판정을 하지 않는다)."""
    ws = wb.create_sheet(title, index)
    for i, word in enumerate(["순번", "년월", "성명", "학번", "학과", "합계", "소계", "월별지급승인", "월별지급부현황"], 1):
        ws.cell(i, 1, word)
        ws.cell(1, i + 1, word)
    return ws


def chart_sheet(wb, title="차트", index=None):
    """실제 차트가 있는 차트 시트(내용이 빈 차트 시트는 openpyxl 이 다시 읽지 못한다). 차트 시트는 셀이 없어 데이터 시트 후보가 아니다."""
    cs = wb.create_chartsheet(title, index)
    data = wb.worksheets[0]
    chart = BarChart()
    chart.add_data(Reference(data, min_col=3, min_row=3, max_row=4))
    cs.add_chart(chart)
    return cs


def partial_header_sheet(wb, title, header_cells):
    """데이터 시트의 머리글 일부만 같은 위치에 가진 시트(병합 없음)."""
    ws = wb.create_sheet(title)
    for coord, text in header_cells.items():
        ws[coord] = text
    return ws


@pytest.fixture(params=["daechung", "ai", "multicultural"])
def case(request, make_input, make_mc_input, tmp_path):
    if request.param == "multicultural":
        path, factory, header = make_mc_input(n=4), (lambda: MulticulturalAdapter(RATES)), {"B1": "순번", "E1": "성명", "F1": "학번"}
    elif request.param == "ai":
        path, factory, header = make_input(n=5), (lambda: DaechungAdapter(program_code="AI", fixed_rate=1000)), {"C1": "순번", "E1": "성명", "F1": "학번"}
    else:
        path, factory, header = make_input(n=5), (lambda: DaechungAdapter()), {"C1": "순번", "E1": "성명", "F1": "학번"}
    counter = {"n": 0}

    def make(fn):
        counter["n"] += 1
        return reshape(path, tmp_path / f"shaped_{counter['n']}.xlsx", fn)

    return SimpleNamespace(name=request.param, path=path, read=lambda p: factory().read(p), header=header, make=make, factory=factory)


def baseline(case):
    r = case.read(case.path)
    return r.batch, r.source_totals, r.warnings, r.notes


def same_result(case, path):
    r = case.read(path)
    assert (r.batch, r.source_totals, r.warnings, r.notes) == baseline(case)


def failure(case, path):
    with pytest.raises(InputValidationFailed) as e:
        case.read(path)
    return e.value


def triples(exc):
    return {(x.code, x.field, x.row) for x in exc.errors}


# ---------------------------------------------------------------- 정상: 시트명·구성이 달라도 같은 결과
def test_original_sheet_name_still_works_and_is_the_baseline(case):
    r = case.read(case.path)
    assert len(r.batch.rows) > 0 and r.source_totals.amount > 0


@pytest.mark.parametrize("title", ["Sheet1", "임의의 시트", "월별지급 2026-09", "x", "원본(재단)"])
def test_any_sheet_name_gives_the_same_result(case, title):
    def rename(wb):
        wb.worksheets[0].title = title
    same_result(case, case.make(rename))


def test_guide_sheet_added_before_the_data_sheet(case):
    same_result(case, case.make(lambda wb: guide_sheet(wb, "안내", 0)))


def test_unneeded_sheets_added_after_the_data_sheet(case):
    def add(wb):
        guide_sheet(wb, "뒤1")
        guide_sheet(wb, "뒤2")
    same_result(case, case.make(add))


def test_sheets_before_and_after_and_a_renamed_data_sheet(case):
    def add(wb):
        wb.worksheets[0].title = "데이터"
        guide_sheet(wb, "앞", 0)
        guide_sheet(wb, "뒤")
    same_result(case, case.make(add))


def test_the_data_sheet_can_be_last_and_the_first_sheet_is_never_assumed(case):
    def move_last(wb):
        ws = wb.worksheets[0]
        guide_sheet(wb, "앞1", 0)
        guide_sheet(wb, "앞2", 1)
        wb.move_sheet(ws, offset=len(wb.worksheets) - 1 - wb.worksheets.index(ws))
        assert wb.worksheets[-1] is ws
    same_result(case, case.make(move_last))


def test_a_sheet_with_only_some_matching_headers_is_not_a_candidate(case):
    def add(wb):
        partial_header_sheet(wb, "일부만", case.header)           # 같은 위치에 순번·성명·학번만 있다
        guide_sheet(wb, "안내", 0)
    same_result(case, case.make(add))


def test_the_old_sheet_name_is_not_trusted_either(case):
    """옛 시트명을 단 가짜 시트가 앞에 있어도, 구조가 맞는 시트를 쓴다."""
    old = "월별지급부현황" if case.name == "multicultural" else "월별지급승인"

    def add(wb):
        real = wb.worksheets[0]
        real.title = "실제 데이터"
        decoy = wb.create_sheet(old, 0)
        decoy["A1"] = "옛 이름만 같고 내용은 다르다"
    same_result(case, case.make(add))


def test_a_chart_sheet_is_not_a_candidate(case):
    same_result(case, case.make(lambda wb: chart_sheet(wb, "차트", 0)))


def test_hidden_helper_sheets_that_do_not_match_are_ignored(case):
    def add(wb):
        guide_sheet(wb, "숨김").sheet_state = "hidden"
    same_result(case, case.make(add))


def test_reading_never_modifies_the_file(case):
    p = case.make(lambda wb: guide_sheet(wb, "안내", 0))
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    case.read(p)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before


# ---------------------------------------------------------------- 모호: 구조가 같은 시트가 둘 이상
def test_two_matching_sheets_are_blocked_as_ambiguous(case):
    def dup(wb):
        wb.copy_worksheet(wb.worksheets[0]).title = "복사본"
    exc = failure(case, case.make(dup))
    assert triples(exc) == {("SHEET_AMBIGUOUS", "sheet", None)}


def test_ambiguity_does_not_depend_on_names_or_order_and_counts_hidden_sheets(case):
    def dup(wb):
        first = wb.worksheets[0]
        first.title = "A"
        copy = wb.copy_worksheet(first)
        copy.title = "B"
        copy.sheet_state = "hidden"
        guide_sheet(wb, "안내", 0)
    assert triples(failure(case, case.make(dup))) == {("SHEET_AMBIGUOUS", "sheet", None)}


def test_three_matching_sheets_are_also_ambiguous(case):
    def dup(wb):
        wb.copy_worksheet(wb.worksheets[0]).title = "복사1"
        wb.copy_worksheet(wb.worksheets[0]).title = "복사2"
    assert triples(failure(case, case.make(dup))) == {("SHEET_AMBIGUOUS", "sheet", None)}


# ---------------------------------------------------------------- 후보 없음: 구조 오류
def test_no_matching_sheet_in_a_multi_sheet_workbook_is_a_structure_error(case):
    def break_header(wb):
        wb.worksheets[0]["F1"] = "다른 제목"
        guide_sheet(wb, "안내", 0)
    assert triples(failure(case, case.make(break_header))) == {("SHEET_NO_MATCH", "sheet", None)}


@pytest.mark.parametrize("what", ["missing", "wrong_position", "wrong_text"])
def test_header_problems_block_with_no_match_when_there_are_several_sheets(case, what):
    def mutate(wb):
        ws = wb.worksheets[0]
        guide_sheet(wb, "안내")
        if what == "missing":
            ws.unmerge_cells("F1:F2")                                   # 학번 제목이 아예 없다
            ws["F1"] = None
        elif what == "wrong_position":
            ws["E1"], ws["F1"] = ws["F1"].value, ws["E1"].value        # 성명·학번 제목이 서로 바뀐 위치에 있다
        else:
            ws["E1"] = "이름"
    assert triples(failure(case, case.make(mutate))) == {("SHEET_NO_MATCH", "sheet", None)}


def test_merge_structure_mismatch_blocks_with_no_match_when_there_are_several_sheets(case):
    def mutate(wb):
        ws = wb.worksheets[0]
        guide_sheet(wb, "안내", 0)
        ws.unmerge_cells("H1:L1" if case.name == "multicultural" else "O1:Q1")
    assert triples(failure(case, case.make(mutate))) == {("SHEET_NO_MATCH", "sheet", None)}


def test_a_workbook_with_no_worksheet_is_a_structure_error(case):
    def only_chart(wb):
        chart_sheet(wb, "차트")
        wb.remove(wb.worksheets[0])                                    # 차트 시트만 남는다
        assert wb.worksheets == []
    assert triples(failure(case, case.make(only_chart))) == {("SHEET_NO_MATCH", "sheet", None)}


# ---------------------------------------------------------------- 기존 계약 유지: 시트가 하나뿐이면 어디가 다른지 위치까지 알려 준다
def test_a_single_sheet_with_a_wrong_layout_keeps_the_detailed_layout_errors(case):
    exc = failure(case, case.make(lambda wb: wb.worksheets[0].__setitem__("F1", "다른 제목")))
    assert ("LAYOUT_HEADER", "F1", None) in triples(exc) and all(c.startswith("LAYOUT_") for c, _, _ in triples(exc))


def test_a_single_renamed_sheet_with_a_wrong_layout_is_a_layout_error_not_a_sheet_name_error(case):
    def mutate(wb):
        wb.worksheets[0].title = "이름이 달라도"
        wb.worksheets[0]["E1"] = "이름"
    codes = {c for c, _, _ in triples(failure(case, case.make(mutate)))}
    assert codes == {"LAYOUT_HEADER"} and "SHEET_MISSING" not in codes


def test_a_single_sheet_with_a_missing_merge_keeps_the_layout_merge_error(case):
    rng = "H1:L1" if case.name == "multicultural" else "O1:Q1"
    exc = failure(case, case.make(lambda wb: wb.worksheets[0].unmerge_cells(rng)))
    assert ("LAYOUT_MERGE", rng, None) in triples(exc)


# ---------------------------------------------------------------- 머리글만 있고 데이터가 없는 경우: 시트는 고르고, 데이터는 기존 규칙으로 차단
def test_header_only_sheet_is_selected_and_then_blocked_by_the_existing_data_rules(make_input, make_mc_input, tmp_path):
    for read, path in ((lambda p: DaechungAdapter().read(p), make_input(n=0)), (lambda p: MulticulturalAdapter(RATES).read(p), make_mc_input(n=0))):
        with pytest.raises(InputValidationFailed) as alone:
            read(path)
        shaped = reshape(path, tmp_path / f"h_{path.name}", lambda wb: guide_sheet(wb, "안내", 0))
        with pytest.raises(InputValidationFailed) as with_guide:
            read(shaped)
        assert triples(alone.value) == triples(with_guide.value) != set()
        assert not {c for c, _, _ in triples(with_guide.value)} & {"SHEET_NO_MATCH", "SHEET_AMBIGUOUS", "SHEET_MISSING"}      # 시트 선택 오류가 아니라 기존 데이터 규칙 오류다


# ---------------------------------------------------------------- 개인정보: 시트명은 오류·repr 에 남지 않는다
def test_errors_never_contain_sheet_names(case):
    def dup(wb):
        wb.worksheets[0].title = MARK + "-원본"
        wb.copy_worksheet(wb.worksheets[0]).title = MARK + "-복사"
    def nomatch(wb):
        wb.worksheets[0].title = MARK + "-원본"
        wb.worksheets[0]["E1"] = "이름"
        guide_sheet(wb, MARK + "-안내")
    for fn in (dup, nomatch):
        exc = failure(case, case.make(fn))
        text = str(exc) + repr(exc) + " ".join(f"{x.code}{x.field}{x.row}" for x in exc.errors)
        assert MARK not in text


# ---------------------------------------------------------------- 기존 출력과 완전 동등 (골든)
@pytest.mark.parametrize("name", CASES)
def test_output_with_renamed_and_extra_sheets_equals_the_golden(name, tmp_path, make_input, make_mc_input, synthetic, monkeypatch):
    program, src, policy = build_case(name, make_input, make_mc_input, synthetic, monkeypatch)

    def shape(wb):
        wb.worksheets[0].title = "재단에서 받은 파일"
        guide_sheet(wb, "안내", 0)
        guide_sheet(wb, "메모")
    shaped = reshape(src, tmp_path / "shaped.xlsx", shape)
    out = tmp_path / "out"
    out.mkdir()
    got = snapshot(name, convert(program, shaped, out, TEMPLATE, policy=policy, base_date=BASE_DATE))
    expected = load_golden(name)
    assert diff(got, json.loads(json.dumps(expected))) == [] and got["filename"] == expected["filename"]
    assert got["sheet_order"] == expected["sheet_order"] and len(got["sheets"]) == len(expected["sheets"])


# ---------------------------------------------------------------- CLI·Tk(공용 실행 계층)가 같은 규칙을 쓴다
def test_cli_accepts_a_renamed_sheet_and_blocks_an_ambiguous_one(make_input, tmp_path, capsys):
    src = make_input(n=3)
    renamed = reshape(src, tmp_path / "r.xlsx", lambda wb: setattr(wb.worksheets[0], "title", "아무이름"))
    out = tmp_path / "out"
    out.mkdir()
    assert cli.main(["convert", "--program", "daechung", "--input", str(renamed), "--out-dir", str(out), "--template", str(TEMPLATE)]) == 0
    assert len(list(out.iterdir())) == 1
    dup = reshape(src, tmp_path / "d.xlsx", lambda wb: wb.copy_worksheet(wb.worksheets[0]))
    out2 = tmp_path / "out2"
    out2.mkdir()
    capsys.readouterr()
    code = cli.main(["convert", "--program", "daechung", "--input", str(dup), "--out-dir", str(out2), "--template", str(TEMPLATE)])
    printed = capsys.readouterr()
    assert code != 0 and list(out2.iterdir()) == [] and "SHEET_AMBIGUOUS" in printed.out + printed.err
    assert "Copy" not in printed.out + printed.err                       # 시트명(복사본 기본 이름)은 출력하지 않는다


def test_shared_execution_layer_used_by_tk_has_the_same_rule(make_input, tmp_path):
    from datetime import date
    src = make_input(n=3)
    ok = reshape(src, tmp_path / "ok.xlsx", lambda wb: (guide_sheet(wb, "안내", 0), setattr(wb.worksheets[1], "title", "다른이름")))
    out = tmp_path / "out"
    out.mkdir()
    o = run_conversion("daechung", ok, out, TEMPLATE, today=date(2099, 10, 7))
    assert o.ok and o.count == 3
    dup = reshape(src, tmp_path / "dup.xlsx", lambda wb: wb.copy_worksheet(wb.worksheets[0]))
    out2 = tmp_path / "out2"
    out2.mkdir()
    bad = run_conversion("daechung", dup, out2, TEMPLATE, today=date(2099, 10, 7))
    assert not bad.ok and list(out2.iterdir()) == [] and "SHEET_AMBIGUOUS" in " ".join(getattr(bad, "details", ()) or ()) + bad.summary
