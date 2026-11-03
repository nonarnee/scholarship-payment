"""정책 파일 만들기(합성 템플릿·가짜 상수만)."""
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from scholarship_payment.config.policy import SYNTHETIC_POLICY
from scholarship_payment.config.policy_builder import USER_KEYS, make_policy_file
from scholarship_payment.config.policy_file import load_policy, policy_to_dict
from scholarship_payment.errors import ValidationFailed

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
VALUES = {"list_title": "가짜 {month}월 명단", "wins_work_name": "가짜근로", "wris_gub_a": "GA", "wris_gub_b": "GB", "remit_info": "가짜({month}월)"}


def test_roundtrip_matches_synthetic_policy_when_given_synthetic_values(tmp_path):
    vals = {k: policy_to_dict(SYNTHETIC_POLICY)[k] for k in USER_KEYS}
    p = make_policy_file(TEMPLATE, vals, tmp_path / "p.json")
    assert load_policy(p) == SYNTHETIC_POLICY


def test_values_are_used_exactly_and_template_items_are_read(tmp_path):
    p = make_policy_file(TEMPLATE, VALUES, tmp_path / "p.json")
    pol = load_policy(p)
    assert pol.list_title == VALUES["list_title"] and pol.wris_gub_b == "GB" and pol.wris_headers == SYNTHETIC_POLICY.wris_headers
    assert json.loads(p.read_text(encoding="utf-8"))["excluded_sheets"] == list(SYNTHETIC_POLICY.excluded_sheets)


@pytest.mark.parametrize("key", USER_KEYS)
@pytest.mark.parametrize("bad", ["", "   ", "<입력 필요>"])
def test_blank_or_placeholder_values_create_no_file(tmp_path, key, bad):
    with pytest.raises(ValidationFailed):
        make_policy_file(TEMPLATE, {**VALUES, key: bad}, tmp_path / "p.json")
    assert list(tmp_path.iterdir()) == []


def test_bad_template_variable_is_rejected(tmp_path):
    with pytest.raises(ValidationFailed):
        make_policy_file(TEMPLATE, {**VALUES, "remit_info": "{x}"}, tmp_path / "p.json")
    assert list(tmp_path.iterdir()) == []


def test_existing_file_is_never_overwritten(tmp_path):
    out = tmp_path / "p.json"
    out.write_text("keep", encoding="utf-8")
    with pytest.raises(ValidationFailed) as e:
        make_policy_file(TEMPLATE, VALUES, out)
    assert e.value.errors[0].code == "POLICY_OUTPUT_EXISTS" and out.read_text(encoding="utf-8") == "keep"


def test_template_without_wris_sheet_is_rejected(tmp_path):
    wb = load_workbook(TEMPLATE)
    wb.remove(wb["WRIS"])
    t = tmp_path / "t.xlsx"
    wb.save(t)
    with pytest.raises(ValidationFailed):
        make_policy_file(t, VALUES, tmp_path / "p.json")
    with pytest.raises(ValidationFailed):
        make_policy_file(tmp_path / "missing.xlsx", VALUES, tmp_path / "p2.json")


def test_errors_do_not_echo_values(tmp_path):
    with pytest.raises(ValidationFailed) as e:
        make_policy_file(TEMPLATE, {**VALUES, "remit_info": "비밀적요{x}"}, tmp_path / "p.json")
    assert "비밀적요" not in str(e.value) + repr(e.value)


def test_cli_make_policy(tmp_path, monkeypatch, capsys):
    from scholarship_payment import __main__ as cli
    answers = iter(VALUES[k] for k in USER_KEYS)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    out = tmp_path / "p.json"
    assert cli.main(["make-policy", "--template", str(TEMPLATE), "--out", str(out)]) == 0
    assert load_policy(out).wins_work_name == "가짜근로"
    answers = iter(VALUES[k] for k in USER_KEYS)
    assert cli.main(["make-policy", "--template", str(TEMPLATE), "--out", str(out)]) == 1      # 덮어쓰기 거부
    assert "POLICY_OUTPUT_EXISTS" in capsys.readouterr().err
