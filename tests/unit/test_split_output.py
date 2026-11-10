"""시트별 3개 파일 저장(분리 모드): 폴더 단위 안전 저장, 파일별·교차 재검증, 통합본과의 값·서식 동등성.
통합 모드는 그대로여야 한다(기본값). 입력·템플릿·정책은 모두 합성이다."""
import hashlib
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from scholarship_payment.adapters.daechung import DaechungAdapter
from scholarship_payment.app.convert import ConversionFailed, finish, prepare
from scholarship_payment.config.policy import SYNTHETIC_POLICY
from scholarship_payment.core.bank_codes import BankCodeTable
from scholarship_payment.errors import ValidationFailed
from scholarship_payment.io.safe_save import save_set
from scholarship_payment.validation.validator import validate
from scholarship_payment.writers.output_check import verify_output, verify_split_set
from scholarship_payment.writers.template_writer import (LIST_PREFIX, SPLIT_KINDS, SPLIT_SUFFIX, WINS, WRIS, build_single_sheet_workbook,
                                                         build_workbook)

from test_golden_equivalence import BASE_DATE, TEMPLATE

KINDS = ("list", "wins", "wris")


def names(d):
    return sorted(p.name for p in Path(d).iterdir())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def book(tag="a"):
    w = Workbook()
    w.active["A1"] = tag
    return w


def ok(_paths):
    return None


# ------------------------------------------------------------------ save_set (폴더 단위 안전 저장)
def books():
    return {k: book(k) for k in KINDS}


SUFFIX = {"list": "명단", "wins": "WINS", "wris": "WRIS"}


def test_save_set_publishes_one_folder_with_three_files_and_no_temp(tmp_path):
    folder, files = save_set(books(), tmp_path, "지급_가상", SUFFIX, ok)
    assert folder == tmp_path / "지급_가상" and names(tmp_path) == ["지급_가상"]
    assert names(folder) == ["지급_가상_WINS.xlsx", "지급_가상_WRIS.xlsx", "지급_가상_명단.xlsx"]
    assert {k: p.parent for k, p in files.items()} == {k: folder for k in KINDS}


def test_verifier_sees_all_three_temp_files_before_publish(tmp_path):
    seen = {}

    def verify(paths):
        seen.update(paths)
        assert set(paths) == set(KINDS) and all(p.exists() and p.parent.name.startswith(".~run-") for p in paths.values())
    save_set(books(), tmp_path, "지급_가상", SUFFIX, verify)
    assert len(seen) == 3 and names(tmp_path) == ["지급_가상"]


def test_verification_failure_leaves_no_folder_and_no_temp(tmp_path):
    keep = tmp_path / "기존.xlsx"
    keep.write_bytes(b"precious")

    def verify(_paths):
        raise ValidationFailed([])
    with pytest.raises(ValidationFailed):
        save_set(books(), tmp_path, "지급_가상", SUFFIX, verify)
    assert names(tmp_path) == ["기존.xlsx"] and keep.read_bytes() == b"precious"


def test_write_failure_midway_leaves_nothing(tmp_path):
    class Boom:
        def save(self, _p):
            raise OSError("disk")
    wbs = {"list": book(), "wins": Boom(), "wris": book()}
    with pytest.raises(ValidationFailed) as ei:
        save_set(wbs, tmp_path, "지급_가상", SUFFIX, ok)
    assert {e.code for e in ei.value.errors} == {"OUTPUT_IO"} and names(tmp_path) == []


def test_existing_folder_or_file_is_never_touched_and_next_name_is_used(tmp_path):
    (tmp_path / "지급_가상").mkdir()
    (tmp_path / "지급_가상" / "a.xlsx").write_bytes(b"keep-a")
    (tmp_path / "지급_가상_2").write_bytes(b"a file with the folder name")
    folder, files = save_set(books(), tmp_path, "지급_가상", SUFFIX, ok)
    assert folder.name == "지급_가상_3" and all(p.name.startswith("지급_가상_3_") for p in files.values())
    assert (tmp_path / "지급_가상" / "a.xlsx").read_bytes() == b"keep-a" and (tmp_path / "지급_가상_2").read_bytes() == b"a file with the folder name"
    assert names(tmp_path) == ["지급_가상", "지급_가상_2", "지급_가상_3"]


def test_existing_empty_folder_is_not_reused(tmp_path):
    (tmp_path / "지급_가상").mkdir()
    folder, _ = save_set(books(), tmp_path, "지급_가상", SUFFIX, ok)
    assert folder.name == "지급_가상_2" and names(tmp_path / "지급_가상") == []


def test_missing_output_dir_is_a_folder_error(tmp_path):
    with pytest.raises(ValidationFailed) as ei:
        save_set(books(), tmp_path / "없음", "지급_가상", SUFFIX, ok)
    assert [e.code for e in ei.value.errors] == ["OUTPUT_DIR_MISSING"]


def test_errors_carry_no_names_or_paths(tmp_path):
    def verify(_paths):
        raise ValidationFailed([])
    with pytest.raises(ValidationFailed) as ei:
        save_set(books(), tmp_path, "지급_가상", SUFFIX, verify)
    assert "지급_가상" not in repr(ei.value) and str(tmp_path) not in repr(ei.value)


