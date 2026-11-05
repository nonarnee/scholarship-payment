"""고급 설정 대화상자(트랜잭션)와 정책 만들기 대화상자."""
import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QLabel  # noqa: E402

from scholarship_payment.config import user_settings as us  # noqa: E402
from scholarship_payment.ui.main_window import MainWindow  # noqa: E402
from scholarship_payment.ui.policy_wizard import PolicyWizardDialog  # noqa: E402

from ui_helpers import SYNTH_VALUES, TEMPLATE  # noqa: E402


@pytest.fixture
def app_win(qapp, make_context, ready_settings):
    ctx = make_context(settings=ready_settings)
    w = MainWindow(context=ctx)
    w.show()
    yield w, ctx
    w.close()


def disk(ctx):
    return us.load(ctx.store.path).settings


def all_text(w):
    return " ".join(x.text() for x in w.findChildren(QLabel))


# ---------- 열기 · 표시 ----------
def test_dialog_opens_on_current_program_and_shows_its_paths(app_win):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    assert d.tabs.current() == "daechung" and d.template_field.text() == str(TEMPLATE)
    assert d.template_badge.text() == "WRIS 머리글 확인됨" and d.policy_badge.text() == "정책 형식 확인됨"
    assert d.apply_button.text() == "설정 저장 및 적용" and d.cancel_button.text() == "취소" and d.reset_button.text() == "기본값으로 복원"
    for banned in ("CONFIG_ID", "쓰기 권한 승인됨", "개 열 매핑", "캐시", "차단됨"):
        assert banned not in all_text(d)


def test_tabs_show_independent_paths_per_program(app_win, tmp_path):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    d.tabs.set_current("ai")
    d.tabs.changed.emit("ai")
    assert d.template_field.text() == "" and d.policy_badge.text() == "설정 필요"
    ctx.chooser.answers["template"].append(str(TEMPLATE))
    d.template_button.click()
    d.tabs.set_current("daechung")
    d.tabs.changed.emit("daechung")
    assert d.template_field.text() == str(TEMPLATE) and d.draft.value("ai", "template_path") == str(TEMPLATE)
    assert d.draft.value("multicultural", "template_path") is None


# ---------- 취소 · 적용 ----------
def test_cancel_leaves_settings_model_and_disk_unchanged(app_win, tmp_path):
    w, ctx = app_win
    before_disk, before_paths = disk(ctx), dict(w.step1.model.paths)
    d = w.step1.build_settings_dialog()
    ctx.chooser.answers["folder"].append(str(tmp_path))
    d.out_dir_button.click()
    d.reset_button.click()
    assert d.draft.value("daechung", "out_dir") is None
    d.cancel_button.click()
    assert d.result() == QDialog.DialogCode.Rejected and d.outcome is None
    assert ctx.store.settings == before_disk and disk(ctx) == before_disk and w.step1.model.paths == before_paths


def test_closing_with_escape_or_close_is_a_cancel(app_win, tmp_path):
    w, ctx = app_win
    before = ctx.store.settings
    d = w.step1.build_settings_dialog()
    ctx.chooser.answers["folder"].append(str(tmp_path))
    d.out_dir_button.click()
    d.reject()
    assert ctx.store.settings == before and w.step1.model.paths["out_dir"] != str(tmp_path)


def test_apply_commits_validated_changes_to_model_and_disk(app_win, tmp_path):
    w, ctx = app_win
    new_out = tmp_path / "new_out"
    new_out.mkdir()
    d = w.step1.build_settings_dialog()
    ctx.chooser.answers["folder"].append(str(new_out))
    d.out_dir_button.click()
    assert d.apply_button.isEnabled()
    d.apply_button.click()
    assert d.outcome.applied and d.outcome.persisted
    assert disk(ctx).paths("daechung").out_dir == str(new_out) and w.step1.model.paths["out_dir"] == str(new_out)
    assert w.step1.notice.isHidden()


def test_apply_is_disabled_for_changed_invalid_paths_and_message_explains(app_win, tmp_path):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"zzz")
    ctx.chooser.answers["template"].append(str(bad))
    d.template_button.click()
    assert not d.apply_button.isEnabled() and d.template_badge.property("badge") == "error" and "열 수 없습니다" in d.template_message.text()
    d.reset_button.click()                                   # 되돌리면 다시 적용 가능
    assert d.apply_button.isEnabled()
    assert ctx.store.settings == disk(ctx)


