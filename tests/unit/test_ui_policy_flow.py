"""정책 파일 만들기(화면 로직): 기존 policy_builder 재사용, 기존 파일 무덮어쓰기, 오류는 코드만."""
import json
from pathlib import Path

import pytest

from scholarship_payment.config.policy_file import load_policy
from scholarship_payment.ui import policy_flow as pf

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
VALUES = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}


def test_fields_for_program_reuse_builder_prompts():
    assert [f.key for f in pf.fields_for("daechung")] == ["list_title", "wins_work_name", "wris_gub_a", "wris_gub_b", "remit_info"]
    assert [f.key for f in pf.fields_for("multicultural")][-2:] == ["rate_urban", "rate_rural"]            # 시급은 자유 문자열이 아니라 두 칸
    assert [f.label for f in pf.fields_for("multicultural")][-2:] == ["시급(도시)", "시급(농어촌)"]
    assert not any(f.key.startswith("rate") for f in pf.fields_for("daechung") + pf.fields_for("ai"))      # 다른 사업에는 시급 칸이 없다
    assert [f.key for f in pf.edit_fields_for("multicultural")] == [f.key for f in pf.fields_for("multicultural")]
    assert [f.key for f in pf.edit_fields_for("daechung")] == [f.key for f in pf.fields_for("daechung")]
    assert all(f.label for f in pf.fields_for("ai"))


def test_suggested_path_is_the_first_free_name_and_never_an_existing_file(tmp_path):
    assert pf.suggest_path("daechung", tmp_path) == tmp_path / "policy_daechung.json"
    (tmp_path / "policy_daechung.json").write_text("keep", encoding="utf-8")
    (tmp_path / "policy_daechung_2.json").write_text("keep", encoding="utf-8")
    assert pf.suggest_path("daechung", tmp_path) == tmp_path / "policy_daechung_3.json"


def test_create_writes_a_loadable_policy(tmp_path):
    out = tmp_path / "cfg" / "policy_daechung.json"
    r = pf.create_policy(TEMPLATE, VALUES, out, "daechung")
    assert r.ok and r.path == out and r.codes == () and load_policy(out).wins_work_name == "합성근로"


def test_create_never_overwrites_an_existing_file(tmp_path):
    out = tmp_path / "policy_daechung.json"
    out.write_text("원래 내용", encoding="utf-8")
    r = pf.create_policy(TEMPLATE, VALUES, out, "daechung")
    assert not r.ok and r.codes == ("POLICY_OUTPUT_EXISTS",) and out.read_text(encoding="utf-8") == "원래 내용"
    assert [p.name for p in tmp_path.iterdir()] == ["policy_daechung.json"]


def test_missing_values_and_bad_template_report_codes_only_and_create_nothing(tmp_path):
    out = tmp_path / "p.json"
    r = pf.create_policy(TEMPLATE, {**VALUES, "wris_gub_a": "  "}, out, "daechung")
    assert not r.ok and r.codes == ("POLICY_KEY_MISSING",) and not out.exists()
    bad = tmp_path / "t.xlsx"
    bad.write_bytes(b"x")
    r = pf.create_policy(bad, VALUES, out, "daechung")
    assert not r.ok and r.codes == ("TEMPLATE_UNREADABLE",) and not out.exists()
    assert "합성근로" not in repr(r)


def test_multicultural_requires_a_valid_rate_table(tmp_path):
    out = tmp_path / "p.json"
    assert pf.create_policy(TEMPLATE, VALUES, out, "multicultural", rates_text="가=1000, 나=2000").ok          # CLI·Tk 경로 유지
    out2 = tmp_path / "p2.json"
    r = pf.create_policy(TEMPLATE, VALUES, out2, "multicultural", rates_text="가:1000")
    assert not r.ok and r.codes == ("POLICY_TYPE",) and not out2.exists()


def test_create_with_the_two_rate_fields_writes_the_two_key_table(tmp_path):
    out = tmp_path / "p.json"
    r = pf.create_policy(TEMPLATE, VALUES, out, "multicultural", rate_values={"rate_urban": "18,000", "rate_rural": "14000"})
    assert r.ok and load_policy(out).rates() == {"도시": 18000, "농어촌": 14000}


@pytest.mark.parametrize("rv", [{"rate_urban": "18000"}, {"rate_urban": "0", "rate_rural": "1"}, {"rate_urban": "x", "rate_rural": "1"}, {}])
def test_create_with_bad_rate_fields_creates_nothing(tmp_path, rv):
    out = tmp_path / "p.json"
    r = pf.create_policy(TEMPLATE, VALUES, out, "multicultural", rate_values=rv)
    assert not r.ok and r.codes == ("POLICY_TYPE",) and not out.exists()


