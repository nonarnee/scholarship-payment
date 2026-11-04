"""다문화 종단 변환: 어댑터 -> 검증 -> 방식 B Writer(사업자번호 열 공란+숨김) -> 출력 재검증. 합성만."""
import dataclasses
from pathlib import Path

import pytest
from openpyxl import load_workbook

from scholarship_payment import __main__ as cli
from scholarship_payment.app.controller import run_conversion
from scholarship_payment.app.convert import ConversionFailed, convert
from scholarship_payment.config.policy import SYNTHETIC_POLICY
from scholarship_payment.config.policy_file import load_policy, policy_to_dict
from scholarship_payment.errors import ValidationFailed
from scholarship_payment.writers.template_writer import _hide_column

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
POLICY = dataclasses.replace(SYNTHETIC_POLICY, hourly_rates=(("가상A", 1000), ("가상B", 1500)), hidden_list_columns=("F",))
LIST = "지급대상자명단(9월)"


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


def test_end_to_end_one_row_per_student_and_column_f_hidden(make_mc_input, synthetic, out):
    st = synthetic.mc_students(4)
    st[2]["rows"] = [("가상기관최근", "가상B", 5 * 60), ("가상기관이전", "가상A", 6 * 60)]
    res = convert("multicultural", make_mc_input(students=st), out, TEMPLATE, policy=POLICY)
    assert res.count == 4 and res.output_path.name == "지급명단_MULTICULTURAL_9999_09.xlsx"
    ws = load_workbook(res.output_path)[LIST]
    assert ws.column_dimensions["F"].hidden is True
    assert [ws[f"F{r}"].value for r in range(5, 9)] == [None] * 4                      # 사업자등록번호 공란
    assert ws["G7"].value == "가상기관최근" and ws["H7"].value == "가상기관최근"
    assert ws["J7"].value == "1,500 / 1,000" and ws["I7"].value == 1                      # 시급이 다르면 위 행부터 둘 다 표시
    assert isinstance(ws["J5"].value, int)
    assert ws["L7"].value == 1500 * 5 + 1000 * 6
    wins, wris = load_workbook(res.output_path)["WINS"], load_workbook(res.output_path)["WRIS"]
    assert wins.max_row == 5 and wris.max_row == 5                                        # 학생당 1행
    assert res.warnings == () and sorted(n.code for n in res.notes) == ["RATE_MIXED_IN_GROUP", "STUDENT_MERGED_ROWS"]


def test_policy_file_roundtrip_with_optional_keys(tmp_path):
    p = tmp_path / "p.json"
    import json
    p.write_text(json.dumps(policy_to_dict(POLICY), ensure_ascii=False), encoding="utf-8")
    assert load_policy(p) == POLICY
    assert "hourly_rates" not in policy_to_dict(SYNTHETIC_POLICY)


@pytest.mark.parametrize("extra", [{"hourly_rates": {"가상A": 0}}, {"hourly_rates": {"가상A": 1.5}}, {"hourly_rates": {"": 5}},
                                   {"hourly_rates": ["가상A"]}, {"hourly_rates": {"가상A": True}}, {"hidden_list_columns": ["f"]},
                                   {"hidden_list_columns": ["F", "F"]}, {"hidden_list_columns": "F"}, {"hidden_list_columns": ["AA"]}])
def test_bad_optional_policy_values_are_rejected(tmp_path, extra):
    import json
    p = tmp_path / "p.json"
    p.write_text(json.dumps({**policy_to_dict(SYNTHETIC_POLICY), **extra}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValidationFailed):
        load_policy(p)


def test_without_rates_in_policy_conversion_is_blocked(make_mc_input, out):
    with pytest.raises(ConversionFailed) as e:
        convert("multicultural", make_mc_input(n=2), out, TEMPLATE, policy=SYNTHETIC_POLICY)
    assert [x.code for x in e.value.errors] == ["POLICY_RATES_MISSING"] and list(out.iterdir()) == []


def test_daechung_is_unaffected_by_optional_keys(make_input, out):
    res = convert("daechung", make_input(n=2), out, TEMPLATE, policy=SYNTHETIC_POLICY)
    assert load_workbook(res.output_path)[LIST].column_dimensions["F"].hidden in (False, None)


def test_controller_and_cli_accept_the_program(make_mc_input, out, tmp_path, capsys):
    import json
    pol = tmp_path / "p.json"
    pol.write_text(json.dumps(policy_to_dict(POLICY), ensure_ascii=False), encoding="utf-8")
    o = run_conversion("multicultural", make_mc_input(n=3), out, TEMPLATE, pol)
    assert o.ok and o.count == 3
    code = cli.main(["convert", "--program", "multicultural", "--input", str(make_mc_input(n=3)), "--out-dir", str(out),
                     "--template", str(TEMPLATE), "--policy", str(pol)])
    assert code == 0 and "대상자 3명" in capsys.readouterr().out


@pytest.mark.parametrize("grouped", [False, True])
def test_hide_column_handles_grouped_dimensions(grouped):
    from openpyxl import Workbook
    ws = Workbook().active
    if grouped:
        ws.column_dimensions["D"].min, ws.column_dimensions["D"].max, ws.column_dimensions["D"].width = 4, 8, 11
    else:
        ws.column_dimensions["F"].width = 11
    _hide_column(ws, "F")
    import io
    from openpyxl import load_workbook as lw
    buf = io.BytesIO()
    ws.parent.save(buf)
    d = lw(io.BytesIO(buf.getvalue())).active.column_dimensions        # 저장·재로드 후에도 F 만 숨겨져 있다
    assert d["F"].hidden is True and d["F"].width == 11
    if grouped:
        assert all(not d[c].hidden and d[c].width == 11 for c in "DEGH")