# ------------------------------------------------------------------ 시트 1개 Workbook
@pytest.fixture
def validated(make_input):
    def _make(n=5):
        res = DaechungAdapter().read(make_input(n=n))
        return validate(res.batch, BankCodeTable.from_workbook(load_workbook(TEMPLATE))), res.source_totals
    return _make


def sheet_of(kind, month):
    return {"list": f"{LIST_PREFIX}{month}월)", "wins": WINS, "wris": WRIS}[kind]


@pytest.mark.parametrize("kind", KINDS)
def test_single_sheet_workbook_has_only_that_sheet_and_no_bank_sheet(kind, validated):
    v, _ = validated()
    wb = build_single_sheet_workbook(v, TEMPLATE, SYNTHETIC_POLICY, BASE_DATE, kind)
    assert wb.sheetnames == [sheet_of(kind, v.batch.month)] and wb.active is wb.worksheets[0]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("n", [1, 45, 120])
def test_single_sheet_matches_the_integrated_sheet_in_values_and_format(kind, n, validated, tmp_path):
    v, _ = validated(n)
    integrated = build_workbook(v, TEMPLATE, SYNTHETIC_POLICY, BASE_DATE)
    single = build_single_sheet_workbook(v, TEMPLATE, SYNTHETIC_POLICY, BASE_DATE, kind)
    p = tmp_path / "s.xlsx"
    single.save(p)
    a, b = integrated[sheet_of(kind, v.batch.month)], load_workbook(p).worksheets[0]
    assert a.max_row == b.max_row and a.max_column == b.max_column
    for row in a.iter_rows():
        for c in row:
            d = b[c.coordinate]
            assert (c.value, c.data_type, c.number_format) == (d.value, d.data_type, d.number_format)
            assert (repr(c.font), repr(c.fill), repr(c.border), repr(c.alignment)) == (repr(d.font), repr(d.fill), repr(d.border), repr(d.alignment))
    assert sorted(map(str, a.merged_cells.ranges)) == sorted(map(str, b.merged_cells.ranges))
    assert {k: (x.width, x.hidden) for k, x in a.column_dimensions.items()} == {k: (x.width, x.hidden) for k, x in b.column_dimensions.items()}
    assert {r: x.height for r, x in a.row_dimensions.items()} == {r: x.height for r, x in b.row_dimensions.items()}


def test_single_sheet_files_have_no_defined_names_pointing_at_removed_sheets(validated, tmp_path):
    v, _ = validated()
    wb = build_single_sheet_workbook(v, TEMPLATE, SYNTHETIC_POLICY, BASE_DATE, "wins")
    p = tmp_path / "s.xlsx"
    wb.save(p)
    back = load_workbook(p)
    for dn in back.defined_names.values():
        assert BASE_DATE not in dn.attr_text and "은행코드" not in (dn.attr_text or "") and "!" not in (dn.attr_text or "")


def test_unknown_kind_is_rejected(validated):
    v, _ = validated()
    with pytest.raises(ValueError):
        build_single_sheet_workbook(v, TEMPLATE, SYNTHETIC_POLICY, BASE_DATE, "bank")
    assert SPLIT_KINDS == KINDS and SPLIT_SUFFIX == SUFFIX


# ------------------------------------------------------------------ 재검증
def write_set(v, tmp_path, tag="set"):
    d = tmp_path / tag
    d.mkdir()
    paths = {}
    for k in KINDS:
        paths[k] = d / f"{tag}_{SUFFIX[k]}.xlsx"
        build_single_sheet_workbook(v, TEMPLATE, SYNTHETIC_POLICY, BASE_DATE, k).save(paths[k])
    return paths


def test_each_split_file_verifies_alone_and_as_a_set(validated, tmp_path):
    v, totals = validated(7)
    paths = write_set(v, tmp_path)
    for k, p in paths.items():
        verify_output(p, v, totals, only=k)
    verify_split_set(paths, v, totals)


def test_a_split_file_with_the_wrong_sheet_is_rejected(validated, tmp_path):
    v, totals = validated(3)
    paths = write_set(v, tmp_path)
    with pytest.raises(ValidationFailed) as ei:
        verify_output(paths["wins"], v, totals, only="wris")
    assert {e.code for e in ei.value.errors} == {"OUTPUT_SHEETS"}


def test_integrated_verification_still_requires_all_four_sheets(validated, tmp_path):
    v, totals = validated(3)
    paths = write_set(v, tmp_path)
    with pytest.raises(ValidationFailed) as ei:
        verify_output(paths["list"], v, totals)
    assert {e.code for e in ei.value.errors} == {"OUTPUT_SHEETS"}


def tamper(path, fn):
    wb = load_workbook(path)
    fn(wb.worksheets[0])
    wb.save(path)