def test_rate_fields_are_ignored_for_other_programs(tmp_path):
    out = tmp_path / "p.json"
    assert pf.create_policy(TEMPLATE, VALUES, out, "ai", rate_values={"rate_urban": "1", "rate_rural": "2"}).ok
    assert "hourly_rates" not in json.loads(out.read_text(encoding="utf-8"))


def test_creation_still_never_overwrites_with_rate_fields(tmp_path):
    out = tmp_path / "p.json"
    out.write_text("원래 내용", encoding="utf-8")
    r = pf.create_policy(TEMPLATE, VALUES, out, "multicultural", rate_values={"rate_urban": "1", "rate_rural": "2"})
    assert not r.ok and r.codes == ("POLICY_OUTPUT_EXISTS",) and out.read_text(encoding="utf-8") == "원래 내용"


# ---------- 기존 정책 수정(화면 로직) ----------
def _policy(tmp_path, program="multicultural", name="policy.json"):
    out = tmp_path / name
    assert pf.create_policy(TEMPLATE, VALUES, out, program, rate_values={"rate_urban": "18000", "rate_rural": "14000"}).ok
    return out


def test_load_edit_returns_the_form_values_for_the_program(tmp_path):
    ld = pf.load_edit(_policy(tmp_path), "multicultural")
    assert ld.ok and ld.codes == () and ld.session is not None
    assert ld.values == VALUES and ld.rate_values == {"rate_urban": "18000", "rate_rural": "14000"}
    assert "합성근로" not in repr(ld) and "18000" not in repr(ld)
    other = pf.load_edit(_policy(tmp_path, "daechung", "d.json"), "daechung")
    assert other.ok and other.rate_values == {}


def test_load_edit_reports_blockers_as_codes_and_leaves_the_file_alone(tmp_path):
    p = tmp_path / "p.json"
    assert pf.create_policy(TEMPLATE, VALUES, p, "multicultural", rates_text="가상A=1000").ok
    before = p.read_bytes()
    ld = pf.load_edit(p, "multicultural")
    assert not ld.ok and ld.session is None and ld.codes == ("POLICY_EDIT_EXTRA_RATE_KEYS",) and ld.blocked and p.read_bytes() == before
    missing = pf.load_edit(tmp_path / "none.json", "daechung")
    assert not missing.ok and missing.codes == ("POLICY_FILE_MISSING",) and not missing.blocked


def test_save_edit_updates_the_file_with_backup_and_reports_names_only(tmp_path):
    p = _policy(tmp_path)
    ld = pf.load_edit(p, "multicultural")
    r = pf.save_edit(ld.session, {**VALUES, "wins_work_name": "새근로"}, {"rate_urban": "19000", "rate_rural": "15000"})
    assert r.ok and r.changed and r.backup_name == "policy.json.bak" and r.codes == ()
    assert load_policy(p).wins_work_name == "새근로" and load_policy(p).rates() == {"도시": 19000, "농어촌": 15000}
    assert "새근로" not in repr(r)


def test_save_edit_failures_are_codes_and_keep_the_file(tmp_path):
    p = _policy(tmp_path)
    before = p.read_bytes()
    ld = pf.load_edit(p, "multicultural")
    r = pf.save_edit(ld.session, VALUES, {"rate_urban": "abc", "rate_rural": "1"})
    assert not r.ok and r.codes == ("POLICY_TYPE",) and p.read_bytes() == before
    r = pf.save_edit(ld.session, {**VALUES, "wris_gub_a": ""}, {"rate_urban": "1", "rate_rural": "1"})
    assert not r.ok and r.codes == ("POLICY_KEY_MISSING",) and p.read_bytes() == before
    p.write_text(p.read_text(encoding="utf-8") + " ", encoding="utf-8")                   # 외부에서 바뀜
    r = pf.save_edit(ld.session, {**VALUES, "wins_work_name": "새"}, {"rate_urban": "1", "rate_rural": "1"})
    assert not r.ok and r.codes == ("POLICY_EDIT_CONFLICT",) and sorted(x.name for x in tmp_path.iterdir()) == ["policy.json"]


def test_unwritable_location_is_reported_without_raising(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    r = pf.create_policy(TEMPLATE, VALUES, blocker / "p.json", "daechung")
    assert not r.ok and r.codes and not (blocker / "p.json").exists()
