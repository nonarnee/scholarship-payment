"""읽기 전용 workflow: 정책 파일 로드(읽기 전후 해시) + prepare + 결과 요약/오류 그룹. 파일을 만들지 않는다."""
import dataclasses
import os
from pathlib import Path

import pytest

from scholarship_payment.app import workflow as wf
from scholarship_payment.app.convert import check_unchanged
from scholarship_payment.config import policy_file
from prep_helpers import PW, TEMPLATE, encrypt, flip_byte_keep_size_and_mtime, make_policy

BASE = "2099.10.07"
CARRY = ((2, 8 * 60, "9999년08월"), (3, 90, "9999년08월"))


@pytest.fixture
def pol(tmp_path):
    return make_policy(tmp_path)


def run(src, pol, template=TEMPLATE, password=None, program="daechung"):
    return wf.run_prepare(program, src, template, pol, BASE, password)


def test_ok_outcome_has_summary_with_only_measured_values(make_input, pol):
    o = run(make_input(n=4), pol)
    assert o.status == "ok" and o.prepared is not None and o.errors == ()
    s = o.summary
    assert (s.year, s.month, s.count, s.base_date, s.program) == (9999, 9, 4, BASE, "daechung")
    assert isinstance(s.total_amount, int) and s.total_amount == o.prepared.total_amount > 0
    assert set(dataclasses.asdict(s)) == {"program", "year", "month", "count", "total_amount", "base_date", "warnings", "notes"}   # 학생별 값·점수 없음


def test_carryover_notes_are_notes_not_warnings(make_input, pol, monkeypatch):
    o = run(make_input(n=4, extra=CARRY), pol)
    assert o.status == "ok" and [g.code for g in o.summary.notes] == ["CARRYOVER_ROW", "STUDENT_MERGED_ROWS"] or {g.code for g in o.summary.notes} >= {"STUDENT_MERGED_ROWS"}
    assert all(g.severity == "note" for g in o.summary.notes) and o.summary.warnings == ()


def test_blocking_errors_are_grouped_by_code_with_rows_only(make_input, pol):
    o = run(make_input(n=5, mutate=lambda ws: ws.__setitem__("F7", ws["F5"].value)), pol)
    assert o.status == "failed" and o.stage == "validate" and o.prepared is None and o.summary is None
    g = next(g for g in o.errors if g.code == "DUPLICATE_STUDENT_ID")
    assert g.severity == "error" and g.rows == (5, 7) and g.count == 2
    assert "가상" not in repr(o) and "0000" not in repr(g)


def test_bank_names_to_fix_are_carried_for_the_message(make_input, pol, tmp_path):
    from openpyxl import load_workbook
    wb = load_workbook(TEMPLATE)
    ws = wb["은행코드"]
    gone = ws.cell(2, 2).value
    ws.cell(2, 3).value = None
    t = tmp_path / "t.xlsx"
    wb.save(t)
    o = run(make_input(n=3, mutate=lambda s: [s.__setitem__(f"T{r}", gone) for r in (3, 4, 5)]), pol, t)
    assert o.status == "failed" and o.missing_banks == (gone,)


def test_password_statuses_and_no_password_in_outcome(make_input, pol, tmp_path):
    enc = encrypt(make_input(n=3), tmp_path / "enc.xlsx")
    assert run(enc, pol).status == "password_required"
    wrong = run(enc, pol, password="틀린-pw")
    assert wrong.status == "password_wrong" and "틀린-pw" not in repr(wrong)
    ok = run(enc, pol, password=PW)
    assert ok.status == "ok" and PW not in repr(ok) + repr(ok.prepared) + repr(ok.summary)


def test_policy_errors_are_reported_before_anything_is_read(make_input, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    o = run(make_input(n=2), bad)
    assert o.status == "failed" and o.stage == "policy" and any(g.code == "POLICY_KEY_MISSING" for g in o.errors)
    missing = run(make_input(n=2), tmp_path / "none.json")
    assert missing.status == "failed" and missing.errors[0].code == "POLICY_FILE_MISSING"


def test_policy_changed_while_loading_is_rejected(make_input, pol, monkeypatch):
    real = policy_file.load_policy

    def load_then_modify(path):
        res = real(path)
        flip_byte_keep_size_and_mtime(path)
        return res

    monkeypatch.setattr(wf, "load_policy", load_then_modify)
    o = run(make_input(n=2), pol)
    assert o.status == "changed" and o.errors[0].code == "INPUT_FILE_CHANGED" and o.errors[0].fields == ("policy",)


def test_source_changed_during_prepare_gives_changed_status(make_input, pol, monkeypatch):
    from scholarship_payment.adapters.daechung import DaechungAdapter
    real = DaechungAdapter.read

    def modify(self, path, password=None):
        r = real(self, path, password)
        flip_byte_keep_size_and_mtime(path)
        return r

    monkeypatch.setattr(DaechungAdapter, "read", modify)
    o = run(make_input(n=2), pol)
    assert o.status == "changed" and o.prepared is None


def test_prepared_carries_policy_fingerprint_so_policy_edits_are_detected(make_input, pol):
    o = run(make_input(n=3), pol)
    assert check_unchanged(o.prepared) == ()
    flip_byte_keep_size_and_mtime(pol)
    assert check_unchanged(o.prepared) == ("policy",)


def test_run_prepare_is_read_only_for_inputs_and_creates_nothing(make_input, pol, tmp_path):
    src = make_input(n=3)
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    h = [Path(p).read_bytes() for p in (src, TEMPLATE, pol)]
    run(src, pol)
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before and [Path(p).read_bytes() for p in (src, TEMPLATE, pol)] == h


def test_all_programs_work_through_the_workflow(make_input, make_mc_input, synthetic, tmp_path, monkeypatch):
    from scholarship_payment.app import convert as conv
    from scholarship_payment.config.policy_builder import make_policy_file
    from prep_helpers import SYNTH_VALUES
    monkeypatch.setattr(conv, "AI_HOURLY_RATE", 1000)
    assert run(make_input(n=3), make_policy(tmp_path, "ai"), program="ai").status == "ok"
    mc_pol = make_policy_file(TEMPLATE, SYNTH_VALUES, tmp_path / "mc.json", "multicultural", "가상A=1000, 가상B=1500")
    assert wf.run_prepare("multicultural", make_mc_input(students=synthetic.mc_students(3)), TEMPLATE, mc_pol, BASE).status == "ok"
    assert os.path.exists(mc_pol)