@pytest.mark.parametrize("kind,cell", [("list", "L5"), ("wins", "G2"), ("wris", "E2")])
def test_tampered_amount_in_any_file_is_caught(kind, cell, validated, tmp_path):
    v, totals = validated(4)
    paths = write_set(v, tmp_path)
    tamper(paths[kind], lambda ws: ws.__setitem__(cell, ws[cell].value + 1))
    with pytest.raises(ValidationFailed):
        verify_split_set(paths, v, totals)


@pytest.mark.parametrize("kind,cell", [("list", "D5"), ("wins", "D2"), ("wris", "C2")])
def test_tampered_student_id_in_any_file_is_caught(kind, cell, validated, tmp_path):
    v, totals = validated(4)
    paths = write_set(v, tmp_path)
    tamper(paths[kind], lambda ws: setattr(ws[cell], "value", "00000000"))
    with pytest.raises(ValidationFailed):
        verify_split_set(paths, v, totals)


def test_row_count_and_missing_file_are_caught(validated, tmp_path):
    v, totals = validated(4)
    paths = write_set(v, tmp_path)
    tamper(paths["wris"], lambda ws: ws.delete_rows(5, 1))
    with pytest.raises(ValidationFailed):
        verify_split_set(paths, v, totals)
    paths2 = write_set(v, tmp_path, "set2")
    paths2["wins"].unlink()
    with pytest.raises(ValidationFailed) as ei:
        verify_split_set(paths2, v, totals)
    assert "OUTPUT_UNREADABLE" in {e.code for e in ei.value.errors}


def test_set_with_a_missing_kind_is_rejected(validated, tmp_path):
    v, totals = validated(2)
    paths = write_set(v, tmp_path)
    del paths["wins"]
    with pytest.raises(ValidationFailed):
        verify_split_set(paths, v, totals)


# ------------------------------------------------------------------ finish(split=True)
@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


def prep(make_input, n):
    return prepare("daechung", make_input(n=n), TEMPLATE, base_date=BASE_DATE)


@pytest.mark.parametrize("n", [1, 45, 70, 120])
def test_split_values_equal_the_integrated_output(n, make_input, out, tmp_path):
    p = prep(make_input, n)
    other = tmp_path / "other"
    other.mkdir()
    whole = finish(p, other)
    res = finish(p, out, split=True)
    assert res.output_path.is_dir() and res.output_path.parent == out and len(res.output_paths) == 3 and res.count == n
    assert names(out) == [Path(p.filename).stem]
    integrated = load_workbook(whole.output_path)
    for kind, path in zip(KINDS, res.output_paths):
        ws = load_workbook(path).worksheets[0]
        ref = integrated[sheet_of(kind, p.month)]
        assert [[c.value for c in r] for r in ws.iter_rows()] == [[c.value for c in r] for r in ref.iter_rows()]


def test_split_total_matches_prepared_and_files_are_named_by_suffix(make_input, out):
    p = prep(make_input, 6)
    res = finish(p, out, split=True)
    stem = Path(p.filename).stem
    assert [x.name for x in res.output_paths] == [f"{stem}_명단.xlsx", f"{stem}_WINS.xlsx", f"{stem}_WRIS.xlsx"]
    ws = load_workbook(res.output_paths[0]).worksheets[0]
    assert ws.cell(5 + p.count, 12).value == p.total_amount


def test_default_mode_is_unchanged_single_file(make_input, out):
    p = prep(make_input, 3)
    res = finish(p, out)
    assert res.output_path.is_file() and res.output_path.name == p.filename and res.output_paths == (res.output_path,)
    assert load_workbook(res.output_path).sheetnames[1:] == [WINS, WRIS, "은행코드"]


def test_split_collision_uses_next_folder_and_keeps_existing(make_input, out):
    p = prep(make_input, 3)
    first = finish(p, out, split=True)
    before = {x.name: sha(x) for x in first.output_paths}
    second = finish(p, out, split=True)
    assert second.output_path.name == first.output_path.name + "_2"
    assert {x.name: sha(x) for x in first.output_paths} == before


def test_split_failure_stage_output_and_no_leftovers(make_input, out, monkeypatch):
    p = prep(make_input, 3)
    import scholarship_payment.app.convert as conv

    def boom(*_a, **_k):
        raise ValidationFailed([])
    monkeypatch.setattr(conv, "verify_split_set", boom)
    with pytest.raises(ConversionFailed) as ei:
        finish(p, out, split=True)
    assert ei.value.stage == "output" and names(out) == []


def test_split_changed_input_creates_nothing(make_input, out):
    src = make_input(n=3)
    p = prepare("daechung", src, TEMPLATE, base_date=BASE_DATE)
    Path(src).write_bytes(Path(src).read_bytes() + b"x")
    with pytest.raises(ConversionFailed) as ei:
        finish(p, out, split=True)
    assert ei.value.stage == "changed" and names(out) == []


def test_split_does_not_modify_template_or_source(make_input, out):
    src = make_input(n=3)
    p = prepare("daechung", src, TEMPLATE, base_date=BASE_DATE)
    before = (sha(src), sha(TEMPLATE))
    finish(p, out, split=True)
    assert (sha(src), sha(TEMPLATE)) == before
