"""공용 실행 계층: 입력 확인·정책 오류·성공/실패 문구(값 비노출)."""
from datetime import date
from pathlib import Path

import pytest

from scholarship_payment.app.controller import run_conversion

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


def test_success(make_input, out):
    o = run_conversion("daechung", make_input(n=3), out, TEMPLATE, today=date(2099, 10, 7))
    assert o.ok and o.stage == "ok" and o.count == 3 and o.output_path.exists() and "3명" in o.summary


@pytest.mark.parametrize("kw,msg", [({"input_path": ""}, "원본"), ({"out_dir": None}, "폴더"), ({"base_date": "2099-10-07"}, "YYYY.MM.DD")])
def test_argument_errors_create_nothing(make_input, out, kw, msg):
    args = dict(program="daechung", input_path=make_input(n=2), out_dir=out, template_path=TEMPLATE)
    args.update(kw)
    o = run_conversion(**args)
    assert not o.ok and o.stage == "args" and msg in o.summary and list(out.iterdir()) == []


def test_bad_policy_never_falls_back_to_synthetic(make_input, out, tmp_path):
    bad = tmp_path / "p.json"
    bad.write_text("{}", encoding="utf-8")
    o = run_conversion("daechung", make_input(n=2), out, TEMPLATE, policy_path=bad)
    assert not o.ok and o.stage == "policy" and list(out.iterdir()) == []


def test_validation_failure_reports_codes_only(make_input, out):
    o = run_conversion("daechung", make_input(mutate=lambda ws: ws.__setitem__("F7", ws["F5"].value)), out, TEMPLATE)
    assert not o.ok and o.stage == "validate" and any("DUPLICATE_STUDENT_ID" in d for d in o.details) and list(out.iterdir()) == []
    assert "가상001" not in " ".join(o.details)


def test_gui_module_imports_without_tk_loaded():
    import scholarship_payment.gui.app as app          # tkinter 는 main() 안에서만 import 한다
    assert callable(app.main)


def test_template_is_required_in_the_shared_layer(make_input, out):
    o = run_conversion("daechung", make_input(n=2), out, "")
    assert not o.ok and o.stage == "args" and "템플릿" in o.summary and list(out.iterdir()) == []


def test_missing_bank_names_are_listed_for_the_user_but_not_in_exception_text(make_input, out, tmp_path):
    from openpyxl import load_workbook
    from scholarship_payment.app.convert import ConversionFailed, convert
    wb = load_workbook(TEMPLATE)
    ws = wb["은행코드"]
    gone = ws["B2"].value
    ws["C2"] = None                      # 한 은행의 WINS 코드를 비운다
    t = tmp_path / "t.xlsx"
    wb.save(t)
    inp = make_input(n=3, mutate=lambda s: [s.__setitem__(f"T{r}", gone) for r in (3, 4, 5)])
    o = run_conversion("daechung", inp, out, t)
    assert not o.ok and o.stage == "validate" and any(gone in d and "은행코드" in d for d in o.details) and list(out.iterdir()) == []
    with pytest.raises(ConversionFailed) as e:
        convert("daechung", inp, out, t)
    assert e.value.missing_banks == (gone,) and gone not in str(e.value) + repr(e.value) + " ".join(str(x) for x in e.value.errors)