def test_persist_failure_is_reported_separately_from_session_apply(app_win, tmp_path, monkeypatch):
    w, ctx = app_win
    new_out = tmp_path / "n"
    new_out.mkdir()
    d = w.step1.build_settings_dialog()
    ctx.chooser.answers["folder"].append(str(new_out))
    d.out_dir_button.click()
    monkeypatch.setattr(us.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))
    d.apply_button.click()
    assert d.outcome.applied and not d.outcome.persisted
    assert w.step1.model.paths["out_dir"] == str(new_out)                   # 이번 실행에는 적용됨
    msg = w.step1.notice_label.text()
    assert not w.step1.notice.isHidden() and "현재 실행에는 적용" in msg and "저장하지 못" in msg and str(tmp_path) not in msg
    assert disk(ctx).paths("daechung").out_dir != str(new_out)             # 파일에는 반영되지 않음


def test_restore_defaults_only_edits_the_draft_until_applied_and_keeps_files(app_win, policy_file):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    d.reset_button.click()
    assert d.template_field.text() == "" and ctx.store.settings.paths("daechung").policy_path == str(policy_file)
    assert policy_file.is_file() and TEMPLATE.is_file()
    d.apply_button.click()
    assert ctx.store.settings.paths("daechung") == us.ProgramPaths() and policy_file.is_file()
    assert not w.next_button.isEnabled() and w.step1.template_badge.text() == "설정 필요"


def test_dialog_background_checks_ignore_stale_results(qapp, make_context, ready_settings, tmp_path):
    from scholarship_payment.ui.runner import ManualRunner
    runner = ManualRunner()
    ctx = make_context(runner=runner, settings=ready_settings)
    w = MainWindow(context=ctx)
    runner.run_all()
    d = w.step1.build_settings_dialog()
    runner.run_all()
    bad, good = tmp_path / "bad.json", ctx.store.settings.paths("daechung").policy_path
    bad.write_text("{}", encoding="utf-8")
    ctx.chooser.answers["policy"] += [good, str(bad)]
    runner.pending.clear()
    d.policy_button.click()
    d.policy_button.click()
    assert not d.apply_button.isEnabled()
    runner.run(1)
    runner.run(0)
    assert d.policy_badge.property("badge") == "error" and not d.apply_button.isEnabled()
    d.cancel_button.click()
    w.close()


# ---------- 정책 만들기 ----------
def _wizard(w, ctx, d):
    return d.build_wizard()


def test_wizard_creates_new_policy_and_sets_it_in_draft_only(app_win, tmp_path):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    d.tabs.set_current("ai"); d.tabs.changed.emit("ai")
    ctx.chooser.answers["template"].append(str(TEMPLATE))
    d.template_button.click()
    wz = d.build_wizard()
    assert isinstance(wz, PolicyWizardDialog) and set(wz.inputs) == set(SYNTH_VALUES)
    for k, val in SYNTH_VALUES.items():
        wz.inputs[k].setText(val)
    wz.create_button.click()
    assert wz.created_path and wz.created_path.is_file() and wz.created_path.parent == ctx.store.path.parent
    assert d.draft.value("ai", "policy_path") == str(wz.created_path) and ctx.store.settings.paths("ai").policy_path is None
    assert d.policy_badge.text() == "정책 형식 확인됨"
    created = wz.created_path
    d.cancel_button.click()                                   # 취소해도 만든 파일은 지우지 않는다
    assert created.is_file() and ctx.store.settings.paths("ai").policy_path is None


def test_wizard_never_overwrites_an_existing_policy_file(app_win, tmp_path, chooser):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    wz = d.build_wizard()
    existing = tmp_path / "keep.json"
    existing.write_text("원래 내용", encoding="utf-8")
    chooser.answers["save"].append(str(existing))
    wz.change_path_button.click()
    for k, val in SYNTH_VALUES.items():
        wz.inputs[k].setText(val)
    wz.create_button.click()
    assert wz.created_path is None and existing.read_text(encoding="utf-8") == "원래 내용" and "이미 있는 파일" in wz.error_label.text()
    assert not wz.error_label.isHidden()


def test_wizard_requires_all_values_and_shows_codes_not_values(app_win):
    w, ctx = app_win
    wz = w.step1.build_settings_dialog().build_wizard()
    wz.inputs["list_title"].setText("합성 {year}")
    wz.create_button.click()
    assert wz.created_path is None and "필요한 항목" in wz.error_label.text() and "합성 {year}" not in wz.error_label.text()


def test_wizard_needs_a_valid_template_first(qapp, make_context):
    ctx = make_context()
    w = MainWindow(context=ctx)
    d = w.step1.build_settings_dialog()
    d.wizard_button.click()                                  # 템플릿이 없으면 열지 않고 안내
    assert "템플릿" in d.message.text() and not d.message.isHidden()
    w.close()


