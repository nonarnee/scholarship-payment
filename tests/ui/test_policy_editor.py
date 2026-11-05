"""정책 파일 수정 화면: 편집 대화상자, 고급 설정 연동(Step 1 전용·생성 중 차단), 설정 취소 시 경로 유지, 수정 후 미리보기 무효화.
합성 정책만 쓴다. 입력한 값은 오류 문구·위젯 라벨에 나오지 않는다.
"""
import json
import os
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLabel  # noqa: E402

from scholarship_payment.config import user_settings as us  # noqa: E402
from scholarship_payment.config.policy_file import load_policy  # noqa: E402
from scholarship_payment.ui import policy_flow, preview as pv  # noqa: E402
from scholarship_payment.ui.main_window import MainWindow  # noqa: E402
from scholarship_payment.ui.navigation import Step  # noqa: E402
from scholarship_payment.ui.policy_editor import PolicyEditDialog  # noqa: E402

from ui_helpers import SYNTH_VALUES, TEMPLATE  # noqa: E402

RATES = {"rate_urban": "18000", "rate_rural": "14000"}


def make_policy(tmp_path, program="daechung", name=None, rates=RATES):
    out = tmp_path / (name or f"policy_{program}_edit.json")
    assert policy_flow.create_policy(TEMPLATE, SYNTH_VALUES, out, program, rate_values=rates if program == "multicultural" else None).ok
    return out


def texts(w):
    return " ".join(x.text() for x in w.findChildren(QLabel))


def fill(dlg, **over):
    for k, e in dlg.inputs.items():
        if k in over:
            e.setText(over[k])


@pytest.fixture
def app_win(qapp, make_context, ready_settings):
    ctx = make_context(settings=ready_settings)
    w = MainWindow(context=ctx)
    w.show()
    yield w, ctx
    w.close()


# ---------- 편집 대화상자 ----------
def test_editor_fills_the_current_values_and_shows_rate_fields_only_for_multicultural(qapp, tmp_path):
    d = PolicyEditDialog("daechung", make_policy(tmp_path))
    assert [k for k in d.inputs] == list(SYNTH_VALUES) and all(d.inputs[k].text() == v for k, v in SYNTH_VALUES.items())
    assert d.save_button.isEnabled() and "시급" not in texts(d)
    m = PolicyEditDialog("multicultural", make_policy(tmp_path, "multicultural"))
    assert list(m.inputs)[-2:] == ["rate_urban", "rate_rural"] and m.inputs["rate_urban"].text() == "18000" and m.inputs["rate_rural"].text() == "14000"
    assert "시급(도시)" in texts(m) and "시급(농어촌)" in texts(m) and "미검증" in texts(m)       # 원본 괄호 값과의 일치는 확인되지 않았다고 표시한다


def test_save_updates_the_same_file_with_a_backup_and_closes(qapp, tmp_path):
    p = make_policy(tmp_path, "multicultural")
    before = p.read_bytes()
    d = PolicyEditDialog("multicultural", p)
    fill(d, wins_work_name="새합성근로", rate_urban="19,000", rate_rural="15000")
    d.save_button.click()
    assert d.result() == QDialog.DialogCode.Accepted and d.saved and d.backup_name == p.name + ".bak"
    pol = load_policy(p)
    assert pol.wins_work_name == "새합성근로" and pol.rates() == {"도시": 19000, "농어촌": 15000}
    assert (tmp_path / (p.name + ".bak")).read_bytes() == before
    assert not [x for x in tmp_path.iterdir() if x.suffix == ".tmp"]


def test_bad_values_show_a_message_without_the_values_and_change_nothing(qapp, tmp_path):
    p = make_policy(tmp_path, "multicultural")
    before = p.read_bytes()
    d = PolicyEditDialog("multicultural", p)
    fill(d, rate_urban="비싼값123", rate_rural="14000")
    d.save_button.click()
    assert not d.saved and d.result() != QDialog.DialogCode.Accepted and not d.error_label.isHidden()
    assert "비싼값123" not in texts(d) and "시급" in d.error_label.text()
    assert p.read_bytes() == before and [x.name for x in tmp_path.iterdir()] == [p.name]
    fill(d, rate_urban="0")
    d.save_button.click()
    assert p.read_bytes() == before
    fill(d, rate_urban="18000", wris_gub_a="  ")
    d.save_button.click()
    assert "필요한 항목" in d.error_label.text() and p.read_bytes() == before


