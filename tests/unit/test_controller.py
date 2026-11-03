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
    o = run_conversion("daechung", make_input(mutate=lambda ws: ws.__setitem__("F6", ws["F5"].value)), out, TEMPLATE)
    assert not o.ok and o.stage == "validate" and any("DUPLICATE_STUDENT_ID" in d for d in o.details) and list(out.iterdir()) == []
    assert "가상001" not in " ".join(o.details)


def test_gui_module_imports_without_tk_loaded():
    import scholarship_payment.gui.app as app          # tkinter 는 main() 안에서만 import 한다
    assert callable(app.main)
