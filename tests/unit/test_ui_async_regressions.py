"""비동기 검사·저장 폴더 사전 확인·설정 일관성 회귀(Qt 무관). 선택이 바뀌거나 파일이 바뀐 뒤에는 이전 성공 상태가 남지 않는다."""
from datetime import date
from pathlib import Path

import pytest

from scholarship_payment.config import user_settings as us
from scholarship_payment.ui import state as st
from scholarship_payment.ui import validators as v
from scholarship_payment.ui.runner import InlineRunner, ManualRunner

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
TODAY = lambda: date(2099, 10, 7)  # noqa: E731


@pytest.fixture
def policy(tmp_path):
    from scholarship_payment.config.policy_builder import make_policy_file
    vals = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}
    return make_policy_file(TEMPLATE, vals, tmp_path / "policy_daechung.json", "daechung")


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


def build(tmp_path, policy, out, runner=None):
    store = st.SettingsStore(tmp_path / "cfg" / "settings.json")
    store.commit(store.settings.with_paths("daechung", template_path=str(TEMPLATE), policy_path=str(policy), out_dir=str(out)))
    return st.Step1Model(store, runner or InlineRunner(), today=TODAY, default_dirs=[]), store


# ---------- 저장 폴더: os.access 는 확정 근거가 아니다 ----------
def test_unwritable_looking_folder_is_a_note_not_a_block_and_not_a_guarantee(tmp_path, monkeypatch):
    monkeypatch.setattr(v.os, "access", lambda p, mode: False)
    r = v.light("dir", tmp_path)
    assert r.level == v.OK and r.note == "DIR_NOT_WRITABLE"
    assert "참고" in v.message("DIR_NOT_WRITABLE") and "변환할 때 확인" in v.message("DIR_NOT_WRITABLE")


def test_writable_looking_folder_never_claims_it_can_be_saved(tmp_path):
    texts = [v.message(c) for c in ("DIR_NOT_WRITABLE", "DIR_MISSING", "DIR_NOT_DIR")]
    assert not [t for t in texts if "저장할 수 있" in t or "저장 가능" in t and "확인" not in t]


def test_ready_is_not_blocked_by_the_advisory_access_check(tmp_path, policy, out, make_input, monkeypatch):
    m, _ = build(tmp_path, policy, out)
    m.set_source(make_input(n=2))
    assert m.ready()
    monkeypatch.setattr(v.os, "access", lambda p, mode: False)
    m.set_out_dir(str(out))
    assert m.ready() and m.state("out_dir").note == "DIR_NOT_WRITABLE"


# ---------- 검사 완료 뒤 파일이 바뀌면 이전 성공이 무효화된다 ----------
def test_same_path_replaced_after_success_is_rechecked_before_leaving_step1(tmp_path, policy, out, make_input):
    runner = ManualRunner()
    m, _ = build(tmp_path, policy, out, runner)
    runner.run_all()
    src = make_input(n=2)
    m.set_source(src)
    runner.run_all()
    assert m.ready()
    src.write_bytes(b"this is no longer an xlsx")                # 같은 경로에서 내용이 바뀜
    m.recheck()
    assert m.state("source").level == v.CHECKING and not m.ready()
    runner.run_all()
    assert m.state("source").code == "SOURCE_NOT_XLSX" and not m.ready()


def test_file_deleted_after_success_is_caught_by_recheck(tmp_path, policy, out, make_input):
    m, _ = build(tmp_path, policy, out)
    src = make_input(n=2)
    m.set_source(src)
    assert m.ready()
    src.unlink()
    m.recheck()
    assert m.state("source").code == "SOURCE_MISSING" and not m.ready()


def test_folder_deleted_after_selection_is_caught_by_recheck(tmp_path, policy, out, make_input):
    m, _ = build(tmp_path, policy, out)
    m.set_source(make_input(n=2))
    out.rmdir()
    m.recheck()
    assert m.state("out_dir").code == "DIR_MISSING" and not m.ready()


def test_recheck_of_unchanged_files_starts_no_new_background_job(tmp_path, policy, out, make_input):
    runner = ManualRunner()
    m, _ = build(tmp_path, policy, out, runner)
    m.set_source(make_input(n=2))
    runner.run_all()
    jobs = len(runner.pending)
    m.recheck()
    assert len(runner.pending) == jobs and m.ready()


