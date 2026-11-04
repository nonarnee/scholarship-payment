"""정책 파일 만들기(화면 로직): 기존 policy_builder 재사용, 기존 파일 무덮어쓰기, 오류는 코드만."""
from pathlib import Path

from scholarship_payment.config.policy_file import load_policy
from scholarship_payment.ui import policy_flow as pf

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
VALUES = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}


def test_fields_for_program_reuse_builder_prompts():
    assert [f.key for f in pf.fields_for("daechung")] == ["list_title", "wins_work_name", "wris_gub_a", "wris_gub_b", "remit_info"]
    assert [f.key for f in pf.fields_for("multicultural")][-1] == "rates"
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
    assert pf.create_policy(TEMPLATE, VALUES, out, "multicultural", rates_text="가=1000, 나=2000").ok
    out2 = tmp_path / "p2.json"
    r = pf.create_policy(TEMPLATE, VALUES, out2, "multicultural", rates_text="가:1000")
    assert not r.ok and r.codes == ("POLICY_TYPE",) and not out2.exists()


def test_unwritable_location_is_reported_without_raising(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    r = pf.create_policy(TEMPLATE, VALUES, blocker / "p.json", "daechung")
    assert not r.ok and r.codes and not (blocker / "p.json").exists()
