"""변환 종단 시험(합성 입력만): 성공 시 파일 생성, 실패 시 어떤 파일도 남기지 않고 원본·템플릿은 불변."""
import hashlib
from pathlib import Path

import pytest
from openpyxl import load_workbook

from scholarship_payment import __main__ as cli
from scholarship_payment.app import convert as convert_mod
from scholarship_payment.app.convert import ConversionFailed, convert
from scholarship_payment.errors import ValidationFailed

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(inp, out, **kw):
    return convert("daechung", inp, out, TEMPLATE, **kw)


def failure(inp, out, **kw):
    with pytest.raises(ConversionFailed) as ei:
        run(inp, out, **kw)
    return ei.value


def triples(exc):
    return {(e.code, e.field, e.row) for e in exc.errors}


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


# ------------------------------------------------------------------ 성공
@pytest.mark.parametrize("n", [1, 45, 120])
def test_success_creates_one_verified_file(make_input, out, n):
    inp = make_input(n=n)
    before_in, before_tpl = sha(inp), sha(TEMPLATE)
    res = run(inp, out)
    assert res.count == n and res.output_path.parent == out and res.output_path.name == "지급명단_DAECHUNG_9999_09.xlsx"
    assert [p.name for p in out.iterdir()] == [res.output_path.name]
    wb = load_workbook(res.output_path)
    assert wb.sheetnames == ["지급대상자명단(9월)", "WINS", "WRIS", "은행코드"]
    assert wb["WINS"].max_row == n + 1
    assert sha(inp) == before_in and sha(TEMPLATE) == before_tpl
    assert [w.code for w in res.warnings] == ["BASE_DATE_UNSET"]


def test_base_date_removes_the_warning(make_input, out):
    res = run(make_input(n=2), out, base_date="2099.10.07")
    assert res.warnings == () and load_workbook(res.output_path)["지급대상자명단(9월)"]["Q2"].value == "*기준 : 2099.10.07"


def test_running_twice_never_overwrites(make_input, out):
    inp = make_input(n=3)
    first = run(inp, out)
    digest = sha(first.output_path)
    second = run(inp, out)
    assert second.output_path.name.endswith("_2.xlsx") and sha(first.output_path) == digest


def test_works_on_the_committed_original_format_fixture(fixture_45, fixture_3_text_ids, out):
    assert run(fixture_45, out).count == 45
    res = run(fixture_3_text_ids, out)
    assert load_workbook(res.output_path)["WINS"]["D2"].value == "00000001"


# ------------------------------------------------------------------ 실패: 단계별, 흔적 없음
def test_input_stage_failure(make_input, out):
    exc = failure(make_input(mutate=lambda ws: ws.__setitem__("F1", "학번2")), out)
    assert exc.stage == "input" and ("LAYOUT_HEADER", "F1", None) in triples(exc) and list(out.iterdir()) == []


def test_validation_stage_failure_duplicate_ids(make_input, out):
    exc = failure(make_input(mutate=lambda ws: ws.__setitem__("F6", ws["F5"].value)), out)
    assert exc.stage == "validate" and {("DUPLICATE_STUDENT_ID", "student_id", 5), ("DUPLICATE_STUDENT_ID", "student_id", 6)} <= triples(exc)
    assert list(out.iterdir()) == []


def test_validation_stage_failure_bank_code_missing_for_one_system(make_input, out):
    exc = failure(make_input(mutate=lambda ws: ws.__setitem__("T5", "가상은행09")), out)       # 합성표: WINS 코드 공란
    assert exc.stage == "validate" and triples(exc) == {("BANK_CODE_MISSING", "wins_bank_code", 5)}
    assert list(out.iterdir()) == []


def test_zero_amount_row_blocks_everything(make_input, out):
    def mutate(ws):
        paid = ws["O7"].value
        ws["O7"] = 0
        ws["O48"] = ws["O48"].value - paid
    exc = failure(make_input(mutate=mutate), out)
    assert exc.stage == "validate" and triples(exc) == {("AMOUNT_NOT_POSITIVE", "pay_amount", 7)} and list(out.iterdir()) == []


def test_template_stage_failures(make_input, out, tmp_path):
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"nope")
    with pytest.raises(ConversionFailed) as ei:
        convert("daechung", make_input(n=2), out, bad)
    assert ei.value.stage == "template" and ei.value.errors[0].code == "TEMPLATE_UNREADABLE"
    wb = load_workbook(TEMPLATE)
    wb["WINS"]["D1"] = "학번2"
    wb.save(tmp_path / "t2.xlsx")
    with pytest.raises(ConversionFailed) as ei:
        convert("daechung", make_input(n=2), out, tmp_path / "t2.xlsx")
    assert ei.value.stage == "template" and ei.value.errors[0].code == "TEMPLATE_LAYOUT" and list(out.iterdir()) == []


def test_output_verification_failure_leaves_no_file(make_input, out, monkeypatch):
    def broken(path, validated, totals):
        raise ValidationFailed([])
    monkeypatch.setattr(convert_mod, "verify_output", broken)
    exc = failure(make_input(n=3), out)
    assert exc.stage == "output" and list(out.iterdir()) == []


def test_missing_output_folder_and_unknown_program(make_input, tmp_path):
    exc = failure(make_input(n=2), tmp_path / "없음")
    assert exc.stage == "output" and exc.errors[0].code == "OUTPUT_DIR_MISSING"
    with pytest.raises(ConversionFailed) as ei:
        convert("other", make_input(n=2), tmp_path, TEMPLATE)
    assert ei.value.errors[0].code == "PROGRAM_UNSUPPORTED"


def test_failure_messages_never_contain_input_values(make_input, out):
    def mutate(ws):
        ws["E5"], ws["U6"], ws["T7"] = "가상비밀이름", "7777777", "가상비밀은행"
    exc = failure(make_input(mutate=mutate), out)
    text = str(exc) + repr(exc) + " ".join(str(e) + repr(e) for e in exc.errors)
    assert not any(s in text for s in ("가상비밀이름", "7777777", "가상비밀은행"))


# ------------------------------------------------------------------ 명령줄
def test_cli_success(make_input, out, capsys):
    code = cli.main(["convert", "--program", "daechung", "--input", str(make_input(n=4)), "--out-dir", str(out), "--template", str(TEMPLATE)])
    text = capsys.readouterr().out
    assert code == 0 and "대상자 4명" in text and "BASE_DATE_UNSET" in text and any(out.iterdir())
    assert "가상001" not in text


def test_cli_failure_exit_code_and_no_file(make_input, out, capsys):
    code = cli.main(["convert", "--program", "daechung", "--input", str(make_input(mutate=lambda ws: ws.__setitem__("F6", ws["F5"].value))),
                     "--out-dir", str(out), "--template", str(TEMPLATE)])
    err = capsys.readouterr().err
    assert code == 1 and "DUPLICATE_STUDENT_ID" in err and "파일을 만들지 않았습니다" in err and list(out.iterdir()) == []


def test_cli_rejects_bad_base_date(make_input, out, capsys):
    code = cli.main(["convert", "--program", "daechung", "--input", str(make_input(n=2)), "--out-dir", str(out),
                     "--template", str(TEMPLATE), "--base-date", "2099-10-07"])
    assert code == 2 and list(out.iterdir()) == []


def test_cli_module_entry_point(make_input, out):
    import os
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    r = subprocess.run([sys.executable, "-m", "scholarship_payment", "convert", "--program", "daechung", "--input",
                        str(make_input(n=2)), "--out-dir", str(out), "--template", str(TEMPLATE)],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0 and len(list(out.iterdir())) == 1
