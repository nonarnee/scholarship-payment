"""Step 1 상태 모델 · 설정 저장소 래퍼 · 고급 설정 임시 편집(Qt 무관). 백그라운드 실행은 ManualRunner 로 순서를 직접 제어한다."""
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
    values = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}
    return make_policy_file(TEMPLATE, values, tmp_path / "policy_daechung.json", "daechung")


@pytest.fixture
def store(tmp_path):
    return st.SettingsStore(tmp_path / "cfg" / "settings.json")


def make_model(store, runner=None, dirs=None):
    return st.Step1Model(store, runner or InlineRunner(), today=TODAY, default_dirs=dirs if dirs is not None else [])


def configured(store, policy, out, program="daechung"):
    store.commit(store.settings.with_paths(program, template_path=str(TEMPLATE), policy_path=str(policy), out_dir=str(out)))
    return store


# ---------- 모델: 필수 입력과 준비 상태 ----------
def test_fresh_model_blocks_next_and_defaults_date_to_today(store):
    m = make_model(store)
    assert m.program == "daechung" and m.base_date == "2099.10.07" and m.state("date").ok
    assert not m.ready() and m.blocking() == ["source", "out_dir", "template", "policy"]


def test_ready_only_when_every_field_is_ok(store, policy, tmp_path, make_input):
    out = tmp_path / "out"
    out.mkdir()
    m = make_model(configured(store, policy, out))
    assert m.state("template").ok and m.state("policy").ok and m.state("out_dir").ok and not m.ready()
    m.set_source(make_input(n=2))
    assert m.ready() and m.blocking() == []
    m.set_base_date("2099-10-07")
    assert not m.ready() and m.state("date").code == "DATE_FORMAT"
    m.set_base_date("2099.10.08")
    assert m.ready()
    m.set_source(None)
    assert not m.ready()


def test_snapshot_is_available_only_when_ready_and_has_no_secrets(store, policy, tmp_path, make_input):
    out = tmp_path / "out"
    out.mkdir()
    m = make_model(configured(store, policy, out))
    assert m.snapshot() is None
    src = make_input(n=2)
    m.set_source(src)
    snap = m.snapshot()
    assert snap.program == "daechung" and snap.source_path == str(src) and snap.base_date == "2099.10.07" and snap.out_dir == str(out)
    assert not hasattr(snap, "password") and {f for f in snap.__dataclass_fields__} == {"program", "base_date", "source_path", "out_dir", "template_path", "policy_path"}


def test_changes_notify_listeners(store):
    m = make_model(store)
    calls = []
    m.on_change(lambda: calls.append(1))
    m.set_base_date("2099.01.01")
    m.set_source("")
    assert len(calls) >= 2


# ---------- 사업별 독립성 ----------
def test_switching_program_loads_that_programs_paths_and_clears_source(store, policy, tmp_path, make_input):
    d_out, a_out = tmp_path / "d", tmp_path / "a"
    d_out.mkdir(); a_out.mkdir()
    store.commit(store.settings.with_paths("daechung", template_path=str(TEMPLATE), policy_path=str(policy), out_dir=str(d_out)).with_paths("ai", out_dir=str(a_out)))
    m = make_model(store)
    m.set_source(make_input(n=2))
    assert m.paths["out_dir"] == str(d_out) and m.paths["policy"] == str(policy)
    m.set_program("ai")
    assert m.paths["out_dir"] == str(a_out) and m.paths["policy"] is None and m.paths["template"] is None and m.paths["source"] is None
    assert not m.state("policy").ok and not m.ready()
    m.set_program("daechung")
    assert m.paths["out_dir"] == str(d_out) and m.paths["policy"] == str(policy) and m.paths["source"] is None


def test_unknown_program_is_rejected(store):
    with pytest.raises(ValueError):
        make_model(store).set_program("other")


def test_last_program_is_restored_and_persisted_on_change(store):
    make_model(store).set_program("multicultural")
    assert us.load(store.path).settings.last_program == "multicultural"
    assert make_model(st.SettingsStore(store.path)).program == "multicultural"