def test_multicultural_wizard_has_two_rate_fields(app_win):
    w, ctx = app_win
    d = w.step1.build_settings_dialog()
    d.tabs.set_current("multicultural"); d.tabs.changed.emit("multicultural")
    ctx.chooser.answers["template"].append(str(TEMPLATE))
    d.template_button.click()
    wz = d.build_wizard()
    assert "rate_urban" in wz.inputs and "rate_rural" in wz.inputs and "rates" not in wz.inputs
    for k, val in SYNTH_VALUES.items():
        wz.inputs[k].setText(val)
    wz.inputs["rate_urban"].setText("1000")
    wz.inputs["rate_rural"].setText("2000")
    wz.create_button.click()
    assert wz.created_path and wz.created_path.is_file()


def test_late_check_results_after_cancel_do_not_touch_the_closed_dialog(qapp, make_context, ready_settings, tmp_path):
    from scholarship_payment.ui import validators as v
    from scholarship_payment.ui.runner import ManualRunner
    runner = ManualRunner()
    ctx = make_context(runner=runner, settings=ready_settings)
    w = MainWindow(context=ctx)
    runner.run_all()
    d = w.step1.build_settings_dialog()
    runner.run_all()
    f = tmp_path / "later.json"
    f.write_text("{}", encoding="utf-8")
    ctx.chooser.answers["policy"].append(str(f))
    d.policy_button.click()
    calls = []
    d.draft.on_change(lambda: calls.append(1))
    d.cancel_button.click()
    runner.pending[-1][1](v.OK_STATE)                         # 닫힌 뒤 늦게 도착한 검사 결과
    assert calls == [] and d.draft.state("daechung", "policy_path").level == v.UNSET
    w.close()


# ---------- 추가 회귀: 저장 상태와 세션 상태의 일관성 ----------
def test_wizard_created_file_survives_dialog_cancel_but_no_setting_changes_anywhere(app_win):
    w, ctx = app_win
    before_settings, before_disk, before_paths = ctx.store.settings, disk(ctx), dict(w.step1.model.paths)
    d = w.step1.build_settings_dialog()
    d.tabs.set_current("ai"); d.tabs.changed.emit("ai")
    ctx.chooser.answers["template"].append(str(TEMPLATE))
    d.template_button.click()
    wz = d.build_wizard()
    for k, val in SYNTH_VALUES.items():
        wz.inputs[k].setText(val)
    wz.create_button.click()
    created = wz.created_path
    d.cancel_button.click()
    assert created.is_file()                                               # 만든 파일은 유지
    assert ctx.store.settings == before_settings and disk(ctx) == before_disk and w.step1.model.paths == before_paths


def test_reopened_dialog_and_program_switch_show_session_values_after_failed_save(app_win, tmp_path, monkeypatch):
    w, ctx = app_win
    new_out = tmp_path / "session_only"
    new_out.mkdir()
    d = w.step1.build_settings_dialog()
    ctx.chooser.answers["folder"].append(str(new_out))
    d.out_dir_button.click()
    monkeypatch.setattr(us.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("denied")))
    d.apply_button.click()
    assert d.outcome.applied and not d.outcome.persisted
    w.step1.program_combo.setCurrentIndex(1)                               # 사업 전환 후 되돌아와도
    w.step1.program_combo.setCurrentIndex(0)
    assert w.step1.out_dir_field.text() == str(new_out)
    d2 = w.step1.build_settings_dialog()                                    # 다시 열어도 세션 값이 보인다
    assert d2.out_dir_field.text() == str(new_out) and d2.tabs.current() == "daechung"
    assert d2.draft.value("daechung", "out_dir") == str(new_out)
    d2.cancel_button.click()
    assert w.step1.model.paths["out_dir"] == str(new_out) and ctx.store.settings.paths("daechung").out_dir == str(new_out)


def test_dialog_changes_for_another_program_do_not_disturb_current_session_paths(app_win, tmp_path):
    w, ctx = app_win
    before = dict(w.step1.model.paths)
    d = w.step1.build_settings_dialog()
    d.tabs.set_current("ai"); d.tabs.changed.emit("ai")
    ctx.chooser.answers["template"].append(str(TEMPLATE))
    d.template_button.click()
    d.apply_button.click()
    assert {k: w.step1.model.paths[k] for k in ("template", "policy", "out_dir")} == {k: before[k] for k in ("template", "policy", "out_dir")}
    assert ctx.store.settings.paths("ai").template_path == str(TEMPLATE) and disk(ctx).paths("ai").template_path == str(TEMPLATE)