def test_extra_rate_keys_block_editing_and_say_why(qapp, tmp_path):
    p = tmp_path / "p.json"
    assert policy_flow.create_policy(TEMPLATE, SYNTH_VALUES, p, "multicultural", rates_text="가상A=1000").ok
    before = p.read_bytes()
    d = PolicyEditDialog("multicultural", p)
    assert not d.save_button.isEnabled() and not d.error_label.isHidden() and "도시" in d.error_label.text() and "농어촌" in d.error_label.text()
    assert not any(e.isEnabled() for e in d.inputs.values()) and "가상A" not in texts(d)
    d.save_button.click()
    assert p.read_bytes() == before and [x.name for x in tmp_path.iterdir()] == ["p.json"]


def test_unreadable_or_missing_file_is_reported_and_nothing_is_written(qapp, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{x", encoding="utf-8")
    d = PolicyEditDialog("daechung", bad)
    assert not d.save_button.isEnabled() and "읽을 수 없" in d.error_label.text() and bad.read_text(encoding="utf-8") == "{x"
    gone = PolicyEditDialog("daechung", tmp_path / "none.json")
    assert not gone.save_button.isEnabled() and "찾을 수 없" in gone.error_label.text() and [x.name for x in tmp_path.iterdir()] == ["bad.json"]


def test_external_change_after_opening_is_a_conflict_and_their_content_stays(qapp, tmp_path):
    p = make_policy(tmp_path)
    d = PolicyEditDialog("daechung", p)
    theirs = json.loads(p.read_text(encoding="utf-8"))
    theirs["wins_work_name"] = "다른사람이고침"
    p.write_text(json.dumps(theirs, ensure_ascii=False), encoding="utf-8")
    fill(d, wins_work_name="내가고침")
    d.save_button.click()
    assert not d.saved and "다른 곳에서 바뀌" in d.error_label.text() and "다른사람이고침" not in texts(d)
    assert json.loads(p.read_text(encoding="utf-8"))["wins_work_name"] == "다른사람이고침" and [x.name for x in tmp_path.iterdir()] == [p.name]


def test_save_failure_keeps_the_original_and_says_so(qapp, tmp_path, monkeypatch):
    p = make_policy(tmp_path)
    before = p.read_bytes()
    d = PolicyEditDialog("daechung", p)
    fill(d, wins_work_name="새")
    from scholarship_payment.config import policy_edit

    def boom(*a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(policy_edit.os, "replace", boom)
    d.save_button.click()
    assert not d.saved and "원본은 그대로" in d.error_label.text() and "denied" not in texts(d)
    assert p.read_bytes() == before and not [x for x in tmp_path.iterdir() if x.suffix == ".tmp"]


def test_cancel_and_enter_do_not_write(qapp, tmp_path):
    p = make_policy(tmp_path)
    before = p.read_bytes()
    d = PolicyEditDialog("daechung", p)
    fill(d, wins_work_name="새")
    d.show()
    QTest.keyClick(d.inputs["wins_work_name"], Qt.Key.Key_Return)
    assert not d.saved and p.read_bytes() == before
    d.cancel_button.click()
    assert d.result() == QDialog.DialogCode.Rejected and p.read_bytes() == before and [x.name for x in tmp_path.iterdir()] == [p.name]


def test_editing_is_refused_when_not_allowed_at_open_and_at_save(qapp, tmp_path):
    p = make_policy(tmp_path)
    before = p.read_bytes()
    d = PolicyEditDialog("daechung", p, allowed=lambda: False)
    assert not d.save_button.isEnabled() and "수정할 수 없" in texts(d)
    flag = {"ok": True}
    d2 = PolicyEditDialog("daechung", p, allowed=lambda: flag["ok"])
    fill(d2, wins_work_name="새")
    flag["ok"] = False                                                    # 대화상자를 연 뒤 생성이 시작된 경우
    d2.save_button.click()
    assert not d2.saved and "수정할 수 없" in d2.error_label.text() and p.read_bytes() == before


# ---------- 고급 설정 연동 ----------
def test_settings_dialog_offers_edit_only_when_a_policy_path_exists(app_win):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    assert d.edit_button.text() == "정책 파일 수정..." and d.edit_button.isEnabled()
    d.tabs.set_current("ai")
    d.tabs.changed.emit("ai")
    assert not d.edit_button.isEnabled()                                   # 정책 파일이 없는 사업


def test_edit_through_the_dialog_changes_the_file_not_the_chosen_path_and_cancel_keeps_it(app_win, policy_file):
    w, ctx = app_win
    before_settings, before_paths = ctx.store.settings, dict(w.step1.model.paths)
    d = w.step1.build_settings_dialog()
    ed = d.build_editor()
    fill(ed, wins_work_name="화면에서고침")
    ed.save_button.click()
    d.finish_edit(ed)
    assert load_policy(policy_file).wins_work_name == "화면에서고침"
    assert d.draft.value("daechung", "policy_path") == str(policy_file) and d.draft.changed() == []
    d.cancel_button.click()
    assert ctx.store.settings == before_settings and w.step1.model.paths["policy"] == before_paths["policy"]      # 설정 취소 → 기존 경로 유지
    assert us.load(ctx.store.path).settings == before_settings


def test_editor_cancel_inside_settings_changes_nothing(app_win, policy_file):
    w, ctx = app_win
    before = policy_file.read_bytes()
    d = w.step1.build_settings_dialog()
    ed = d.build_editor()
    fill(ed, wins_work_name="취소할값")
    ed.cancel_button.click()
    d.finish_edit(ed)
    assert policy_file.read_bytes() == before and [x.name for x in policy_file.parent.glob("*.bak*")] == []


def test_a_saved_edit_rechecks_the_policy_state_in_the_dialog_and_in_step1(app_win, policy_file):
    from scholarship_payment.ui import validators as v
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    assert d.draft.state("daechung", "policy_path").ok and w.model.state("policy").ok
    # 외부에서 값이 깨진 정책이 되도록 수정한 것처럼, 편집 저장 후 두 곳의 검사가 다시 실행되었는지를 토큰 증가로 확인한다.
    tok_draft = d.draft._checks._tokens[("daechung", "policy_path")]
    tok_model = w.model._checks._tokens["policy"]
    ed = d.build_editor()
    fill(ed, wins_work_name="재검사")
    ed.save_button.click()
    d.finish_edit(ed)
    assert d.draft._checks._tokens[("daechung", "policy_path")] > tok_draft and w.model._checks._tokens["policy"] > tok_model
    assert d.draft.state("daechung", "policy_path").ok and w.model.state("policy").ok


def test_editing_is_offered_on_step1_only_and_never_while_generating(app_win, make_input, monkeypatch):
    w, ctx = app_win
    assert w.step1.policy_edit_allowed() and w.step1.build_settings_dialog().edit_button.isEnabled()
    w.step1.model.set_source(make_input(n=3))
    assert w.next_button.isEnabled()
    w.next_button.click()
    assert w.navigator.current == Step.REVIEW
    d = w.step1.build_settings_dialog()                                    # Step 2/3 에서 열린 고급 설정에서는 수정 버튼이 막힌다
    assert not d.edit_button.isEnabled() and "첫 단계" in texts(d)
    w.navigator.back()
    assert w.navigator.current == Step.FILE and w.step1.build_settings_dialog().edit_button.isEnabled()
    monkeypatch.setattr(type(w.generation), "busy", property(lambda self: True))
    blocked = w.step1.build_settings_dialog()
    assert not blocked.edit_button.isEnabled() and "생성 중" in texts(blocked)
    assert blocked.build_editor() is None or not blocked.build_editor().save_button.isEnabled()


# ---------- 수정 후 미리보기 재사용 금지 ----------
def test_after_a_policy_edit_the_old_preview_is_not_reused(app_win, make_input, policy_file):
    w, ctx = app_win
    w.step1.model.set_source(make_input(n=3))
    w.next_button.click()
    old = w.step2.session.prepared
    assert w.step2.session.state == pv.READY and old is not None
    w.navigator.back()                                                     # 처음 단계로 돌아오면 확인 결과는 버려진다
    assert w.step2.session.prepared is None
    d = w.step1.build_settings_dialog()
    ed = d.build_editor()
    fill(ed, wins_work_name="미리보기무효")
    ed.save_button.click()
    d.finish_edit(ed)
    w.next_button.click()
    new = w.step2.session.prepared
    assert new is not None and new is not old and new.policy_fp.sha256 != old.policy_fp.sha256


def test_a_policy_edit_event_invalidates_a_ready_preview(app_win, make_input, policy_file):
    w, ctx = app_win
    w.step1.model.set_source(make_input(n=3))
    w.next_button.click()
    assert w.step2.session.state == pv.READY
    w.model.policy_edited(str(policy_file))                                # 같은 경로의 정책이 수정되었다는 알림
    s = w.step2.session
    assert s.state == pv.INVALIDATED and s.prepared is None and "policy" in s.changed_codes


def test_an_edit_of_another_file_does_not_touch_the_preview(app_win, make_input, tmp_path):
    w, ctx = app_win
    w.step1.model.set_source(make_input(n=3))
    w.next_button.click()
    w.model.policy_edited(str(tmp_path / "other.json"))
    assert w.step2.session.state == pv.READY


# ---------- 정책 만들기 화면의 시급 두 칸 ----------
def test_wizard_shows_two_rate_fields_for_multicultural_only(app_win):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    assert not any(k.startswith("rate") for k in d.build_wizard().inputs)
    d.tabs.set_current("multicultural")
    d.tabs.changed.emit("multicultural")
    ctx.chooser.answers["template"].append(str(TEMPLATE))
    d.template_button.click()
    wz = d.build_wizard()
    assert list(wz.inputs)[-2:] == ["rate_urban", "rate_rural"] and "rates" not in wz.inputs
    assert "시급(도시)" in texts(wz) and "시급(농어촌)" in texts(wz)
    for k, val in SYNTH_VALUES.items():
        wz.inputs[k].setText(val)
    wz.inputs["rate_urban"].setText("18000")
    wz.inputs["rate_rural"].setText("가격")
    wz.create_button.click()
    assert wz.created_path is None and not wz.error_label.isHidden() and "가격" not in texts(wz)
    wz.inputs["rate_rural"].setText("14000")
    wz.create_button.click()
    assert wz.created_path and load_policy(wz.created_path).rates() == {"도시": 18000, "농어촌": 14000}


# ================= 커밋 전 추가 검증: UX 안내 · 검증 상태 일관성 =================
def sha(p):
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def shared_settings(policy_file, out_dir):
    """같은 정책 JSON 경로를 두 사업(대청교·다문화)에 지정한 설정."""
    return (us.UserSettings(last_program="daechung")
            .with_paths("daechung", template_path=str(TEMPLATE), policy_path=str(policy_file), out_dir=str(out_dir))
            .with_paths("multicultural", template_path=str(TEMPLATE), policy_path=str(policy_file), out_dir=str(out_dir)))


def test_editor_says_that_saving_is_immediate_and_survives_cancelling_settings(qapp, tmp_path):
    d = PolicyEditDialog("daechung", make_policy(tmp_path))
    t = texts(d)
    assert "즉시 반영" in t and "되돌아가지 않습니다" in t and "취소해도" in t        # 저장하면 바로 파일에 반영되고, 이후 설정을 취소해도 되돌리지 않는다
    assert "이 창을 취소하면 파일은 바뀌지 않습니다" in t and "백업" in t


def test_settings_dialog_keeps_a_visible_note_about_immediate_saving(app_win):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    assert not d.edit_note.isHidden() and "즉시 반영" in d.edit_note.text() and "되돌아가지 않습니다" in d.edit_note.text()
    d.tabs.set_current("ai")
    d.tabs.changed.emit("ai")
    assert d.edit_note.isHidden()                                              # 정책 파일이 없는 사업에서는 숨긴다


def test_after_saving_the_dialog_reports_the_backup_and_that_cancelling_does_not_undo(app_win, policy_file):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    assert d.edit_result.isHidden()
    ed = d.build_editor()
    fill(ed, wins_work_name="저장한값")
    ed.save_button.click()
    d.finish_edit(ed)
    assert not d.edit_result.isHidden() and (policy_file.name + ".bak") in d.edit_result.text() and "되돌아가지 않습니다" in d.edit_result.text()
    d.cancel_button.click()                                                    # 이후 설정을 취소해도
    assert load_policy(policy_file).wins_work_name == "저장한값"               # 저장한 정책 JSON 은 되돌아가지 않는다


def test_cancelled_or_unchanged_edits_report_nothing_and_leave_the_file_byte_identical(app_win, policy_file):
    import os
    w, ctx = app_win
    before_sha, before_mtime = sha(policy_file), os.stat(policy_file).st_mtime_ns
    d = w.step1.build_settings_dialog()
    ed = d.build_editor()
    fill(ed, wins_work_name="바꿨다가취소")
    ed.cancel_button.click()
    d.finish_edit(ed)
    assert d.edit_result.isHidden()
    ed2 = d.build_editor()                                                     # 아무것도 바꾸지 않고 저장
    ed2.save_button.click()
    d.finish_edit(ed2)
    assert d.edit_result.isHidden() and not ed2.saved
    assert sha(policy_file) == before_sha and os.stat(policy_file).st_mtime_ns == before_mtime
    assert sorted(x.name for x in policy_file.parent.glob("*policy_daechung.json*")) == [policy_file.name]


def test_a_policy_path_shared_by_two_programs_is_rechecked_for_both_after_an_edit(qapp, make_context, policy_file, out_dir):
    """회귀: 한 탭에서 수정하면 같은 파일을 쓰는 다른 사업 탭의 검사 결과가 수정 전 상태로 남을 수 있었다."""
    ctx = make_context(settings=shared_settings(policy_file, out_dir))
    w = MainWindow(context=ctx)
    w.show()
    d = w.step1.build_settings_dialog()
    d.tabs.set_current("multicultural")
    d.tabs.changed.emit("multicultural")                                       # 다문화 탭도 한 번 확인되어 결과가 남는다
    d.tabs.set_current("daechung")
    d.tabs.changed.emit("daechung")
    mc_before = d.draft._checks._tokens[("multicultural", "policy_path")]
    dc_before = d.draft._checks._tokens[("daechung", "policy_path")]
    ed = d.build_editor()
    fill(ed, wins_work_name="공유정책수정")
    ed.save_button.click()
    d.finish_edit(ed)
    assert d.draft._checks._tokens[("daechung", "policy_path")] > dc_before
    assert d.draft._checks._tokens[("multicultural", "policy_path")] > mc_before        # 같은 파일을 쓰는 다른 사업도 다시 검사했다
    d.tabs.set_current("multicultural")
    d.tabs.changed.emit("multicultural")
    assert d.draft.state("multicultural", "policy_path").ok and d.draft.changed() == []
    w.close()


def test_a_program_that_does_not_use_the_edited_file_is_not_rechecked(qapp, make_context, policy_file, out_dir, tmp_path):
    other = tmp_path / "other_policy.json"
    other.write_bytes(policy_file.read_bytes())
    settings = (us.UserSettings(last_program="daechung")
                .with_paths("daechung", template_path=str(TEMPLATE), policy_path=str(policy_file), out_dir=str(out_dir))
                .with_paths("ai", template_path=str(TEMPLATE), policy_path=str(other), out_dir=str(out_dir)))
    w = MainWindow(context=make_context(settings=settings))
    d = w.step1.build_settings_dialog()
    d.tabs.set_current("ai")
    d.tabs.changed.emit("ai")
    d.tabs.set_current("daechung")
    d.tabs.changed.emit("daechung")
    ai_before = d.draft._checks._tokens[("ai", "policy_path")]
    ed = d.build_editor()
    fill(ed, wins_work_name="한쪽만수정")
    ed.save_button.click()
    d.finish_edit(ed)
    assert d.draft._checks._tokens[("ai", "policy_path")] == ai_before
    w.close()


def test_switching_to_a_program_that_shares_the_edited_file_revalidates_the_changed_file(qapp, make_context, policy_file, out_dir):
    ctx = make_context(settings=shared_settings(policy_file, out_dir))
    w = MainWindow(context=ctx)
    w.show()
    d = w.step1.build_settings_dialog()
    ed = d.build_editor()
    fill(ed, wins_work_name="전환전수정")
    ed.save_button.click()
    d.finish_edit(ed)
    d.cancel_button.click()
    tok = w.model._checks._tokens["policy"]
    policy_file.write_text("{깨진 JSON", encoding="utf-8")                      # 수정 뒤에 파일이 외부에서 다시 바뀌었다
    w.model.set_program("multicultural")                                       # 같은 파일을 쓰는 다른 사업으로 전환
    assert w.model._checks._tokens["policy"] > tok                             # 저장된 상태를 믿지 않고 파일을 다시 검사한다
    st = w.model.state("policy")
    assert not st.ok and st.code == "POLICY_UNREADABLE"
    w.close()