def test_session_out_dir_choice_is_not_persisted(store, tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    m = make_model(store)
    m.set_out_dir(str(out))
    assert m.state("out_dir").ok and us.load(store.path).settings.paths("daechung").out_dir is None


def test_source_path_and_date_never_reach_the_settings_file(store, make_input):
    m = make_model(store)
    m.set_source(make_input(n=2))
    m.set_base_date("2099.01.02")
    m.set_program("ai")
    text = store.path.read_text(encoding="utf-8")
    assert "synthetic" not in text and "2099" not in text and "source" not in text


# ---------- 기본 위치 탐색 · 경로 변경 ----------
def test_defaults_come_from_default_paths_when_settings_are_empty(store, policy, tmp_path):
    shutil_dir = tmp_path / "appdata"
    shutil_dir.mkdir()
    (shutil_dir / "template_daechung.xlsx").write_bytes(TEMPLATE.read_bytes())
    (shutil_dir / "policy_daechung.json").write_bytes(Path(policy).read_bytes())
    m = make_model(store, dirs=[shutil_dir])
    assert m.paths["template"] == str(shutil_dir / "template_daechung.xlsx") and m.state("template").ok and m.state("policy").ok


def test_saved_path_that_disappeared_is_flagged_and_does_not_fall_back_silently(store, policy, tmp_path):
    shutil_dir = tmp_path / "appdata"
    shutil_dir.mkdir()
    (shutil_dir / "template_daechung.xlsx").write_bytes(TEMPLATE.read_bytes())
    store.commit(store.settings.with_paths("daechung", template_path=str(tmp_path / "moved.xlsx")))
    m = make_model(store, dirs=[shutil_dir])
    assert m.paths["template"] == str(tmp_path / "moved.xlsx") and m.state("template").code == "TEMPLATE_MISSING"
    assert m.state("policy").level == v.UNSET and not m.ready()


def test_other_programs_stay_untouched_when_one_path_breaks(store, policy, tmp_path):
    store.commit(store.settings.with_paths("daechung", policy_path=str(tmp_path / "gone.json")).with_paths("ai", policy_path=str(policy)))
    m = make_model(store)
    assert m.state("policy").code == "POLICY_FILE_MISSING"
    m.set_program("ai")
    assert m.state("policy").ok


# ---------- 백그라운드 검증: 오래된 결과 무시 ----------
def test_stale_background_result_is_ignored_when_selection_changed(store, make_input, tmp_path):
    runner = ManualRunner()
    m = make_model(store, runner)
    first, second = make_input(n=2), tmp_path / "bad.xlsx"
    second.write_bytes(b"not a zip")
    m.set_source(first)
    m.set_source(second)
    assert m.state("source").level == v.CHECKING and len(runner.pending) == 2
    runner.run(1)                                           # 최신(손상 파일) 결과가 먼저 도착
    assert m.state("source").code == "SOURCE_NOT_XLSX"
    runner.run(0)                                           # 늦게 도착한 이전 파일의 '통과'는 무시
    assert m.state("source").code == "SOURCE_NOT_XLSX" and m.paths["source"] == str(second) and not m.ready()


def test_stale_result_is_ignored_after_source_is_cleared_or_program_switched(store, make_input):
    runner = ManualRunner()
    m = make_model(store, runner)
    m.set_source(make_input(n=2))
    m.set_source(None)
    runner.run_all()
    assert m.state("source").level == v.UNSET
    m.set_source(make_input(n=2))
    m.set_program("ai")
    runner.run_all()
    assert m.state("source").level == v.UNSET and m.paths["source"] is None


def test_checking_state_blocks_ready_until_the_result_arrives(store, policy, tmp_path, make_input):
    out = tmp_path / "out"
    out.mkdir()
    runner = ManualRunner()
    m = make_model(configured(store, policy, out), runner)
    runner.run_all()
    m.set_source(make_input(n=2))
    assert m.state("source").level == v.CHECKING and not m.ready()
    runner.run_all()
    assert m.ready()


def test_light_failure_does_not_start_a_background_job(store, tmp_path):
    runner = ManualRunner()
    m = make_model(store, runner)
    runner.pending.clear()
    m.set_source(tmp_path / "없음.xlsx")
    assert runner.pending == [] and m.state("source").code == "SOURCE_MISSING"


def test_three_tiers_are_reported_separately(store, make_input, tmp_path):
    runner = ManualRunner()
    m = make_model(store, runner)
    runner.pending.clear()
    m.set_source(make_input(n=2))
    assert v.light("source", m.paths["source"]).ok and m.state("source").level == v.CHECKING     # 존재는 확인, 구조는 확인 중
    runner.run_all()
    assert m.state("source").ok and not m.ready()                                              # 구조 통과 ≠ 변환 준비 완료(다른 필수 입력 남음)


# ---------- 설정 저장소 ----------
def test_store_reports_corrupt_file_recovery_once(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{broken", encoding="utf-8")
    s = st.SettingsStore(p)
    assert s.load_status == us.LOAD_RECOVERED and s.backup_name == "settings.json.bak" and s.settings == us.UserSettings()
    assert (tmp_path / "settings.json.bak").read_text(encoding="utf-8") == "{broken"


def test_store_commit_distinguishes_session_apply_from_persistence(tmp_path, monkeypatch):
    s = st.SettingsStore(tmp_path / "settings.json")
    new = s.settings.with_paths("ai", out_dir="/x")
    monkeypatch.setattr(us.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))
    out = s.commit(new)
    assert out.applied and not out.persisted and out.code == us.SAVE_FAILED
    assert s.settings == new                                             # 현재 세션에는 적용됨
    assert not (tmp_path / "settings.json").exists()


def test_model_survives_unwritable_settings_when_switching_program(tmp_path, monkeypatch):
    s = st.SettingsStore(tmp_path / "settings.json")
    m = make_model(s)
    monkeypatch.setattr(us.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))
    m.set_program("ai")
    assert m.program == "ai" and m.persist_failed


# ---------- 고급 설정 임시 편집(트랜잭션) ----------
def test_draft_starts_as_copy_and_cancel_changes_nothing(store, policy, tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    configured(store, policy, out)
    before = store.settings
    d = st.SettingsDraft(store.settings, InlineRunner(), default_dirs=[])
    d.set_path("daechung", "out_dir", str(tmp_path))
    d.reset_program("daechung")
    d.discard()
    assert store.settings == before and us.load(store.path).settings == before


def test_draft_apply_blocks_changed_invalid_paths_but_not_untouched_ones(store, tmp_path):
    store.commit(store.settings.with_paths("ai", policy_path=str(tmp_path / "old_gone.json")))        # 이미 깨진 저장값
    d = st.SettingsDraft(store.settings, InlineRunner(), default_dirs=[])
    assert d.can_apply()                                                   # 건드리지 않은 깨진 값은 막지 않는다
    d.set_path("daechung", "policy_path", str(tmp_path / "nope.json"))
    assert not d.can_apply() and d.state("daechung", "policy_path").code == "POLICY_FILE_MISSING"
    d.set_path("daechung", "policy_path", None)
    assert d.can_apply()


def test_draft_blocks_apply_while_checking_and_ignores_stale_results(store, policy, tmp_path):
    runner = ManualRunner()
    d = st.SettingsDraft(store.settings, runner, default_dirs=[])
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    d.set_path("daechung", "policy_path", str(policy))
    d.set_path("daechung", "policy_path", str(bad))
    assert not d.can_apply()
    runner.run(1)
    assert d.state("daechung", "policy_path").level == v.ERROR and not d.can_apply()
    runner.run(0)                                                          # 이전 선택(정상)의 늦은 결과는 무시
    assert d.state("daechung", "policy_path").level == v.ERROR and d.result().paths("daechung").policy_path == str(bad)


def test_draft_result_applies_to_store_and_updates_model(store, policy, tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    m = make_model(store)
    d = st.SettingsDraft(store.settings, InlineRunner(), default_dirs=[])
    d.set_path("daechung", "template_path", str(TEMPLATE))
    d.set_path("daechung", "policy_path", str(policy))
    d.set_path("daechung", "out_dir", str(out))
    assert d.can_apply()
    outcome = m.apply_settings(d.result())
    assert outcome.applied and outcome.persisted
    assert m.state("template").ok and m.state("policy").ok and m.state("out_dir").ok and m.paths["out_dir"] == str(out)
    assert us.load(store.path).settings.paths("daechung").policy_path == str(policy)


def test_draft_reset_program_clears_only_that_program(store, policy, tmp_path):
    store.commit(store.settings.with_paths("daechung", policy_path=str(policy)).with_paths("ai", policy_path=str(policy)))
    d = st.SettingsDraft(store.settings, InlineRunner(), default_dirs=[])
    d.reset_program("daechung")
    assert d.result().paths("daechung") == us.ProgramPaths() and d.result().paths("ai").policy_path == str(policy)
    assert store.settings.paths("daechung").policy_path == str(policy)    # 원본 설정은 그대로(복사본 편집)


def test_draft_does_not_delete_template_or_policy_files(store, policy, tmp_path):
    store.commit(store.settings.with_paths("daechung", policy_path=str(policy)))
    d = st.SettingsDraft(store.settings, InlineRunner(), default_dirs=[])
    d.reset_program("daechung")
    assert Path(policy).is_file()


def test_apply_after_apply_keeps_session_out_dir_choice_if_default_unchanged(store, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    m = make_model(store)
    m.set_out_dir(str(a))
    m.apply_settings(store.settings.with_paths("daechung", template_path=str(TEMPLATE)))
    assert m.paths["out_dir"] == str(a)
    m.apply_settings(store.settings.with_paths("daechung", out_dir=str(b)))
    assert m.paths["out_dir"] == str(b)


# ---------- 정책 파일 수정 알림·재검사 ----------
def test_policy_edited_restarts_the_check_for_the_selected_file_only(store, policy, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    runner = ManualRunner()
    m = make_model(configured(store, policy, out), runner)
    runner.run_all()
    assert m.state("policy").ok
    token = m._checks._tokens["policy"]
    seen = []
    m.on_policy_edited(seen.append)
    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")
    m.policy_edited(str(other))                                       # 다른 파일의 수정은 무시한다
    assert m._checks._tokens["policy"] == token and seen == [] and m.state("policy").ok
    m.policy_edited(str(policy))
    assert m._checks._tokens["policy"] > token and seen == [str(policy)]
    assert m.state("policy").level == v.CHECKING                      # 이전 성공 결과를 그대로 쓰지 않고 다시 검사한다
    runner.run_all()
    assert m.state("policy").ok


def test_policy_edited_catches_a_change_even_when_size_and_mtime_are_the_same(store, policy, tmp_path):
    import os
    out = tmp_path / "out"
    out.mkdir()
    runner = ManualRunner()
    m = make_model(configured(store, policy, out), runner)
    runner.run_all()
    s = policy.stat()
    data = bytearray(policy.read_bytes())
    i = data.index(b"ZZ0001")
    data[i:i + 6] = b"{{{{{{"                                       # 같은 길이로 깨뜨린다(형식 오류가 되는 값은 아니지만 내용은 달라진다)
    policy.write_bytes(bytes(data))
    os.utime(policy, ns=(s.st_atime_ns, s.st_mtime_ns))
    m.recheck()                                                       # 크기·시각만 보는 기존 재확인은 놓친다
    assert m.state("policy").ok
    token = m._checks._tokens["policy"]
    m.policy_edited(str(policy))                                      # 수정 알림은 무조건 다시 검사한다
    assert m._checks._tokens["policy"] > token


def test_draft_refresh_check_rechecks_without_changing_settings(store, policy, tmp_path):
    runner = ManualRunner()
    d = st.SettingsDraft(configured(store, policy, tmp_path).settings, runner, default_dirs=[])
    d.check_displayed("daechung")
    runner.run_all()
    token = d._checks._tokens[("daechung", "policy_path")]
    d.refresh_check("daechung", "policy_path")
    assert d._checks._tokens[("daechung", "policy_path")] > token and d.changed() == [] and d.value("daechung", "policy_path") == str(policy)
    runner.run_all()
    assert d.state("daechung", "policy_path").ok


def test_draft_refresh_check_does_not_turn_an_auto_found_policy_into_a_saved_path(store, policy, tmp_path):
    d = st.SettingsDraft(store.settings, InlineRunner(), default_dirs=[tmp_path])        # tmp_path 에 policy_daechung.json 이 있어 자동 탐색된다
    path, auto = d.effective("daechung", "policy_path")
    assert auto and path == str(policy)
    d.refresh_check("daechung", "policy_path")
    assert d.value("daechung", "policy_path") is None and d.changed() == [] and d.state("daechung", "policy_path").ok