def test_template_or_policy_edited_after_success_is_rechecked(tmp_path, policy, out, make_input):
    runner = ManualRunner()
    m, _ = build(tmp_path, policy, out, runner)
    m.set_source(make_input(n=2))
    runner.run_all()
    assert m.ready()
    Path(policy).write_text("{}", encoding="utf-8")
    m.recheck()
    assert m.state("policy").level == v.CHECKING and not m.ready()
    runner.run_all()
    assert m.state("policy").code.startswith("POLICY_") and not m.ready()


# ---------- 검사 중 선택 제거·사업 전환 ----------
def test_in_flight_template_and_policy_results_are_dropped_after_program_switch(tmp_path, policy, out):
    runner = ManualRunner()
    m, _ = build(tmp_path, policy, out, runner)
    assert m.state("template").level == v.CHECKING and m.state("policy").level == v.CHECKING
    m.set_program("ai")                                            # ai 에는 지정된 템플릿·정책이 없다
    runner.run_all()                                               # daechung 의 늦은 '통과' 결과 도착
    assert m.paths["template"] is None and m.state("template").level == v.UNSET and m.state("policy").level == v.UNSET
    assert not m.ready()


def test_removing_the_selection_while_checking_drops_the_late_result(tmp_path, policy, out, make_input):
    runner = ManualRunner()
    m, _ = build(tmp_path, policy, out, runner)
    runner.run_all()
    m.set_source(make_input(n=2))
    m.set_source(None)
    runner.run_all()
    assert m.state("source").level == v.UNSET and m.paths["source"] is None and not m.ready()


def test_next_stays_blocked_until_every_required_check_has_finished(tmp_path, policy, out, make_input):
    runner = ManualRunner()
    m, _ = build(tmp_path, policy, out, runner)
    m.set_source(make_input(n=2))
    assert len(runner.pending) == 3 and not m.ready()
    for i in range(3):
        assert not m.ready()
        runner.run(i)
    assert m.ready()


def test_a_check_that_raises_becomes_a_fixed_error_without_the_message(tmp_path, policy, out, monkeypatch, make_input):
    m, _ = build(tmp_path, policy, out)
    monkeypatch.setattr(v, "light", lambda kind, path: (_ for _ in ()).throw(OSError("C:\\사용자\\홍길동\\원본.xlsx 접근 거부")))
    m.set_source(make_input(n=2))
    s = m.state("source")
    assert s.level == v.ERROR and s.code == "CHECK_FAILED" and "홍길동" not in repr(s) and "홍길동" not in v.message(s.code)


# ---------- 설정 저장 실패 · 세션 일관성 ----------
def test_session_value_survives_failed_save_and_disk_catches_up_on_next_successful_save(tmp_path, policy, out, monkeypatch):
    m, store = build(tmp_path, policy, out)
    other = tmp_path / "other"
    other.mkdir()
    real = us.os.replace
    monkeypatch.setattr(us.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))
    outcome = m.apply_settings(store.settings.with_paths("daechung", out_dir=str(other)))
    assert outcome.applied and not outcome.persisted and m.persist_failed
    assert store.settings.paths("daechung").out_dir == str(other) and m.paths["out_dir"] == str(other)
    assert us.load(store.path).settings.paths("daechung").out_dir == str(out)        # 디스크는 이전 값
    m.set_program("ai")
    assert m.persist_failed and store.settings.paths("daechung").out_dir == str(other)  # 여전히 저장 실패 → 세션 값 유지
    monkeypatch.setattr(us.os, "replace", real)
    m.set_program("daechung")
    assert not m.persist_failed and us.load(store.path).settings == store.settings    # 저장되면 디스크 = 세션
    assert m.paths["out_dir"] == str(other)


def test_program_switch_roundtrip_never_mixes_programs_after_failed_save(tmp_path, policy, out, monkeypatch):
    m, store = build(tmp_path, policy, out)
    monkeypatch.setattr(us.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))
    m.apply_settings(store.settings.with_paths("ai", out_dir=str(out)))
    m.set_program("ai")
    assert m.paths["out_dir"] == str(out) and m.paths["policy"] is None
    m.set_program("daechung")
    assert m.paths["policy"] == str(policy) and m.paths["source"] is None
